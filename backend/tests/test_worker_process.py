"""The outreach worker as a real operating-system process: `python -m app.outreach_worker` against a
temporary database and the local mock site, started, signalled and killed the way a deployment would.

Needs psutil (see requirements-dev.txt) to see which browser processes a worker left behind.
"""
import os
import re
import signal
import subprocess
import sys
import threading
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import psutil

from test_outreach import INVITE_ONLY, MOCK, OutreachCase  # noqa: E402  (sets the isolated environment and imports the app)
from app import models  # noqa: E402
from app.config import settings  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.linkedin_session import store  # noqa: E402
from app.publishing_models import WorkerHeartbeat  # noqa: E402
import safety  # noqa: E402

BACKEND = Path(__file__).resolve().parent.parent
TESTS = Path(__file__).resolve().parent
WINDOWS = sys.platform == "win32"
LOG_TIME = re.compile(r"^(\d\d):(\d\d):(\d\d)\.(\d{3}) ")


class WorkerProcess:
    """A worker subprocess whose output is collected on a thread so its pipe never fills."""

    def __init__(self, **overrides: str) -> None:
        safety.assert_isolated_database(settings.database_url)
        env = {
            **os.environ,
            "DATABASE_URL": settings.database_url,  # the test's temporary database, never synex.db
            "SECRET_KEY": os.environ["SECRET_KEY"],
            "AUTH_PROVIDER": "local",
            "DEEPGRAM_API_KEY": "dg-SENTINEL-never-leak-9f3a7c",  # the built-in sign-in, whatever backend/.env says
            "ENCRYPTION_KEY": os.environ["ENCRYPTION_KEY"],
            "OUTREACH_PAGES_FACTORY": "mock_linkedin:pages_from_env",
            "MOCK_LINKEDIN_URL": MOCK.base_url,
            "PYTHONPATH": os.pathsep.join([str(BACKEND), str(TESTS)]),
            "PYTHONUNBUFFERED": "1",
            "OUTREACH_TICK_INTERVAL_SECONDS": "1",
            "OUTREACH_ACTION_GAP_MIN_SECONDS": "0",
            "OUTREACH_ACTION_GAP_MAX_SECONDS": "0",
            "OUTREACH_INBOX_SYNC_INTERVAL_MINUTES": "100000",
            "OUTREACH_ACCEPTANCE_CHECK_INTERVAL_HOURS": "100000",
            "LINKEDIN_SESSION_POLL_INTERVAL_SECONDS": "0.1",
            "LINKEDIN_SESSION_MAX_BROWSERS": "2",
            **overrides,
        }
        self.proc = subprocess.Popen(
            [sys.executable, "-m", "app.outreach_worker"], cwd=str(BACKEND), env=env, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, text=True, creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if WINDOWS else 0)
        self.lines: list[str] = []
        self._reader = threading.Thread(target=self._read, daemon=True)
        self._reader.start()

    def _read(self) -> None:
        for line in self.proc.stdout:
            self.lines.append(line.rstrip("\n"))

    @property
    def output(self) -> str:
        return "\n".join(self.lines)

    @property
    def worker_id(self) -> str:
        match = re.search(r"outreach worker ([0-9a-f]{32}) started", self.output)
        return match.group(1) if match else ""

    def browser_pids(self) -> list[int]:
        try:
            return [child.pid for child in psutil.Process(self.proc.pid).children(recursive=True)]
        except psutil.NoSuchProcess:
            return []

    def stop(self, timeout: float = 40) -> int:
        """Ask the worker to stop the way the platform does: CTRL+BREAK to its console group on Windows, SIGTERM elsewhere."""
        if self.proc.poll() is None:
            self.proc.send_signal(signal.CTRL_BREAK_EVENT if WINDOWS else signal.SIGTERM)
        code = self.proc.wait(timeout=timeout)
        self._reader.join(timeout=5)
        return code

    def kill(self) -> None:
        """Hard stop, with no chance to clean up: TerminateProcess on Windows, SIGKILL elsewhere."""
        for child in self.browser_pids():
            try:
                psutil.Process(child).kill()
            except psutil.NoSuchProcess:
                pass
        self.proc.kill()
        self.proc.wait(timeout=20)
        self._reader.join(timeout=5)

    def ensure_stopped(self) -> None:
        if self.proc.poll() is None:
            self.kill()


def seconds(line: str) -> float:
    h, m, s, ms = map(int, LOG_TIME.match(line).groups())
    return h * 3600 + m * 60 + s + ms / 1000


class WorkerProcessCase(OutreachCase):
    serial = True  # a concurrency test: run_tests.py runs it alone, never beside other tests
    def setUp(self):
        super().setUp()
        self.processes: list[WorkerProcess] = []
        self.addCleanup(lambda: [p.ensure_stopped() for p in self.processes])

    def start(self, **overrides) -> WorkerProcess:
        process = WorkerProcess(**overrides)
        self.processes.append(process)
        return process

    def wait_until(self, condition, timeout=90, what="condition"):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if condition():
                return
            time.sleep(0.25)
        self.fail(f"timed out waiting for {what}; worker output:\n" + "\n".join(p.output for p in self.processes)[-3000:])

    def task_rows(self, ttype="send_invite"):
        with SessionLocal() as db:
            return [(t.id, t.status, t.committed_at, t.claimed_by) for t in db.query(models.AgentTask).filter_by(type=ttype).order_by(models.AgentTask.created_at)]


class CleanShutdownTest(WorkerProcessCase):
    def test_a_real_worker_process_runs_one_task_saves_state_and_stops_cleanly(self):
        account_id = self.make_account()
        before = store.load_state(self.account_row(account_id))
        self.assertNotIn("li_seen", {c["name"] for c in before["cookies"]})
        self.make_campaign(["ann"], [{"type": "connection_request", "message": "Hi {{first_name}}"}, {"type": "end"}], [account_id], launch=True)

        worker = self.start()
        self.wait_until(lambda: [row for row in self.task_rows() if row[1] == "done"], what="the invitation task to finish")
        self.wait_until(lambda: "outreach lease released" in worker.output, 30, "the browser to close and the lease to be released")
        children = worker.browser_pids()

        code = worker.stop()
        output = worker.output

        self.assertEqual(code, 0, output[-2000:])
        # The task completed exactly once.
        self.assertEqual(MOCK.invites, [("ann", "Hi Ann")])
        self.assertEqual([row[1] for row in self.task_rows()], ["done"])
        # The browser closed.
        self.assertIn("linkedin browser closed (0 still open)", output)
        self.assertEqual([pid for pid in children if psutil.pid_exists(pid) and psutil.Process(pid).is_running()], [])
        self.assertEqual(worker.browser_pids(), [])
        # Storage state was saved back after the batch: the site set a cookie during the visit.
        self.assertIn("outreach session state saved", output)
        after = store.load_state(self.account_row(account_id))
        self.assertIn("li_seen", {c["name"] for c in after["cookies"]})
        # The lease was released, the worker said it stopped, nothing blew up.
        with SessionLocal() as db:
            self.assertIsNone(db.get(models.AccountLease, account_id))
        self.assertIn(f"outreach worker {worker.worker_id} stopped", output)
        self.assertNotIn("Traceback", output)
        # The heartbeat stopped with the process.
        with SessionLocal() as db:
            beat = db.get(WorkerHeartbeat, f"outreach-{worker.worker_id}")
            last = beat.checked_at
        time.sleep(3)
        with SessionLocal() as db:
            self.assertEqual(db.get(WorkerHeartbeat, f"outreach-{worker.worker_id}").checked_at, last)
        self.assertGreater(datetime.now(timezone.utc).replace(tzinfo=None) - last.replace(tzinfo=None), timedelta(seconds=2))

    def test_the_heartbeat_advances_while_the_worker_runs(self):
        worker = self.start()
        self.wait_until(lambda: worker.worker_id, 30, "the worker to start")

        def beat():
            with SessionLocal() as db:
                row = db.get(WorkerHeartbeat, f"outreach-{worker.worker_id}")
                return row.checked_at if row else None

        self.wait_until(lambda: beat() is not None, 30, "the first heartbeat")
        first = beat()
        self.wait_until(lambda: beat() > first, 20, "the heartbeat to advance")
        self.assertEqual(worker.stop(), 0)


class HardStopTest(WorkerProcessCase):
    def test_a_worker_killed_mid_action_leaves_the_task_for_review_and_it_is_never_resent(self):
        account_id = self.make_account()
        self.make_campaign(["ann"], [{"type": "connection_request", "message": "Hi {{first_name}}"}, {"type": "end"}], [account_id], launch=True)
        MOCK.commit_delay = 8  # the invitation is "being sent" for eight seconds

        first = self.start(OUTREACH_LEASE_SECONDS="3")
        self.wait_until(lambda: [row for row in self.task_rows() if row[1] == "running" and row[2] is not None], 60, "the invitation to be mid-action")
        first.kill()

        (task_id, status, committed, _), = self.task_rows()
        self.assertEqual(status, "running")
        self.assertIsNotNone(committed)  # the irreversible click had been reached

        # A replacement worker finds the abandoned task, takes over the account, and does not send again.
        MOCK.commit_delay = 0
        second = self.start(OUTREACH_STALE_TASK_SECONDS="1", OUTREACH_LEASE_SECONDS="3")
        self.wait_until(lambda: [row for row in self.task_rows() if row[1] == "needs_review"], 60, "the abandoned task to need review")
        time.sleep(6)  # give a mistaken retry every chance to happen
        self.assertEqual(second.stop(), 0, second.output[-2000:])

        self.assertEqual([row[1] for row in self.task_rows()], ["needs_review"])
        with SessionLocal() as db:
            run = db.query(models.SequenceRun).one()
            self.assertEqual(run.status, "needs_review")
        self.assertLessEqual(len(MOCK.invites), 1)  # never a second send
        self.assertEqual(len(self.task_rows()), 1)


class TwoWorkersTest(WorkerProcessCase):
    def test_two_worker_processes_never_share_an_account_and_never_send_twice(self):
        account_id = self.make_account()
        names = ["ann", "bob", "cy", "dee", "eli", "fay"]
        self.make_campaign(names, [{"type": "connection_request", "message": "Hi {{first_name}}"}, {"type": "end"}], [account_id], launch=True)
        self.tick()
        self.assertEqual(len(self.task_rows()), 6)

        env = dict(OUTREACH_BATCH_MAX_ACTIONS="2", OUTREACH_ACTION_GAP_MIN_SECONDS="0.4", OUTREACH_ACTION_GAP_MAX_SECONDS="0.4",
                   OUTREACH_LEASE_SECONDS="30")
        one, two = self.start(**env), self.start(**env)
        self.wait_until(lambda: all(row[1] == "done" for row in self.task_rows()), 120, "all six invitations to finish")
        for worker in (one, two):
            self.assertEqual(worker.stop(), 0, worker.output[-2000:])

        # Every lead was invited exactly once.
        self.assertEqual(sorted(user for user, _ in MOCK.invites), sorted(names))
        self.assertEqual(len(self.task_rows()), 6)
        # Each task was claimed by exactly one of the two workers.
        claimed_by = {row[3] for row in self.task_rows()}
        self.assertTrue(claimed_by <= {one.worker_id, two.worker_id})

        # Leases never overlapped: from "acquired" to "released" (after the browser closed), one holder at a time.
        spans = []
        for worker in (one, two):
            opened = None
            for line in worker.lines:
                if "outreach lease acquired" in line:
                    opened = seconds(line)
                elif "outreach lease released" in line and opened is not None:
                    spans.append((opened, seconds(line), worker.worker_id))
                    opened = None
        self.assertGreaterEqual(len(spans), 3)
        spans.sort()
        for earlier, later in zip(spans, spans[1:]):
            self.assertLessEqual(earlier[1], later[0], f"two sessions overlapped: {earlier} and {later}")
        with SessionLocal() as db:
            self.assertIsNone(db.get(models.AccountLease, account_id))


class LeaseHeartbeatTest(WorkerProcessCase):
    def test_a_batch_longer_than_the_lease_keeps_it_and_a_waiting_worker_never_overlaps(self):
        account_id = self.make_account()
        names = ["ann", "bob", "cy"]
        self.make_campaign(names, [{"type": "connection_request", "message": "Hi {{first_name}}"}, {"type": "end"}], [account_id], launch=True)
        self.tick()
        MOCK.commit_delay = 5  # every invitation takes longer than the 3 second lease
        env = dict(OUTREACH_BATCH_MAX_ACTIONS="3", OUTREACH_LEASE_SECONDS="3")

        holder = self.start(**env)
        self.wait_until(lambda: "outreach lease acquired" in holder.output, 60, "the first worker to take the lease")
        waiting = self.start(**env)  # polls every second and wants the same account the whole time
        self.wait_until(lambda: all(row[1] == "done" for row in self.task_rows()), 120, "all three invitations to finish")
        for worker in (holder, waiting):
            self.assertEqual(worker.stop(), 0, worker.output[-2000:])

        self.assertEqual(sorted(user for user, _ in MOCK.invites), sorted(names))  # nobody invited twice
        spans = []
        for worker in (holder, waiting):
            opened = None
            for line in worker.lines:
                if "outreach lease acquired" in line:
                    opened = seconds(line)
                elif "outreach lease released" in line and opened is not None:
                    spans.append((opened, seconds(line), worker.worker_id))
                    opened = None
        spans.sort()
        self.assertGreater(spans[0][1] - spans[0][0], 3.0, "the batch should have outlasted the lease")
        for earlier, later in zip(spans, spans[1:]):
            self.assertLessEqual(earlier[1], later[0], f"two sessions overlapped: {earlier} and {later}")
        self.assertEqual(len({row[3] for row in self.task_rows()} & {holder.worker_id}), 1)


class LeaseLossTest(OutreachCase):
    def test_a_worker_that_loses_its_lease_stops_before_its_next_action_and_hands_back_what_it_claimed(self):
        account_id = self.make_account()
        self.make_campaign(["ann", "bob", "cy", "dee"], [{"type": "connection_request", "message": "Hi {{first_name}}"}, {"type": "end"}], [account_id], launch=True)
        self.tick()
        MOCK.commit_delay = 1.5
        with patch.object(settings, "outreach_lease_seconds", 1.5):
            self.worker.run_once()
            deadline = time.monotonic() + 30
            while not MOCK.invites and time.monotonic() < deadline:
                time.sleep(0.1)
            self.assertTrue(MOCK.invites, "the first invitation should have been sent")
            with SessionLocal() as db:  # another holder takes the account while the batch is still running
                lease = db.get(models.AccountLease, account_id)
                lease.holder, lease.expires_at = "intruder", datetime.now(timezone.utc) + timedelta(hours=1)
                db.commit()
            self.worker.join(timeout=60)

        statuses = [t.status for t in self.tasks("send_invite")]
        self.assertLessEqual(len(MOCK.invites), 2, "the worker kept acting after it lost the lease")
        self.assertNotIn("running", statuses)
        self.assertIn("pending", statuses)  # what it had not done stays available, nothing is stuck or lost
        self.assertEqual(statuses.count("done"), len(MOCK.invites))
        with SessionLocal() as db:
            self.assertEqual(db.get(models.AccountLease, account_id).holder, "intruder")  # it did not release another worker's lease


class FreshDiskTest(WorkerProcessCase):
    """A redeploy gives a worker an empty disk. Everything an account needs lives encrypted in the database, so the
    account stays connected and the worker keeps acting for it."""

    def test_a_worker_on_a_brand_new_empty_disk_keeps_the_account_connected_and_acts_with_the_stored_session(self):
        import shutil
        import tempfile
        account_id = self.make_account("redeploy")
        with SessionLocal() as db:
            before = db.get(models.LinkedInAccount, account_id)
            stored = (before.session_state_encrypted, before.status, before.session_status)
        self.assertTrue(stored[0], "the session state must be stored in the database")

        def fresh_disk():
            folder = tempfile.mkdtemp(prefix="empty-disk-")
            return folder, {"TMP": folder, "TEMP": folder, "TMPDIR": folder}

        # First deploy: an empty disk, one action.
        disk_a, env_a = fresh_disk()
        self.make_campaign(["ann"], INVITE_ONLY, [account_id], launch=True)
        first = self.start(**env_a)
        self.wait_until(lambda: len(MOCK.invites) == 1, what="the first deploy's action")
        first.stop()
        shutil.rmtree(disk_a, ignore_errors=True)  # the container and its disk are gone

        # A redeploy: a new process, a new empty disk, nothing carried over except the database.
        disk_b, env_b = fresh_disk()
        self.assertEqual(os.listdir(disk_b), [])
        with SessionLocal() as db:  # time passes between deploys: the human-pacing gap after the first send is over
            db.get(models.LinkedInAccount, account_id).next_action_at = None
            db.commit()
        self.make_campaign(["bob"], INVITE_ONLY, [account_id], launch=True)
        second = self.start(**env_b)
        self.wait_until(lambda: len(MOCK.invites) == 2, what="the redeployed worker's action")
        second.stop()
        self.assertEqual(sorted(user for user, _ in MOCK.invites), ["ann", "bob"])
        with SessionLocal() as db:
            after = db.get(models.LinkedInAccount, account_id)
            self.assertEqual((after.status, after.session_status), (stored[1], stored[2]))  # still connected, not asked to reconnect
            self.assertTrue(after.session_state_encrypted)
        self.assertEqual([t[1] for t in self.task_rows()], ["done", "done"])
        shutil.rmtree(disk_b, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
