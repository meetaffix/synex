"""Sender policy boundaries, rolling reservations and workspace authorization."""
import unittest
from datetime import datetime, timedelta, timezone

from pydantic import ValidationError

from test_linkedin_session import SessionApiCase
from app import account_policy, engine, models
from app.database import SessionLocal

NOW = datetime(2026, 11, 16, 12, tzinfo=timezone.utc)


class PolicyMathTest(unittest.TestCase):
    def account(self, preset="custom", limit=5, stop=40, days=0):
        return models.LinkedInAccount(id="policy-test", name="Policy test", management_config={
            "policyStartedAt": (NOW - timedelta(days=days)).isoformat(),
            "policy": {"preset": preset, "range": 1, "actions": {"send_invite": {
                "dailyLimit": limit, "stopAt": stop, "increaseBy": 1, "intervalDays": 7}}}})

    def test_zero_remains_stopped_under_every_preset(self):
        for preset in ("off", "custom", "conservative", "balanced", "aggressive"):
            self.assertEqual(account_policy.bounds(self.account(preset, 0, days=365), "send_invite", NOW), (0, 0, 0))

    def test_presets_ranges_and_repeatability_never_exceed_ceiling(self):
        for preset, days, expected in (("conservative", 7, 6), ("balanced", 2, 5),
                                      ("balanced", 3, 7), ("balanced", 5, 9), ("aggressive", 2, 11)):
            account = self.account(preset, days=days)
            low, high, budget = account_policy.bounds(account, "send_invite", NOW)
            self.assertEqual((low, high), (expected - 1, expected + 1))
            self.assertLessEqual(low, budget)
            self.assertLessEqual(budget, high)
            self.assertEqual(account_policy.bounds(account, "send_invite", NOW)[2], budget)
        self.assertEqual(account_policy.bounds(self.account("aggressive", days=365), "send_invite", NOW)[:2], (39, 40))

    def test_invalid_or_unknown_limits_are_rejected(self):
        for body in ({"range": 11}, {"actions": {"unknown": {"dailyLimit": 1, "stopAt": 1}}},
                     {"actions": {"send_invite": {"dailyLimit": 41, "stopAt": 41}}},
                     {"actions": {"send_invite": {"dailyLimit": 5, "stopAt": 4}}}):
            with self.assertRaises(ValidationError):
                account_policy.SenderPolicy.model_validate(body)


class PolicyApiTest(SessionApiCase):
    def test_saved_policy_is_enforced_at_queue_and_manual_reply(self):
        account_id = self.connect_and_wait()
        payload = {"actions": {"send_message": {"dailyLimit": 0, "stopAt": 20}}}
        saved = self.client.put(f"/linkedin-accounts/{account_id}/policy", json=payload)
        self.assertEqual(saved.status_code, 200, saved.text)
        detail = self.client.get(f"/linkedin-accounts/{account_id}/details").json()
        self.assertEqual(next(x for x in detail["usage"] if x["action"] == "send_message")["budget"], 0)
        with SessionLocal() as db:
            account = db.get(models.LinkedInAccount, account_id)
            account.daily_action_limit = 20
            self.assertIsNone(engine.emit_task(db, account, "send_message", {}, "must-not-queue"))
            self.assertIn("limit", engine.manual_send_refusal(db, account, "send_message", NOW))

    def test_rolling_window_counts_yesterday_and_actual_commit_time(self):
        account_id = self.connect_and_wait()
        with SessionLocal() as db:
            for index, hours in enumerate((23, 25)):
                db.add(models.AgentTask(account_id=account_id, type="send_message", status="done",
                                       created_at=NOW - timedelta(hours=hours), idempotency_key=f"rolling-{index}"))
            db.add(models.AgentTask(account_id=account_id, type="send_message", status="done",
                                   created_at=NOW - timedelta(days=3), committed_at=NOW - timedelta(hours=1),
                                   idempotency_key="delayed-send"))
            db.flush()
            self.assertEqual(account_policy.rolling_usage(db, account_id, NOW, "send_message"), 2)

    def test_seat_deactivation_frees_seat_but_keeps_history_and_stops_tasks(self):
        account_id = self.connect_and_wait()
        self.assertEqual(self.client.get("/linkedin-accounts/overview").json()["seatsUsed"], 1)
        self.assertEqual(self.client.post(f"/linkedin-accounts/{account_id}/deactivate").status_code, 204)
        self.assertEqual(self.client.get("/linkedin-accounts/overview").json()["seatsUsed"], 0)
        self.assertEqual(self.client.get("/linkedin-accounts").json()[0]["status"], "paused")
        with SessionLocal() as db:
            account = db.get(models.LinkedInAccount, account_id)
            self.assertFalse(engine.account_is_live(account))
            self.assertIsNone(engine.emit_task(db, account, "send_invite", {}, "inactive-seat"))

    def test_other_workspace_cannot_read_or_mutate_policy(self):
        self.assertEqual(self.client.get("/linkedin-accounts/not-owned/details").status_code, 404)
        self.assertEqual(self.client.put("/linkedin-accounts/not-owned/policy", json={}).status_code, 404)


if __name__ == "__main__":
    unittest.main()
