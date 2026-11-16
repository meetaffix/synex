from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    Index,
    Table,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from .database import Base


def _uuid() -> str:
    return uuid.uuid4().hex


def _now() -> datetime:
    return datetime.now(timezone.utc)


# Many-to-many: a lead can live in several lists, a list holds many leads.
lead_list_members = Table(
    "lead_list_members",
    Base.metadata,
    Column("lead_id", String, ForeignKey("leads.id", ondelete="CASCADE"), primary_key=True),
    Column("list_id", String, ForeignKey("lead_lists.id", ondelete="CASCADE"), primary_key=True),
)


class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=_uuid)
    email = Column(String, unique=True, nullable=False, index=True)
    full_name = Column(String, nullable=False)
    hashed_password = Column(String, nullable=False)
    company = Column(String, nullable=True)
    role = Column(String, default="Member")
    plan = Column(String, default="free")  # free | pro | scale
    avatar_url = Column(String, nullable=True)
    # The Clerk user this row is linked to (nullable: set on first Clerk sign-in, matched by verified email).
    clerk_user_id = Column(String, nullable=True)

    # Account settings (persisted, no hardcoded UI defaults).
    notification_prefs = Column(JSON, default=dict)  # {pref_id: bool}
    two_factor_enabled = Column(Boolean, default=False)
    integrations = Column(JSON, default=list)  # [{provider, connected, config}]

    created_at = Column(DateTime(timezone=True), default=_now)

    accounts = relationship("LinkedInAccount", back_populates="user", cascade="all, delete-orphan")
    lead_lists = relationship("LeadList", back_populates="user", cascade="all, delete-orphan")
    leads = relationship("Lead", back_populates="user", cascade="all, delete-orphan")
    campaigns = relationship("Campaign", back_populates="user", cascade="all, delete-orphan")
    conversations = relationship("Conversation", back_populates="user", cascade="all, delete-orphan")
    templates = relationship("Template", back_populates="user", cascade="all, delete-orphan")


class PasswordResetToken(Base):
    """A single-use, time-limited password-reset token."""

    __tablename__ = "password_reset_tokens"

    id = Column(String, primary_key=True, default=_uuid)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    token = Column(String, unique=True, nullable=False, index=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    used = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), default=_now)

    user = relationship("User")


class LinkedInAccount(Base):
    __tablename__ = "linkedin_accounts"

    id = Column(String, primary_key=True, default=_uuid)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name = Column(String, nullable=False)
    email = Column(String, nullable=True)
    headline = Column(String, nullable=True)
    linkedin_url = Column(String, nullable=True)
    avatar_url = Column(String, nullable=True)
    # Lifecycle intent: pending (awaiting extension pairing) | active | paused.
    # The displayed status also factors in the extension heartbeat.
    status = Column(String, default="pending")
    # A new account starts STOPPED (0) until its owner sets a limit; the warm-up then starts at 5 a day. Existing accounts keep theirs.
    daily_action_limit = Column(Integer, default=0)
    daily_actions_used = Column(Integer, default=0)
    last_action_date = Column(String, nullable=True)  # ISO date of the daily_actions_used window
    # Per-type counters within the same daily window (for the health dashboard).
    messages_today = Column(Integer, default=0)
    connections_today = Column(Integer, default=0)
    messages_sent = Column(Integer, default=0)
    connections_sent = Column(Integer, default=0)
    last_sync_at = Column(DateTime(timezone=True), default=_now)
    created_at = Column(DateTime(timezone=True), default=_now)
    # Earliest time this account may perform its next outreach action. The engine
    # sets it after each emitted task to spread the daily quota across the
    # working window (human-like pacing) instead of bursting.
    next_action_at = Column(DateTime(timezone=True), nullable=True)
    # When this account first started sending. Used to ramp the effective daily
    # limit up gradually (warm-up) so a fresh account doesn't blast its full
    # quota from day one. Set on the first emitted action.
    warmup_started_at = Column(DateTime(timezone=True), nullable=True)

    # Browser-extension pairing. The token authenticates the extension as this
    # account; the session itself never leaves the user's browser.
    agent_token = Column(String, unique=True, nullable=True, index=True)
    agent_last_seen_at = Column(DateTime(timezone=True), nullable=True)
    # Set by "Sync now" in the UI; the extension picks it up on its next poll.
    sync_requested = Column(Boolean, default=False)

    # Cloud execution mode — tasks are executed server-side via the Voyager API
    # instead of by the browser extension, using stored encrypted cookies routed
    # through a per-account residential proxy.
    # extension (default) | cloud
    execution_mode = Column(String, default="extension")
    # Fernet-encrypted LinkedIn li_at and JSESSIONID cookies.
    li_at_encrypted = Column(Text, nullable=True)
    jsessionid_encrypted = Column(Text, nullable=True)
    cookie_harvested_at = Column(DateTime(timezone=True), nullable=True)
    # active | paused | cookie_expired | proxy_error
    cloud_status = Column(String, nullable=True)
    # Set by "Enable cloud mode" in the UI; the extension harvests cookies on
    # its next poll and POSTs them back via POST /agent {action: "harvest"}.
    harvest_session_requested = Column(Boolean, default=False)

    # Server-side Playwright session (app/linkedin_session). The storage state
    # and proxy URL are Fernet-encrypted; no password is ever stored.
    session_state_encrypted = Column(Text, nullable=True)
    # connected | needs_reconnect | restricted | disconnected (NULL = never connected)
    session_status = Column(String, nullable=True)
    # Fixed at first connect: {userAgent, viewport, locale, timezoneId}.
    browser_profile = Column(JSON, nullable=True)
    proxy_url_encrypted = Column(Text, nullable=True)
    last_checked_at = Column(DateTime(timezone=True), nullable=True)
    connected_at = Column(DateTime(timezone=True), nullable=True)
    # Single-use reconnect link: only the SHA-256 digest of the token is kept.
    reconnect_token_digest = Column(String, nullable=True)
    reconnect_token_expires_at = Column(DateTime(timezone=True), nullable=True)
    # Failed sign-ins made with the current reconnect token; the token is invalidated at the cap.
    reconnect_token_failures = Column(Integer, default=0)
    # Email or E.164 phone number used to sign in (never a password).
    login_identifier = Column(String, nullable=True)
    # Which LinkedIn conversations may be imported: all | synex_only (NULL means synex_only).
    sync_mode = Column(String, nullable=True)
    # The workspace member who connected the account; only they may change sync_mode.
    connected_by_user_id = Column(String, nullable=True)
    # Why the executor stopped this account (shown in the account object); cleared on reconnect or resume.
    paused_reason = Column(String, nullable=True)
    last_inbox_sync_at = Column(DateTime(timezone=True), nullable=True)
    # Versioned sender policy. Defaults preserve existing limits; updates replace the JSON value.
    management_config = Column(JSON, nullable=True)

    user = relationship("User", back_populates="accounts")


class LeadList(Base):
    __tablename__ = "lead_lists"

    id = Column(String, primary_key=True, default=_uuid)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    color = Column(String, default="#7C5CFF")
    created_at = Column(DateTime(timezone=True), default=_now)

    user = relationship("User", back_populates="lead_lists")
    leads = relationship("Lead", secondary=lead_list_members, back_populates="lists")


class Lead(Base):
    __tablename__ = "leads"

    id = Column(String, primary_key=True, default=_uuid)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    first_name = Column(String, nullable=False, default="")
    last_name = Column(String, nullable=False, default="")
    company = Column(String, default="")
    job_title = Column(String, default="")
    headline = Column(Text, nullable=True)
    linkedin_url = Column(String, default="")
    email = Column(String, nullable=True)
    phone = Column(String, nullable=True)
    location = Column(String, nullable=True)
    industry = Column(String, nullable=True)
    # When this person became a 1st-degree connection (connections import).
    connected_at = Column(DateTime(timezone=True), nullable=True)
    mutual_connections = Column(Integer, nullable=True)
    # 1, 2 or 3 (3 = 3rd or beyond) as LinkedIn showed it when the lead was collected; None when unknown.
    connection_degree = Column(Integer, nullable=True)
    tags = Column(JSON, default=list)
    # Where the lead came from: csv | connections | search_url | inbox_sync | manual
    source = Column(String, nullable=True)
    # new | contacted | connected | replied | interested | not_interested | bounced
    status = Column(String, default="new")
    notes = Column(Text, nullable=True)
    campaign_id = Column(String, ForeignKey("campaigns.id", ondelete="SET NULL"), nullable=True)
    avatar_url = Column(String, nullable=True)
    # Optional IANA timezone; overrides the campaign timezone for working hours.
    timezone = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now)
    updated_at = Column(DateTime(timezone=True), default=_now, onupdate=_now)

    user = relationship("User", back_populates="leads")
    lists = relationship("LeadList", secondary=lead_list_members, back_populates="leads")
    campaign = relationship("Campaign", back_populates="leads")


class Campaign(Base):
    __tablename__ = "campaigns"

    id = Column(String, primary_key=True, default=_uuid)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    status = Column(String, default="draft")  # draft | active | paused | completed
    account_id = Column(String, ForeignKey("linkedin_accounts.id", ondelete="SET NULL"), nullable=True)
    # Additional sending accounts for load balancing. The engine distributes
    # tasks across [account_id] + account_ids, picking the live account with
    # the most remaining daily capacity per action.
    account_ids = Column(JSON, default=list)
    lead_list_id = Column(String, ForeignKey("lead_lists.id", ondelete="SET NULL"), nullable=True)

    # Sending configuration
    daily_connection_limit = Column(Integer, default=20)
    daily_message_limit = Column(Integer, default=40)
    timezone = Column(String, default="America/New_York")
    start_hour = Column(Integer, default=9)
    end_hour = Column(Integer, default=17)
    working_days = Column(JSON, default=lambda: [1, 2, 3, 4, 5])

    # Behaviour settings (campaign wizard, step 5).
    random_delay = Column(Boolean, default=True)
    stop_when_replied = Column(Boolean, default=True)
    stop_when_accepted = Column(Boolean, default=False)
    ai_personalization = Column(Boolean, default=False)
    # Pause the whole campaign (instead of stopping just the run) when a
    # prospect exhausts its retry budget — lets the user investigate first.
    pause_on_failure = Column(Boolean, default=False)
    # How the prospect list was built: {"type": "...", "filters": {...}, "sourceUrl": "..."}
    audience_source = Column(JSON, nullable=True)

    launched_at = Column(DateTime(timezone=True), nullable=True)
    # Consecutive failed tasks; reset by any success. Drives pause_on_failure.
    consecutive_failures = Column(Integer, default=0)
    paused_reason = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now)
    updated_at = Column(DateTime(timezone=True), default=_now, onupdate=_now)

    user = relationship("User", back_populates="campaigns")
    account = relationship("LinkedInAccount")
    lead_list = relationship("LeadList")
    leads = relationship("Lead", back_populates="campaign")
    steps = relationship(
        "CampaignStep",
        back_populates="campaign",
        cascade="all, delete-orphan",
        order_by="CampaignStep.order",
    )
    conversations = relationship("Conversation", back_populates="campaign")


class CampaignStep(Base):
    __tablename__ = "campaign_steps"

    id = Column(String, primary_key=True, default=_uuid)
    campaign_id = Column(String, ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False)
    type = Column(String, nullable=False)  # connection_request | message | follow_up | wait | end
    order = Column(Integer, default=0)
    message = Column(Text, nullable=True)
    delay_hours = Column(Integer, nullable=True)
    # Reserved for conditional branches; execution is not implemented yet.
    parent_step_id = Column(String, nullable=True)
    branch_condition = Column(JSON, nullable=True)

    campaign = relationship("Campaign", back_populates="steps")


class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(String, primary_key=True, default=_uuid)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    lead_id = Column(String, ForeignKey("leads.id", ondelete="CASCADE"), nullable=False)
    campaign_id = Column(String, ForeignKey("campaigns.id", ondelete="SET NULL"), nullable=True)
    account_id = Column(String, ForeignKey("linkedin_accounts.id", ondelete="SET NULL"), nullable=True)
    # LinkedIn's own conversation id — used to dedupe synced threads.
    li_conversation_id = Column(String, nullable=True, index=True)
    last_message_preview = Column(Text, default="")
    last_message_at = Column(DateTime(timezone=True), default=_now)
    unread = Column(Boolean, default=False)
    status = Column(String, default="active")  # active | interested | not_interested | archived

    user = relationship("User", back_populates="conversations")
    lead = relationship("Lead")
    campaign = relationship("Campaign", back_populates="conversations")
    messages = relationship(
        "Message",
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="Message.sent_at",
    )


class Message(Base):
    __tablename__ = "messages"

    id = Column(String, primary_key=True, default=_uuid)
    conversation_id = Column(String, ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False)
    direction = Column(String, nullable=False)  # inbound | outbound
    body = Column(Text, nullable=False)
    sent_at = Column(DateTime(timezone=True), default=_now)
    read = Column(Boolean, default=True)
    # LinkedIn's event id — used to dedupe synced messages.
    li_event_id = Column(String, nullable=True, index=True)
    # Delivery state for outbound replies queued from the unibox. Synced and
    # campaign-driven messages are "sent" on arrival; a manual reply starts
    # "queued" and flips to "sent" / "failed" when the extension reports back.
    delivery_status = Column(String, default="sent")  # queued | sent | failed
    delivery_error = Column(String, nullable=True)
    # The executor task that sent this message; lets a re-check prove it was already sent.
    task_id = Column(String, nullable=True, index=True)

    conversation = relationship("Conversation", back_populates="messages")


class LeadDraft(Base):
    """A message prepared BEFORE a campaign sends, for one lead and one step.

    AI personalization happens here, at campaign preparation, never while sending: the engine sends only finished
    text. A draft starts as ``proposed``; the user reviews and edits it and approves it, and only an ``approved``
    draft is sent. A lead without an approved draft gets the step's template with variables and spintax.
    """

    __tablename__ = "lead_drafts"
    __table_args__ = (UniqueConstraint("campaign_id", "step_id", "lead_id", name="ux_lead_drafts_campaign_step_lead"),)

    id = Column(String, primary_key=True, default=_uuid)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    campaign_id = Column(String, ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False, index=True)
    step_id = Column(String, ForeignKey("campaign_steps.id", ondelete="CASCADE"), nullable=False)
    lead_id = Column(String, ForeignKey("leads.id", ondelete="CASCADE"), nullable=False, index=True)
    body = Column(Text, nullable=False)
    status = Column(String, default="proposed", nullable=False)  # proposed | approved
    source = Column(String, default="ai", nullable=False)  # ai (Deepgram) | template (fallback) | edited (by a person)
    created_at = Column(DateTime(timezone=True), default=_now)
    approved_at = Column(DateTime(timezone=True), nullable=True)


class Template(Base):
    __tablename__ = "templates"

    id = Column(String, primary_key=True, default=_uuid)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name = Column(String, nullable=False)
    category = Column(String, default="first_message")  # connection | first_message | follow_up | reply
    body = Column(Text, nullable=False, default="")
    usage_count = Column(Integer, default=0)
    reply_rate = Column(Float, default=0.0)
    created_at = Column(DateTime(timezone=True), default=_now)
    updated_at = Column(DateTime(timezone=True), default=_now, onupdate=_now)

    user = relationship("User", back_populates="templates")


class SequenceRun(Base):
    """Per-(campaign, lead) execution state for the outreach engine.

    The engine advances each run through the campaign's steps, respecting wait
    delays and the sequence rules. Acceptance / replies are driven by real
    signals (inbox or a connected provider) — never fabricated.
    """

    __tablename__ = "sequence_runs"

    id = Column(String, primary_key=True, default=_uuid)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    campaign_id = Column(String, ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False)
    lead_id = Column(String, ForeignKey("leads.id", ondelete="CASCADE"), nullable=False)
    current_step_order = Column(Integer, default=0)  # legacy; position is current_step_id
    # The step this run is on. Stored by id so steps can be added to a live campaign.
    current_step_id = Column(String, nullable=True)
    last_acceptance_check_at = Column(DateTime(timezone=True), nullable=True)
    # running | waiting_connection | awaiting_agent | needs_review | completed | stopped
    status = Column(String, default="running")
    stop_reason = Column(String, nullable=True)  # replied | not_interested | interested | ended
    next_action_at = Column(DateTime(timezone=True), default=_now)
    started_at = Column(DateTime(timezone=True), default=_now)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    campaign = relationship("Campaign")
    lead = relationship("Lead")


class ImportJob(Base):
    """A prospect-import request. CSV imports complete immediately; URL-based
    sources are recorded for a connected LinkedIn provider to fulfil."""

    __tablename__ = "import_jobs"

    id = Column(String, primary_key=True, default=_uuid)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    # csv | search_url | sales_navigator_url | post_url
    source = Column(String, nullable=False)
    source_url = Column(String, nullable=True)
    list_ids = Column(JSON, default=list)
    status = Column(String, default="pending")  # pending | processing | completed | failed
    created_count = Column(Integer, default=0)
    # Live progress reported by the extension while it pages through results.
    fetched_count = Column(Integer, default=0)
    total_count = Column(Integer, nullable=True)
    detail = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now)
    # Bumped on every progress/results report. A processing job whose updated_at
    # goes stale (extension died mid-import) is swept to "failed" so the UI never
    # spins forever. onupdate fires on any UPDATE to this row.
    updated_at = Column(DateTime(timezone=True), default=_now, onupdate=_now)


class LeadEvent(Base):
    """An immutable audit-trail entry for a lead.

    Every meaningful transition (imported, connection sent, accepted, message
    sent, replied, status change, enriched, meeting booked…) writes one row, so
    a lead's full history across campaigns can be reconstructed and the
    dashboard activity feed reflects real events.
    """

    __tablename__ = "lead_events"

    id = Column(String, primary_key=True, default=_uuid)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    lead_id = Column(String, ForeignKey("leads.id", ondelete="CASCADE"), nullable=False, index=True)
    campaign_id = Column(String, ForeignKey("campaigns.id", ondelete="SET NULL"), nullable=True)
    account_id = Column(String, ForeignKey("linkedin_accounts.id", ondelete="SET NULL"), nullable=True)
    # imported | enriched | connection_sent | connected | message_sent |
    # replied | status_changed | interested | not_interested | meeting_booked |
    # closed | added_to_campaign | note
    type = Column(String, nullable=False)
    detail = Column(String, nullable=True)
    step_id = Column(String, nullable=True)
    task_id = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now, index=True)

    lead = relationship("Lead")
    campaign = relationship("Campaign")


class TeamMember(Base):
    """A seat in a workspace.

    The workspace is identified by its owner (the user who signed up and owns
    the data). A member authenticates as themselves but reads/writes the
    owner's workspace, gated by their role:

    * admin   — everything, including LinkedIn accounts and team management
    * manager — campaigns, leads, lists, templates, inbox
    * member  — read-only data access plus working the inbox
    """

    __tablename__ = "team_members"

    id = Column(String, primary_key=True, default=_uuid)
    owner_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    # Null until the invited email signs up / accepts.
    member_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    email = Column(String, nullable=False)
    role = Column(String, default="member")  # admin | manager | member
    status = Column(String, default="invited")  # invited | active
    created_at = Column(DateTime(timezone=True), default=_now)

    owner = relationship("User", foreign_keys=[owner_id])
    member = relationship("User", foreign_keys=[member_id])


class AgentTask(Base):
    """A unit of work the browser extension executes against LinkedIn.

    The backend (engine) emits tasks; the extension pulls them, performs the
    action in the user's logged-in tab, and reports the result back.
    """

    __tablename__ = "agent_tasks"

    id = Column(String, primary_key=True, default=_uuid)
    account_id = Column(String, ForeignKey("linkedin_accounts.id", ondelete="CASCADE"), nullable=False)
    sequence_run_id = Column(String, ForeignKey("sequence_runs.id", ondelete="CASCADE"), nullable=True)
    # send_invite | send_message | visit_profile | follow_profile | like_post
    type = Column(String, nullable=False)
    payload = Column(JSON, default=dict)
    # pending | running | done | failed | needs_review | cancelled
    status = Column(String, default="pending")
    result = Column(JSON, nullable=True)
    attempts = Column(Integer, default=0)
    # run id + step id (or a reply/inbox key). Unique: the same action can never be queued twice.
    idempotency_key = Column(String, nullable=True)
    # Atomic claim: a versioned UPDATE moves pending -> running for exactly one worker.
    claimed_by = Column(String, nullable=True)
    claimed_at = Column(DateTime(timezone=True), nullable=True)
    version = Column(Integer, default=0)
    next_attempt_at = Column(DateTime(timezone=True), nullable=True)
    # Set just before the irreversible click. A task with this set is never retried automatically.
    committed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now)
    updated_at = Column(DateTime(timezone=True), default=_now, onupdate=_now)

    __table_args__ = (Index("ux_agent_tasks_idempotency", "idempotency_key", unique=True),)

    account = relationship("LinkedInAccount")
    sequence_run = relationship("SequenceRun")


class AgentActivity(Base):
    """A real-time progress event emitted by the browser extension.

    The extension reports what it is doing as it does it (connecting, fetching
    connections, processing profiles, syncing conversations, saving leads,
    completed/failed). The CRM reads these back to render a live progress log,
    so the user can tell whether the agent is running, stalled, or has failed —
    instead of staring at a single static number. Best-effort and append-only;
    old rows are pruned per account to keep the log bounded.
    """

    __tablename__ = "agent_activity"

    id = Column(String, primary_key=True, default=_uuid)
    account_id = Column(String, ForeignKey("linkedin_accounts.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    # cycle | connections_import | inbox_sync | task
    scope = Column(String, nullable=False, default="cycle")
    # Ties an event to an ImportJob when the work is an import (nullable otherwise).
    job_id = Column(String, nullable=True, index=True)
    # Short slug: connecting | fetching_connections | processing_profiles |
    # saving_leads | syncing_conversations | completed | …
    step = Column(String, nullable=False)
    # running | ok | warn | error
    status = Column(String, nullable=False, default="running")
    message = Column(Text, nullable=True)
    # Optional progress counters (e.g. profiles fetched so far / total).
    count = Column(Integer, nullable=True)
    total = Column(Integer, nullable=True)
    # Executor audit: which campaign step ran, which task, and its outcome.
    campaign_id = Column(String, nullable=True, index=True)
    step_id = Column(String, nullable=True)
    task_id = Column(String, nullable=True, index=True)
    result = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now, index=True)

    account = relationship("LinkedInAccount")


class OutreachControl(Base):
    """Single-row control plane for the outreach executor (id is always "global")."""

    __tablename__ = "outreach_controls"

    id = Column(String, primary_key=True, default="global")
    kill_switch = Column(Boolean, default=False)
    updated_by = Column(String, nullable=True)
    updated_at = Column(DateTime(timezone=True), default=_now, onupdate=_now)


class AccountLease(Base):
    """Which worker may hold a browser session for an account. Acquired with one conditional
    upsert, so two workers can never both hold it; it expires if its holder dies."""

    __tablename__ = "account_leases"

    account_id = Column(String, ForeignKey("linkedin_accounts.id", ondelete="CASCADE"), primary_key=True)
    holder = Column(String, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)


class LeadCollection(Base):
    """One "add leads" request: a source, its parameters, the sender that reads LinkedIn, and where the people go.

    draft -> previewing -> preview_ready -> queued -> running -> completed | stopped | failed.
    Sources that never touch LinkedIn (pasted URLs, CSV, existing lists, inbox contacts) resolve in the API and skip
    the queued/running states. People found are staged in ``LeadCollectionItem`` and only become leads on import.
    """

    __tablename__ = "lead_collections"

    id = Column(String, primary_key=True, default=_uuid)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    account_id = Column(String, ForeignKey("linkedin_accounts.id", ondelete="SET NULL"), nullable=True)
    source = Column(String, nullable=False)
    params = Column(JSON, default=dict)          # source URLs, reaction types, filters, column mapping, ...
    options = Column(JSON, default=dict)         # degrees, skip_in_campaign, skip_contacted, skip_connected
    list_name = Column(String, nullable=False, default="")
    max_leads = Column(Integer, nullable=False, default=50)
    status = Column(String, default="draft")
    fetched_count = Column(Integer, default=0)
    created_count = Column(Integer, default=0)
    skipped = Column(JSON, default=dict)         # reason -> count
    preview = Column(JSON, nullable=True)        # {"people": [first 10], "degrees": {"1": n, "2": n, "3": n, "unknown": n}}
    list_id = Column(String, nullable=True)
    stop_requested = Column(Boolean, default=False)
    detail = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now)
    updated_at = Column(DateTime(timezone=True), default=_now, onupdate=_now)


class LeadCollectionItem(Base):
    __tablename__ = "lead_collection_items"

    id = Column(String, primary_key=True, default=_uuid)
    collection_id = Column(String, ForeignKey("lead_collections.id", ondelete="CASCADE"), nullable=False, index=True)
    url_key = Column(String, nullable=False)     # dedup.normalize_linkedin_url
    profile_url = Column(String, nullable=False)
    name = Column(String, default="")
    headline = Column(Text, nullable=True)
    company = Column(String, nullable=True)
    location = Column(String, nullable=True)
    degree = Column(Integer, nullable=True)
    extra = Column(JSON, default=dict)           # CSV columns, email, ... carried to the lead
