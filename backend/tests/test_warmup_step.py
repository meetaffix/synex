"""An owner can warm an established account up faster, per account; the configured limit still caps it and odd values are bounded."""
import os
import unittest
from datetime import datetime, timedelta, timezone

os.environ.setdefault("SECRET_KEY", "test-secret-not-for-production-0123456789")
os.environ.setdefault("ENCRYPTION_KEY", "test-encryption-not-for-production-0123456789")
os.environ.setdefault("AUTH_PROVIDER", "local")
from app import engine, models


def account(step=None, limit=150, days=3):
    config = {} if step is None else {"warmupStepPerDay": step}
    now = datetime(2026, 11, 25, 12, tzinfo=timezone.utc)
    a = models.LinkedInAccount(name="A", daily_action_limit=limit, management_config=config, warmup_started_at=now - timedelta(days=days))
    return a, now


class WarmupStepTest(unittest.TestCase):
    def test_the_default_step_is_five_a_day(self):
        a, now = account()
        self.assertEqual(engine.effective_daily_limit(a, now), 5 + 3 * 5)

    def test_an_owner_step_of_fifteen_grows_three_times_faster(self):
        a, now = account(step=15)
        self.assertEqual(engine.effective_daily_limit(a, now), 5 + 3 * 15)

    def test_the_configured_limit_still_caps_it(self):
        a, now = account(step=15, limit=40, days=10)
        self.assertEqual(engine.effective_daily_limit(a, now), 40)

    def test_odd_values_are_bounded(self):
        self.assertEqual(engine.warmup_step(account(step=500)[0]), engine.WARMUP_STEP_MAX)
        self.assertEqual(engine.warmup_step(account(step=0)[0]), engine.WARMUP_STEP_MIN)
        self.assertEqual(engine.warmup_step(account(step="fast")[0]), engine.WARMUP_STEP)


if __name__ == "__main__":
    unittest.main()
