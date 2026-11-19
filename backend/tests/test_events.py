"""Events a workspace can be told about: a sender connected, and a campaign paused (by hand or automatically). Each reaches the notification outbox."""
import unittest

from test_outreach import IDENTITY, OutreachCase, SessionLocal, session_state  # noqa: E402  (sets the isolated environment)
from app import models, outreach_results
from app.config import settings
from app.linkedin_session import store
from app.linkedin_session.pages import Profile


class EventTest(OutreachCase):
    def listen(self, *events):
        self.client.put("/integrations/notifications", json={"emails": ["boss@example.com"], **{e: True for e in events}})

    def outbox(self):
        with SessionLocal() as db:
            return [m.subject for m in db.query(models.OutboxEmail).order_by(models.OutboxEmail.created_at)]

    def test_connecting_a_sender_tells_the_workspace_and_a_reconnect_tells_it_again(self):
        self.listen("account_connected")
        profile = Profile(name="Grace Hopper", headline="Admiral", url="https://www.linkedin.com/in/grace/", avatar_url=None)
        first = store.save_session(workspace_id=self.user_id, target_account_id=None, identifier="grace@example.com", profile=profile,
                                   storage_state=session_state("ok"), identity=IDENTITY, proxy_url=None)
        self.assertEqual(self.outbox(), ["Synex: A sender account was connected"])
        store.save_session(workspace_id=self.user_id, target_account_id=first, identifier="grace@example.com", profile=profile,
                           storage_state=session_state("ok"), identity=IDENTITY, proxy_url=None)
        self.assertEqual(len(self.outbox()), 2)

    def test_nothing_is_sent_when_the_notification_is_off(self):
        self.listen()  # account_connected stays at its default: on, so turn it off explicitly
        self.client.put("/integrations/notifications", json={"emails": ["boss@example.com"], "account_connected": False})
        store.save_session(workspace_id=self.user_id, target_account_id=None, identifier="g@example.com",
                           profile=Profile(name="G", headline=None, url="https://www.linkedin.com/in/g/", avatar_url=None), storage_state=session_state("ok"), identity=IDENTITY, proxy_url=None)
        self.assertEqual(self.outbox(), [])

    def test_pausing_a_campaign_by_hand_tells_the_workspace_once(self):
        self.listen("campaign_paused")
        campaign_id = self.make_campaign(["ann"])
        for expected in (1, 1):  # pausing an already paused campaign is not news
            r = self.client.post("/campaigns", json={"action": "update", "id": campaign_id, "status": "paused"})
            self.assertEqual(r.status_code, 200, r.text)
            self.assertEqual(len(self.outbox()), expected)
        self.assertEqual(self.outbox(), ["Synex: A campaign was paused"])

    def test_an_automatic_pause_after_repeated_failures_tells_the_workspace_with_the_reason(self):
        self.listen("campaign_paused")
        campaign_id = self.make_campaign(["ann"], pause_on_failure=True)
        with SessionLocal() as db:
            campaign = db.get(models.Campaign, campaign_id)
            for _ in range(settings.outreach_max_consecutive_failures):
                outreach_results.register_failure(campaign)
            db.commit()
            self.assertEqual(campaign.status, "paused")
        with SessionLocal() as db:
            mail = db.query(models.OutboxEmail).one()
            self.assertEqual(mail.subject, "Synex: A campaign was paused")
            self.assertIn("failed actions in a row", mail.body)


if __name__ == "__main__":
    unittest.main()
