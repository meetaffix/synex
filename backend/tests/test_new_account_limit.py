"""A new sender account starts stopped (daily limit 0) until its owner sets a limit; the warm-up then starts at 5 a day and never
goes above the hard ceilings. Existing accounts keep the values they have."""
import atexit
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

TEMP = tempfile.TemporaryDirectory()
os.environ["DATABASE_URL"] = "sqlite:///" + TEMP.name.replace("\\", "/") + "/test.db"
os.environ["SECRET_KEY"] = "test-secret-not-for-production-0123456789"
os.environ["ENCRYPTION_KEY"] = "test-encryption-not-for-production-0123456789"
os.environ["AUTH_PROVIDER"] = "local"
os.environ.setdefault("DEEPGRAM_API_KEY", "dg-SENTINEL-never-leak-9f3a7c")
import safety
safety.assert_isolated_database(os.environ["DATABASE_URL"])
from app import database, engine, models, publishing_models  # noqa: F401
from app.config import DAILY_ACTION_CEILING, DAILY_TYPE_CEILINGS, WEEKLY_INVITE_CEILING
from app.database import Base, SessionLocal
from app.linkedin_session import store
from app.linkedin_session.pages import Profile
from app.migrations import migrate
from app.serializers import account_out

atexit.register(database.engine.dispose)
NOW = datetime.now(timezone.utc)


def profile(slug="ada"):
    return Profile(name="Ada", headline="Engineer", url=f"https://www.linkedin.com/in/{slug}", avatar_url=None)


class NewAccountLimitTest(unittest.TestCase):
    def setUp(self):
        Base.metadata.drop_all(database.engine)
        Base.metadata.create_all(database.engine)
        with SessionLocal() as db:
            user = models.User(email="a@example.com", full_name="A", hashed_password="x")
            db.add(user)
            db.commit()
            self.user_id = user.id

    def connect(self, slug="ada", target=None):
        return store.save_session(workspace_id=self.user_id, target_account_id=target, identifier="a@example.com", profile=profile(slug),
                                  storage_state={"cookies": []}, identity={"userAgent": "x"}, proxy_url=None)

    def account(self, account_id):
        with SessionLocal() as db:
            account = db.get(models.LinkedInAccount, account_id)
            db.expunge(account)
            return account

    def test_an_account_created_by_connecting_starts_stopped_and_cannot_act(self):
        account = self.account(self.connect())
        self.assertEqual(account.daily_action_limit, 0)
        self.assertEqual(engine.configured_daily_limit(account), 0)
        self.assertEqual(engine.effective_daily_limit(account, NOW), 0)
        self.assertEqual(engine.remaining_capacity(account, NOW), 0)
        self.assertFalse(account_out(account)["warmingUp"])

    def test_connecting_again_never_resets_a_limit_the_owner_set(self):
        account_id = self.connect()
        with SessionLocal() as db:
            db.get(models.LinkedInAccount, account_id).daily_action_limit = 30
            db.commit()
        self.assertEqual(self.connect(target=account_id), account_id)
        self.assertEqual(self.account(account_id).daily_action_limit, 30)
        self.assertEqual(self.connect(), account_id)  # the same profile connected again updates it, no duplicate
        self.assertEqual(self.account(account_id).daily_action_limit, 30)

    def test_existing_accounts_keep_their_values_through_the_migration(self):
        with SessionLocal() as db:
            for name, limit in (("keeps fifty", 50), ("keeps thirty", 30), ("stopped", 0)):
                db.add(models.LinkedInAccount(user_id=self.user_id, name=name, daily_action_limit=limit))
            db.commit()
        migrate()
        with SessionLocal() as db:
            limits = {a.name: a.daily_action_limit for a in db.query(models.LinkedInAccount)}
        self.assertEqual(limits, {"keeps fifty": 50, "keeps thirty": 30, "stopped": 0})

    def test_once_the_owner_sets_a_limit_the_warm_up_starts_at_five_and_never_passes_the_ceilings(self):
        def account(limit, started_days_ago=None):
            return models.LinkedInAccount(name="x", daily_action_limit=limit,
                                          warmup_started_at=None if started_days_ago is None else NOW - timedelta(days=started_days_ago))
        self.assertEqual(engine.effective_daily_limit(account(40), NOW), 5)  # day one, never started
        self.assertEqual(engine.effective_daily_limit(account(40, 0), NOW), 5)
        self.assertEqual(engine.effective_daily_limit(account(40, 3), NOW), 20)
        self.assertEqual(engine.effective_daily_limit(account(3, 10), NOW), 3)  # a limit below the warm-up wins
        self.assertEqual(engine.effective_daily_limit(account(0, 100), NOW), 0)  # 0 stays 0 whatever the age
        # A value above the ceiling, however it got there, is held at the ceiling.
        self.assertEqual(engine.configured_daily_limit(account(5000)), DAILY_ACTION_CEILING)
        self.assertEqual(engine.effective_daily_limit(account(5000, 400), NOW), DAILY_ACTION_CEILING)

    def test_the_agreed_hard_ceilings_are_unchanged(self):
        self.assertEqual(DAILY_TYPE_CEILINGS, {"send_invite": 40, "send_message": 100, "visit_profile": 80,
                                            "follow_profile": 50, "check_connection": 80,
                                            "sync_inbox": 48, "sync_connections": 12, "collect_leads": 20, "withdraw_invite": 20, "like_post": 30, "send_inmail": 15, "send_voice_note": 20, "engage_post": 25})
        self.assertEqual(WEEKLY_INVITE_CEILING, 150)
        self.assertEqual(DAILY_ACTION_CEILING, 200)


if __name__ == "__main__":
    unittest.main()
