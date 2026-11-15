"""A local HTTP forward proxy for the proxy-test endpoint. Never reaches the internet:
it answers every request itself, like a proxy sitting in front of a neutral IP-echo
service. Credentials are checked the way a real authenticating proxy would."""
import atexit
import base64
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class MockProxy:
    def __init__(self, username: str = "pxuser", password: str = "Pr0xy-Secret-Marker") -> None:
        self.username, self.password = username, password
        self.require_auth = False
        self.delay = 0.0
        self.body = {"ip": "203.0.113.7", "country": "NL"}
        self.raw_body: str | None = None
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), self._handler())
        self.port = self._server.server_address[1]

    def url(self, with_credentials: bool = False) -> str:
        auth = f"{self.username}:{self.password}@" if with_credentials else ""
        return f"http://{auth}127.0.0.1:{self.port}"

    def start(self) -> "MockProxy":
        threading.Thread(target=self._server.serve_forever, daemon=True).start()
        return self

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()

    def _handler(self):
        proxy = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                if proxy.delay:
                    time.sleep(proxy.delay)
                if proxy.require_auth:
                    expected = "Basic " + base64.b64encode(f"{proxy.username}:{proxy.password}".encode()).decode()
                    if self.headers.get("Proxy-Authorization") != expected:
                        self.send_response(407)
                        self.send_header("Proxy-Authenticate", 'Basic realm="proxy"')
                        self.send_header("Content-Length", "0")
                        self.end_headers()
                        return
                payload = (proxy.raw_body if proxy.raw_body is not None else json.dumps(proxy.body)).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                try:
                    self.wfile.write(payload)
                except OSError:
                    pass  # the client gave up (timeout test)

        return Handler


_shared: "MockProxy | None" = None


def shared_proxy() -> MockProxy:
    global _shared
    if _shared is None:
        _shared = MockProxy().start()
        atexit.register(_shared.stop)
    return _shared
