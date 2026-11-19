"""Manual engagement: a reaction or a comment on one post, made by hand, done by the worker on the mock site within the sender's limits, with a history."""
import unittest
from unittest.mock import patch

from test_outreach import MOCK, OutreachCase, SessionLocal  # noqa: E402  (sets the isolated environment)
from app import models
from app.config import DAILY_TYPE_CEILINGS
from app.linkedin_session import actions
from app.routers import engagement


class EngagementCase(OutreachCase):
    def setUp(self):
        super().setUp()
        hosts = patch.object(engagement, "HOSTS", engagement.HOSTS | {"127.0.0.1"})  # the mock site stands in for linkedin.com
        hosts.start()
        self.addCleanup(hosts.stop)

    def engage(self, account_id, post="7", **body):
        return self.client.post("/engagement", json={"accountId": account_id, "postUrl": MOCK.post_url(post), **body})

    def run_worker(self, rounds=3):
        for _ in range(rounds):
            self.worker.run_once(wait=True)


class ActionTest(EngagementCase):
    def test_a_reaction_and_a_comment_land_on_the_post_and_a_second_reaction_does_nothing(self):
        url = MOCK.post_url("7")
        self.assertEqual(self.open_session(lambda s: actions.engage_post(s, url, "Celebrate", "Congratulations!")), actions.EngageResult.DONE)
        self.assertEqual((MOCK.post("7")["reaction"], MOCK.post("7")["comments"]), ("Celebrate", ["Congratulations!"]))
        self.assertEqual(self.open_session(lambda s: actions.engage_post(s, url, "Like", None)), actions.EngageResult.ALREADY_REACTED)
        self.assertEqual(MOCK.post("7")["reaction"], "Celebrate")  # not changed
        self.assertEqual(self.open_session(lambda s: actions.engage_post(s, url, "Like", None)), actions.EngageResult.ALREADY_REACTED)
        self.assertEqual(self.open_session(lambda s: actions.engage_post(s, MOCK.post_url("8"), "Like", None)), actions.EngageResult.DONE)
        self.assertEqual(MOCK.post("8")["reaction"], "Like")
        self.assertEqual(self.open_session(lambda s: actions.engage_post(s, MOCK.post_url("0"), "Like", None)), actions.EngageResult.POST_UNAVAILABLE)


class ApiTest(EngagementCase):
    def test_queued_then_done_by_the_worker_and_listed_in_the_history(self):
        account_id = self.make_account("Ada")
        r = self.engage(account_id, reaction="insightful", comment="Useful, thank you")
        self.assertEqual(r.status_code, 201, r.text)
        self.assertEqual(r.json()["status"], "queued")
        self.run_worker()
        self.assertEqual((MOCK.post("7")["reaction"], MOCK.post("7")["comments"]), ("Insightful", ["Useful, thank you"]))
        item = self.client.get("/engagement").json()["items"][0]
        self.assertEqual((item["status"], item["account"], item["reaction"], item["comment"]), ("done", "Ada", "insightful", "Useful, thank you"))
        self.assertEqual(self.client.get("/engagement").json()["reactions"], ["like", "celebrate", "support", "love", "insightful", "funny"])

    def test_an_unavailable_post_is_recorded_as_failed_with_the_reason(self):
        account_id = self.make_account()
        self.engage(account_id, post="0", reaction="like")
        self.run_worker()
        item = self.client.get("/engagement").json()["items"][0]
        self.assertEqual((item["status"], item["detail"]), ("failed", "The post could not be opened."))

    def test_what_is_refused_and_why(self):
        account_id = self.make_account()
        self.assertEqual(self.engage(account_id).status_code, 422)  # neither a reaction nor a comment
        self.assertEqual(self.engage(account_id, reaction="angry").status_code, 422)
        self.assertEqual(self.engage(account_id, comment="x" * 1251).status_code, 422)
        bad = self.client.post("/engagement", json={"accountId": account_id, "postUrl": "https://example.com/feed/update/urn:li:activity:1/", "reaction": "like"})
        self.assertEqual(bad.status_code, 422)
        self.assertIn("linkedin.com/feed/update/", bad.json()["detail"])
        self.assertEqual(self.client.post("/engagement", json={"accountId": account_id, "postUrl": "https://www.linkedin.com/in/someone/", "reaction": "like"}).status_code, 422)
        self.assertEqual(self.engage("not-mine", reaction="like").status_code, 404)
        stopped = self.make_account("Stopped", daily_limit=0)
        refused = self.engage(stopped, reaction="like")
        self.assertEqual(refused.status_code, 409)
        self.assertIn("daily limit is 0", refused.json()["detail"])

    def test_the_hard_ceiling_holds(self):
        account_id = self.make_account(daily_limit=200)
        with SessionLocal() as db:
            for i in range(DAILY_TYPE_CEILINGS["engage_post"]):
                db.add(models.AgentTask(account_id=account_id, type="engage_post", status="done", idempotency_key=f"used{i}", payload={}))
            db.commit()
        r = self.engage(account_id, reaction="like")
        self.assertEqual(r.status_code, 409)
        self.assertEqual(self.client.get("/engagement").json()["items"], [])  # nothing half-saved

    def test_a_queued_one_can_be_cancelled_and_a_done_one_cannot(self):
        account_id = self.make_account()
        queued = self.engage(account_id, reaction="like").json()
        self.assertEqual(self.client.delete(f"/engagement/{queued['id']}").status_code, 204)
        self.run_worker()
        self.assertIsNone(MOCK.post("7")["reaction"])  # cancelled before it ran
        done = self.engage(account_id, post="9", reaction="love").json()
        self.run_worker()
        self.assertEqual(self.client.delete(f"/engagement/{done['id']}").status_code, 409)
        statuses = {i["id"]: i["status"] for i in self.client.get("/engagement").json()["items"]}
        self.assertEqual(statuses, {queued["id"]: "cancelled", done["id"]: "done"})


if __name__ == "__main__":
    unittest.main()
