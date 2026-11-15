"""Logging that cannot leak. An exception's message can carry anything (a password typed into a
form, a cookie in a URL, a proxy address with credentials, a message body), so failures are logged
by type and call site only, never by message and never with a full traceback."""
import logging
import traceback


def failure_site(exc: BaseException, depth: int = 3) -> str:
    """`file:line in function` for the innermost frames of the exception, without any message text."""
    frames = traceback.extract_tb(exc.__traceback__)[-depth:]
    return " <- ".join(f"{frame.filename.rsplit('/', 1)[-1].rsplit(chr(92), 1)[-1]}:{frame.lineno} in {frame.name}" for frame in reversed(frames))


def log_failure(logger: logging.Logger, message: str, exc: BaseException) -> None:
    logger.error("%s: %s at %s", message, type(exc).__name__, failure_site(exc) or "unknown")
