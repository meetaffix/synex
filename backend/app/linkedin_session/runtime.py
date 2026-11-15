"""A dedicated event-loop thread for Playwright.

Playwright needs a loop that can spawn subprocesses (the Proactor loop on
Windows). Uvicorn may be running a different loop policy, so browser work never
shares the web server's loop; request threads submit coroutines here instead.
"""
import asyncio
import sys
import threading
from collections.abc import Awaitable, Callable
from concurrent.futures import Future
from typing import Any, TypeVar

T = TypeVar("T")


def _new_loop() -> asyncio.AbstractEventLoop:
    return asyncio.ProactorEventLoop() if sys.platform == "win32" else asyncio.new_event_loop()


class BrowserRuntime:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None

    @property
    def running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def start(self) -> None:
        with self._lock:
            if self.running:
                return
            ready = threading.Event()
            self._loop = _new_loop()
            self._thread = threading.Thread(target=self._run, args=(self._loop, ready), name="linkedin-browsers", daemon=True)
            self._thread.start()
            ready.wait()

    @staticmethod
    def _run(loop: asyncio.AbstractEventLoop, ready: threading.Event) -> None:
        asyncio.set_event_loop(loop)
        loop.call_soon(ready.set)
        try:
            loop.run_forever()
        finally:
            loop.close()

    def submit(self, coro: Awaitable[T]) -> Future[T]:
        assert self._loop is not None, "runtime not started"
        return asyncio.run_coroutine_threadsafe(coro, self._loop)  # type: ignore[arg-type]

    def call_soon(self, fn: Callable[..., Any], *args: Any) -> None:
        assert self._loop is not None, "runtime not started"
        self._loop.call_soon_threadsafe(fn, *args)

    def stop(self, timeout: float = 10) -> None:
        with self._lock:
            if not self.running or self._loop is None or self._thread is None:
                return
            self._loop.call_soon_threadsafe(self._loop.stop)
            self._thread.join(timeout)
