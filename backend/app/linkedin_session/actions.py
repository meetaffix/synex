"""Outreach actions performed through an open LinkedIn browser session.

Each action navigates, checks for logged-out, restricted and checkpoint pages
(raising :class:`SessionError`, which makes the executor stop that account), and
returns a typed result. Anything irreversible happens only after
``ActionSession.before_commit`` has run, so the caller can record that the page was
touched; nothing here retries.

UNVERIFIED: the selectors behind these actions (see ``pages.REAL_PROFILE_SELECTORS``)
have never been run against linkedin.com. They are best effort and are expected to
need correction on first real use. The flows are tested against a local mock site.
No CAPTCHA or checkpoint is ever solved or bypassed.
"""
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum

from playwright.async_api import Page

from .pages import NOTE_LIMIT, ProfilePages, SessionProblem, ThreadMessage


class SessionError(Exception):
    """The session cannot act: logged out, restricted or stopped at a checkpoint."""

    def __init__(self, kind: SessionProblem) -> None:
        super().__init__(kind.value)
        self.kind = kind


class InviteResult(str, Enum):
    SENT = "sent"
    ALREADY_CONNECTED = "already_connected"
    ALREADY_PENDING = "already_pending"
    NOTE_TOO_LONG = "note_too_long"
    WEEKLY_LIMIT_REACHED = "weekly_limit_reached"
    PROFILE_UNAVAILABLE = "profile_unavailable"


class MessageResult(str, Enum):
    SENT = "sent"
    NOT_CONNECTED = "not_connected"
    PROFILE_UNAVAILABLE = "profile_unavailable"


class VisitResult(str, Enum):
    VISITED = "visited"
    PROFILE_UNAVAILABLE = "profile_unavailable"


class LikeResult(str, Enum):
    LIKED = "liked"
    ALREADY_LIKED = "already_liked"
    NO_POSTS = "no_posts"
    PROFILE_UNAVAILABLE = "profile_unavailable"


class InMailResult(str, Enum):
    SENT = "sent"
    ALREADY_CONNECTED = "already_connected"  # a normal message is possible, so no InMail is spent
    NO_CREDITS = "no_credits"
    NOT_FREE = "not_free"  # a free InMail was asked for but this profile does not offer one
    NOT_AVAILABLE = "not_available"
    PROFILE_UNAVAILABLE = "profile_unavailable"


class VoiceResult(str, Enum):
    SENT = "sent"
    NOT_CONNECTED = "not_connected"
    PROFILE_UNAVAILABLE = "profile_unavailable"


class EngageResult(str, Enum):
    DONE = "done"
    ALREADY_REACTED = "already_reacted"
    POST_UNAVAILABLE = "post_unavailable"


class FollowResult(str, Enum):
    FOLLOWED = "followed"
    ALREADY_FOLLOWING = "already_following"
    PROFILE_UNAVAILABLE = "profile_unavailable"


class ConnectionStatus(str, Enum):
    CONNECTED = "connected"
    PENDING = "pending"
    NOT_CONNECTED = "not_connected"
    PROFILE_UNAVAILABLE = "profile_unavailable"


@dataclass(frozen=True)
class WithdrawResult(str, Enum):
    WITHDRAWN = "withdrawn"
    NOT_PENDING = "not_pending"
    PROFILE_UNAVAILABLE = "profile_unavailable"


@dataclass(frozen=True)
class InboundConversation:
    thread_id: str
    profile_url: str
    messages: list[ThreadMessage]


async def _noop() -> None:
    return None


@dataclass
class ActionSession:
    page: Page
    pages: ProfilePages
    # Awaited right before an irreversible click (send, invite, follow).
    before_commit: Callable[[], Awaitable[None]] = field(default=_noop)


async def _open(session: ActionSession, profile_url: str) -> bool:
    """Open a profile; False when it is unavailable. Raises SessionError on a bad session."""
    await session.pages.goto(session.page, profile_url)
    await _guard(session)
    return not await session.pages.profile_unavailable(session.page)


async def _guard(session: ActionSession) -> None:
    problem = await session.pages.session_problem(session.page)
    if problem is not None:
        raise SessionError(problem)


async def visit_profile(session: ActionSession, profile_url: str) -> VisitResult:
    available = await _open(session, profile_url)
    return VisitResult.VISITED if available else VisitResult.PROFILE_UNAVAILABLE


async def get_connection_status(session: ActionSession, profile_url: str) -> ConnectionStatus:
    if not await _open(session, profile_url):
        return ConnectionStatus.PROFILE_UNAVAILABLE
    return ConnectionStatus(await session.pages.connection_state(session.page))


async def send_connection_request(session: ActionSession, profile_url: str, note: str | None = None) -> InviteResult:
    if note and len(note) > NOTE_LIMIT:
        return InviteResult.NOTE_TOO_LONG
    if not await _open(session, profile_url):
        return InviteResult.PROFILE_UNAVAILABLE
    state = await session.pages.connection_state(session.page)
    if state == "connected":
        return InviteResult.ALREADY_CONNECTED
    if state == "pending":
        return InviteResult.ALREADY_PENDING
    await session.pages.start_invite(session.page)
    await _guard(session)
    if await session.pages.invite_limit_reached(session.page):
        return InviteResult.WEEKLY_LIMIT_REACHED
    if note:
        await session.pages.fill_invite_note(session.page, note)
    await session.before_commit()
    await session.pages.submit_invite(session.page)
    await _guard(session)
    if await session.pages.invite_note_rejected(session.page):
        return InviteResult.NOTE_TOO_LONG
    if await session.pages.invite_limit_reached(session.page):
        return InviteResult.WEEKLY_LIMIT_REACHED
    return InviteResult.SENT


async def send_message(session: ActionSession, profile_url: str, text: str) -> MessageResult:
    if not await _open(session, profile_url):
        return MessageResult.PROFILE_UNAVAILABLE
    if await session.pages.connection_state(session.page) != "connected":
        return MessageResult.NOT_CONNECTED
    await session.pages.start_message(session.page)
    await _guard(session)
    await session.before_commit()
    await session.pages.submit_message(session.page, text)
    await _guard(session)
    if await session.pages.last_sent_text(session.page) != text.strip():
        raise RuntimeError("message was not confirmed in the thread")
    return MessageResult.SENT


async def withdraw_invite(session: ActionSession, profile_url: str) -> WithdrawResult:
    """Take back a connection request that is still pending. Does nothing when the person has accepted or it is not pending."""
    if not await _open(session, profile_url):
        return WithdrawResult.PROFILE_UNAVAILABLE
    if await session.pages.connection_state(session.page) != "pending":
        return WithdrawResult.NOT_PENDING
    await session.before_commit()
    await session.pages.withdraw_invite(session.page)
    await _guard(session)
    return WithdrawResult.WITHDRAWN if await session.pages.connection_state(session.page) != "pending" else WithdrawResult.PROFILE_UNAVAILABLE


async def like_post(session: ActionSession, profile_url: str) -> LikeResult:
    """Like the person's most recent post. UNVERIFIED on the real site (selectors are guesses)."""
    if not await _open(session, profile_url):
        return LikeResult.PROFILE_UNAVAILABLE
    await session.pages.open_activity(session.page, profile_url)
    await _guard(session)
    if not await session.pages.has_posts(session.page):
        return LikeResult.NO_POSTS
    if await session.pages.first_post_liked(session.page):
        return LikeResult.ALREADY_LIKED
    if not await session.pages.can_like(session.page):
        return LikeResult.NO_POSTS
    await session.before_commit()
    await session.pages.like_first_post(session.page)
    await _guard(session)
    return LikeResult.LIKED if await session.pages.first_post_liked(session.page) else LikeResult.NO_POSTS


async def send_inmail(session: ActionSession, profile_url: str, subject: str, text: str, free: bool) -> InMailResult:
    """An InMail (uses a credit) or a free InMail (an open profile) to someone who is not a connection. UNVERIFIED on the real site."""
    if not await _open(session, profile_url):
        return InMailResult.PROFILE_UNAVAILABLE
    if await session.pages.connection_state(session.page) == "connected":
        return InMailResult.ALREADY_CONNECTED
    if not await session.pages.can_open_inmail(session.page):
        return InMailResult.NOT_AVAILABLE
    await session.pages.start_inmail(session.page)
    await _guard(session)
    if await session.pages.inmail_out_of_credits(session.page) and not await session.pages.inmail_is_free(session.page):
        return InMailResult.NO_CREDITS
    if free and not await session.pages.inmail_is_free(session.page):
        return InMailResult.NOT_FREE
    await session.before_commit()
    await session.pages.submit_inmail(session.page, subject, text)
    await _guard(session)
    return InMailResult.SENT


async def send_voice_note(session: ActionSession, profile_url: str, audio_path: str) -> VoiceResult:
    """Attach a prepared audio file to a conversation and send it. UNVERIFIED on the real site, and LinkedIn may not accept audio files from a
    computer at all; the real test decides whether this path stays."""
    if not await _open(session, profile_url):
        return VoiceResult.PROFILE_UNAVAILABLE
    if await session.pages.connection_state(session.page) != "connected":
        return VoiceResult.NOT_CONNECTED
    await session.pages.start_message(session.page)
    await _guard(session)
    await session.before_commit()
    await session.pages.attach_and_send_audio(session.page, audio_path)
    await _guard(session)
    return VoiceResult.SENT


async def engage_post(session: ActionSession, post_url: str, reaction: str | None, comment: str | None) -> EngageResult:
    """React to a post and, or, comment on it, as the person asked by hand. UNVERIFIED on the real site (selectors are guesses)."""
    if not await _open(session, post_url):
        return EngageResult.POST_UNAVAILABLE
    already = await session.pages.has_reacted(session.page)
    if reaction and already and not comment:
        return EngageResult.ALREADY_REACTED
    await session.before_commit()
    if reaction and not already:
        await session.pages.react(session.page, reaction)
        await _guard(session)
    if comment:
        await session.pages.comment(session.page, comment)
        await _guard(session)
    return EngageResult.DONE


async def follow_profile(session: ActionSession, profile_url: str) -> FollowResult:
    if not await _open(session, profile_url):
        return FollowResult.PROFILE_UNAVAILABLE
    if await session.pages.is_following(session.page):
        return FollowResult.ALREADY_FOLLOWING
    if not await session.pages.can_follow(session.page):
        return FollowResult.PROFILE_UNAVAILABLE
    await session.before_commit()
    await session.pages.follow(session.page)
    await _guard(session)
    return FollowResult.FOLLOWED if await session.pages.is_following(session.page) else FollowResult.PROFILE_UNAVAILABLE


async def fetch_new_messages(session: ActionSession, since: datetime | None) -> list[InboundConversation]:
    """Conversations updated after ``since`` (all of them when it is None), with their messages."""
    refs = await session.pages.list_conversations(session.page, since)
    await _guard(session)
    cutoff = since.astimezone(timezone.utc) if since else None
    conversations: list[InboundConversation] = []
    for ref in refs:
        if cutoff and datetime.fromisoformat(ref.updated_at) <= cutoff:
            continue
        messages = await session.pages.read_thread(session.page, ref.thread_id)
        await _guard(session)
        conversations.append(InboundConversation(ref.thread_id, ref.profile_url, messages))
    return conversations
