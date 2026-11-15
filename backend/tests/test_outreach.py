"""Outreach executor tests: action layer, worker, engine limits, safety controls, dry run.
Everything runs against the local mock LinkedIn site and temporary databases."""
import atexit
import json
import os
import tempfile
import threading
import time
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

TEMP = tempfile.TemporaryDirectory()
# Same values as the other test modules: whichever is imported first fixes the settings.
os.environ["DATABASE_URL"] = "sqlite:///" + TEMP.name.replace("\\", "/") + "/test.db"
os.environ["SECRET_KEY"] = "test-secret-not-for-production-0123456789"
os.environ["ENCRYPTION_KEY"] = "test-encryption-not-for-production-0123456789"
os.environ["LINKEDIN_CLIENT_ID"] = "test-client"
os.environ["LINKEDIN_CLIENT_SECRET"] = "test-client-secret"
import safety
safety.assert_isolated_database(os.environ["DATABASE_URL"])
from fastapi.testclient import TestClient
from app import engine, models, outreach_results as results
from app.config import settings
safety.assert_isolated_database(settings.database_url)
from app.database import Base, SessionLocal, engine as db_engine
from app.linkedin_session import actions
from app.linkedin_session.actions import ActionSession, SessionError
from app.linkedin_session.manager import SessionManager
from app.linkedin_session.pages import SessionProblem
from app.main import app, _attempts
from app.linkedin_session.schemas import AccountOut
from app.migrations import migrate
from app import planner
from app.outreach_worker import OutreachWorker
from app.publishing_models import Migration
from app.security import encrypt_secret
from mock_linkedin import shared_mock

atexit.register(db_engine.dispose)
ORIGIN = {"Origin": "http://localhost:5173"}
MOCK = shared_mock()
REAL_ACTION_GAP = engine._action_gap  # the engine's own pacing, before OutreachCase.setUp replaces it with zero
IDENTITY = {"userAgent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36",
            "viewport": {"width": 1366, "height": 768}, "locale": "en-US", "timezoneId": "UTC"}
FULL_SEQUENCE = [
    {"type": "connection_request", "message": "Hi {{first_name}}"},
    {"type": "wait", "delay_hours": 0},
    {"type": "message", "message": "Hello {{first_name}}, thanks for connecting"},
    {"type": "wait", "delay_hours": 48},
    {"type": "follow_up", "message": "Following up, {{first_name}}"},
    {"type": "end"},
]


INVITE_ONLY = [{"type": "connection_request", "message": "Hi"}, {"type": "end"}]


class Crash(BaseException):
    """Simulates the worker process dying: not an Exception, so nothing handles it."""




def session_state(user: str) -> dict:
    cookie = lambda name, value: {"name": name, "value": value, "domain": "127.0.0.1", "path": "/", "expires": -1,
                                  "httpOnly": False, "secure": False, "sameSite": "Lax"}
    return {"cookies": [cookie("li_at", "ok"), cookie("li_user", user)], "origins": []}


class OutreachCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manager = SessionManager(MOCK.site, max_browsers=3, attempt_timeout=60, poll_interval=0.1, headless=True)

    @classmethod
    def tearDownClass(cls):
        cls.manager.shutdown()

    def setUp(self):
        Base.metadata.drop_all(db_engine)
        migrate()
        _attempts.clear()
        MOCK.reset()
        for name, value in (("outreach_action_gap_min_seconds", 0), ("outreach_action_gap_max_seconds", 0),
                            ("outreach_acceptance_check_interval_hours", 0), ("outreach_inbox_sync_interval_minutes", 1000),
                            ("outreach_task_retry_backoff_seconds", 0), ("outreach_stale_task_seconds", 600),
                            ("outreach_kill_switch", False), ("outreach_weekly_connection_limit", 100),
                            ("outreach_max_consecutive_failures", 5), ("outreach_task_max_attempts", 3)):
            patcher = patch.object(settings, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        pacing = patch.object(engine, "_action_gap", return_value=timedelta(0))
        pacing.start()
        self.addCleanup(pacing.stop)
        self.worker = OutreachWorker(self.manager, MOCK.pages)
        self.addCleanup(self.settle)
        self.client = TestClient(app, headers=ORIGIN)
        self.addCleanup(self.client.close)
        r = self.client.post("/auth", json={"action": "register", "email": "owner@example.com", "fullName": "Owner", "password": "Strong-Test-Password!"})
        self.assertEqual(r.status_code, 200, r.text)
        self.user_id = r.json()["user"]["id"]

    def settle(self):
        self.worker.stopping.set()
        self.worker.join(timeout=30)

    # ---- data helpers ------------------------------------------------------------------

    def make_account(self, name="sender", tz="UTC", sync_mode="synex_only", daily_limit=50, session_user="ok") -> str:
        with SessionLocal() as db:
            account = models.LinkedInAccount(
                user_id=self.user_id, name=name, status="active", session_status="connected", sync_mode=sync_mode,
                daily_action_limit=daily_limit, warmup_started_at=datetime.now(timezone.utc) - timedelta(days=60),
                browser_profile={**IDENTITY, "timezoneId": tz}, session_state_encrypted=encrypt_secret(json.dumps(session_state(session_user))),
                connected_by_user_id=self.user_id, login_identifier=f"{name}@example.com")
            db.add(account)
            db.commit()
            return account.id

    def make_campaign(self, leads, steps=None, accounts=None, launch=True, **fields) -> str:
        accounts = accounts or [self.make_account()]
        with SessionLocal() as db:
            lead_list = models.LeadList(user_id=self.user_id, name="List")
            db.add(lead_list)
            created = datetime.now(timezone.utc) - timedelta(hours=1)
            for index, lead in enumerate(leads):
                spec = lead if isinstance(lead, dict) else {"user": lead}
                row = models.Lead(user_id=self.user_id, first_name=spec["user"].title(), last_name="Test", status=spec.get("status", "new"),
                                  linkedin_url=spec.get("url", MOCK.profile_url(spec["user"])), timezone=spec.get("timezone"),
                                  created_at=created + timedelta(milliseconds=index))
                lead_list.leads.append(row)
            schedule = dict(timezone="UTC", start_hour=0, end_hour=24, working_days=[0, 1, 2, 3, 4, 5, 6], random_delay=False)
            schedule.update(fields)
            campaign = models.Campaign(
                user_id=self.user_id, name="Campaign", status="active", account_id=accounts[0], account_ids=accounts[1:],
                lead_list=lead_list, **schedule)
            for i, step in enumerate(FULL_SEQUENCE if steps is None else steps):
                campaign.steps.append(models.CampaignStep(type=step["type"], order=i, message=step.get("message"), delay_hours=step.get("delay_hours")))
            db.add(campaign)
            db.flush()
            if launch:
                engine.launch_campaign(db, campaign)
            db.commit()
            return campaign.id

    def drive(self, until, rounds=14):
        for _ in range(rounds):
            self.worker.run_once(wait=True)
            if until():
                return
        self.fail("campaign did not reach the expected state")

    def tasks(self, ttype=None):
        with SessionLocal() as db:
            query = db.query(models.AgentTask).order_by(models.AgentTask.created_at)
            return [t for t in query.all() if ttype is None or t.type == ttype]

    def run_of(self, user: str) -> models.SequenceRun:
        with SessionLocal() as db:
            lead = db.query(models.Lead).filter_by(first_name=user.title()).one()
            return db.query(models.SequenceRun).filter_by(lead_id=lead.id).one()

    def lead_status(self, user: str) -> str:
        with SessionLocal() as db:
            return db.query(models.Lead).filter_by(first_name=user.title()).one().status

    def account_row(self, account_id: str) -> models.LinkedInAccount:
        with SessionLocal() as db:
            return db.get(models.LinkedInAccount, account_id)

    def tick(self):
        with SessionLocal() as db:
            return engine.tick(db)

    def open_session(self, fn, user="ok"):
        """Run an async action against the mock site inside a real browser session."""
        outcome = {}

        async def work(page, context):
            outcome["value"] = await fn(ActionSession(page, MOCK.pages))

        self.manager.submit_session_work(storage_state=session_state(user), identity=IDENTITY, proxy_url=None, work=work).result(60)
        return outcome["value"]


# ===================================================================== action layer

class ActionLayerTest(OutreachCase):
    def test_invite_results(self):
        MOCK.accept("linked")
        MOCK.profile("waiting")["state"] = "pending"

        async def run(session):
            return [
                await actions.send_connection_request(session, MOCK.profile_url("fresh"), "Hello there"),
                await actions.send_connection_request(session, MOCK.profile_url("linked")),
                await actions.send_connection_request(session, MOCK.profile_url("waiting")),
                await actions.send_connection_request(session, MOCK.profile_url("toolong"), "x" * 301),
                await actions.send_connection_request(session, MOCK.profile_url("gone")),
            ]

        sent, connected, pending, too_long, gone = self.open_session(run)
        self.assertEqual((sent, connected, pending, too_long, gone),
                         (actions.InviteResult.SENT, actions.InviteResult.ALREADY_CONNECTED, actions.InviteResult.ALREADY_PENDING,
                          actions.InviteResult.NOTE_TOO_LONG, actions.InviteResult.PROFILE_UNAVAILABLE))
        self.assertEqual(MOCK.invites, [("fresh", "Hello there")])

    def test_weekly_limit_sends_nothing(self):
        MOCK.weekly_limit = True
        result = self.open_session(lambda s: actions.send_connection_request(s, MOCK.profile_url("fresh"), "Hi"))
        self.assertEqual(result, actions.InviteResult.WEEKLY_LIMIT_REACHED)
        self.assertEqual(MOCK.invites, [])

    def test_message_visit_follow_and_status_results(self):
        MOCK.accept("friend")
        MOCK.profile("followed")["following"] = True
        MOCK.profile("waiting")["state"] = "pending"

        async def run(session):
            return {
                "sent": await actions.send_message(session, MOCK.profile_url("friend"), "Hello friend"),
                "stranger": await actions.send_message(session, MOCK.profile_url("stranger"), "Hello"),
                "gone_message": await actions.send_message(session, MOCK.profile_url("gone"), "Hello"),
                "visited": await actions.visit_profile(session, MOCK.profile_url("stranger")),
                "gone_visit": await actions.visit_profile(session, MOCK.profile_url("gone")),
                "followed": await actions.follow_profile(session, MOCK.profile_url("stranger")),
                "already": await actions.follow_profile(session, MOCK.profile_url("followed")),
                "gone_follow": await actions.follow_profile(session, MOCK.profile_url("gone")),
                "connected": await actions.get_connection_status(session, MOCK.profile_url("friend")),
                "pending": await actions.get_connection_status(session, MOCK.profile_url("waiting")),
                "not_connected": await actions.get_connection_status(session, MOCK.profile_url("nobody")),
                "gone_status": await actions.get_connection_status(session, MOCK.profile_url("gone")),
            }

        r = self.open_session(run)
        self.assertEqual((r["sent"], r["stranger"], r["gone_message"]),
                         (actions.MessageResult.SENT, actions.MessageResult.NOT_CONNECTED, actions.MessageResult.PROFILE_UNAVAILABLE))
        self.assertEqual((r["visited"], r["gone_visit"]), (actions.VisitResult.VISITED, actions.VisitResult.PROFILE_UNAVAILABLE))
        self.assertEqual((r["followed"], r["already"], r["gone_follow"]),
                         (actions.FollowResult.FOLLOWED, actions.FollowResult.ALREADY_FOLLOWING, actions.FollowResult.PROFILE_UNAVAILABLE))
        self.assertEqual((r["connected"], r["pending"], r["not_connected"], r["gone_status"]),
                         (actions.ConnectionStatus.CONNECTED, actions.ConnectionStatus.PENDING,
                          actions.ConnectionStatus.NOT_CONNECTED, actions.ConnectionStatus.PROFILE_UNAVAILABLE))
        self.assertEqual(MOCK.sent_messages, [("friend", "Hello friend")])
        self.assertEqual(MOCK.follows, ["stranger"])

    def test_fetch_new_messages_respects_the_cutoff(self):
        MOCK.reply("old", "an older message")
        time.sleep(0.05)
        cutoff = datetime.now(timezone.utc)
        time.sleep(0.05)
        MOCK.reply("new", "a newer message")

        everything = self.open_session(lambda s: actions.fetch_new_messages(s, None))
        recent = self.open_session(lambda s: actions.fetch_new_messages(s, cutoff))
        self.assertEqual(sorted(c.thread_id for c in everything), ["new", "old"])
        self.assertEqual([c.thread_id for c in recent], ["new"])
        self.assertEqual((recent[0].messages[0].direction, recent[0].messages[0].text), ("in", "a newer message"))
        self.assertTrue(recent[0].profile_url.endswith("/in/new/"))

    def test_session_problems_are_typed_errors(self):
        for flag, expected in (("force_logged_out", SessionProblem.LOGGED_OUT), ("force_restricted", SessionProblem.RESTRICTED)):
            MOCK.reset()
            setattr(MOCK, flag, True)
            with self.assertRaises(SessionError) as caught:
                self.open_session(lambda s: actions.visit_profile(s, MOCK.profile_url("fresh")))
            self.assertEqual(caught.exception.kind, expected)

    def test_checkpoint_or_restriction_mid_action_stops_the_action(self):
        for fault, expected in (("checkpoint", SessionProblem.CHECKPOINT), ("restricted", SessionProblem.RESTRICTED), ("logged_out", SessionProblem.LOGGED_OUT)):
            MOCK.reset()
            MOCK.accept("friend")
            MOCK.fault = fault
            with self.assertRaises(SessionError) as caught:
                self.open_session(lambda s: actions.send_message(s, MOCK.profile_url("friend"), "Hello"))
            self.assertEqual(caught.exception.kind, expected)
            self.assertEqual(MOCK.sent_messages, [])
            MOCK.fault = "checkpoint"
            with self.assertRaises(SessionError):
                self.open_session(lambda s: actions.send_connection_request(s, MOCK.profile_url("fresh"), "Hi"))
            self.assertEqual(MOCK.invites, [])


# ===================================================================== full campaign

class CampaignFlowTest(OutreachCase):
    def test_invite_acceptance_message_reply_and_stop(self):
        self.setting_inbox_every_cycle = patch.object(settings, "outreach_inbox_sync_interval_minutes", 0)
        self.setting_inbox_every_cycle.start()
        self.addCleanup(self.setting_inbox_every_cycle.stop)
        campaign_id = self.make_campaign(["ann"])

        self.drive(lambda: MOCK.invites)
        self.assertEqual(MOCK.invites, [("ann", "Hi Ann")])
        self.assertEqual(self.lead_status("ann"), "contacted")

        self.drive(lambda: any(t.type == "check_connection" and t.status == "done" for t in self.tasks()))
        self.assertEqual(MOCK.sent_messages, [])  # not accepted yet: the check ran, no message went out
        self.assertEqual(self.run_of("ann").status, "waiting_connection")

        MOCK.accept("ann")
        self.drive(lambda: MOCK.sent_messages)
        self.assertEqual(MOCK.sent_messages, [("ann", "Hello Ann, thanks for connecting")])
        self.assertEqual(self.lead_status("ann"), "connected")

        MOCK.reply("ann", "Thanks, tell me more")
        self.drive(lambda: self.run_of("ann").status == "stopped")
        run = self.run_of("ann")
        self.assertEqual((run.status, run.stop_reason), ("stopped", "replied"))
        self.assertEqual(self.lead_status("ann"), "replied")
        self.assertEqual(len(MOCK.sent_messages), 1)  # the 48h follow-up never went out

        with SessionLocal() as db:
            convo = db.query(models.Conversation).one()
            self.assertEqual(sorted((m.direction, m.body) for m in convo.messages),
                             [("inbound", "Thanks, tell me more"), ("outbound", "Hello Ann, thanks for connecting")])
            types = {e.type for e in db.query(models.LeadEvent).all()}
            self.assertTrue({"added_to_campaign", "connection_sent", "connected", "message_sent", "replied"} <= types)
            # Audit trail: every executed action wrote agent_activity with campaign, step, result and time.
            sends = [a for a in db.query(models.AgentActivity).filter(models.AgentActivity.step.in_(["send_invite", "send_message"])).all()]
            self.assertEqual(sorted(a.result for a in sends), ["sent", "sent"])
            for row in sends:
                self.assertEqual(row.campaign_id, campaign_id)
                self.assertIsNotNone(row.step_id)
                self.assertIsNotNone(row.task_id)
                self.assertIsNotNone(row.created_at)
            events = db.query(models.LeadEvent).filter(models.LeadEvent.type.in_(["connection_sent", "message_sent"])).all()
            self.assertTrue(all(e.step_id and e.task_id and e.account_id and e.campaign_id for e in events))

    def test_profile_visit_and_follow_steps(self):
        self.make_campaign(["vic"], [{"type": "profile_visit"}, {"type": "follow"}, {"type": "end"}])
        self.drive(lambda: MOCK.follows)
        self.assertEqual(MOCK.follows, ["vic"])
        self.drive(lambda: self.run_of("vic").status == "completed")

    def test_steps_added_to_a_live_campaign_are_picked_up(self):
        campaign_id = self.make_campaign(["gus"], [{"type": "profile_visit"}, {"type": "end"}])
        self.tick()
        with SessionLocal() as db:
            campaign = db.get(models.Campaign, campaign_id)
            end = next(s for s in campaign.steps if s.type == "end")
            end.order = 2
            campaign.steps.append(models.CampaignStep(type="follow", order=1))
            db.commit()
        self.drive(lambda: MOCK.follows)
        self.assertEqual(MOCK.follows, ["gus"])

    def test_synex_only_stores_no_unrelated_conversations(self):
        account_id = self.make_account(sync_mode="synex_only")
        self.make_campaign(["ann"], [{"type": "connection_request", "message": "Hi"}, {"type": "wait", "delay_hours": 48}, {"type": "end"}], [account_id])
        self.drive(lambda: MOCK.invites)
        MOCK.reply("stranger", "Buy my product")
        MOCK.reply("ann", "Hello back")
        with patch.object(settings, "outreach_inbox_sync_interval_minutes", 0):
            self.drive(lambda: self.account_row(account_id).last_inbox_sync_at is not None)
        with SessionLocal() as db:
            self.assertEqual(db.query(models.Lead).filter_by(first_name="Stranger").count(), 0)
            self.assertEqual([c.lead.first_name for c in db.query(models.Conversation).all()], ["Ann"])

    def test_sync_mode_all_imports_every_conversation(self):
        account_id = self.make_account(sync_mode="all")
        MOCK.reply("stranger", "Buy my product")
        self.make_campaign(["ann"], [{"type": "profile_visit"}, {"type": "end"}], [account_id])
        with patch.object(settings, "outreach_inbox_sync_interval_minutes", 0):
            self.drive(lambda: self.account_row(account_id).last_inbox_sync_at is not None)
        with SessionLocal() as db:
            lead = db.query(models.Lead).filter_by(first_name="Stranger").one()
            self.assertEqual(lead.source, "inbox_sync")
            self.assertEqual(db.query(models.Conversation).filter_by(lead_id=lead.id).count(), 1)

    def test_replies_before_outreach_do_not_stop_a_run(self):
        MOCK.reply("ann", "An old message from before the campaign")
        self.make_campaign(["ann"], [{"type": "connection_request", "message": "Hi"}, {"type": "wait", "delay_hours": 48}, {"type": "end"}])
        with patch.object(settings, "outreach_inbox_sync_interval_minutes", 0):
            self.drive(lambda: MOCK.invites and self.tasks("sync_inbox") and all(t.status == "done" for t in self.tasks("sync_inbox")))
        self.assertNotEqual(self.run_of("ann").status, "stopped")


# ===================================================================== limits and schedule

class LimitsTest(OutreachCase):
    def test_daily_limit_parks_the_rest(self):
        account_id = self.make_account(daily_limit=2)
        self.make_campaign(["a1", "a2", "a3"], [{"type": "connection_request", "message": "Hi"}, {"type": "end"}], [account_id])
        with patch.object(engine, "_action_gap", return_value=timedelta(0)):
            for _ in range(3):
                self.tick()
        self.assertEqual(len(self.tasks("send_invite")), 2)
        third = self.run_of("a3")
        self.assertGreater(engine._aware(third.next_action_at), datetime.now(timezone.utc))

    def test_weekly_connection_cap(self):
        account_id = self.make_account()
        with patch.object(settings, "outreach_weekly_connection_limit", 2):
            with SessionLocal() as db:
                for n in range(2):
                    db.add(models.AgentTask(account_id=account_id, type="send_invite", status="done", idempotency_key=f"old-{n}",
                                            created_at=datetime.now(timezone.utc) - timedelta(days=2)))
                db.commit()
            self.make_campaign(["b1"], [{"type": "connection_request", "message": "Hi"}, {"type": "end"}], [account_id])
            self.tick()
        self.assertEqual(len(self.tasks("send_invite")), 2)  # only the two old ones
        self.assertGreater(engine._aware(self.run_of("b1").next_action_at), datetime.now(timezone.utc))

    def test_weekly_cap_ignores_invites_older_than_a_week(self):
        account_id = self.make_account()
        with patch.object(settings, "outreach_weekly_connection_limit", 1):
            with SessionLocal() as db:
                db.add(models.AgentTask(account_id=account_id, type="send_invite", status="done", idempotency_key="old",
                                        created_at=datetime.now(timezone.utc) - timedelta(days=8)))
                db.commit()
            self.make_campaign(["b1"], [{"type": "connection_request", "message": "Hi"}, {"type": "end"}], [account_id])
            self.tick()
        self.assertEqual(len(self.tasks("send_invite")), 2)

    def test_working_hours_are_evaluated_in_the_campaign_timezone(self):
        campaign = SimpleNamespace(timezone="Asia/Tokyo", working_days=[1, 2, 3, 4, 5], start_hour=9, end_hour=17)
        wednesday = datetime(2026, 3, 4, tzinfo=timezone.utc)
        self.assertTrue(engine.within_hours(campaign, wednesday.replace(hour=1), None))    # 10:00 in Tokyo
        self.assertFalse(engine.within_hours(campaign, wednesday.replace(hour=12), None))  # 21:00 in Tokyo
        self.assertFalse(engine.within_hours(campaign, datetime(2026, 3, 7, 1, tzinfo=timezone.utc), None))  # Saturday in Tokyo
        self.assertFalse(engine.within_hours(campaign, datetime(2026, 3, 3, 23, tzinfo=timezone.utc), None))  # 08:00 Wednesday in Tokyo
        self.assertTrue(engine.within_hours(campaign, datetime(2026, 3, 4, 0, 30, tzinfo=timezone.utc), None))  # 09:30 Wednesday in Tokyo

    def test_a_lead_timezone_overrides_the_campaign_timezone(self):
        campaign = SimpleNamespace(timezone="Asia/Tokyo", working_days=[1, 2, 3, 4, 5], start_hour=9, end_hour=17)
        lead = SimpleNamespace(timezone="America/New_York")
        moment = datetime(2026, 3, 4, 14, tzinfo=timezone.utc)  # 23:00 Tokyo, 09:00 New York
        self.assertFalse(engine.within_hours(campaign, moment, None))
        self.assertTrue(engine.within_hours(campaign, moment, lead))
        self.assertFalse(engine.within_hours(campaign, moment, SimpleNamespace(timezone=None)))

    def test_a_lead_outside_its_hours_is_parked_not_sent(self):
        zone = "Pacific/Kiritimati"
        self.make_campaign([{"user": "late", "timezone": zone}], [{"type": "connection_request", "message": "Hi"}, {"type": "end"}])
        start = (engine._local(datetime.now(timezone.utc), zone).hour + 2) % 24  # a one-hour window that is not the lead's current hour
        with SessionLocal() as db:
            campaign = db.query(models.Campaign).one()
            campaign.start_hour, campaign.end_hour = start, start + 1
            db.commit()
        self.tick()
        self.assertEqual(self.tasks("send_invite"), [])
        self.assertGreater(engine._aware(self.run_of("late").next_action_at), datetime.now(timezone.utc))

    def test_daily_counters_roll_over_in_the_account_timezone(self):
        moment = datetime(2026, 3, 4, 12, 30, tzinfo=timezone.utc)  # 01:30 on 5 March in Auckland, still 4 March in UTC
        auckland = SimpleNamespace(browser_profile={"timezoneId": "Pacific/Auckland"}, last_action_date="2026-03-04",
                                   daily_actions_used=7, messages_today=3, connections_today=4)
        utc = SimpleNamespace(browser_profile={"timezoneId": "UTC"}, last_action_date="2026-03-04",
                              daily_actions_used=7, messages_today=3, connections_today=4)
        engine._roll_daily_window(auckland, moment)
        engine._roll_daily_window(utc, moment)
        self.assertEqual((auckland.last_action_date, auckland.daily_actions_used, auckland.connections_today), ("2026-03-05", 0, 0))
        self.assertEqual((utc.last_action_date, utc.daily_actions_used, utc.connections_today), ("2026-03-04", 7, 4))
        self.assertEqual(engine.remaining_capacity(SimpleNamespace(
            browser_profile={"timezoneId": "Pacific/Auckland"}, last_action_date="2026-03-04", daily_actions_used=50,
            daily_action_limit=50, warmup_started_at=moment - timedelta(days=60)), moment), 50)


# ===================================================================== no double sends

class NoDoubleSendTest(OutreachCase):
    INVITE_ONLY = [{"type": "connection_request", "message": "Hi {{first_name}}"}, {"type": "end"}]

    def crashing_invite(self):
        real = actions.send_connection_request

        async def send_then_die(session, url, note=None):
            await real(session, url, note)
            raise Crash

        return patch("app.outreach_worker.actions.send_connection_request", side_effect=send_then_die)

    def test_a_worker_that_dies_mid_action_leaves_the_task_for_review_and_never_resends(self):
        self.make_campaign(["ann"], self.INVITE_ONLY)
        with self.crashing_invite():
            self.worker.run_once(wait=True)
        self.assertEqual(MOCK.invites, [("ann", "Hi Ann")])
        crashed = self.tasks("send_invite")[0]
        self.assertEqual(crashed.status, "running")
        self.assertIsNotNone(crashed.committed_at)

        with patch.object(settings, "outreach_stale_task_seconds", 0):
            time.sleep(0.05)
            self.worker = OutreachWorker(self.manager, MOCK.pages)
            self.worker.run_once(wait=True)
        self.assertEqual(self.tasks("send_invite")[0].status, "needs_review")
        self.assertEqual(self.run_of("ann").status, "needs_review")
        for _ in range(3):
            self.worker.run_once(wait=True)
        self.assertEqual(MOCK.invites, [("ann", "Hi Ann")])
        self.assertEqual(len(self.tasks("send_invite")), 1)

    def test_two_workers_racing_for_one_task_send_once(self):
        account_id = self.make_account()
        self.make_campaign(["ann"], self.INVITE_ONLY, [account_id])
        self.tick()
        other = OutreachWorker(SessionManager(MOCK.site, max_browsers=2, attempt_timeout=60, poll_interval=0.1, headless=True), MOCK.pages)
        self.addCleanup(other.manager.shutdown)
        errors = []

        def go(worker):
            try:
                worker.run_once(wait=True)
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)

        threads = [threading.Thread(target=go, args=(w,)) for w in (self.worker, other)]
        [t.start() for t in threads]
        [t.join() for t in threads]
        self.assertEqual(errors, [])
        self.assertEqual(MOCK.invites, [("ann", "Hi Ann")])
        self.assertEqual(len(self.tasks("send_invite")), 1)

    def test_only_one_caller_can_claim_a_task(self):
        account_id = self.make_account()
        self.make_campaign(["ann"], self.INVITE_ONLY, [account_id])
        self.tick()
        winners, barrier = [], threading.Barrier(8)

        def claim(n):
            with SessionLocal() as db:
                barrier.wait()
                task_id = results.claim_next_task(db, account_id, f"worker-{n}", datetime.now(timezone.utc))
                if task_id:
                    winners.append(task_id)

        threads = [threading.Thread(target=claim, args=(n,)) for n in range(8)]
        [t.start() for t in threads]
        [t.join() for t in threads]
        self.assertEqual(len(winners), 1)
        self.assertEqual(self.tasks("send_invite")[0].attempts, 1)

    def test_running_the_same_tick_twice_queues_one_task(self):
        self.make_campaign(["ann"], self.INVITE_ONLY)
        self.tick()
        self.tick()
        self.assertEqual(len(self.tasks("send_invite")), 1)
        self.worker.run_once(wait=True)
        self.assertEqual(MOCK.invites, [("ann", "Hi Ann")])

    def test_the_idempotency_key_is_unique_in_the_database(self):
        account_id = self.make_account()
        with SessionLocal() as db:
            db.add(models.AgentTask(account_id=account_id, type="send_invite", idempotency_key="run:step"))
            db.commit()
            db.add(models.AgentTask(account_id=account_id, type="send_invite", idempotency_key="run:step"))
            from sqlalchemy.exc import IntegrityError
            with self.assertRaises(IntegrityError):
                db.commit()

    def test_state_is_rechecked_before_acting(self):
        self.make_campaign(["ann", "bob"], self.INVITE_ONLY, [self.make_account(), self.make_account("second")])
        self.tick()
        with SessionLocal() as db:  # both leads reply/connect after their tasks were queued
            db.query(models.Lead).filter_by(first_name="Ann").update({"status": "interested"})
            db.query(models.Lead).filter_by(first_name="Bob").update({"status": "connected"})
            db.commit()
        self.worker.run_once(wait=True)
        self.assertEqual(MOCK.invites, [])
        self.assertTrue(all(t.status == "cancelled" for t in self.tasks("send_invite")))

    def test_a_message_already_recorded_for_the_task_is_not_sent_again(self):
        self.make_campaign(["ann"], [{"type": "message", "message": "Hello"}, {"type": "end"}], launch=True)
        with SessionLocal() as db:
            db.query(models.Lead).update({"status": "connected"})
            db.commit()
        self.tick()
        task = self.tasks("send_message")[0]
        with SessionLocal() as db:
            lead = db.query(models.Lead).one()
            convo = engine.get_or_create_convo(db, None, lead, db.query(models.LinkedInAccount).one(), datetime.now(timezone.utc))
            db.add(models.Message(conversation_id=convo.id, direction="outbound", body="Hello", task_id=task.id))
            db.commit()
        self.worker.run_once(wait=True)
        self.assertEqual(MOCK.sent_messages, [])

    def test_failures_before_touching_the_page_retry_then_fail(self):
        self.make_campaign(["ann"], self.INVITE_ONLY)
        calls = []

        async def fail_early(session, url, note=None):
            calls.append(1)
            raise RuntimeError("navigation failed")

        with patch("app.outreach_worker.actions.send_connection_request", side_effect=fail_early):
            for _ in range(5):
                self.worker.run_once(wait=True)
        task = self.tasks("send_invite")[0]
        self.assertEqual((len(calls), task.attempts, task.status), (3, 3, "failed"))
        self.assertIsNone(task.committed_at)
        self.assertEqual(self.run_of("ann").stop_reason, "send_failed")
        self.assertEqual(MOCK.invites, [])

    def test_retries_wait_for_their_backoff(self):
        self.make_campaign(["ann"], self.INVITE_ONLY)
        calls = []

        async def fail_early(session, url, note=None):
            calls.append(1)
            raise RuntimeError("navigation failed")

        with patch.object(settings, "outreach_task_retry_backoff_seconds", 3600):
            with patch("app.outreach_worker.actions.send_connection_request", side_effect=fail_early):
                for _ in range(3):
                    self.worker.run_once(wait=True)
        task = self.tasks("send_invite")[0]
        self.assertEqual((len(calls), task.status), (1, "pending"))
        self.assertGreater(engine._aware(task.next_attempt_at), datetime.now(timezone.utc) + timedelta(minutes=30))

    def test_a_failure_after_the_irreversible_click_needs_review_and_is_not_retried(self):
        self.make_campaign(["ann"], self.INVITE_ONLY)
        real = actions.send_connection_request

        async def send_then_error(session, url, note=None):
            await real(session, url, note)
            raise RuntimeError("lost the page after sending")

        with patch("app.outreach_worker.actions.send_connection_request", side_effect=send_then_error):
            for _ in range(3):
                self.worker.run_once(wait=True)
        self.assertEqual(self.tasks("send_invite")[0].status, "needs_review")
        self.assertEqual(MOCK.invites, [("ann", "Hi Ann")])


# ===================================================================== safety controls

class SafetyTest(OutreachCase):
    INVITE_ONLY = [{"type": "connection_request", "message": "Hi"}, {"type": "end"}]

    def api_user(self, role):
        with SessionLocal() as db:
            db.query(models.User).filter_by(id=self.user_id).update({"role": role})
            db.commit()

    def test_a_logged_out_session_pauses_the_account_before_anything_is_sent(self):
        account_id = self.make_account()
        self.make_campaign(["ann", "bob"], self.INVITE_ONLY, [account_id])
        MOCK.force_logged_out = True
        for _ in range(3):
            self.worker.run_once(wait=True)
        account = self.account_row(account_id)
        self.assertEqual((account.session_status, account.status), ("needs_reconnect", "pending"))
        self.assertIn("signed this account out", account.paused_reason)
        self.assertEqual(MOCK.invites, [])
        self.assertTrue(all(t.status == "pending" for t in self.tasks("send_invite")))  # untouched, safe to resume

    def test_a_checkpoint_after_the_click_stops_the_account_and_needs_review(self):
        account_id = self.make_account()
        self.make_campaign(["ann", "bob"], self.INVITE_ONLY, [account_id])
        MOCK.fault = "checkpoint"
        for _ in range(3):
            self.worker.run_once(wait=True)
        account = self.account_row(account_id)
        self.assertEqual(account.session_status, "needs_reconnect")
        self.assertIn("security check", account.paused_reason)
        self.assertEqual(MOCK.invites, [])
        # The account stopped: the second lead's queued invite was never touched.
        self.assertEqual([t.status for t in self.tasks("send_invite")], ["needs_review", "pending"])
        self.assertEqual(self.run_of("ann").status, "needs_review")

    def test_a_restriction_marks_the_account_restricted(self):
        account_id = self.make_account()
        self.make_campaign(["ann"], self.INVITE_ONLY, [account_id])
        MOCK.fault = "restricted"
        self.worker.run_once(wait=True)
        account = self.account_row(account_id)
        self.assertEqual(account.session_status, "restricted")
        self.assertIn("restricted", account.paused_reason)

    def test_the_pause_reason_is_shown_in_the_account_object_and_cleared_on_resume(self):
        account_id = self.make_account()
        self.make_campaign(["ann"], self.INVITE_ONLY, [account_id])
        MOCK.force_logged_out = True
        self.worker.run_once(wait=True)
        listed = self.client.get("/linkedin-accounts").json()[0]
        self.assertEqual((listed["status"], listed["id"]), ("needs_reconnect", account_id))
        self.assertIn("signed this account out", listed["pausedReason"])
        patched = self.client.patch(f"/linkedin-accounts/{account_id}", json={"paused": False}).json()
        self.assertIsNone(patched["pausedReason"])

    def test_a_campaign_pauses_after_consecutive_failures(self):
        with patch.object(settings, "outreach_max_consecutive_failures", 2), patch.object(settings, "outreach_task_max_attempts", 1):
            campaign_id = self.make_campaign(["ann", "bob", "cy"], self.INVITE_ONLY, pause_on_failure=True)

            async def fail(session, url, note=None):
                raise RuntimeError("boom")

            with patch("app.outreach_worker.actions.send_connection_request", side_effect=fail), \
                    patch.object(engine, "_action_gap", return_value=timedelta(0)):
                for _ in range(4):
                    self.worker.run_once(wait=True)
        with SessionLocal() as db:
            campaign = db.get(models.Campaign, campaign_id)
            self.assertEqual(campaign.status, "paused")
            self.assertGreaterEqual(campaign.consecutive_failures, 2)
            self.assertIn("failed actions in a row", campaign.paused_reason)

    def test_a_success_resets_the_failure_streak(self):
        with patch.object(settings, "outreach_max_consecutive_failures", 2), patch.object(settings, "outreach_task_max_attempts", 1):
            campaign_id = self.make_campaign(["ann"], self.INVITE_ONLY, pause_on_failure=True)
            with SessionLocal() as db:
                db.get(models.Campaign, campaign_id).consecutive_failures = 1
                db.commit()
            self.worker.run_once(wait=True)
        with SessionLocal() as db:
            self.assertEqual(db.get(models.Campaign, campaign_id).consecutive_failures, 0)
            self.assertEqual(db.get(models.Campaign, campaign_id).status, "active")

    def test_the_kill_switch_setting_stops_everything(self):
        self.make_campaign(["ann"], self.INVITE_ONLY)
        with patch.object(settings, "outreach_kill_switch", True):
            outcome = self.worker.run_once(wait=True)
        self.assertTrue(outcome["killed"])
        self.assertEqual((self.tasks(), MOCK.invites), ([], []))
        self.worker.run_once(wait=True)
        self.assertEqual(MOCK.invites, [("ann", "Hi")])

    def test_the_admin_endpoint_stops_and_resumes_execution(self):
        self.make_campaign(["ann"], self.INVITE_ONLY)
        self.assertEqual(self.client.post("/outreach/kill-switch", json={"enabled": True}).status_code, 403)
        self.assertEqual(self.client.get("/outreach/status").status_code, 403)
        self.api_user("Admin")
        on = self.client.post("/outreach/kill-switch", json={"enabled": True})
        self.assertEqual((on.status_code, on.json()["killSwitch"], on.json()["forcedBySetting"]), (200, True, False))
        self.worker.run_once(wait=True)
        self.assertEqual((self.tasks(), MOCK.invites), ([], []))
        self.assertEqual(self.client.get("/outreach/status").json()["killSwitch"], True)
        self.assertEqual(self.client.post("/outreach/kill-switch", json={"enabled": False}).json()["killSwitch"], False)
        self.worker.run_once(wait=True)
        self.assertEqual(MOCK.invites, [("ann", "Hi")])
        self.assertEqual(self.client.get("/outreach/status").json()["workersActive"], 1)

    def test_the_kill_switch_stops_a_batch_between_actions(self):
        account_id = self.make_account()
        self.make_campaign(["ann", "bob"], self.INVITE_ONLY, [account_id])
        with patch.object(engine, "_action_gap", return_value=timedelta(0)):
            self.tick()
            self.tick()
        self.assertEqual(len(self.tasks("send_invite")), 2)
        real = actions.send_connection_request

        async def send_then_kill(session, url, note=None):
            outcome = await real(session, url, note)
            with SessionLocal() as db:
                db.add(models.OutreachControl(id="global", kill_switch=True))
                db.commit()
            return outcome

        with patch("app.outreach_worker.actions.send_connection_request", side_effect=send_then_kill):
            self.worker.run_once(wait=True)
        self.assertEqual(len(MOCK.invites), 1)
        self.assertEqual(sorted(t.status for t in self.tasks("send_invite")), ["done", "pending"])


# ===================================================================== dry run, launch, replies

class DryRunTest(OutreachCase):
    def test_dry_run_matches_what_the_engine_queues_and_the_worker_sends(self):
        first, second = self.make_account("first"), self.make_account("second")
        campaign_id = self.make_campaign(["ann", "bob", "cy"], FULL_SEQUENCE, [first, second], launch=False)
        before = (len(self.tasks()), len(MOCK.invites))
        plan = self.client.post(f"/campaigns/{campaign_id}/dry-run")
        self.assertEqual(plan.status_code, 200, plan.text)
        planned = plan.json()["actions"]
        self.assertEqual((len(self.tasks()), len(MOCK.invites)), before)  # sends and changes nothing
        self.assertEqual([a["leadName"] for a in planned], ["Ann Test", "Bob Test", "Cy Test"])
        self.assertEqual({a["taskType"] for a in planned}, {"send_invite"})
        self.assertEqual({k for k in planned[0]}, {"leadId", "leadName", "accountId", "accountName", "stepId", "stepOrder", "stepType",
                                                   "taskType", "message", "aiPersonalized", "earliestAt", "skipReason"})
        self.assertEqual(planned[0]["message"], "Hi Ann")

        with SessionLocal() as db:
            engine.launch_campaign(db, db.get(models.Campaign, campaign_id))
            db.commit()
        with patch.object(engine, "_action_gap", return_value=timedelta(seconds=45)):
            self.tick()
        queued = [(t.payload["leadId"], t.account_id, t.type, t.payload["message"]) for t in self.tasks("send_invite")]
        self.assertEqual(len(queued), 2)  # two accounts, one action each per tick
        self.assertEqual(queued, [(a["leadId"], a["accountId"], a["taskType"], a["message"]) for a in planned[:2]])
        self.worker.run_once(wait=True)
        self.assertEqual(sorted(MOCK.invites), [("ann", planned[0]["message"]), ("bob", planned[1]["message"])])

    def test_dry_run_explains_skips_and_caps_at_fifty(self):
        campaign_id = self.make_campaign(
            [{"user": "nourl", "url": ""}, {"user": "replied", "status": "replied"}] + [f"lead{n:02d}" for n in range(55)],
            FULL_SEQUENCE, launch=False)
        actions_out = self.client.post(f"/campaigns/{campaign_id}/dry-run").json()["actions"]
        self.assertEqual(len(actions_out), 50)
        reasons = {a["leadName"]: a["skipReason"] for a in actions_out if a["skipReason"]}
        self.assertEqual(reasons["Nourl Test"], "Lead has no LinkedIn URL.")
        self.assertIn("replied", reasons["Replied Test"])

    def test_dry_run_is_workspace_scoped(self):
        campaign_id = self.make_campaign(["ann"], FULL_SEQUENCE, launch=False)
        other = TestClient(app, headers=ORIGIN)
        self.addCleanup(other.close)
        other.post("/auth", json={"action": "register", "email": "other@example.com", "fullName": "Other", "password": "Strong-Test-Password!"})
        self.assertEqual(other.post(f"/campaigns/{campaign_id}/dry-run").status_code, 404)

    def test_dry_run_reports_when_no_account_can_send(self):
        account_id = self.make_account()
        with SessionLocal() as db:
            db.get(models.LinkedInAccount, account_id).session_status = "needs_reconnect"
            db.commit()
        campaign_id = self.make_campaign(["ann"], FULL_SEQUENCE, [account_id], launch=False)
        planned = self.client.post(f"/campaigns/{campaign_id}/dry-run").json()["actions"]
        self.assertIn("capacity", planned[0]["skipReason"])


class LaunchValidationTest(OutreachCase):
    def launch(self, campaign_id):
        return self.client.post("/campaigns", json={"action": "update", "id": campaign_id, "status": "active"})

    def draft(self, leads=("ann",), steps=None, accounts=None, **fields):
        campaign_id = self.make_campaign(list(leads), steps if steps is not None else FULL_SEQUENCE, accounts, launch=False, **fields)
        with SessionLocal() as db:
            db.get(models.Campaign, campaign_id).status = "draft"
            db.commit()
        return campaign_id

    def types(self, response):
        self.assertEqual(response.status_code, 422, response.text)
        return {item["type"]: item["msg"] for item in response.json()["detail"]}

    def test_a_complete_campaign_launches(self):
        response = self.launch(self.draft())
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["status"], "active")
        self.assertEqual(len(self.client.get("/campaigns").json()), 1)
        self.assertEqual(self.client.get("/campaigns").json()[0]["accountStatus"], "connected")

    def test_each_missing_item_has_its_own_422(self):
        account_id = self.make_account()
        with SessionLocal() as db:
            db.get(models.LinkedInAccount, account_id).session_status = "disconnected"
            db.commit()
        no_account = self.types(self.launch(self.draft(accounts=[account_id])))
        self.assertIn("launch.no_connected_account", no_account)
        self.assertIn("Sender accounts", no_account["launch.no_connected_account"])

        empty = self.types(self.launch(self.draft(leads=())))
        self.assertIn("launch.empty_lead_list", empty)

        no_steps = self.types(self.launch(self.draft(steps=[])))
        self.assertIn("launch.no_steps", no_steps)

        only_waits = self.types(self.launch(self.draft(steps=[{"type": "wait", "delay_hours": 1}])))
        self.assertIn("launch.no_actionable_step", only_waits)

        blank = self.types(self.launch(self.draft(steps=[{"type": "message", "message": " "}])))
        self.assertIn("launch.empty_message", blank)

        for bad in ({"start_hour": 17, "end_hour": 9}, {"working_days": []}, {"timezone": "Mars/Olympus"}, {"end_hour": 30}):
            campaign_id = self.draft()
            with SessionLocal() as db:
                for key, value in bad.items():
                    setattr(db.get(models.Campaign, campaign_id), key, value)
                db.commit()
            self.assertIn("launch.invalid_working_hours", self.types(self.launch(campaign_id)), bad)

    def test_every_missing_item_is_reported_at_once(self):
        account_id = self.make_account()
        with SessionLocal() as db:
            db.get(models.LinkedInAccount, account_id).status = "paused"
            db.commit()
        found = self.types(self.launch(self.draft(leads=(), steps=[], accounts=[account_id])))
        self.assertEqual(set(found), {"launch.no_connected_account", "launch.empty_lead_list", "launch.no_steps"})


class ReplyTest(OutreachCase):
    def conversation(self, lead_status="connected", user="ann"):
        account_id = self.make_account()
        with SessionLocal() as db:
            lead = models.Lead(user_id=self.user_id, first_name=user.title(), last_name="Test", status=lead_status, linkedin_url=MOCK.profile_url(user))
            db.add(lead)
            db.flush()
            convo = models.Conversation(user_id=self.user_id, lead_id=lead.id, account_id=account_id, status="active")
            db.add(convo)
            db.commit()
            return convo.id, account_id

    def test_a_reply_is_queued_and_sent_through_the_action_layer(self):
        MOCK.accept("ann")
        convo_id, _ = self.conversation()
        r = self.client.post("/conversations", json={"action": "reply", "conversationId": convo_id, "body": "Happy to chat"})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual((r.json()["deliveryStatus"], r.json()["delivery"]["accountLive"]), ("queued", True))
        self.assertEqual(MOCK.sent_messages, [])
        self.worker.run_once(wait=True)
        self.assertEqual(MOCK.sent_messages, [("ann", "Happy to chat")])
        with SessionLocal() as db:
            message = db.query(models.Message).one()
            self.assertEqual((message.delivery_status, message.task_id), ("sent", self.tasks("send_message")[0].id))

    def test_a_reply_to_someone_not_connected_fails_visibly(self):
        convo_id, _ = self.conversation(lead_status="contacted")
        self.client.post("/conversations", json={"action": "reply", "conversationId": convo_id, "body": "Hello"})
        self.worker.run_once(wait=True)
        self.assertEqual(MOCK.sent_messages, [])
        with SessionLocal() as db:
            message = db.query(models.Message).one()
            self.assertEqual(message.delivery_status, "failed")
            self.assertIn("not connected", message.delivery_error)

    def test_a_reply_needs_a_connected_account(self):
        convo_id, account_id = self.conversation()
        with SessionLocal() as db:
            db.get(models.LinkedInAccount, account_id).session_status = "needs_reconnect"
            db.commit()
        r = self.client.post("/conversations", json={"action": "reply", "conversationId": convo_id, "body": "Hello"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("Sender accounts", r.json()["detail"])

    def test_replies_are_idempotent_per_message(self):
        MOCK.accept("ann")
        convo_id, _ = self.conversation()
        self.client.post("/conversations", json={"action": "reply", "conversationId": convo_id, "body": "Once"})
        for _ in range(3):
            self.worker.run_once(wait=True)
        self.assertEqual(MOCK.sent_messages, [("ann", "Once")])


class CampaignActionsTest(OutreachCase):
    def test_retry_after_needs_review_can_queue_the_step_again(self):
        campaign_id = self.make_campaign(["ann"], [{"type": "connection_request", "message": "Hi"}, {"type": "end"}])
        self.tick()
        with SessionLocal() as db:
            db.query(models.AgentTask).update({"status": "needs_review"})
            db.query(models.SequenceRun).update({"status": "needs_review"})
            db.commit()
        run_id = self.run_of("ann").id
        r = self.client.post("/campaigns", json={"action": "run", "id": campaign_id, "runId": run_id, "runAction": "retry"})
        self.assertEqual(r.status_code, 200, r.text)
        self.tick()
        self.assertEqual(sorted(t.status for t in self.tasks("send_invite")), ["abandoned", "pending"])

    def test_skip_moves_the_run_past_the_current_step(self):
        campaign_id = self.make_campaign(["ann"], [{"type": "connection_request", "message": "Hi"}, {"type": "profile_visit"}, {"type": "end"}])
        run = self.run_of("ann")
        r = self.client.post("/campaigns", json={"action": "run", "id": campaign_id, "runId": run.id, "runAction": "skip"})
        self.assertEqual((r.status_code, r.json()["stepOrder"]), (200, 1))

    def test_the_monitor_reports_tasks_by_the_new_statuses(self):
        campaign_id = self.make_campaign(["ann"], [{"type": "connection_request", "message": "Hi"}, {"type": "end"}])
        self.tick()
        monitor = self.client.get(f"/campaigns?id={campaign_id}&monitor=1").json()
        self.assertEqual(len(monitor["currentActions"]), 1)
        self.assertEqual(monitor["currentActions"][0]["status"], "pending")


class MigrationTest(OutreachCase):
    def test_existing_runs_move_from_step_order_to_step_id(self):
        self.make_campaign(["ann"], FULL_SEQUENCE)
        with SessionLocal() as db:
            run = db.query(models.SequenceRun).one()
            run.current_step_id, run.current_step_order = None, 2
            db.query(Migration).filter_by(version="006_outreach_executor").delete()
            db.commit()
        migrate()
        migrate()
        with SessionLocal() as db:
            step = db.get(models.CampaignStep, db.query(models.SequenceRun).one().current_step_id)
            self.assertEqual((step.type, step.order), ("message", 2))


# ===================================================================== lead timezone, branch columns, daily usage, planner times, lease

class LeadTimezoneTest(OutreachCase):
    def test_a_lead_timezone_can_be_set_returned_updated_and_cleared(self):
        created = self.client.post("/leads", json={"action": "create", "firstName": "Tara", "lastName": "Nakamura", "timezone": "Asia/Tokyo"})
        self.assertEqual(created.status_code, 200, created.text)
        self.assertEqual(created.json()["timezone"], "Asia/Tokyo")
        lead_id = created.json()["id"]
        self.assertEqual(self.client.get("/leads").json()[0]["timezone"], "Asia/Tokyo")
        with SessionLocal() as db:
            self.assertEqual(db.get(models.Lead, lead_id).timezone, "Asia/Tokyo")

        updated = self.client.post("/leads", json={"action": "update", "id": lead_id, "timezone": "Europe/Paris"})
        self.assertEqual(updated.json()["timezone"], "Europe/Paris")
        self.assertEqual(self.client.post("/leads", json={"action": "update", "id": lead_id, "timezone": ""}).json()["timezone"], None)
        self.assertEqual(self.client.post("/leads", json={"action": "update", "id": lead_id, "firstName": "Tara T"}).json()["timezone"], None)

    def test_an_unknown_timezone_is_rejected_without_echoing_it(self):
        for body in ({"action": "create", "firstName": "A", "timezone": "Mars/Olympus-Marker"},
                     {"action": "bulk", "leads": [{"firstName": "A", "timezone": "Mars/Olympus-Marker"}]}):
            r = self.client.post("/leads", json=body)
            self.assertEqual(r.status_code, 422, r.text)
            self.assertNotIn("Olympus-Marker", r.text)

    def test_csv_import_carries_the_timezone_and_a_reimport_fills_a_missing_one(self):
        rows = [{"firstName": "Ann", "lastName": "Lee", "linkedinUrl": "https://www.linkedin.com/in/ann-lee", "timezone": "America/New_York"},
                {"firstName": "Bo", "lastName": "Ray", "linkedinUrl": "https://www.linkedin.com/in/bo-ray"}]
        self.assertEqual(self.client.post("/leads", json={"action": "bulk", "leads": rows, "listIds": []}).status_code, 200)
        by_name = {lead["firstName"]: lead for lead in self.client.get("/leads").json()}
        self.assertEqual((by_name["Ann"]["timezone"], by_name["Bo"]["timezone"]), ("America/New_York", None))
        again = [{"firstName": "Bo", "lastName": "Ray", "linkedinUrl": "https://www.linkedin.com/in/bo-ray", "timezone": "Europe/Berlin"},
                 {"firstName": "Ann", "lastName": "Lee", "linkedinUrl": "https://www.linkedin.com/in/ann-lee", "timezone": "Asia/Tokyo"}]
        self.client.post("/leads", json={"action": "bulk", "leads": again, "listIds": []})
        by_name = {lead["firstName"]: lead for lead in self.client.get("/leads").json()}
        self.assertEqual((by_name["Bo"]["timezone"], by_name["Ann"]["timezone"]), ("Europe/Berlin", "America/New_York"))

    def test_the_engine_uses_the_timezone_set_through_the_api(self):
        lead = self.client.post("/leads", json={"action": "create", "firstName": "Kai", "lastName": "T", "timezone": "Pacific/Kiritimati",
                                                "linkedinUrl": MOCK.profile_url("kai")}).json()
        campaign = SimpleNamespace(timezone="UTC", working_days=[0, 1, 2, 3, 4, 5, 6], start_hour=9, end_hour=17)
        with SessionLocal() as db:
            row = db.get(models.Lead, lead["id"])
            noon_utc = datetime(2026, 3, 4, 12, tzinfo=timezone.utc)  # 02:00 the next day in Kiritimati (UTC+14)
            self.assertTrue(engine.within_hours(campaign, noon_utc, None))
            self.assertFalse(engine.within_hours(campaign, noon_utc, row))


class BranchColumnTest(OutreachCase):
    def test_branch_columns_are_persisted_returned_and_kept_on_update(self):
        steps = [{"type": "connection_request", "order": 0, "message": "Hi"},
                 {"type": "message", "order": 1, "message": "Hello", "parentStepId": "parent-1", "branchCondition": {"when": "accepted", "within_days": 3}},
                 {"type": "end", "order": 2}]
        created = self.client.post("/campaigns", json={"action": "create", "name": "Branches", "steps": steps})
        self.assertEqual(created.status_code, 200, created.text)
        returned = {s["order"]: s for s in created.json()["steps"]}
        self.assertEqual((returned[1]["parentStepId"], returned[1]["branchCondition"]), ("parent-1", {"when": "accepted", "within_days": 3}))
        self.assertEqual((returned[0]["parentStepId"], returned[0]["branchCondition"]), (None, None))
        with SessionLocal() as db:
            row = db.query(models.CampaignStep).filter_by(message="Hello").one()
            self.assertEqual((row.parent_step_id, row.branch_condition), ("parent-1", {"when": "accepted", "within_days": 3}))
        listed = self.client.get("/campaigns").json()[0]["steps"]
        self.assertEqual(sorted(s["parentStepId"] or "" for s in listed), ["", "", "parent-1"])

        again = self.client.post("/campaigns", json={"action": "update", "id": created.json()["id"], "steps": [
            {**s, "id": s["id"], "delay_hours": None} for s in created.json()["steps"]]})
        self.assertEqual({s["order"]: s["parentStepId"] for s in again.json()["steps"]}[1], "parent-1")

    def test_branch_columns_do_not_change_how_a_run_executes(self):
        campaign_id = self.make_campaign(["ann"], [{"type": "connection_request", "message": "Hi"}, {"type": "end"}])
        with SessionLocal() as db:
            step = db.query(models.CampaignStep).filter_by(type="connection_request").one()
            step.parent_step_id, step.branch_condition = "elsewhere", {"when": "never"}
            db.commit()
        self.worker.run_once(wait=True)
        self.assertEqual(MOCK.invites, [("ann", "Hi")])


class DailyUsageTimezoneTest(OutreachCase):
    def account_with_usage(self, tz):
        account_id = self.make_account(tz=tz)
        with SessionLocal() as db:
            row = db.get(models.LinkedInAccount, account_id)
            row.last_action_date, row.daily_actions_used = "2026-03-04", 7
            row.warmup_started_at = datetime(2025, 1, 1, tzinfo=timezone.utc)  # long past warm-up on the dates used here
            db.commit()
        return self.account_row(account_id)

    def test_usage_resets_at_midnight_in_the_accounts_timezone(self):
        kolkata = self.account_with_usage("Asia/Kolkata")
        before = datetime(2026, 3, 4, 18, 29, tzinfo=timezone.utc)  # 23:59 on 4 March in IST
        after = datetime(2026, 3, 4, 18, 31, tzinfo=timezone.utc)   # 00:01 on 5 March in IST
        self.assertEqual(AccountOut.from_model(kolkata, self.user_id, now=before).daily_actions_used, 7)
        self.assertEqual(AccountOut.from_model(kolkata, self.user_id, now=after).daily_actions_used, 0)
        # The engine agrees at both instants.
        self.assertEqual(engine.remaining_capacity(kolkata, before), kolkata.daily_action_limit - 7)
        self.assertEqual(engine.remaining_capacity(kolkata, after), kolkata.daily_action_limit)

    def test_the_same_instant_is_still_the_same_day_for_a_utc_account(self):
        utc = self.account_with_usage("UTC")
        after = datetime(2026, 3, 4, 18, 31, tzinfo=timezone.utc)
        self.assertEqual(AccountOut.from_model(utc, self.user_id, now=after).daily_actions_used, 7)

    def test_the_api_reports_usage_for_today_in_the_accounts_timezone(self):
        account_id = self.make_account(tz="Asia/Kolkata")
        today = engine._local(datetime.now(timezone.utc), "Asia/Kolkata").date().isoformat()
        with SessionLocal() as db:
            row = db.get(models.LinkedInAccount, account_id)
            row.last_action_date, row.daily_actions_used = today, 4
            db.commit()
        self.assertEqual(self.client.get("/linkedin-accounts").json()[0]["dailyActionsUsed"], 4)


class DryRunTimesTest(OutreachCase):
    HOURS = dict(start_hour=9, end_hour=17, working_days=[1, 2, 3, 4, 5])

    def plan(self, now, leads=("ann", "bob"), steps=None, **extra):
        account_id = extra.pop("account_id", None) or self.make_account()
        campaign_id = self.make_campaign(list(leads), steps or [{"type": "connection_request", "message": "Hi"}, {"type": "end"}],
                                         [account_id], launch=False, **{**self.HOURS, **extra})
        with SessionLocal() as db:
            return planner.plan_campaign(db, db.get(models.Campaign, campaign_id), now)

    def test_inside_working_hours_the_first_action_is_now_and_the_next_follows_the_engines_pacing(self):
        wednesday = datetime(2026, 3, 4, 10, 0, tzinfo=timezone.utc)
        first, second = self.plan(wednesday)
        self.assertEqual(first.earliest_at, wednesday)
        # The engine spreads what is left of the day's allowance (4 of 5 on this warm-up day) over the 7 working
        # hours left, clamped to 20 minutes, at the fastest jitter (x0.7): 1200 s x 0.7 = 14 minutes.
        # DryRunMatchesWorkerTest runs the worker to show it really waits this long.
        self.assertEqual(second.earliest_at, wednesday + timedelta(minutes=14))

    def test_outside_working_days_it_waits_for_the_next_working_morning(self):
        saturday = datetime(2026, 3, 7, 12, 0, tzinfo=timezone.utc)
        first, _ = self.plan(saturday)
        self.assertEqual(first.earliest_at, datetime(2026, 3, 9, 9, 0, tzinfo=timezone.utc))  # Monday 09:00

    def test_after_hours_it_waits_for_the_next_morning(self):
        evening = datetime(2026, 3, 4, 18, 0, tzinfo=timezone.utc)
        first, _ = self.plan(evening)
        self.assertEqual(first.earliest_at, datetime(2026, 3, 5, 9, 0, tzinfo=timezone.utc))

    def test_a_wait_step_pushes_the_first_action_out(self):
        wednesday = datetime(2026, 3, 4, 10, 0, tzinfo=timezone.utc)
        first, _ = self.plan(wednesday, steps=[{"type": "wait", "delay_hours": 48}, {"type": "connection_request", "message": "Hi"}, {"type": "end"}])
        self.assertEqual(first.earliest_at, datetime(2026, 3, 6, 10, 0, tzinfo=timezone.utc))  # Friday

    def test_the_lead_timezone_decides_the_working_window(self):
        wednesday = datetime(2026, 3, 4, 10, 0, tzinfo=timezone.utc)  # 19:00 in Tokyo, outside 09:00-17:00 there
        tokyo, plain = self.plan(wednesday, leads=[{"user": "tokyo", "timezone": "Asia/Tokyo"}, "plain"])
        self.assertEqual(tokyo.earliest_at, datetime(2026, 3, 5, 0, 0, tzinfo=timezone.utc))  # 09:00 Thursday in Tokyo
        self.assertEqual(plain.earliest_at, wednesday)  # the Tokyo lead waits for tomorrow, so it does not delay this one

    def test_the_campaign_timezone_decides_the_window_for_leads_without_one(self):
        wednesday = datetime(2026, 3, 4, 10, 0, tzinfo=timezone.utc)  # 11:00 in Amsterdam, inside
        late = datetime(2026, 3, 4, 16, 30, tzinfo=timezone.utc)      # 17:30 in Amsterdam, outside
        inside, = self.plan(wednesday, leads=["ann"], timezone="Europe/Amsterdam")
        outside, = self.plan(late, leads=["ann"], timezone="Europe/Amsterdam")
        self.assertEqual(inside.earliest_at, wednesday)
        self.assertEqual(outside.earliest_at, datetime(2026, 3, 5, 8, 0, tzinfo=timezone.utc))  # 09:00 Thursday in Amsterdam

    def test_an_account_out_of_capacity_today_is_planned_for_its_next_working_morning(self):
        # What the engine does with it; DryRunMatchesWorkerTest runs the worker to prove it.
        wednesday = datetime(2026, 3, 4, 10, 0, tzinfo=timezone.utc)
        plan = self.plan(wednesday, leads=["a1", "a2", "a3"], account_id=self.make_account(daily_limit=2))
        self.assertEqual([a.skip_reason for a in plan], [None, None, None])
        self.assertEqual(plan[2].earliest_at, datetime(2026, 3, 5, 9, 0, tzinfo=timezone.utc))


class DryRunMatchesWorkerTest(OutreachCase):
    """The dry run is a promise. Run the real engine and worker on a controlled clock and hold them to it:
    the same leads, accounts, steps and order, and nothing done earlier than its planned time."""

    def check(self, account_ids, leads, expected_count, seed=None, **fields):
        now = datetime.now(timezone.utc)
        start = (now + timedelta(days=(2 - now.weekday()) % 7 or 7)).replace(hour=10, minute=0, second=0, microsecond=0)  # a Wednesday, 10:00 UTC
        clock = {"now": start}
        # The clock is controlled, and so is the pacing jitter: pinned to its fastest end, the case the plan describes
        # exactly. (At any slower jitter actions only happen later, never earlier.)
        patches = [patch.object(engine, "_now", lambda: clock["now"]), patch.object(engine, "_action_gap", REAL_ACTION_GAP),
                   patch.object(engine.random, "uniform", lambda low, high: low)]
        [p.start() for p in patches]
        self.addCleanup(lambda: [p.stop() for p in patches])

        campaign_id = self.make_campaign(leads, [{"type": "connection_request", "message": "Hi {{first_name}}"}, {"type": "end"}], account_ids,
                                         launch=True, **{"start_hour": 9, "end_hour": 17, "working_days": [1, 2, 3, 4, 5], **fields})
        if seed:
            seed(start)
        with SessionLocal() as db:
            planned = [a for a in planner.plan_campaign(db, db.get(models.Campaign, campaign_id), start) if a.skip_reason is None]
        self.assertEqual(len(planned), expected_count)

        executed: list[tuple[str, str, str, datetime]] = []   # (lead, account id, step id, clock when it was done)
        seen: set[str] = set()
        for _ in range(500):
            self.worker.run_once(wait=True)
            with SessionLocal() as db:
                for task in db.query(models.AgentTask).filter_by(status="done", type="send_invite").filter(
                        models.AgentTask.sequence_run_id.isnot(None)).order_by(models.AgentTask.created_at):
                    if task.id not in seen:
                        seen.add(task.id)
                        run = db.get(models.SequenceRun, task.sequence_run_id)
                        executed.append((db.get(models.Lead, run.lead_id).first_name, task.account_id,
                                         (task.idempotency_key or "").rsplit(":", 1)[-1], clock["now"]))
            if len(seen) == len(planned):
                break
            # Move the clock straight to the next moment the engine has anything due (never past it).
            with SessionLocal() as db:
                queued = db.query(models.AgentTask).filter(models.AgentTask.status.in_(["pending", "running"])).count()
                due = [engine._aware(r.next_action_at) for r in db.query(models.SequenceRun).filter(
                    models.SequenceRun.status.in_(["running", "waiting_connection"])) if r.next_action_at]
            later = [t for t in due if t > clock["now"]]
            if not queued:
                clock["now"] = min(later) if later else clock["now"] + timedelta(seconds=60)
        self.assertEqual(len(executed), len(planned), "the worker did not finish what the dry run listed")

        report = (f"planned: {[(a.lead_name, a.account_name, a.earliest_at.isoformat()) for a in planned]}  "
                  f"executed: {[(e[0], e[1][:6], e[3].isoformat()) for e in executed]}")
        first = lambda action: action.lead_name.split()[0]
        # The same leads, accounts and steps.
        self.assertEqual({lead: (account, step) for lead, account, step, _ in executed},
                         {first(a): (a.account_id, a.step_id) for a in planned}, report)
        # Never earlier than planned.
        for lead, _, _, at in executed:
            plan = next(a for a in planned if first(a) == lead)
            self.assertGreaterEqual(at, plan.earliest_at, f"{lead} was done at {at}, before its planned {plan.earliest_at}. {report}")
        # The same order.
        self.assertEqual([lead for lead, *_ in executed], [first(a) for a in sorted(planned, key=lambda a: a.earliest_at)], report)
        return planned, executed

    def test_two_accounts_a_lead_in_another_timezone_and_the_next_day(self):
        leads = [{"user": "ann"}, {"user": "tokyo", "timezone": "Asia/Tokyo"}, {"user": "bob"}, {"user": "cy"}, {"user": "dee"}]
        self.check([self.make_account("first"), self.make_account("second")], leads, 5)

    def test_a_lead_past_the_daily_limit_is_planned_and_done_on_the_accounts_next_day(self):
        planned, executed = self.check([self.make_account(daily_limit=2)], ["a1", "a2", "a3"], 3)
        self.assertEqual(planned[2].earliest_at.date(), planned[0].earliest_at.date() + timedelta(days=1))
        self.assertEqual(planned[2].earliest_at.hour, 9)  # the account's next day, once working hours open

    def test_a_campaign_connection_limit_pushes_the_rest_to_the_next_day(self):
        planned, _ = self.check([self.make_account()], ["a1", "a2", "a3"], 3, daily_connection_limit=2)
        self.assertEqual(planned[2].earliest_at.date(), planned[0].earliest_at.date() + timedelta(days=1))

    def test_the_hard_ceiling_counts_other_campaigns_and_moves_the_rest_to_the_next_day(self):
        account_id = self.make_account(daily_limit=200)

        def seed(start):  # 38 invites already sent today by another campaign: 2 left under the 40/day ceiling
            with SessionLocal() as db:
                for n in range(38):
                    db.add(models.AgentTask(account_id=account_id, type="send_invite", status="done", idempotency_key=f"other-{n}",
                                            created_at=start - timedelta(minutes=30 + n)))
                db.commit()

        planned, _ = self.check([account_id], ["a1", "a2", "a3"], 3, seed=seed, daily_connection_limit=40)
        self.assertEqual(planned[2].earliest_at.date(), planned[0].earliest_at.date() + timedelta(days=1))

    def test_a_limit_of_zero_plans_nothing_and_the_worker_sends_nothing(self):
        for account_limit, campaign_limit in ((0, 20), (50, 0)):
            with self.subTest(account_limit=account_limit, campaign_limit=campaign_limit):
                MOCK.reset()
                start = datetime.now(timezone.utc).replace(hour=10, minute=0, second=0, microsecond=0)
                clock = {"now": start}
                with patch.object(engine, "_now", lambda: clock["now"]):
                    account_id = self.make_account(f"zero-{account_limit}", daily_limit=account_limit)
                    campaign_id = self.make_campaign([f"z{account_limit}a", f"z{account_limit}b"], INVITE_ONLY, [account_id],
                                                     daily_connection_limit=campaign_limit)
                    with SessionLocal() as db:
                        plan = planner.plan_campaign(db, db.get(models.Campaign, campaign_id), start)
                    self.assertEqual([a.task_type for a in plan], [None, None])
                    for action in plan:
                        self.assertTrue(action.skip_reason.startswith("Paused for this action"), action.skip_reason)
                    for _ in range(4):  # three days of the worker running
                        self.worker.run_once(wait=True)
                        clock["now"] += timedelta(hours=20)
                    self.assertEqual(MOCK.invites, [])
                    with SessionLocal() as db:
                        self.assertEqual(db.query(models.AgentTask).filter_by(account_id=account_id, type="send_invite").count(), 0)


class LeaseTest(OutreachCase):
    def acquire(self, account_id, holder, now):
        with SessionLocal() as db:
            return results.acquire_lease(db, account_id, holder, now)

    def test_exactly_one_of_many_simultaneous_holders_wins(self):
        account_id = self.make_account()
        now, outcomes, barrier = datetime.now(timezone.utc), [], threading.Barrier(8)

        def go(n):
            barrier.wait()
            outcomes.append((n, self.acquire(account_id, f"worker-{n}", now)))

        threads = [threading.Thread(target=go, args=(n,)) for n in range(8)]
        [t.start() for t in threads]
        [t.join() for t in threads]
        winners = [n for n, won in outcomes if won]
        self.assertEqual(len(winners), 1)
        with SessionLocal() as db:
            self.assertEqual(db.get(models.AccountLease, account_id).holder, f"worker-{winners[0]}")

    def test_the_holder_renews_others_wait_and_an_expired_lease_can_be_taken(self):
        account_id = self.make_account()
        now = datetime.now(timezone.utc)
        self.assertTrue(self.acquire(account_id, "a", now))
        self.assertTrue(self.acquire(account_id, "a", now + timedelta(seconds=10)))   # renewal
        self.assertFalse(self.acquire(account_id, "b", now + timedelta(seconds=20)))  # still held
        late = now + timedelta(seconds=10 + settings.outreach_lease_seconds + 1)
        self.assertTrue(self.acquire(account_id, "b", late))                           # holder died: it expired
        self.assertFalse(self.acquire(account_id, "a", late + timedelta(seconds=1)))

    def test_only_the_holder_can_release(self):
        account_id = self.make_account()
        now = datetime.now(timezone.utc)
        self.acquire(account_id, "a", now)
        with SessionLocal() as db:
            results.release_lease(db, account_id, "b")
        self.assertFalse(self.acquire(account_id, "b", now + timedelta(seconds=1)))
        with SessionLocal() as db:
            results.release_lease(db, account_id, "a")
        self.assertTrue(self.acquire(account_id, "b", now + timedelta(seconds=2)))

    def test_a_task_cannot_be_claimed_without_the_lease(self):
        account_id = self.make_account()
        self.make_campaign(["ann"], [{"type": "connection_request", "message": "Hi"}, {"type": "end"}], [account_id])
        self.tick()
        now = datetime.now(timezone.utc)
        with SessionLocal() as db:
            self.assertIsNotNone(results.claim_next_task(db, account_id, "holder", now))  # takes the lease, then claims
        self.make_campaign(["bob"], [{"type": "connection_request", "message": "Hi"}, {"type": "end"}], [account_id])
        self.tick()
        with SessionLocal() as db:
            self.assertIsNone(results.claim_next_task(db, account_id, "someone-else", now))

    def test_a_worker_without_the_lease_opens_no_browser(self):
        account_id = self.make_account()
        self.make_campaign(["ann"], [{"type": "connection_request", "message": "Hi"}, {"type": "end"}], [account_id])
        self.tick()
        self.acquire(account_id, "another-worker", datetime.now(timezone.utc))
        self.assertFalse(self.worker._start_batch(account_id))
        self.assertEqual(self.manager.open_browsers, 0)
        outcome = self.worker.run_once(wait=True)
        self.assertEqual((outcome["started"], MOCK.invites), ([], []))

    def test_a_finished_batch_releases_the_lease(self):
        account_id = self.make_account()
        self.make_campaign(["ann"], [{"type": "connection_request", "message": "Hi"}, {"type": "end"}], [account_id])
        self.worker.run_once(wait=True)
        self.assertEqual(MOCK.invites, [("ann", "Hi")])
        with SessionLocal() as db:
            self.assertIsNone(db.get(models.AccountLease, account_id))


# ===================================================================== zero means stopped; hard ceilings

class ZeroAndCeilingTest(OutreachCase):
    """A limit of 0 stops that action. The hard ceilings in config hold whatever a setting, a campaign or the API says."""

    def outreach_tasks(self):
        return [t for t in self.tasks() if t.type != "sync_inbox"]

    def conversation_on(self, account_id):
        with SessionLocal() as db:
            lead = models.Lead(user_id=self.user_id, first_name="Ann", last_name="Test", status="connected", linkedin_url=MOCK.profile_url("ann"))
            db.add(lead)
            db.flush()
            convo = models.Conversation(user_id=self.user_id, lead_id=lead.id, account_id=account_id, status="active")
            db.add(convo)
            db.commit()
            return convo.id

    def test_an_account_limit_of_zero_sends_nothing(self):
        account_id = self.make_account(daily_limit=0)
        self.make_campaign(["a1", "a2"], INVITE_ONLY, [account_id])
        self.make_campaign(["v1"], [{"type": "profile_visit"}, {"type": "end"}], [account_id])
        for _ in range(3):
            self.worker.run_once(wait=True)
        self.assertEqual((self.outreach_tasks(), MOCK.invites), ([], []))
        self.assertEqual(engine.effective_daily_limit(self.account_row(account_id), datetime.now(timezone.utc)), 0)

    def test_a_campaign_limit_of_zero_stops_only_that_action(self):
        account_id = self.make_account()
        self.make_campaign(["a1", "a2"], INVITE_ONLY, [account_id], daily_connection_limit=0)
        self.make_campaign([{"user": "m1", "status": "connected"}], [{"type": "message", "message": "Hello"}, {"type": "end"}],
                           [account_id], daily_message_limit=0)
        self.make_campaign(["v1"], [{"type": "profile_visit"}, {"type": "end"}], [account_id])
        for _ in range(3):
            self.tick()
        self.assertEqual(sorted(t.type for t in self.outreach_tasks()), ["visit_profile"])

    def test_the_daily_ceilings_hold_across_several_campaigns_on_one_account(self):
        cases = [  # task type, step, ceiling, lead status, campaign fields (the campaign limit as high as it may go, or unset)
            ("send_invite", {"type": "connection_request", "message": "Hi"}, 40, "new", {"daily_connection_limit": 40}),
            ("send_invite", {"type": "connection_request", "message": "Hi"}, 40, "new", {"daily_connection_limit": None}),
            ("send_message", {"type": "message", "message": "Hello"}, 100, "connected", {"daily_message_limit": 100}),
            ("visit_profile", {"type": "profile_visit"}, 80, "new", {}),
            ("follow_profile", {"type": "follow"}, 50, "new", {}),
        ]
        for index, (ttype, step, ceiling, status, fields) in enumerate(cases):
            with self.subTest(ttype=ttype, fields=fields):
                account_id = self.make_account(f"ceiling-{index}", daily_limit=200)
                per_campaign = ceiling * 3 // 4  # two campaigns together ask for one and a half times the ceiling
                for c in range(2):
                    leads = [{"user": f"c{index}x{c}x{n}", "status": status} for n in range(per_campaign)]
                    campaign_id = self.make_campaign(leads, [step, {"type": "end"}], [account_id])
                    with SessionLocal() as db:  # set after creation, so an unset (NULL) limit is stored as NULL, not the default
                        campaign = db.get(models.Campaign, campaign_id)
                        for name, value in fields.items():
                            setattr(campaign, name, value)
                        db.commit()
                        self.assertEqual({name: getattr(campaign, name) for name in fields}, fields)
                for _ in range(3):
                    self.tick()
                with SessionLocal() as db:
                    queued = db.query(models.AgentTask).filter_by(account_id=account_id, type=ttype).count()
                self.assertEqual(queued, ceiling)

    def test_the_weekly_invite_ceiling_holds_even_when_the_setting_is_higher(self):
        account_id = self.make_account(daily_limit=200)
        now = datetime.now(timezone.utc)
        with patch.object(settings, "outreach_weekly_connection_limit", 1000):
            with SessionLocal() as db:
                for n in range(150):
                    db.add(models.AgentTask(account_id=account_id, type="send_invite", status="done", idempotency_key=f"week-{n}",
                                            created_at=now - timedelta(days=2 + n % 4, minutes=n)))
                db.commit()
            self.make_campaign(["w1"], INVITE_ONLY, [account_id])
            for _ in range(2):
                self.tick()
        self.assertEqual(len(self.tasks("send_invite")), 150)

    def test_a_reply_from_a_stopped_account_is_refused(self):
        convo_id = self.conversation_on(self.make_account(daily_limit=0))
        r = self.client.post("/conversations", json={"action": "reply", "conversationId": convo_id, "body": "Hello"})
        self.assertEqual(r.status_code, 409, r.text)
        self.assertIn("paused", r.json()["detail"])
        self.assertEqual(self.tasks("send_message"), [])

    def test_a_reply_past_the_message_ceiling_is_refused(self):
        account_id = self.make_account(daily_limit=200)
        with SessionLocal() as db:
            for n in range(100):
                db.add(models.AgentTask(account_id=account_id, type="send_message", status="done", idempotency_key=f"msg-{n}"))
            db.commit()
        convo_id = self.conversation_on(account_id)
        r = self.client.post("/conversations", json={"action": "reply", "conversationId": convo_id, "body": "Hello"})
        self.assertEqual(r.status_code, 409, r.text)
        self.assertIn("100", r.json()["detail"])
        self.assertEqual(len(self.tasks("send_message")), 100)


class LimitApiTest(OutreachCase):
    def create(self, **fields):
        return self.client.post("/campaigns", json={"action": "create", "name": "Limits", **fields})

    def test_over_ceiling_campaign_limits_are_rejected_naming_the_ceiling(self):
        for field, value, ceiling in (("dailyConnectionLimit", 41, "40"), ("dailyMessageLimit", 101, "100")):
            r = self.create(**{field: value})
            self.assertEqual(r.status_code, 422, field)
            self.assertIn(ceiling, json.dumps(r.json()), field)
        self.assertEqual(self.create(dailyConnectionLimit=-1).status_code, 422)
        campaign = self.create(dailyConnectionLimit=0, dailyMessageLimit=0).json()
        self.assertEqual((campaign["dailyConnectionLimit"], campaign["dailyMessageLimit"]), (0, 0))  # kept, not replaced by a default
        update = lambda **f: self.client.post("/campaigns", json={"action": "update", "id": campaign["id"], **f})
        r = update(dailyConnectionLimit=41)
        self.assertEqual(r.status_code, 422)
        self.assertIn("40", json.dumps(r.json()))
        self.assertEqual(update(dailyConnectionLimit=40).json()["dailyConnectionLimit"], 40)
        self.assertEqual(update(dailyConnectionLimit=0).json()["dailyConnectionLimit"], 0)

    def test_the_migration_lowers_over_ceiling_limits_logs_them_and_keeps_zero(self):
        over = self.make_account("over", daily_limit=500)
        zero = self.make_account("zero", daily_limit=0)
        loud = self.make_campaign(["m1"], INVITE_ONLY, [over], launch=False, daily_connection_limit=90, daily_message_limit=0)
        quiet = self.make_campaign(["m2"], INVITE_ONLY, [zero], launch=False, daily_connection_limit=0, daily_message_limit=300)
        with SessionLocal() as db:
            db.query(Migration).filter_by(version="007_limit_ceilings").delete()
            db.commit()
        with self.assertLogs("app.migrations", "WARNING") as logs:
            migrate()
        with SessionLocal() as db:
            self.assertEqual((db.get(models.LinkedInAccount, over).daily_action_limit, db.get(models.LinkedInAccount, zero).daily_action_limit), (200, 0))
            first, second = db.get(models.Campaign, loud), db.get(models.Campaign, quiet)
            self.assertEqual((first.daily_connection_limit, first.daily_message_limit), (40, 0))
            self.assertEqual((second.daily_connection_limit, second.daily_message_limit), (0, 100))
        self.assertEqual(len(logs.output), 3, logs.output)
        self.assertTrue(any("90" in line and "40" in line for line in logs.output), logs.output)
        with self.assertNoLogs("app.migrations", "WARNING"):
            migrate()  # runs once only


if __name__ == "__main__":
    unittest.main()
