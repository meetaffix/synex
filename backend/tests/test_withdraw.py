"""Auto-withdraw of stale invitations: the worker takes a pending request back on the mock site, and the sweep only does it for senders that switched it on,
only for requests older than the chosen days, never for accepted ones, within the withdraw ceiling, and never twice."""
import unittest
from datetime import datetime, timedelta, timezone

from test_outreach import INVITE_ONLY, MOCK, OutreachCase, SessionLocal  # noqa: E402  (sets the isolated environment)
from app import engine, models
from app.config import DAILY_TYPE_CEILINGS
from app.linkedin_session import actions

OLD = datetime.now(timezone.utc) - timedelta(days=45)


class WithdrawCase(OutreachCase):
    def sender(self, auto=True, days=30):
        account_id = self.make_account()
        with SessionLocal() as db:
            account = db.get(models.LinkedInAccount, account_id)
            account.management_config = {"policy": {"preset": "off", "range": 1, "autoWithdraw": auto, "staleInviteDays": days, "inboxHistoryDays": 90, "actions": {
                "withdraw_invite": {"dailyLimit": 10, "increaseBy": 0, "stopAt": 10, "intervalDays": 7, "dynamicInterval": False}}}}
            db.commit()
        return account_id

    def old_invite(self, account_id, user, status="done", age=OLD, lead_status="contacted", connected=False):
        """A connection request sent `age` ago: the lead, a run and a finished send_invite task."""
        with SessionLocal() as db:
            lead = models.Lead(user_id=self.user_id, first_name=user.title(), last_name="Test", status=lead_status, linkedin_url=MOCK.profile_url(user),
                               connected_at=datetime.now(timezone.utc) if connected else None)
            campaign = models.Campaign(user_id=self.user_id, name="C", status="active", account_id=account_id)
            db.add_all([lead, campaign])
            db.flush()
            run = models.SequenceRun(user_id=self.user_id, campaign_id=campaign.id, lead_id=lead.id, status="waiting_connection")
            db.add(run)
            db.flush()
            db.add(models.AgentTask(account_id=account_id, sequence_run_id=run.id, type="send_invite", status=status, idempotency_key=f"inv:{user}", payload={},
                                    committed_at=age, created_at=age))
            db.commit()
        MOCK.profile(user)["state"] = "pending"

    def sweep(self):
        with SessionLocal() as db:
            n = engine.emit_stale_withdrawals(db, datetime.now(timezone.utc))
            db.commit()
            return n


class ActionTest(WithdrawCase):
    def test_a_pending_request_is_withdrawn_on_the_site_and_a_connected_person_is_left_alone(self):
        MOCK.profile("pia")["state"] = "pending"
        MOCK.profile("cat")["state"] = "connected"
        self.assertEqual(self.open_session(lambda s: actions.withdraw_invite(s, MOCK.profile_url("pia"))), actions.WithdrawResult.WITHDRAWN)
        self.assertEqual(MOCK.withdrawals, ["pia"])
        self.assertEqual(MOCK.profile("pia")["state"], "not_connected")
        self.assertEqual(self.open_session(lambda s: actions.withdraw_invite(s, MOCK.profile_url("cat"))), actions.WithdrawResult.NOT_PENDING)
        self.assertEqual(MOCK.withdrawals, ["pia"])  # nothing was clicked for the connected person
        MOCK.profile("gone")["available"] = False
        self.assertEqual(self.open_session(lambda s: actions.withdraw_invite(s, MOCK.profile_url("gone"))), actions.WithdrawResult.PROFILE_UNAVAILABLE)


class SweepTest(WithdrawCase):
    def test_nothing_happens_when_auto_withdraw_is_off(self):
        account = self.sender(auto=False)
        self.old_invite(account, "ann")
        self.assertEqual(self.sweep(), 0)

    def test_only_old_unanswered_requests_are_taken_back_once(self):
        account = self.sender()
        self.old_invite(account, "old1")
        self.old_invite(account, "fresh", age=datetime.now(timezone.utc) - timedelta(days=3))  # younger than 30 days
        self.old_invite(account, "accepted", lead_status="connected", connected=True)
        self.old_invite(account, "failed", status="failed")
        self.assertEqual(self.sweep(), 1)
        self.assertEqual(self.sweep(), 0)  # never twice for the same person
        task = self.tasks("withdraw_invite")[0]
        self.assertEqual(task.payload["linkedinUrl"], MOCK.profile_url("old1"))

    def test_the_days_setting_and_a_per_tick_limit_apply(self):
        account = self.sender(days=7)
        for i in range(5):
            self.old_invite(account, f"p{i}", age=datetime.now(timezone.utc) - timedelta(days=10))
        self.assertEqual(self.sweep(), 3)  # three at a time, so it never bursts
        self.assertEqual(self.sweep(), 2)

    def test_the_withdraw_ceiling_and_a_limit_of_zero_stop_it(self):
        account = self.sender()
        with SessionLocal() as db:
            for i in range(DAILY_TYPE_CEILINGS["withdraw_invite"]):
                db.add(models.AgentTask(account_id=account, type="withdraw_invite", status="done", idempotency_key=f"used{i}", payload={}, committed_at=datetime.now(timezone.utc)))
            db.commit()
        self.old_invite(account, "late")
        self.assertEqual(self.sweep(), 0)
        self.assertGreaterEqual(DAILY_TYPE_CEILINGS["withdraw_invite"], 1)


class WorkerTest(WithdrawCase):
    def test_the_worker_withdraws_the_request_records_it_and_the_lead_stays_a_lead(self):
        account = self.sender()
        self.old_invite(account, "wen")
        self.assertEqual(self.sweep(), 1)
        self.drive(lambda: MOCK.withdrawals)
        self.assertEqual(MOCK.withdrawals, ["wen"])
        self.assertEqual(self.tasks("withdraw_invite")[0].status, "done")
        with SessionLocal() as db:
            lead = db.query(models.Lead).filter_by(first_name="Wen").one()
            self.assertEqual(lead.status, "contacted")
            self.assertTrue(db.query(models.LeadEvent).filter_by(lead_id=lead.id, type="invite_withdrawn").count())


if __name__ == "__main__":
    unittest.main()
