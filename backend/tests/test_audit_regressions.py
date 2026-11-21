"""Regressions found in the 21 Nov 2026 audit: a run left waiting for a task that was never queued, an inbox read that stops after a few
hours because it ignores its own daily budget, and replies detected from messages that were there before any outreach."""
import unittest
from datetime import datetime, timedelta, timezone

from test_outreach import MOCK, OutreachCase, SessionLocal  # noqa: E402  (sets the isolated environment)
from app import engine, models, outreach_results as results
from app.linkedin_session.actions import InboundConversation
from app.linkedin_session.pages import ThreadMessage

MESSAGE_ONLY = [{"type": "message", "message": "Hello {{first_name}}"}, {"type": "end"}]


class StuckRunTest(OutreachCase):
    def test_a_run_is_never_parked_for_a_task_that_does_not_exist(self):
        """A failed task keeps its idempotency key (so a worker never re-sends by itself). If the run is put back to running,
        the engine must not park it for 24 hours waiting for the task: it must say the step failed."""
        self.make_campaign([{"user": "vimal", "status": "connected"}], MESSAGE_ONLY)
        self.tick()
        (task,) = self.tasks("send_message")
        with SessionLocal() as db:  # what the 18 Nov live test left behind: a failed task, its key kept, the run running again
            row = db.get(models.AgentTask, task.id)
            row.status = "failed"
            run = db.query(models.SequenceRun).one()
            run.status, run.next_action_at = "running", datetime.now(timezone.utc)
            db.commit()
        self.tick()
        run = self.run_of("vimal")
        self.assertNotEqual(run.status, "awaiting_agent", "the run waits for a task that is not queued")
        self.assertEqual((run.status, run.stop_reason), ("stopped", "send_failed"))

    def test_a_run_whose_task_is_still_queued_keeps_waiting(self):
        self.make_campaign([{"user": "vimal", "status": "connected"}], MESSAGE_ONLY)
        self.tick()
        with SessionLocal() as db:
            run = db.query(models.SequenceRun).one()
            run.status, run.next_action_at = "running", datetime.now(timezone.utc)
            db.commit()
        self.tick()
        self.assertEqual(self.run_of("vimal").status, "awaiting_agent")
        self.assertEqual(len(self.tasks("send_message")), 1)


class InboxBudgetTest(OutreachCase):
    def test_inbox_reads_are_spread_over_the_day_so_the_budget_does_not_run_out_in_hours(self):
        from unittest.mock import patch
        from app.config import settings
        account_id = self.make_account()
        with SessionLocal() as db:
            account = db.get(models.LinkedInAccount, account_id)
            account.management_config = {"policy": {"preset": "off", "range": 1, "actions": {
                "sync_inbox": {"dailyLimit": 12, "increaseBy": 0, "stopAt": 12, "intervalDays": 7, "dynamicInterval": False}}}}
            account.last_inbox_sync_at = datetime.now(timezone.utc) - timedelta(minutes=20)
            db.commit()
        with patch.object(settings, "outreach_inbox_sync_interval_minutes", 15):
            with SessionLocal() as db:
                queued = engine.emit_inbox_syncs(db, datetime.now(timezone.utc))
                db.commit()
        self.assertEqual(queued, 0, "12 reads a day must be about two hours apart, not every 15 minutes")


class FalseReplyTest(OutreachCase):
    def _thread(self, messages):
        return InboundConversation("t1", MOCK.profile_url("vimal"), [ThreadMessage(f"e{i}", d, text, datetime.now(timezone.utc).isoformat())
                                                                    for i, (d, text) in enumerate(messages)])

    def _store(self, messages):
        account_id = self.make_account()
        self.make_campaign([{"user": "vimal", "status": "connected"}], MESSAGE_ONLY, [account_id], launch=False)
        with SessionLocal() as db:
            lead = db.query(models.Lead).one()
            engine.record_event(db, lead, "message_sent", "sent", account=db.get(models.LinkedInAccount, account_id))
            db.commit()
            results._store_thread(db, db.get(models.LinkedInAccount, account_id), lead, self._thread(messages), datetime.now(timezone.utc) + timedelta(minutes=1))
            db.commit()
        return self.lead_status("vimal")

    def test_a_message_that_came_before_ours_is_not_a_reply(self):
        """The live reader stamps every message with the time of the read, so time cannot tell old from new: order does."""
        self.assertEqual(self._store([("in", "Thanks for the earlier chat"), ("out", "Hello Vimal")]), "connected")

    def test_a_message_after_ours_is_a_reply(self):
        self.assertEqual(self._store([("out", "Hello Vimal"), ("in", "Hi, tell me more")]), "replied")


class ConfirmBeforeSendTest(OutreachCase):
    """Anything that can start a real send after the first launch needs an explicit confirmation from the person at the screen."""

    def _campaign(self):
        return self.make_campaign([{"user": "vimal", "status": "connected"}], MESSAGE_ONLY)

    def _update(self, campaign_id, **fields):
        return self.client.post("/campaigns", json={"action": "update", "id": campaign_id, **fields})

    def test_resume_needs_a_confirmation(self):
        campaign_id = self._campaign()
        self.assertEqual(self._update(campaign_id, status="paused").status_code, 200)  # pausing never needs one
        refused = self._update(campaign_id, status="active")
        self.assertEqual(refused.status_code, 409, refused.text)
        self.assertIn("send_confirmation_required", refused.text)
        with SessionLocal() as db:
            self.assertEqual(db.query(models.Campaign).one().status, "paused")
        self.assertEqual(self._update(campaign_id, status="active", confirmSend=True).status_code, 200)

    def test_retry_and_skip_need_a_confirmation(self):
        campaign_id = self._campaign()
        run_id = self.run_of("vimal").id
        for action in ("retry", "skip"):
            body = {"action": "run", "id": campaign_id, "runId": run_id, "runAction": action}
            refused = self.client.post("/campaigns", json=body)
            self.assertEqual(refused.status_code, 409, refused.text)
            self.assertIn("send_confirmation_required", refused.text)
        self.assertEqual(self.client.post("/campaigns", json={"action": "run", "id": campaign_id, "runId": run_id, "runAction": "retry", "confirmSend": True}).status_code, 200)

    def test_adding_a_person_to_a_running_campaign_needs_a_confirmation(self):
        campaign_id = self._campaign()
        with SessionLocal() as db:
            lead = models.Lead(user_id=self.user_id, first_name="Late", last_name="Test", status="connected", linkedin_url=MOCK.profile_url("late"))
            db.add(lead)
            db.commit()
            lead_id = lead.id
        refused = self.client.post(f"/leads/{lead_id}/add-to-campaign", json={"campaignId": campaign_id})
        self.assertEqual(refused.status_code, 409, refused.text)
        self.assertIn("send_confirmation_required", refused.text)
        self.assertEqual(self.client.post(f"/leads/{lead_id}/add-to-campaign", json={"campaignId": campaign_id, "confirmSend": True}).status_code, 200)

    def test_adding_a_person_to_a_paused_campaign_sends_nothing_so_needs_none(self):
        campaign_id = self._campaign()
        self._update(campaign_id, status="paused")
        with SessionLocal() as db:
            lead = models.Lead(user_id=self.user_id, first_name="Late", last_name="Test", status="connected", linkedin_url=MOCK.profile_url("late"))
            db.add(lead)
            db.commit()
            lead_id = lead.id
        self.assertEqual(self.client.post(f"/leads/{lead_id}/add-to-campaign", json={"campaignId": campaign_id}).status_code, 200)


if __name__ == "__main__":
    unittest.main()
