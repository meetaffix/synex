"""Proxy connectivity test.

Makes one request to a neutral endpoint (``linkedin_proxy_test_url``, never
LinkedIn) through the proxy under test. Proxy credentials are used only to build
the client: they never appear in a result, an exception message that is shown, or
a log line. Only fixed messages and error codes leave this module.
"""
import ipaddress
import logging
import socket
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from dataclasses import dataclass
from urllib.parse import urlsplit

import httpx

from ..config import settings

log = logging.getLogger("synex.linkedin_session")

MESSAGES = {
    "proxy_not_allowed": "Proxy addresses on private or local networks are not allowed.",
    "proxy_unreachable": "Synex could not reach the proxy. Check the host and port.",
    "proxy_rejected": "The proxy refused the connection. Check the username and password.",
    "timeout": "The proxy did not respond in time.",
    "bad_response": "The proxy answered, but not with the expected response.",
    "unknown": "The test failed for an unexpected reason.",
}


@dataclass(frozen=True)
class ProxyTestResult:
    ok: bool
    latency_ms: int | None = None
    exit_ip: str | None = None
    country: str | None = None
    error_code: str | None = None

    @property
    def error_message(self) -> str | None:
        return MESSAGES[self.error_code] if self.error_code else None


def _failure(code: str) -> ProxyTestResult:
    log.info("linkedin proxy test failed: %s", code)
    return ProxyTestResult(ok=False, error_code=code)


def _is_public_host(host: str) -> bool:
    try:
        addresses = {info[4][0] for info in socket.getaddrinfo(host, None)}
    except OSError:
        return True  # unresolvable hosts fail later as proxy_unreachable
    return all(ipaddress.ip_address(address).is_global for address in addresses)


def proxy_host_allowed(proxy_url: str) -> bool:
    """False for proxies on private, loopback or link-local addresses unless explicitly allowed."""
    host = urlsplit(proxy_url).hostname or ""
    return settings.linkedin_proxy_test_allow_private or _is_public_host(host)


def _request(proxy_url: str, timeout: float) -> httpx.Response:
    with httpx.Client(proxy=proxy_url, timeout=timeout) as client:
        return client.get(settings.linkedin_proxy_test_url)


def _read_result(response: httpx.Response, started: float) -> ProxyTestResult:
    if response.status_code == 407:
        return _failure("proxy_rejected")
    if response.status_code != 200:
        return _failure("bad_response")
    try:
        data = response.json()
        exit_ip = str(ipaddress.ip_address(str(data["ip"])))
    except (ValueError, KeyError, TypeError):
        return _failure("bad_response")
    country = data.get("country")
    return ProxyTestResult(ok=True, latency_ms=round((time.monotonic() - started) * 1000), exit_ip=exit_ip,
                           country=country[:64] if isinstance(country, str) else None)


def run_proxy_test(proxy_url: str) -> ProxyTestResult:
    if not proxy_host_allowed(proxy_url):
        return _failure("proxy_not_allowed")
    timeout = settings.linkedin_proxy_test_timeout_seconds
    started = time.monotonic()
    pool = ThreadPoolExecutor(max_workers=1)
    future = pool.submit(_request, proxy_url, timeout)
    try:
        # httpx timeouts apply per phase; this bounds the whole test.
        response = future.result(timeout=timeout)
    except (FutureTimeout, httpx.TimeoutException):
        return _failure("timeout")
    except httpx.ProxyError:
        return _failure("proxy_rejected")
    except httpx.TransportError:
        return _failure("proxy_unreachable")
    except Exception as exc:  # noqa: BLE001 - only the type is logged
        log.warning("linkedin proxy test error: %s", type(exc).__name__)
        return _failure("unknown")
    finally:
        pool.shutdown(wait=False, cancel_futures=True)
    return _read_result(response, started)
