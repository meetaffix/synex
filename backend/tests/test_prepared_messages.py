"""No AI calls while sending. AI drafts are prepared before launch (cost shown first, review, approval); the engine, the
worker and the dry run use finished text only. No external call is made while a database transaction is open."""
import inspect
import json
import threading
import time
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from sqlalchemy import event

from test_outreach import INVITE_ONLY, MOCK, OutreachCase, SessionLocal  # noqa: E402  (sets the isolated environment)
from app import database, drafts, engine, models, planner, providers  # noqa: E402
from app.config import DEEPGRAM_USD_PER_MINUTE, DRAFT_SECONDS_ESTIMATE  # noqa: E402

AI_CALLED = "an AI service was called"


class HeldConnections:
    """How many database connections each thread has checked out right now.

    `database.engine.pool.checkedout()` counts every thread in the process. CI runs all the tests in ONE process (`python -m unittest discover`), where a
    daemon thread left by an earlier test (a webhook delivery, a draft job, a worker) can hold a connection at the moment this test samples the pool, so the
    old assertion failed now and then for a reason that has nothing to do with the code under test. The property to prove is that the thread making the
    external call holds no connection, so that is what is counted."""

    def __init__(self, engine):
        self._lock = threading.Lock()
        self._owner: dict[int, int] = {}
        event.listen(engine, "checkout", self._out)
        event.listen(engine, "checkin", self._in)

    def _out(self, dbapi_connection, record, proxy):
        with self._lock:
            self._owner[id(record)] = threading.get_ident()

    def _in(self, dbapi_connection, record):
        with self._lock:
            self._owner.pop(id(record), None)

    def here(self) -> int:
        me = threading.get_ident()
        with self._lock:
            return sum(1 for owner in self._owner.values() if owner == me)


HELD = HeldConnections(database.engine)


def forbid_ai():
    """Patch every way a campaign could reach Deepgram so that any call fails loudly. Returns the patchers' mocks."""
    return [
        patch("app.deepgram_text.complete", side_effect=AssertionError(AI_CALLED)),
        patch.object(providers.DeepgramAIProvider, "generate_message", side_effect=AssertionError(AI_CALLED)),
        patch("app.providers.get_ai_provider", side_effect=AssertionError(AI_CALLED)),
    ]


class PreparedCase(OutreachCase):
    def campaign_ids(self, campaign_id):
        with SessionLocal() as db:
            campaign = db.get(models.Campaign, campaign_id)
            return {"step": campaign.steps[0].id, "leads": {l.first_name.lower(): l.id for l in campaign.lead_list.leads}}

    def add_draft(self, campaign_id, user, body, status="approved"):
        ids = self.campaign_ids(campaign_id)
        with SessionLocal() as db:
            db.add(models.LeadDraft(user_id=self.user_id, campaign_id=campaign_id, step_id=ids["step"], lead_id=ids["leads"][user],
                                    body=body, status=status, source="ai"))
            db.commit()

    def sent(self):
        return {user: text for user, text in MOCK.invites}


class NoAiWhileSendingTest(PreparedCase):
    def test_the_engine_has_no_way_to_reach_an_ai_provider(self):
        source = inspect.getsource(engine)
        self.assertNotIn("get_ai_provider", source)
        self.assertNotIn("generate_message", source)
        self.assertFalse(hasattr(engine, "render_message"))
        self.assertFalse(hasattr(engine, "get_ai_provider"))

    def test_the_worker_sends_the_template_with_deepgram_unreachable_even_when_ai_personalization_is_on(self):
        mocks = [p.start() for p in forbid_ai()]
        self.addCleanup(patch.stopall)
        steps = [{"type": "connection_request", "message": "{Hi|Hello} {{first_name}}, from {{company}}"}, {"type": "end"}]
        self.make_campaign([{"user": "ann"}, {"user": "bob"}], steps, ai_personalization=True)
        for _ in range(3):
            self.worker.run_once(wait=True)
        self.assertEqual(sorted(self.sent()), ["ann", "bob"])
        for user, text in self.sent().items():
            self.assertRegex(text, rf"^(Hi|Hello) {user.title()}, from ")
        self.assertEqual([m.call_count for m in mocks], [0, 0, 0], "Deepgram was reached while sending")

    def test_an_approved_draft_is_sent_and_a_proposed_one_is_not(self):
        mocks = [p.start() for p in forbid_ai()]
        self.addCleanup(patch.stopall)
        campaign_id = self.make_campaign([{"user": "ann"}, {"user": "bob"}, {"user": "cy"}], [{"type": "connection_request", "message": "Template for {{first_name}}"}, {"type": "end"}],
                                         launch=False, ai_personalization=True)
        self.add_draft(campaign_id, "ann", "Approved text for Ann", "approved")
        self.add_draft(campaign_id, "bob", "Proposed text for Bob", "proposed")
        with SessionLocal() as db:
            engine.launch_campaign(db, db.get(models.Campaign, campaign_id))
            db.commit()
        for _ in range(4):
            self.worker.run_once(wait=True)
        self.assertEqual(self.sent(), {"ann": "Approved text for Ann", "bob": "Template for Bob", "cy": "Template for Cy"})
        self.assertEqual([m.call_count for m in mocks], [0, 0, 0])

    def test_the_dry_run_shows_exactly_what_the_worker_sends(self):
        campaign_id = self.make_campaign([{"user": "ann"}, {"user": "bob"}], [{"type": "connection_request", "message": "{Hi|Hello|Hey} {{first_name}}"}, {"type": "end"}],
                                         launch=False, ai_personalization=True)
        self.add_draft(campaign_id, "ann", "Prepared for Ann")
        with SessionLocal() as db:
            plan = planner.plan_campaign(db, db.get(models.Campaign, campaign_id), datetime.now(timezone.utc))
        planned = {a.lead_name.split()[0].lower(): (a.message, a.ai_personalized) for a in plan if a.skip_reason is None}
        self.assertEqual(planned["ann"], ("Prepared for Ann", True))
        self.assertFalse(planned["bob"][1])
        with SessionLocal() as db:
            engine.launch_campaign(db, db.get(models.Campaign, campaign_id))
            db.commit()
        for _ in range(3):
            self.worker.run_once(wait=True)
        self.assertEqual(self.sent(), {user: text for user, (text, _) in planned.items()})

    def test_message_for_is_the_one_place_the_text_is_chosen(self):
        campaign_id = self.make_campaign([{"user": "ann"}], [{"type": "connection_request", "message": "T {{first_name}}"}, {"type": "end"}], launch=False)
        with SessionLocal() as db:
            campaign = db.get(models.Campaign, campaign_id)
            step, lead = campaign.steps[0], campaign.lead_list.leads[0]
            self.assertEqual(engine.message_for(db, campaign, step, lead), ("T Ann", False))
            db.add(models.LeadDraft(user_id=self.user_id, campaign_id=campaign_id, step_id=step.id, lead_id=lead.id, body="Draft", status="approved"))
            db.commit()
            self.assertEqual(engine.message_for(db, campaign, step, lead), ("Draft", True))


class DraftPreparationTest(PreparedCase):
    LEADS = [{"user": name} for name in ("ann", "bob", "cy", "dee", "eli")]

    def setUp(self):
        super().setUp()
        self.calls: list[tuple[str, int]] = []

        def fake(provider_self, step_type, tone, ctx):
            self.calls.append((ctx["first_name"], HELD.here()))  # connections open at the moment of the call
            return f"Hi {ctx['first_name']}, a prepared note."
        self.fake = patch.object(providers.DeepgramAIProvider, "generate_message", fake)
        self.fake.start()
        self.addCleanup(self.fake.stop)
        self.campaign_id = self.make_campaign(self.LEADS, INVITE_ONLY, launch=False, ai_personalization=True)
        self.url = f"/campaigns/{self.campaign_id}/drafts"

    def generate(self, count=None):
        count = self.client.post(f"{self.url}/estimate").json()["count"] if count is None else count
        r = self.client.post(f"{self.url}/generate", json={"confirmedCount": count})
        drafts.wait_for_job(self.campaign_id)
        return r

    def test_the_cost_estimate_is_shown_before_anything_is_generated(self):
        r = self.client.post(f"{self.url}/estimate")
        self.assertEqual(r.status_code, 200, r.text)
        e = r.json()
        self.assertEqual((e["count"], e["provider"], e["secondsPerDraft"]), (5, "deepgram", DRAFT_SECONDS_ESTIMATE))
        self.assertEqual(e["estimatedUsd"], round(5 * DRAFT_SECONDS_ESTIMATE / 60 * DEEPGRAM_USD_PER_MINUTE, 4))
        self.assertGreater(e["estimatedUsd"], 0)
        self.assertEqual(self.calls, [])  # estimating called nothing
        self.assertEqual(self.client.get(self.url).json()["counts"], {"proposed": 0, "approved": 0})

    def test_generation_needs_the_count_the_user_saw(self):
        r = self.client.post(f"{self.url}/generate", json={"confirmedCount": 3})
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.json()["detail"]["estimate"]["count"], 5)  # the new estimate comes back
        self.assertEqual(self.calls, [])
        self.assertEqual(self.client.post(f"{self.url}/generate", json={"confirmedCount": 0}).status_code, 409)

    def test_drafts_are_generated_as_proposed_with_no_transaction_open_during_the_ai_call(self):
        r = self.generate()
        self.assertEqual(r.status_code, 202, r.text)
        listing = self.client.get(self.url).json()
        self.assertEqual(listing["counts"], {"proposed": 5, "approved": 0})
        self.assertEqual(sorted(d["leadName"].split()[0] for d in listing["drafts"]), ["Ann", "Bob", "Cy", "Dee", "Eli"])
        self.assertEqual({d["source"] for d in listing["drafts"]}, {"ai"})
        self.assertEqual(len(self.calls), 5)
        self.assertEqual({open_connections for _, open_connections in self.calls}, {0}, "a database connection was open while Deepgram was called")
        self.assertEqual(listing["job"]["state"], "done")
        self.assertEqual(self.client.post(f"{self.url}/estimate").json()["count"], 0)  # nothing left to draft

    def test_a_proposed_draft_is_not_sent_until_it_is_approved(self):
        self.generate()
        with SessionLocal() as db:
            engine.launch_campaign(db, db.get(models.Campaign, self.campaign_id))
            db.commit()
        for _ in range(3):
            self.worker.run_once(wait=True)
        self.assertEqual(set(self.sent().values()), {"Hi"})  # the template (INVITE_ONLY), not the proposed drafts

    def test_approved_drafts_are_what_the_worker_sends(self):
        self.generate()
        self.assertEqual(self.client.post(f"{self.url}/approve", json={"all": True}).json(), {"approved": 5})
        with SessionLocal() as db:
            engine.launch_campaign(db, db.get(models.Campaign, self.campaign_id))
            db.commit()
        for _ in range(6):
            self.worker.run_once(wait=True)
        self.assertEqual(self.sent(), {name: f"Hi {name.title()}, a prepared note." for name in ("ann", "bob", "cy", "dee", "eli")})
        self.assertEqual(len(self.calls), 5)  # sending added no AI call

    def test_review_edit_approve_and_discard(self):
        self.generate()
        listing = self.client.get(self.url).json()["drafts"]
        first, second = listing[0]["id"], listing[1]["id"]
        edited = self.client.patch(f"{self.url}/{first}", json={"body": "My own words for them"}).json()
        self.assertEqual((edited["body"], edited["source"], edited["status"]), ("My own words for them", "edited", "proposed"))
        self.assertEqual(self.client.post(f"{self.url}/approve", json={"draftIds": [first]}).json(), {"approved": 1})
        again = self.client.patch(f"{self.url}/{first}", json={"body": "Changed after approval"}).json()
        self.assertEqual(again["status"], "proposed")  # an edit needs a fresh approval
        self.assertEqual(self.client.patch(f"{self.url}/{first}", json={"body": "x" * 301}).status_code, 422)  # connection note limit
        self.assertEqual(self.client.delete(f"{self.url}/{second}").json(), {"ok": True})
        self.assertEqual(len(self.client.get(self.url).json()["drafts"]), 4)
        self.assertEqual(self.client.post(f"{self.url}/estimate").json()["count"], 1)  # the discarded one can be drafted again
        self.assertEqual(self.client.post(f"{self.url}/approve", json={}).status_code, 422)

    def test_the_per_campaign_cap_limits_the_estimate_and_the_generation(self):
        with patch.object(drafts, "DRAFT_CAP_PER_CAMPAIGN", 3):
            e = self.client.post(f"{self.url}/estimate").json()
            self.assertEqual((e["count"], e["available"], e["capped"], e["cap"]), (3, 5, True, 3))
            self.generate()
            self.assertEqual(self.client.get(self.url).json()["counts"]["proposed"], 3)
            self.assertEqual(self.client.post(f"{self.url}/estimate").json()["count"], 0)

    def test_drafts_are_made_in_batches_each_in_its_own_transaction(self):
        reports = []
        with patch.object(drafts, "DRAFT_BATCH_SIZE", 2):
            done = drafts.generate_drafts(self.campaign_id, 5, progress=reports.append)
        self.assertEqual([r["created"] for r in reports], [2, 4, 5])
        self.assertEqual(done["created"], 5)

    def test_when_deepgram_fails_the_drafts_fall_back_to_the_template(self):
        self.fake.stop()
        with patch.object(providers.DeepgramAIProvider, "generate_message", side_effect=RuntimeError("down")):
            self.generate()
        listing = self.client.get(self.url).json()["drafts"]
        self.assertEqual({d["source"] for d in listing}, {"template"})
        self.assertTrue(all("Ann" in d["body"] or "Bob" in d["body"] or d["leadName"].split()[0] in d["body"] for d in listing))
        self.fake.start()

    def test_without_a_deepgram_key_the_estimate_is_free_and_says_so(self):
        from app.assistant.config import assistant_config
        with patch.object(assistant_config, "deepgram_api_key", ""):
            e = self.client.post(f"{self.url}/estimate").json()
        self.assertEqual((e["provider"], e["estimatedUsd"]), ("template", 0.0))

    def test_only_the_owners_workspace_and_signed_in_users_reach_the_drafts(self):
        from fastapi.testclient import TestClient
        from app.main import app
        anonymous = TestClient(app, headers={"Origin": "http://localhost:5173"})
        self.addCleanup(anonymous.close)
        for method, path in (("get", ""), ("post", "/estimate"), ("post", "/generate"), ("post", "/approve")):
            self.assertEqual(getattr(anonymous, method)(self.url + path).status_code, 401, path)
        self.assertEqual(self.client.get("/campaigns/not-a-campaign/drafts").status_code, 404)


class ConnectionCountingTest(PreparedCase):
    def test_a_connection_held_by_another_thread_is_not_counted_against_this_one(self):
        """The cause of the occasional CI failure: the old process-wide count saw 1 here, this thread's own count sees 0."""
        taken, release = threading.Event(), threading.Event()

        def other_thread():
            with database.engine.connect():
                taken.set()
                release.wait(10)
        thread = threading.Thread(target=other_thread, daemon=True)
        thread.start()
        self.assertTrue(taken.wait(5))
        try:
            self.assertEqual(database.engine.pool.checkedout(), 1)  # what the old assertion measured
            self.assertEqual(HELD.here(), 0)
            with database.engine.connect():
                self.assertEqual(HELD.here(), 1)  # a connection held by THIS thread is still caught
            self.assertEqual(HELD.here(), 0)
        finally:
            release.set()
            thread.join(5)


class NoTransactionDuringExternalCallsTest(PreparedCase):
    """Every other route that reaches Deepgram releases its database connection first."""

    def setUp(self):
        super().setUp()
        self.open_during_call: list[int] = []

        def fake_complete(system, text, timeout=25.0):
            self.open_during_call.append(HELD.here())
            return "A drafted line."
        patcher = patch("app.deepgram_text.complete", fake_complete)
        patcher.start()
        self.addCleanup(patcher.stop)
        publishing_patch = patch("app.publishing.complete", fake_complete)
        publishing_patch.start()
        self.addCleanup(publishing_patch.stop)

    def test_the_generate_message_route(self):
        r = self.client.post("/ai/generate-message", json={"stepType": "message", "firstName": "Ada"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(self.open_during_call, [0])

    def test_the_publishing_assist_route(self):
        r = self.client.post("/publishing/assist", json={"body": "a post", "instruction": "Make concise"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(self.open_during_call, [0])

    def test_the_assistant_draft_tool(self):
        from app.assistant import tools
        from app.assistant.registry import ToolContext
        with SessionLocal() as db:
            owner = db.get(models.User, self.user_id)
            ctx = ToolContext(db=db, actor=owner, workspace=owner, role="admin", page={})
            result = tools._draft(ctx, tools.DraftMessage(step_type="message"))
        self.assertIn("draft", result)
        self.assertEqual(self.open_during_call, [0])


if __name__ == "__main__":
    unittest.main()
