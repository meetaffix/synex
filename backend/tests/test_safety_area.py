"""Area 11, the safety controls that are not tested elsewhere: the daily total, ramp-up, random gaps, the test profile, the audit log and secrets in logs."""
import io
import logging
import unittest
from datetime import datetime, timedelta, timezone

from test_outreach import INVITE_ONLY, MOCK, OutreachCase, SessionLocal, session_state  # noqa: E402  (sets the isolated environment)
from app import account_policy, engine, models
from app.config import DAILY_ACTION_CEILING, DAILY_TYPE_CEILINGS, WEEKLY_INVITE_CEILING

REAL_GAP = engine._action_gap  # OutreachCase replaces it with a zero gap so tests run fast; this test needs the real one


class CeilingTest(OutreachCase):
    def test_the_daily_total_is_held_at_200_whatever_the_account_says(self):
        account_id = self.make_account(daily_limit=5000)
        with SessionLocal() as db:
            account = db.get(models.LinkedInAccount, account_id)
            self.assertEqual(engine.configured_daily_limit(account), DAILY_ACTION_CEILING)
            self.assertEqual(DAILY_ACTION_CEILING, 200)
            for days_ago in (0, 3, 400):
                account.warmup_started_at = datetime.now(timezone.utc) - timedelta(days=days_ago)
                self.assertLessEqual(engine.effective_daily_limit(account, datetime.now(timezone.utc)), 200)

    def test_a_policy_above_any_ceiling_is_refused_by_the_api(self):
        account_id = self.make_account()
        too_high = {action: {"dailyLimit": 1, "increaseBy": 0, "stopAt": ceiling + 1, "intervalDays": 7, "dynamicInterval": False} for action, ceiling in DAILY_TYPE_CEILINGS.items()}
        for action in DAILY_TYPE_CEILINGS:
            r = self.client.put(f"/linkedin-accounts/{account_id}/policy", json={"preset": "custom", "range": 1, "actions": {action: too_high[action]}, "autoWithdraw": False, "staleInviteDays": 30, "inboxHistoryDays": 90})
            self.assertEqual(r.status_code, 422, action)

    def test_ramp_up_never_goes_above_a_ceiling_on_any_day_for_any_action(self):
        account_id = self.make_account()
        with SessionLocal() as db:
            account = db.get(models.LinkedInAccount, account_id)
            account.management_config = {"policy": {"preset": "custom", "range": 3, "autoWithdraw": False, "staleInviteDays": 30, "inboxHistoryDays": 90, "actions": {
                action: {"dailyLimit": 1, "increaseBy": 10, "stopAt": ceiling, "intervalDays": 1, "dynamicInterval": False} for action, ceiling in DAILY_TYPE_CEILINGS.items()}}}
            start = datetime.now(timezone.utc)
            for day in range(0, 400, 7):
                moment = start + timedelta(days=day)
                for action, ceiling in DAILY_TYPE_CEILINGS.items():
                    low, high, budget = account_policy.bounds(account, action, moment)
                    self.assertLessEqual(max(low, high, budget), ceiling, (action, day))
        self.assertEqual(WEEKLY_INVITE_CEILING, 150)

    def test_ramp_up_starts_low_and_a_stopped_action_never_restarts(self):
        account_id = self.make_account()
        with SessionLocal() as db:
            account = db.get(models.LinkedInAccount, account_id)
            account.management_config = {"policy": {"preset": "custom", "range": 1, "autoWithdraw": False, "staleInviteDays": 30, "inboxHistoryDays": 90, "actions": {
                "send_invite": {"dailyLimit": 5, "increaseBy": 5, "stopAt": 25, "intervalDays": 1, "dynamicInterval": False},
                "send_message": {"dailyLimit": 0, "increaseBy": 10, "stopAt": 40, "intervalDays": 1, "dynamicInterval": False}}}}
            account.warmup_started_at = datetime.now(timezone.utc)
            now = datetime.now(timezone.utc)
            self.assertLessEqual(account_policy.bounds(account, "send_invite", now)[2], 6)  # day one: about the start value
            self.assertEqual(account_policy.bounds(account, "send_message", now + timedelta(days=60))[2], 0)  # 0 stays 0, however long it ramps


class TestProfileTest(OutreachCase):
    def test_the_test_profile_is_five_visits_five_requests_five_messages_and_stops_everything_else(self):
        profile = account_policy.test_profile_actions()
        self.assertEqual(set(profile), set(DAILY_TYPE_CEILINGS))
        self.assertEqual({a: p["dailyLimit"] for a, p in profile.items() if p["dailyLimit"]}, {"visit_profile": 5, "send_invite": 5, "send_message": 5, "check_connection": 5, "sync_inbox": 12})
        for action in ("follow_profile", "like_post", "send_inmail", "send_voice_note", "withdraw_invite", "collect_leads", "sync_connections"):
            self.assertEqual((profile[action]["dailyLimit"], profile[action]["stopAt"]), (0, 0), action)

    def test_applying_it_holds_every_action_at_its_number_on_every_day(self):
        account_id = self.make_account()
        applied = self.client.put(f"/linkedin-accounts/{account_id}/policy", json={"preset": "custom", "range": 1, "actions": account_policy.test_profile_actions(),
                                                                                  "autoWithdraw": False, "staleInviteDays": 30, "inboxHistoryDays": 90})
        self.assertEqual(applied.status_code, 200, applied.text)
        with SessionLocal() as db:
            account = db.get(models.LinkedInAccount, account_id)
            for day in range(0, 120, 9):
                moment = datetime.now(timezone.utc) + timedelta(days=day)
                self.assertLessEqual(account_policy.bounds(account, "visit_profile", moment)[1], 5)
                self.assertLessEqual(account_policy.bounds(account, "send_invite", moment)[1], 5)
                self.assertLessEqual(account_policy.bounds(account, "send_message", moment)[1], 5)
                self.assertEqual(account_policy.bounds(account, "like_post", moment)[2], 0)

    def test_the_ceilings_endpoint_tells_the_whole_truth(self):
        info = self.client.get("/outreach/ceilings").json()
        self.assertEqual((info["dailyTotal"], info["weeklyInvites"], info["newAccountDailyLimit"]), (200, 150, 0))
        self.assertEqual({row["action"]: row["ceiling"] for row in info["daily"]}, DAILY_TYPE_CEILINGS)
        self.assertEqual(info["testProfile"]["send_invite"], 5)
        self.assertTrue(all(row["label"] for row in info["daily"]))


class GapTest(OutreachCase):
    def test_gaps_between_actions_are_random_and_never_a_burst(self):
        account_id = self.make_account()
        campaign_id = self.make_campaign(["ann"], INVITE_ONLY, accounts=[account_id], launch=False)
        with SessionLocal() as db:
            campaign, account = db.get(models.Campaign, campaign_id), db.get(models.LinkedInAccount, account_id)
            now = datetime.now(timezone.utc).replace(hour=10, minute=0, second=0, microsecond=0)
            base = engine.pacing_base(campaign, now, None, engine.remaining_capacity(account, now))
            gaps = [REAL_GAP(campaign, account, now, None).total_seconds() for _ in range(60)]
        self.assertGreater(len({round(g, 3) for g in gaps}), 30, "the gaps repeat: they are not random")
        self.assertGreaterEqual(min(gaps), base * engine.GAP_JITTER[0] - 0.01)
        self.assertLessEqual(max(gaps), base * engine.GAP_JITTER[1] + 0.01)
        self.assertGreaterEqual(min(gaps), 30)  # never a burst: the floor is about half a minute


class AuditTest(OutreachCase):
    def test_every_action_is_in_the_audit_log_with_account_person_campaign_and_the_reason(self):
        account_id = self.make_account("Ada")
        self.make_campaign(["ann", "bob"], INVITE_ONLY, accounts=[account_id])
        MOCK.profile("bob")["available"] = False
        for _ in range(8):
            self.tick()
            self.worker.run_once(wait=True)
        log = self.client.get("/outreach/audit").json()
        by_person = {(i["person"], i["action"]): i for i in log["items"] if i["person"]}
        sent = by_person[("Ann Test", "send_invite")]
        self.assertEqual((sent["result"], sent["reason"], sent["account"], sent["campaign"], sent["status"]), ("sent", "Done.", "Ada", "Campaign", "ok"))
        skipped = by_person[("Bob Test", "send_invite")]
        self.assertEqual(skipped["result"], "profile_unavailable")
        self.assertIn("could not be opened", skipped["reason"])
        with SessionLocal() as db:
            done = db.query(models.AgentTask).filter(models.AgentTask.status == "done", models.AgentTask.type == "send_invite").count()
            self.assertEqual(done + db.query(models.AgentTask).filter(models.AgentTask.type == "send_invite", models.AgentTask.status != "done").count(), 2)
        self.assertEqual(log["total"], len([i for i in log["items"]]))
        self.assertEqual(self.client.get(f"/outreach/audit?accountId={account_id}&limit=1").json()["limit"], 1)
        self.assertEqual(self.client.get("/outreach/audit?accountId=nope").json()["items"], [])

    def test_the_audit_log_never_shows_another_workspaces_actions(self):
        with SessionLocal() as db:
            other = models.User(email="other@example.com", full_name="Other", hashed_password="x")
            db.add(other)
            db.flush()
            account = models.LinkedInAccount(user_id=other.id, name="Theirs", status="active", session_status="connected")
            db.add(account)
            db.flush()
            db.add(models.AgentActivity(account_id=account.id, user_id=other.id, scope="task", step="send_invite", status="ok", message="x", result="sent"))
            db.commit()
        self.assertEqual(self.client.get("/outreach/audit").json()["items"], [])


class SecretsTest(OutreachCase):
    def test_a_session_cookie_and_stored_secrets_never_reach_the_logs_while_actions_run(self):
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        root = logging.getLogger()
        previous = root.level
        root.addHandler(handler)
        root.setLevel(logging.DEBUG)
        self.addCleanup(lambda: (root.removeHandler(handler), root.setLevel(previous)))
        sentinel = "SENTINEL-cookie-value-1f9a"
        account_id = self.make_account(session_user=sentinel)
        self.make_campaign(["ann"], INVITE_ONLY, accounts=[account_id])
        MOCK.fault = None
        for _ in range(6):
            self.tick()
            self.worker.run_once(wait=True)
        text = stream.getvalue()
        self.assertNotIn(sentinel, text)
        self.assertNotIn(str(session_state(sentinel)["cookies"][0]["value"]) + "SECRET", text)
        for secret in ("li_at", "Sup3r", "password="):
            self.assertNotIn(secret, text)


if __name__ == "__main__":
    unittest.main()
