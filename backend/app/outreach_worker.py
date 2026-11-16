"""Run with python -m app.outreach_worker.

Polls on an interval: runs the engine to queue due tasks, claims them atomically, and
performs them through each account's saved browser session. One browser per account at
a time, in strict task order, with a randomized gap between actions; the global browser
cap comes from LINKEDIN_SESSION_MAX_BROWSERS.

No double sends: tasks are claimed with a versioned UPDATE, state is re-read just before
acting, and a task whose worker died mid-action becomes ``needs_review`` and is never
retried automatically. Only tasks that failed before touching the page retry, with backoff.
"""
import asyncio
import importlib
import logging
import os
import random
import signal
import threading
import shutil
import uuid
from concurrent.futures import Future
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from playwright.async_api import BrowserContext, Page
from sqlalchemy.exc import IntegrityError

from . import engine, models, outreach_results as results
from .config import settings
from .database import SessionLocal
from .logsafe import log_failure
from .linkedin_session import actions, store
from .linkedin_session.actions import ActionSession, SessionError
from .linkedin_session.manager import SessionManager
from .linkedin_session.pages import PROFILE_PAGES, ProfilePages
from .linkedin_session.service import get_manager
from .publishing_models import WorkerHeartbeat

log = logging.getLogger("synex.outreach")
ACCOUNT_BACKOFF_SECONDS = 60


@dataclass(frozen=True)
class TaskSnapshot:
    id: str
    type: str
    profile_url: str
    message: str
    since: datetime | None
    payload: dict | None = None


class OutreachWorker:
    def __init__(self, manager: SessionManager | None = None, pages: ProfilePages = PROFILE_PAGES) -> None:
        self.id = uuid.uuid4().hex
        self.manager = manager or get_manager()
        self.pages = pages
        self.stopping = threading.Event()
        self._batches: dict[str, Future[None]] = {}
        self._cooldown: dict[str, datetime] = {}

    # ---- one polling cycle -----------------------------------------------------------

    def run_once(self, wait: bool = False) -> dict:
        """One cycle: heartbeat, sweep, engine tick, start a batch per account with work."""
        self._reap()
        with SessionLocal() as db:
            self._heartbeat(db)
            if engine.kill_switch_active(db):
                return {"killed": True, "started": []}
            results.sweep_stale_tasks(db, datetime.now(timezone.utc))
            try:
                ticked = engine.tick(db)
            except IntegrityError:
                db.rollback()  # another worker queued the same task first; the next cycle re-reads
                ticked = {"processed": 0}
            accounts = self._accounts_with_work(db)
        started = [account_id for account_id in accounts if self._start_batch(account_id)]
        if wait:
            self.join()
        return {**ticked, "started": started}

    def join(self, timeout: float = 120) -> None:
        for future in list(self._batches.values()):
            try:
                future.result(timeout=timeout)
            except BaseException as exc:  # noqa: BLE001 - a crashed batch must not stop the worker
                log.warning("outreach batch ended with %s", type(exc).__name__)
        self._reap()

    def shutdown(self) -> None:
        self.stopping.set()
        self.join(timeout=60)
        self.manager.shutdown()

    def _heartbeat(self, db) -> None:
        beat = db.get(WorkerHeartbeat, f"outreach-{self.id}") or WorkerHeartbeat(id=f"outreach-{self.id}")
        beat.checked_at = datetime.now(timezone.utc)
        db.add(beat)
        db.commit()

    def _reap(self) -> None:
        for account_id, future in list(self._batches.items()):
            if not future.done():
                continue
            del self._batches[account_id]
            error = future.exception()
            with SessionLocal() as db:
                results.release_lease(db, account_id, self.id)
            if error is not None:
                log.warning("outreach browser for account %s failed: %s", account_id, type(error).__name__)
                self._cooldown[account_id] = datetime.now(timezone.utc) + timedelta(seconds=ACCOUNT_BACKOFF_SECONDS)

    def _accounts_with_work(self, db) -> list[str]:
        now = datetime.now(timezone.utc)
        ids = {row[0] for row in db.query(models.AgentTask.account_id).filter(
            models.AgentTask.status == "pending",
            (models.AgentTask.next_attempt_at.is_(None)) | (models.AgentTask.next_attempt_at <= now)).distinct()}
        live = [a.id for a in db.query(models.LinkedInAccount).filter(models.LinkedInAccount.id.in_(ids)) if engine.account_is_live(a)]
        return [a for a in live if a not in self._batches and self._cooldown.get(a, now) <= now]

    def _start_batch(self, account_id: str) -> bool:
        with SessionLocal() as db:
            account = db.get(models.LinkedInAccount, account_id)
            state, identity, proxy = store.load_state(account), account.browser_profile, store.load_proxy(account)
            if state is None or not identity:
                return False
            if settings.require_account_proxy and not proxy:  # the hosted safety gate: no proxy, no browser, no lease
                log.warning("account %s has no proxy: this server requires one, so no browser is opened for it", account_id)
                self._cooldown[account_id] = datetime.now(timezone.utc) + timedelta(minutes=10)
                return False
            # No browser is opened for an account this worker does not hold the lease for.
            if not results.acquire_lease(db, account_id, self.id, datetime.now(timezone.utc)):
                return False
            log.info("outreach lease acquired account=%s worker=%s", account_id, self.id)
        self._batches[account_id] = self.manager.submit_session_work(
            storage_state=state, identity=identity, proxy_url=proxy,
            work=lambda page, context: self._batch(account_id, page, context))
        # The lease is given up only once the browser has closed, so two sessions never overlap.
        self._batches[account_id].add_done_callback(lambda _future: self._release(account_id))
        return True

    # ---- one account's batch (runs on the browser thread) -----------------------------

    async def _batch(self, account_id: str, page: Page, context: BrowserContext) -> None:
        session = ActionSession(page, self.pages)
        executed = 0
        lost = asyncio.Event()
        keeper = asyncio.create_task(self._keep_lease(account_id, lost))
        log.info("outreach batch started account=%s worker=%s", account_id, self.id)
        try:
            while not self.stopping.is_set() and not lost.is_set() and executed < settings.outreach_batch_max_actions:
                if await asyncio.to_thread(self._killed):
                    break
                task_id = await asyncio.to_thread(self._claim, account_id)
                if task_id is None:
                    break
                if lost.is_set():  # lost between the claim and the action: nothing was touched, so hand the task back
                    await asyncio.to_thread(results.unclaim_task, task_id, self.id)
                    break
                executed += 1
                if await self._execute(session, account_id, task_id):
                    break
                if executed < settings.outreach_batch_max_actions and await asyncio.to_thread(self._has_more, account_id):
                    gap = random.uniform(settings.outreach_action_gap_min_seconds,
                                         max(settings.outreach_action_gap_min_seconds, settings.outreach_action_gap_max_seconds))
                    try:
                        await asyncio.wait_for(lost.wait(), timeout=gap)  # the pause ends early if the lease is lost
                    except asyncio.TimeoutError:
                        pass
        finally:
            keeper.cancel()
            try:
                await asyncio.to_thread(store.save_state, account_id, await context.storage_state())
                log.info("outreach session state saved account=%s", account_id)
            except Exception as exc:  # noqa: BLE001 - the browser may already be gone
                log.warning("outreach could not save session state: %s", type(exc).__name__)
            log.info("outreach batch ended account=%s worker=%s", account_id, self.id)

    async def _keep_lease(self, account_id: str, lost: asyncio.Event) -> None:
        """Renews the account's lease on a heartbeat for as long as the batch runs, so a long action or pause
        cannot let it expire. If another worker holds the account now, or the lease could not be renewed for a
        whole lease period, the batch is told to stop before its next action."""
        interval = max(0.05, settings.outreach_lease_seconds / 3)
        last_renewed = datetime.now(timezone.utc)
        while True:
            await asyncio.sleep(interval)
            try:
                held = await asyncio.to_thread(self._renew, account_id)
            except Exception as exc:  # noqa: BLE001 - a database hiccup is retried until the lease would have expired
                log_failure(log, "outreach lease renewal failed", exc)
                held = None
            now = datetime.now(timezone.utc)
            if held:
                last_renewed = now
            elif held is False or (now - last_renewed).total_seconds() >= settings.outreach_lease_seconds:
                log.warning("outreach lease lost account=%s worker=%s", account_id, self.id)
                lost.set()
                return

    async def _execute(self, session: ActionSession, account_id: str, task_id: str) -> bool:
        """Perform one claimed task. Returns True when the account must stop."""
        reason = await asyncio.to_thread(results.precheck, task_id)
        if reason:
            await asyncio.to_thread(results.skip_task, task_id, reason)
            return False
        snapshot = await asyncio.to_thread(self._snapshot, task_id)
        session.before_commit = lambda: asyncio.to_thread(results.mark_committed, task_id)
        try:
            outcome = await self._perform(session, snapshot)
        except results.PolicyChanged as error:
            await asyncio.to_thread(results.skip_task, task_id, str(error))
            return False
        except SessionError as error:
            await asyncio.to_thread(results.handle_session_error, account_id, task_id, error.kind.value)
            return True
        except Exception as error:  # noqa: BLE001 - classified by whether the page was touched
            await asyncio.to_thread(results.fail_task, task_id, type(error).__name__)
            return False
        if snapshot.type == "sync_inbox":
            await asyncio.to_thread(results.apply_inbox, task_id, outcome)
        elif snapshot.type in ("collect_leads", "sync_connections"):
            await asyncio.to_thread(results.apply_result, task_id, outcome)
        else:
            await asyncio.to_thread(results.apply_result, task_id, outcome.value)
        return False

    @staticmethod
    async def _perform(session: ActionSession, task: TaskSnapshot):
        if task.type == "send_invite":
            return await actions.send_connection_request(session, task.profile_url, task.message or None)
        if task.type == "send_message":
            return await actions.send_message(session, task.profile_url, task.message)
        if task.type == "visit_profile":
            return await actions.visit_profile(session, task.profile_url)
        if task.type == "follow_profile":
            return await actions.follow_profile(session, task.profile_url)
        if task.type == "withdraw_invite":
            return await actions.withdraw_invite(session, task.profile_url)
        if task.type == "like_post":
            return await actions.like_post(session, task.profile_url)
        if task.type == "send_inmail":
            payload = task.payload or {}
            return await actions.send_inmail(session, task.profile_url, str(payload.get("subject") or ""), task.message, bool(payload.get("free")))
        if task.type == "send_voice_note":
            from . import voice
            path = voice.audio_file((task.payload or {}).get("audioId"))
            if path is None:
                raise RuntimeError("the prepared voice note is missing")
            try:
                return await actions.send_voice_note(session, task.profile_url, str(path))
            finally:
                shutil.rmtree(path.parent, ignore_errors=True)
        if task.type == "check_connection":
            return await actions.get_connection_status(session, task.profile_url)
        if task.type == "sync_inbox":
            return await actions.fetch_new_messages(session, task.since)
        if task.type == "collect_leads":
            from . import collection_runner
            return await collection_runner.run(session, (task.payload or {})["collectionId"], (task.payload or {}).get("mode", "run"))
        if task.type == "sync_connections":
            from . import connections_runner
            return await connections_runner.run(session, (task.payload or {})["accountId"], (task.payload or {}).get("kind", "connection"))
        raise ValueError(f"unknown task type {task.type}")

    # ---- sync helpers run through asyncio.to_thread -----------------------------------

    def _release(self, account_id: str) -> None:
        with SessionLocal() as db:
            results.release_lease(db, account_id, self.id)
        log.info("outreach lease released account=%s worker=%s", account_id, self.id)

    def _renew(self, account_id: str) -> bool:
        with SessionLocal() as db:
            return results.acquire_lease(db, account_id, self.id, datetime.now(timezone.utc))

    def _killed(self) -> bool:
        with SessionLocal() as db:
            return engine.kill_switch_active(db)

    def _claim(self, account_id: str) -> str | None:
        with SessionLocal() as db:
            return results.claim_next_task(db, account_id, self.id, datetime.now(timezone.utc))

    @staticmethod
    def _has_more(account_id: str) -> bool:
        with SessionLocal() as db:
            return db.query(models.AgentTask.id).filter_by(account_id=account_id, status="pending").first() is not None

    @staticmethod
    def _snapshot(task_id: str) -> TaskSnapshot:
        with SessionLocal() as db:
            task = db.get(models.AgentTask, task_id)
            payload = task.payload or {}
            return TaskSnapshot(task.id, task.type, payload.get("linkedinUrl", ""), payload.get("message", ""),
                                engine._aware(task.account.last_inbox_sync_at), dict(payload))


def load_pages() -> ProfilePages:
    """The real LinkedIn pages, unless OUTREACH_PAGES_FACTORY ("module:function") names a factory returning
    another ProfilePages. Tests use it to point the worker process at a local mock site."""
    spec = os.environ.get("OUTREACH_PAGES_FACTORY")
    if not spec:
        return PROFILE_PAGES
    module, _, function = spec.partition(":")
    return getattr(importlib.import_module(module), function)()


def cycle(worker: OutreachWorker) -> None:
    """One polling cycle that never raises. A failure is logged by type and call site only: its message
    could carry a cookie, a message body or a proxy credential."""
    try:
        worker.run_once()
    except Exception as exc:  # noqa: BLE001 - one bad cycle must not stop the worker
        log_failure(log, "outreach worker cycle failed", exc)


def run(worker: OutreachWorker) -> None:
    """Poll until told to stop, then finish the current action and close every browser."""
    for name in ("SIGINT", "SIGTERM", "SIGBREAK"):  # SIGBREAK is how a Windows console process is asked to stop
        if hasattr(signal, name):
            signal.signal(getattr(signal, name), lambda *_: worker.stopping.set())
    log.info("outreach worker %s started", worker.id)
    while not worker.stopping.is_set():
        cycle(worker)
        worker.stopping.wait(settings.outreach_tick_interval_seconds)
    worker.shutdown()
    log.info("outreach worker %s stopped", worker.id)


def main() -> None:
    from .check_env import require_valid_env
    from .migrations import migrate

    require_valid_env("The outreach worker")  # names of what is wrong, never values
    migrate()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s.%(msecs)03d %(name)s %(message)s", datefmt="%H:%M:%S")
    pages = load_pages()
    manager = SessionManager(
        pages.site, max_browsers=settings.effective_max_browsers,
        attempt_timeout=settings.linkedin_session_attempt_timeout_seconds,
        poll_interval=settings.linkedin_session_poll_interval_seconds, headless=settings.linkedin_session_headless)
    run(OutreachWorker(manager, pages))


if __name__ == "__main__":
    main()
