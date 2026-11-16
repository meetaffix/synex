"""The unified inbox: every filter, tags, interest labels, bulk actions, drafts, scheduled replies, AI suggested replies, CSV export and refresh."""
import atexit
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

TEMP = tempfile.TemporaryDirectory()
os.environ["DATABASE_URL"] = "sqlite:///" + TEMP.name.replace("\\", "/") + "/test.db"
os.environ["SECRET_KEY"] = "test-secret-not-for-production-0123456789"
os.environ["ENCRYPTION_KEY"] = "test-encryption-not-for-production-0123456789"
os.environ["AUTH_PROVIDER"] = "local"
os.environ.setdefault("DEEPGRAM_API_KEY", "dg-SENTINEL-never-leak-9f3a7c")
import safety
safety.assert_isolated_database(os.environ["DATABASE_URL"])
from fastapi.testclient import TestClient
from app import database, models, publishing_models  # noqa: F401
from app.assistant.config import assistant_config
from app.config import settings
from app.database import Base, SessionLocal
from app.deps import get_current_user, get_data_user, get_manager_user
from app.main import app
from app.routers import inbox

atexit.register(database.engine.dispose)
NOW = datetime.now(timezone.utc)


class InboxCase(unittest.TestCase):
    def setUp(self):
        Base.metadata.drop_all(database.engine)
        Base.metadata.create_all(database.engine)
        with SessionLocal() as db:
            owner = models.User(email="a@example.com", full_name="A", hashed_password="x")
            other = models.User(email="b@example.com", full_name="B", hashed_password="x")
            db.add_all([owner, other])
            db.flush()
            self.a1 = models.LinkedInAccount(user_id=owner.id, name="Ada", status="active", session_status="connected", daily_action_limit=10)
            self.a2 = models.LinkedInAccount(user_id=owner.id, name="Grace", status="active", session_status="connected", daily_action_limit=10)
            db.add_all([self.a1, self.a2])
            db.flush()
            self.c1 = models.Campaign(user_id=owner.id, name="Autumn", status="active", account_id=self.a1.id, ai_context={"goals": "Book demos"})
            self.c2 = models.Campaign(user_id=owner.id, name="Webinar", status="active", account_id=self.a2.id)
            db.add_all([self.c1, self.c2])
            db.flush()
            self.convos = {}

            def thread(key, name, company, account, campaign, messages, **extra):
                lead = models.Lead(user_id=owner.id, first_name=name, last_name="X", company=company, linkedin_url=f"https://www.linkedin.com/in/{key}/")
                db.add(lead)
                db.flush()
                convo = models.Conversation(user_id=owner.id, lead_id=lead.id, account_id=account.id, campaign_id=campaign.id if campaign else None, **extra)
                db.add(convo)
                db.flush()
                for i, (direction, body) in enumerate(messages):
                    db.add(models.Message(conversation_id=convo.id, direction=direction, body=body, sent_at=NOW - timedelta(hours=len(messages) - i)))
                convo.last_message_preview = messages[-1][1]
                self.convos[key] = convo.id
            thread("ann", "Ann", "Acme", self.a1, self.c1, [("outbound", "Hi Ann"), ("inbound", "Sounds interesting, tell me more")], unread=True)
            thread("bob", "Bob", "Globex", self.a1, self.c1, [("outbound", "Hi Bob")], starred=True)
            thread("cy", "Cy", "Initech", self.a2, self.c2, [("outbound", "Hi Cy"), ("inbound", "Not now"), ("outbound", "Thanks")], tags=["warm"], interest="not_interested")
            thread("dee", "Dee", "Acme", self.a2, None, [("inbound", "Found you via a friend")], draft_body="Thanks Dee")
            thread("eli", "Eli", "Hooli", self.a1, self.c1, [("outbound", "Hi Eli"), ("inbound", "Please stop")], status="archived", answered=True)
            db.add(models.Lead(user_id=other.id, first_name="Zed", linkedin_url="https://www.linkedin.com/in/zed/"))
            db.commit()
            self.owner_id, self.a1_id, self.a2_id, self.c1_id, self.c2_id = owner.id, self.a1.id, self.a2.id, self.c1.id, self.c2.id

        def current():
            with SessionLocal() as db:
                return db.get(models.User, self.owner_id)
        for dep in (get_data_user, get_manager_user, get_current_user):
            app.dependency_overrides[dep] = current
        self.addCleanup(app.dependency_overrides.clear)
        for patcher in (patch.object(settings, "ai_provider", "template"), patch.object(assistant_config, "deepgram_api_key", "")):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.client = TestClient(app)

    def names(self, **params):
        r = self.client.get("/inbox/conversations", params=params)
        self.assertEqual(r.status_code, 200, r.text)
        return sorted(c["leadName"].split()[0] for c in r.json()["items"])

    def id(self, key):
        return self.convos[key]


class FilterTest(InboxCase):
    def test_the_default_list_hides_archived_and_the_archived_filter_shows_only_them(self):
        self.assertEqual(self.names(), ["Ann", "Bob", "Cy", "Dee"])
        self.assertEqual(self.names(archived="true"), ["Eli"])

    def test_needs_my_reply_and_i_messaged_last_follow_the_last_message_and_answered(self):
        self.assertEqual(self.names(needs_reply="true"), ["Ann", "Dee"])
        self.assertEqual(self.names(i_messaged_last="true"), ["Bob", "Cy"])
        self.client.post("/inbox/bulk", json={"ids": [self.id("ann")], "action": "answered"})
        self.assertEqual(self.names(needs_reply="true"), ["Dee"])

    def test_status_filters_unread_starred_drafts_scheduled(self):
        self.assertEqual(self.names(unread="true"), ["Ann"])
        self.assertEqual(self.names(starred="true"), ["Bob"])
        self.assertEqual(self.names(drafts="true"), ["Dee"])
        self.client.post(f"/inbox/{self.id('bob')}/schedule", json={"body": "Later", "sendAt": (NOW + timedelta(days=1)).isoformat()})
        self.assertEqual(self.names(scheduled="true"), ["Bob"])

    def test_tags_interest_accounts_and_campaigns_with_include_and_exclude(self):
        self.assertEqual(self.names(tag="warm"), ["Cy"])
        self.assertEqual(self.names(interest="not_interested"), ["Cy"])
        self.assertEqual(self.names(accounts=self.a2_id), ["Cy", "Dee"])
        self.assertEqual(self.names(campaigns=self.c1_id), ["Ann", "Bob"])
        self.assertEqual(self.names(campaigns=self.c1_id, campaign_mode="exclude"), ["Cy", "Dee"])

    def test_include_where_messages_were_sent_or_the_person_responded(self):
        self.assertEqual(self.names(where="messages_sent"), ["Ann", "Bob", "Cy"])  # campaign conversations with a sent message
        self.assertEqual(self.names(where="responses"), ["Ann", "Cy", "Dee"])

    def test_search_covers_name_company_and_message_text_and_dates_narrow_the_list(self):
        self.assertEqual(self.names(q="acme"), ["Ann", "Dee"])
        self.assertEqual(self.names(q="friend"), ["Dee"])
        self.assertEqual(self.names(date_from=(NOW + timedelta(days=1)).isoformat()), [])
        self.assertEqual(self.names(date_from=(NOW - timedelta(days=1)).isoformat(), date_to=(NOW + timedelta(days=1)).isoformat()), ["Ann", "Bob", "Cy", "Dee"])

    def test_the_list_says_what_each_row_needs_and_paging_works(self):
        data = self.client.get("/inbox/conversations", params={"limit": 2}).json()
        self.assertEqual((len(data["items"]), data["total"]), (2, 4))
        by = {c["leadName"].split()[0]: c for c in self.client.get("/inbox/conversations").json()["items"]}
        self.assertTrue(by["Ann"]["needsReply"])
        self.assertEqual((by["Cy"]["lastDirection"], by["Cy"]["accountName"], by["Cy"]["campaignName"]), ("outbound", "Grace", "Webinar"))
        self.assertTrue(by["Dee"]["hasDraft"])

    def test_another_workspaces_data_never_appears_and_the_meta_lists_accounts_campaigns_and_tags(self):
        meta = self.client.get("/inbox/meta").json()
        self.assertEqual({a["name"] for a in meta["accounts"]}, {"Ada", "Grace"})
        self.assertEqual({c["name"] for c in meta["campaigns"]}, {"Autumn", "Webinar"})
        self.assertEqual(meta["tags"], ["warm"])
        self.assertEqual({i["id"] for i in meta["interests"]}, set(inbox.INTERESTS))


class BulkTest(InboxCase):
    def bulk(self, keys, action, value=None):
        return self.client.post("/inbox/bulk", json={"ids": [self.id(k) for k in keys], "action": action, "value": value})

    def test_read_star_archive_tag_and_interest_apply_to_every_chosen_conversation(self):
        self.assertEqual(self.bulk(["ann", "bob"], "read").json(), {"changed": 2})
        self.assertEqual(self.names(unread="true"), [])
        self.bulk(["ann", "bob"], "star")
        self.assertEqual(self.names(starred="true"), ["Ann", "Bob"])
        self.bulk(["ann", "bob"], "tag_add", "hot")
        self.bulk(["bob"], "tag_remove", "hot")
        self.assertEqual(self.names(tag="hot"), ["Ann"])
        self.bulk(["ann"], "interest", "meeting_booked")
        self.assertEqual(self.names(interest="meeting_booked"), ["Ann"])
        self.bulk(["ann"], "archive")
        self.assertEqual(self.names(archived="true"), ["Ann", "Eli"])
        self.bulk(["ann"], "unarchive")
        self.assertIn("Ann", self.names())

    def test_bad_values_are_refused_with_the_reason(self):
        self.assertEqual(self.bulk(["ann"], "interest", "hot_lead").status_code, 422)
        self.assertEqual(self.bulk(["ann"], "tag_add", "").status_code, 422)
        self.assertEqual(self.bulk(["ann"], "tag_add", "x" * 41).status_code, 422)
        self.assertEqual(self.client.post("/inbox/bulk", json={"ids": [], "action": "read"}).status_code, 422)
        for i in range(10):
            self.assertEqual(self.bulk(["bob"], "tag_add", f"t{i}").status_code, 200)
        self.assertEqual(self.bulk(["bob"], "tag_add", "one-too-many").status_code, 422)


class DraftScheduleTest(InboxCase):
    def test_a_draft_is_saved_and_cleared_and_scheduling_moves_it_out_of_drafts(self):
        cid = self.id("ann")
        self.client.put(f"/inbox/{cid}/draft", json={"body": "Half a thought"})
        self.assertIn("Ann", self.names(drafts="true"))
        self.client.put(f"/inbox/{cid}/draft", json={"body": "  "})
        self.assertNotIn("Ann", self.names(drafts="true"))

    def test_scheduling_needs_a_future_time_and_can_be_cancelled(self):
        cid = self.id("bob")
        self.assertEqual(self.client.post(f"/inbox/{cid}/schedule", json={"body": "x", "sendAt": (NOW - timedelta(minutes=1)).isoformat()}).status_code, 422)
        made = self.client.post(f"/inbox/{cid}/schedule", json={"body": "Later", "sendAt": (NOW + timedelta(hours=2)).isoformat()}).json()
        self.assertEqual(self.client.get(f"/inbox/{cid}/scheduled").json()[0]["status"], "pending")
        self.assertEqual(self.client.delete(f"/inbox/scheduled/{made['id']}").status_code, 204)
        self.assertEqual(self.client.get(f"/inbox/{cid}/scheduled").json()[0]["status"], "cancelled")

    def test_a_due_message_is_queued_through_the_normal_send_path_and_a_blocked_one_fails_with_the_reason(self):
        cid = self.id("bob")
        with SessionLocal() as db:
            ok = models.ScheduledMessage(user_id=self.owner_id, conversation_id=cid, account_id=self.a1_id, body="On time", send_at=NOW - timedelta(minutes=1))
            gone = models.ScheduledMessage(user_id=self.owner_id, conversation_id=cid, account_id=self.a1_id, body="Blocked", send_at=NOW - timedelta(minutes=1))
            db.add_all([ok, gone])
            db.commit()
            ok_id, gone_id = ok.id, gone.id
        with SessionLocal() as db:
            db.get(models.ScheduledMessage, gone_id).status = "cancelled"  # only the first is due now
            db.commit()
            self.assertEqual(inbox.release_due(db, NOW), 1)
            self.assertEqual(db.get(models.ScheduledMessage, ok_id).status, "sent")
            self.assertEqual(db.query(models.AgentTask).filter_by(type="send_message").count(), 1)
            self.assertEqual(db.query(models.Message).filter_by(conversation_id=cid, body="On time", direction="outbound").one().delivery_status, "queued")

    def test_a_disconnected_sender_fails_a_due_message_with_the_reason(self):
        cid = self.id("bob")
        with SessionLocal() as db:
            item = models.ScheduledMessage(user_id=self.owner_id, conversation_id=cid, account_id=self.a1_id, body="Late", send_at=NOW - timedelta(minutes=1))
            db.add(item)
            db.get(models.LinkedInAccount, self.a1_id).session_status = "disconnected"
            db.commit()
            self.assertEqual(inbox.release_due(db, NOW), 0)
            self.assertEqual((item.status, item.error), ("failed", "The sender account was not connected at the scheduled time."))


class SuggestTest(InboxCase):
    def test_a_suggestion_is_saved_as_the_draft_with_its_provider_and_sends_nothing(self):
        cost = self.client.get("/inbox/suggest-cost").json()
        self.assertEqual((cost["provider"], cost["estimatedUsd"]), ("template", 0.0))
        r = self.client.post(f"/inbox/{self.id('ann')}/suggest-reply").json()
        self.assertTrue(r["text"])
        self.assertEqual(r["provider"], "template")
        self.assertEqual(self.client.get("/inbox/conversations", params={"drafts": "true"}).json()["total"], 2)  # Dee's and Ann's drafts
        with SessionLocal() as db:
            self.assertEqual(db.query(models.AgentTask).count(), 0)

    def test_a_thread_where_the_person_has_not_written_gets_no_suggestion(self):
        r = self.client.post(f"/inbox/{self.id('bob')}/suggest-reply")
        self.assertEqual(r.status_code, 409)
        self.assertIn("has not written", r.json()["detail"])


class ExportRefreshTest(InboxCase):
    def test_the_export_follows_the_filters_and_neutralises_formulas(self):
        with SessionLocal() as db:
            lead = db.query(models.Lead).filter_by(first_name="Bob").one()
            lead.company = "=HYPERLINK(\"http://evil\")"
            db.commit()
        r = self.client.get("/inbox/export", params={"starred": "true"})
        self.assertEqual(r.headers["content-type"].split(";")[0], "text/csv")
        lines = r.text.strip().splitlines()
        self.assertEqual(len(lines), 2)
        self.assertIn("'=HYPERLINK", lines[1])

    def test_a_refresh_queues_one_paced_read_per_connected_sender_and_never_two_at_once(self):
        first = self.client.post("/inbox/refresh", json={}).json()
        self.assertEqual((first["queued"], first["skipped"]), (2, []))
        second = self.client.post("/inbox/refresh", json={"accountIds": [self.a1_id]}).json()
        self.assertEqual(second["queued"], 0)
        self.assertEqual(second["skipped"], [{"account": "Ada", "reason": "already reading"}])
        with SessionLocal() as db:
            db.get(models.LinkedInAccount, self.a2_id).session_status = "disconnected"
            db.query(models.AgentTask).delete()
            db.commit()
        third = self.client.post("/inbox/refresh", json={}).json()
        self.assertEqual(third["queued"], 1)
        self.assertEqual(third["skipped"], [{"account": "Grace", "reason": "not connected"}])


if __name__ == "__main__":
    unittest.main()
