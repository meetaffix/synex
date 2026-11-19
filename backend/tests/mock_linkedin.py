"""A local stand-in for LinkedIn: the login flow plus profiles, invitations and messaging.
Never contacts linkedin.com.

Login scenario is chosen by the local part of the email address (a phone number signs in as "phone<digits>"):
    ok          success                       code        email code challenge (PIN)
    approve     app-approval challenge        checkpoint  unrecognised checkpoint (captcha marker)
    slow        never reaches a known page    (anything else behaves like ok)
A wrong password is rejected for every scenario. Session cookies are honoured on every page.

Outreach state lives in ``profiles`` / ``conversations`` and is inspectable: ``invites``, ``follows`` and
``sent_messages`` record what the "site" received. ``fault`` makes the next irreversible action end on a
logged-out, checkpoint or restricted page. ``accept(user)`` and ``reply(user, text)`` simulate the other side.
"""
import atexit
import os
import threading
import time
from datetime import datetime, timezone
from html import escape
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs

from app.linkedin_session.pages import ProfilePages, ProfileSelectors, Selectors, Site

MOCK_SELECTORS = Selectors(
    username="#username", password="#password", submit="button#sign-in",
    login_error="#error-for-password", code_input="input[name=pin]", code_submit="button#verify",
    code_error="#pin-error", code_hint="#challenge-hint", approval_marker="#app-approval",
    captcha_marker="#captcha", logged_in_marker="#global-nav", restricted_marker="#restricted-notice",
    profile_name="h1", profile_headline=".headline", profile_avatar="img.avatar")

MOCK_PROFILE_SELECTORS = ProfileSelectors(
    unavailable_marker="#unavailable", connect_button="#connect", pending_marker="#pending",
    message_button="#message", follow_button="#follow", following_marker="#following",
    note_toggle="#add-note", note_input="textarea#note", send_invite_button="button#send-invite",
    invite_limit_marker="#invite-limit", note_error="#note-error", composer_input="textarea#composer",
    composer_send="button#composer-send", conversation_item="li.conv", conversation_profile_link="a.conv-link",
    thread_message=".msg", like_button="button#like", liked_marker="#liked", no_posts_marker="#no-posts",
    inmail_button="#inmail", inmail_subject="input#subject", inmail_body="textarea#inmail-body", inmail_send="button#inmail-send",
    inmail_free_marker="#inmail-free", inmail_no_credits_marker="#no-credits", attach_input="input#attach", attach_send="button#attach-send",
    reaction_open="button[aria-label^='React Like']", reaction_choice="button[aria-label='{name}']", reacted_marker="button[aria-pressed='true']",
    comment_box="textarea#comment", comment_submit="button#comment-post")

_REAL_FIELDS = """<div data-copy="{n}"><label for="{n}a"><div>Email or phone</div></label><div><input type="email" id="{n}a" autocomplete="username" value=""/></div>
<label for="{n}b"><div>Password</div></label><div><input type="password" id="{n}b" autocomplete="current-password" value=""/><button type="button" aria-label="Show password"><span>eye</span></button></div>
<div><input type="checkbox" aria-label="Keep me signed in" checked=""/><p>Keep me signed in</p></div>
<button type="button" data-real-signin="1"><span><span>Sign in</span></span></button>
<button type="button"><span><span>Sign in with Google</span></span></button></div>"""
REAL_SHAPE_LOGIN = (
    "{notice}"
    '<div style="display:none">' + _REAL_FIELDS.replace("{n}", "h") + "</div>"
    "<div>" + _REAL_FIELDS.replace("{n}", "v") + "</div>"
    """<script>document.querySelectorAll('[data-real-signin]').forEach(btn => btn.addEventListener('click', async () => {{
      const root = btn.closest('[data-copy]');
      const u = root.querySelector('input[type=email]').value, p = root.querySelector('input[type=password]').value;
      const r = await fetch('/login', {{method: 'POST', headers: {{'Content-Type': 'application/x-www-form-urlencoded'}}, body: new URLSearchParams({{u, p}})}});
      if (r.redirected) {{ window.location.href = r.url; }} else {{ document.body.innerHTML = await r.text(); }}
    }}));</script>""")

PAGE = "<!doctype html><html><body>{body}</body></html>"
FAULT_TARGETS = {"logged_out": "/login", "checkpoint": "/checkpoint/unknown", "restricted": "/restricted"}


class MockLinkedIn:
    def __init__(self, password: str = "S3cret-Pa55-xyzzy", code: str = "482913", real_shape: bool = False) -> None:
        self.password, self.code = password, code
        # real_shape: the sign-in page copies the structure of LinkedIn's real page (read 15 Nov 2026): generated ids, no <form>,
        # a type=button "Sign in" button that posts with script, and the markup shipped twice with one copy hidden.
        self.real_shape = real_shape
        self.approved = False
        self.force_logged_out = False
        self.force_restricted = False
        self.weekly_limit = False
        self.fault: str | None = None
        self.commit_delay = 0.0
        self.seen = 0
        self.profiles: dict[str, dict] = {}
        self.conversations: dict[str, list[dict]] = {}
        self.invites: list[tuple[str, str]] = []
        self.follows: list[str] = []
        self.withdrawals: list[str] = []
        self.likes: list[str] = []
        self.inmails: list[tuple[str, str, str]] = []
        self.voice_notes: list[tuple[str, str, int]] = []
        self.inmail_credits = 5
        self.posts: dict[str, dict] = {}
        self.sent_messages: list[tuple[str, str]] = []
        self._event = 0
        self._lock = threading.Lock()
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), self._handler())
        self.base_url = f"http://127.0.0.1:{self._server.server_address[1]}"
        self.site = Site(self.base_url, MOCK_SELECTORS)
        self.pages = ProfilePages(self.site, MOCK_PROFILE_SELECTORS)

    def start(self) -> "MockLinkedIn":
        threading.Thread(target=self._server.serve_forever, daemon=True).start()
        return self

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()

    def reset(self) -> None:
        self.approved = self.force_logged_out = self.force_restricted = self.weekly_limit = False
        self.fault = None
        self.profiles.clear()
        self.conversations.clear()
        self.invites.clear()
        self.follows.clear()
        self.withdrawals.clear()
        self.likes.clear()
        self.inmails.clear()
        self.voice_notes.clear()
        self.inmail_credits = 5
        self.posts.clear()
        self.sent_messages.clear()

    # ---- simulation helpers ------------------------------------------------------------

    def profile_url(self, user: str) -> str:
        return f"{self.base_url}/in/{user}/"

    def post(self, post_id: str) -> dict:
        return self.posts.setdefault(post_id, {"reaction": None, "comments": [], "available": post_id != "0"})

    def post_url(self, post_id: str) -> str:
        return f"{self.base_url}/feed/update/urn:li:activity:{post_id}/"

    def profile(self, user: str) -> dict:
        return self.profiles.setdefault(user, {"state": "not_connected", "following": False, "available": user != "gone", "posts": 1, "liked": False, "inmail": "none"})

    def accept(self, user: str) -> None:
        self.profile(user)["state"] = "connected"

    def _add_message(self, user: str, direction: str, text: str) -> None:
        with self._lock:
            self._event += 1
            self.conversations.setdefault(user, []).append(
                {"id": f"e{self._event}", "direction": direction, "text": text, "sent_at": datetime.now(timezone.utc).isoformat()})

    def reply(self, user: str, text: str) -> None:
        self._add_message(user, "in", text)

    # ---- http --------------------------------------------------------------------------

    def _handler(self):
        mock = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):  # keep test output quiet
                pass

            def handle(self):
                try:
                    super().handle()
                except (ConnectionResetError, BrokenPipeError):
                    pass  # a test stopped the browser (or the whole worker) mid-request

            def _cookies(self) -> dict[str, str]:
                return {k: v.value for k, v in SimpleCookie(self.headers.get("Cookie", "")).items()}

            def _send(self, status=200, body="", cookies=(), location=None):
                self.send_response(status)
                self.send_header("Content-Type", "text/html")
                for cookie in cookies:
                    self.send_header("Set-Cookie", cookie)
                if location:
                    self.send_header("Location", location)
                self.end_headers()
                self.wfile.write(PAGE.format(body=body).encode())

            def _redirect(self, location: str):
                self._send(303, location=location)

            def _signed_in(self) -> bool:
                return self._cookies().get("li_at") == "ok" and not mock.force_logged_out

            def _consume_fault(self) -> bool:
                """Send the browser to a problem page instead of completing a commit action."""
                if mock.fault is None:
                    return False
                target = FAULT_TARGETS[mock.fault]
                mock.fault = None
                self._redirect(target)
                return True

            # ---- pages ----
            def _login_page(self, error=False):
                if mock.real_shape:
                    return self._send(body=REAL_SHAPE_LOGIN.format(
                        notice="<p>Hmm, that's not the right password. Please try again.</p>" if error else ""))
                notice = '<div id="error-for-password">Wrong password</div>' if error else ""
                self._send(body=f'{notice}<form method="post" action="/login"><input id="username" name="u">'
                                '<input id="password" name="p" type="password"><button id="sign-in" type="submit">Sign in</button></form>')

            def _challenge_page(self, error=False):
                notice = '<div id="pin-error">Incorrect code</div>' if error else ""
                self._send(body='<div id="challenge-hint">We sent a code to your email.</div>' + notice +
                                '<form method="post" action="/checkpoint/challenge"><input name="pin"><button id="verify" type="submit">Verify</button></form>')

            def _signed_in_redirect(self, user: str):
                self._send(303, cookies=["li_at=ok; Path=/", f"li_user={user}; Path=/"], location="/feed/")

            def _messages_html(self, user: str) -> str:
                return "".join(
                    f'<div class="msg" data-event-id="{m["id"]}" data-direction="{m["direction"]}" data-sent-at="{m["sent_at"]}">{escape(m["text"])}</div>'
                    for m in mock.conversations.get(user, []))

            def _profile_page(self, user: str):
                profile = mock.profile(user)
                if not profile["available"]:
                    return self._send(404, '<div id="unavailable">Profile is not available</div>')
                state = profile["state"]
                connect = {"connected": f'<a id="message" href="/messaging/compose/{user}/">Message</a>',
                           "pending": f'<a id="pending" href="/in/{user}/withdraw/">Pending</a>',  # opens the withdraw confirmation
                           "not_connected": f'<a id="connect" href="/in/{user}/connect/">Connect</a>'}[state]
                if state == "not_connected" and profile["inmail"] != "none":
                    connect += f'<a id="inmail" href="/messaging/inmail/{user}/">InMail</a>'
                follow = ('<span id="following">Following</span>' if profile["following"] else
                          f'<form method="post" action="/in/{user}/follow/"><button id="follow">Follow</button></form>')
                mock.seen += 1  # a cookie that changes on every visit proves the browser's state was saved back
                self._send(cookies=[f"li_seen={mock.seen}; Path=/"],
                           body=(f'<title>Mock {user.title()} | LinkedIn</title><main><h2>Mock {user.title()}</h2>' if mock.real_shape
                                 else f'<h1>Mock {user.title()}</h1>') + f'<div class="headline">Engineer at Mock Co</div>'
                                f'<img class="avatar" src="{mock.base_url}/avatar-{user}.png">{connect}{follow}')

            def do_GET(self):
                path, cookies = self.path.split("?")[0], self._cookies()
                if path == "/login":
                    return self._login_page()
                if path == "/checkpoint/challenge":
                    return self._challenge_page()
                if path == "/checkpoint/approval":
                    if mock.approved:
                        return self._signed_in_redirect(cookies.get("pending", "approve"))
                    return self._send(body='<div id="app-approval">Open the LinkedIn app to approve</div>'
                                           '<meta http-equiv="refresh" content="1">')
                if path == "/checkpoint/unknown":
                    return self._send(body='<div id="captcha">Security verification</div>')
                if path == "/slow":
                    return self._send(body="<p>Loading...</p>")
                if path == "/restricted":
                    return self._send(body='<div id="restricted-notice">Your account has been restricted</div>')
                if path == "/feed/":
                    if mock.force_restricted:
                        return self._redirect("/restricted")
                    if not self._signed_in():
                        return self._redirect("/login")
                    return self._send(body='<nav id="global-nav">Home</nav>')
                if path == "/in/me/":
                    return self._redirect(f"/in/{cookies.get('li_user', 'ok')}/")
                # Everything below needs a signed-in session.
                if mock.force_restricted:
                    return self._redirect("/restricted")
                if not self._signed_in():
                    return self._redirect("/login")
                parts = [p for p in path.split("/") if p]
                if parts[:1] == ["in"] and len(parts) == 2:
                    return self._profile_page(parts[1])
                if parts[:1] == ["in"] and len(parts) == 3 and parts[2] == "connect":
                    if mock.weekly_limit:
                        return self._send(body='<div id="invite-limit">You have reached the weekly invitation limit</div>')
                    return self._send(body=f'<form method="post" action="/in/{parts[1]}/connect/"><textarea id="note" name="note"></textarea>'
                                           '<button id="send-invite">Send</button></form>')
                if parts[:1] == ["in"] and len(parts) == 3 and parts[2] == "withdraw":
                    return self._send(body=f'<form method="post" action="/in/{parts[1]}/withdraw/"><button id="confirm-withdraw">Withdraw</button></form>')
                if parts[:1] == ["in"] and len(parts) == 4 and parts[2:] == ["recent-activity", "all"]:
                    profile = mock.profile(parts[1])
                    if profile["posts"] <= 0:
                        return self._send(body='<div id="no-posts">No recent activity</div>')
                    if profile["liked"]:
                        return self._send(body='<button id="liked" aria-pressed="true" aria-label="Like">Liked</button>')
                    return self._send(body=f'<form method="post" action="/in/{parts[1]}/like/"><button id="like" aria-label="React Like">Like</button></form>')
                if parts[:2] == ["feed", "update"] and len(parts) == 3 and parts[2].startswith("urn:li:activity:"):
                    post_id = parts[2].rsplit(":", 1)[1]
                    state = mock.post(post_id)
                    if not state["available"]:
                        return self._send(404, '<div id="unavailable">This post is not available</div>')
                    action = f"/feed/update/{parts[2]}/"
                    reactions = "".join(
                        f'<form method="post" action="{action}react/"><input type="hidden" name="reaction" value="{name}">'
                        f'<button aria-label="{"React Like" if name == "Like" else name}"{" aria-pressed=\"true\"" if state["reaction"] == name else ""}>{name}</button></form>'
                        for name in ("Like", "Celebrate", "Support", "Love", "Insightful", "Funny"))
                    comments = "".join(f'<p class="comment">{escape(c)}</p>' for c in state["comments"])
                    return self._send(body=f'<article>A post</article>{reactions}{comments}<form method="post" action="{action}comment/">'
                                           '<textarea id="comment" name="text"></textarea><button id="comment-post">Post</button></form>')
                if parts[:2] == ["messaging", "inmail"] and len(parts) == 3:
                    profile = mock.profile(parts[2])
                    free = '<div id="inmail-free">Free message</div>' if profile["inmail"] == "free" else ""
                    if profile["inmail"] == "credit" and mock.inmail_credits <= 0:
                        return self._send(body='<div id="no-credits">You are out of InMail credits</div>')
                    return self._send(body=f'{free}<form method="post" action="/messaging/inmail/{parts[2]}/"><input id="subject" name="subject">'
                                           '<textarea id="inmail-body" name="text"></textarea><button id="inmail-send">Send</button></form>')
                if parts[:2] == ["messaging", "compose"] and len(parts) == 3:
                    return self._send(body=f'{self._messages_html(parts[2])}<form method="post" action="/messaging/compose/{parts[2]}/">'
                                           '<textarea id="composer" name="text"></textarea><button id="composer-send">Send</button></form>'
                                           f'<form method="post" action="/messaging/voice/{parts[2]}/"><input type="file" id="attach" accept="audio/*">'
                                           '<input type="hidden" id="aname" name="name"><input type="hidden" id="asize" name="size">'
                                           '<button id="attach-send">Send voice note</button></form>'
                                           "<script>document.getElementById('attach').onchange=function(e){var f=e.target.files[0];"
                                           "document.getElementById('aname').value=f.name;document.getElementById('asize').value=f.size;};</script>")
                if parts[:2] == ["messaging", "thread"] and len(parts) == 3:
                    return self._send(body=self._messages_html(parts[2]))
                if parts == ["messaging"]:
                    items = "".join(
                        f'<li class="conv" data-thread-id="{u}" data-updated-at="{msgs[-1]["sent_at"]}"><a class="conv-link" href="/in/{u}/">{u}</a></li>'
                        for u, msgs in mock.conversations.items() if msgs)
                    return self._send(body=f"<ul>{items}</ul>")
                self._send(404, "not found")

            def do_POST(self):
                form = parse_qs(self.rfile.read(int(self.headers.get("Content-Length", 0))).decode())
                field = lambda name: form.get(name, [""])[0]
                parts = [p for p in self.path.split("?")[0].split("/") if p]
                if self.path == "/login":
                    if field("p") != mock.password:
                        return self._login_page(error=True)
                    identifier = field("u")
                    user = "phone" + "".join(c for c in identifier if c.isdigit()) if identifier.startswith("+") else identifier.split("@")[0].lower().split("+")[0]
                    pending = f"pending={user}; Path=/"
                    if user == "code":
                        return self._send(303, cookies=[pending], location="/checkpoint/challenge")
                    if user == "approve":
                        return self._send(303, cookies=[pending], location="/checkpoint/approval")
                    if user == "checkpoint":
                        return self._send(303, location="/checkpoint/unknown")
                    if user == "slow":
                        return self._send(303, location="/slow")
                    return self._signed_in_redirect(user)
                if self.path == "/checkpoint/challenge":
                    if field("pin") != mock.code:
                        return self._challenge_page(error=True)
                    return self._signed_in_redirect(self._cookies().get("pending", "code"))
                if not self._signed_in():
                    return self._redirect("/login")
                if parts[:1] == ["in"] and len(parts) == 3 and parts[2] == "connect":
                    if self._consume_fault():
                        return
                    time.sleep(mock.commit_delay)  # lets a test stop the worker while the invitation is being sent
                    note = field("note")
                    if len(note) > 300:
                        return self._send(body='<div id="note-error">Note is too long</div>')
                    mock.invites.append((parts[1], note))
                    mock.profile(parts[1])["state"] = "pending"
                    return self._redirect(f"/in/{parts[1]}/")
                if parts[:1] == ["in"] and len(parts) == 3 and parts[2] == "withdraw":
                    if self._consume_fault():
                        return
                    mock.withdrawals.append(parts[1])
                    mock.profile(parts[1])["state"] = "not_connected"
                    return self._redirect(f"/in/{parts[1]}/")
                if parts[:2] == ["feed", "update"] and len(parts) == 4 and parts[3] in ("react", "comment"):
                    if self._consume_fault():
                        return
                    state = mock.post(parts[2].rsplit(":", 1)[1])
                    if parts[3] == "react":
                        state["reaction"] = field("reaction")
                    else:
                        state["comments"].append(field("text"))
                    return self._redirect(f"/feed/update/{parts[2]}/")
                if parts[:1] == ["in"] and len(parts) == 3 and parts[2] == "like":
                    if self._consume_fault():
                        return
                    mock.likes.append(parts[1])
                    mock.profile(parts[1])["liked"] = True
                    return self._redirect(f"/in/{parts[1]}/recent-activity/all/")
                if parts[:2] == ["messaging", "inmail"] and len(parts) == 3:
                    if self._consume_fault():
                        return
                    if mock.profile(parts[2])["inmail"] == "credit":
                        mock.inmail_credits -= 1
                    mock.inmails.append((parts[2], field("subject"), field("text")))
                    mock._add_message(parts[2], "out", field("text"))
                    return self._redirect(f"/in/{parts[2]}/")
                if parts[:2] == ["messaging", "voice"] and len(parts) == 3:
                    if self._consume_fault():
                        return
                    mock.voice_notes.append((parts[2], field("name"), int(field("size") or 0)))
                    mock._add_message(parts[2], "out", "[Voice note]")
                    return self._redirect(f"/messaging/compose/{parts[2]}/")
                if parts[:1] == ["in"] and len(parts) == 3 and parts[2] == "follow":
                    if self._consume_fault():
                        return
                    mock.follows.append(parts[1])
                    mock.profile(parts[1])["following"] = True
                    return self._redirect(f"/in/{parts[1]}/")
                if parts[:2] == ["messaging", "compose"] and len(parts) == 3:
                    if self._consume_fault():
                        return
                    mock.sent_messages.append((parts[2], field("text")))
                    mock._add_message(parts[2], "out", field("text"))
                    return self._redirect(f"/messaging/compose/{parts[2]}/")
                self._send(404, "not found")

        return Handler


_shared: "MockLinkedIn | None" = None


def shared_mock() -> MockLinkedIn:
    """One mock site per test process, started once and stopped at exit, so every test module can use it."""
    global _shared
    if _shared is None:
        _shared = MockLinkedIn().start()
        atexit.register(_shared.stop)
    return _shared


def pages_from_env() -> ProfilePages:
    """OUTREACH_PAGES_FACTORY target: lets a real worker process run against the mock site."""
    site = Site(os.environ["MOCK_LINKEDIN_URL"], MOCK_SELECTORS)
    return ProfilePages(site, MOCK_PROFILE_SELECTORS)
