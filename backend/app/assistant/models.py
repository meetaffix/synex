import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text

from ..database import Base


def _id() -> str:
    return uuid.uuid4().hex


def _now() -> datetime:
    return datetime.now(timezone.utc)


class AssistantSettings(Base):
    """One row per workspace (keyed by the workspace owner's user id)."""
    __tablename__ = "assistant_settings"
    workspace_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    enabled = Column(Boolean, default=True, nullable=False)
    monthly_minute_cap = Column(Integer, default=60, nullable=False)  # 0 stops the assistant
    idle_timeout_seconds = Column(Integer, default=120, nullable=False)
    history_enabled = Column(Boolean, default=False, nullable=False)  # transcripts are stored only when on
    language = Column(String, default="en", nullable=False)  # en | en-IN
    updated_at = Column(DateTime(timezone=True), default=_now, onupdate=_now)


class AssistantUsage(Base):
    __tablename__ = "assistant_usage"
    workspace_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    month = Column(String, primary_key=True)  # YYYY-MM, UTC
    seconds = Column(Float, default=0.0, nullable=False)


class AssistantAudit(Base):
    __tablename__ = "assistant_audit"
    id = Column(String, primary_key=True, default=_id)
    workspace_id = Column(String, nullable=False, index=True)
    user_id = Column(String, nullable=False, index=True)
    tool = Column(String, nullable=False)
    kind = Column(String, nullable=False)  # read | draft | write | system
    arguments = Column(JSON, default=dict)  # personal data minimised
    status = Column(String, nullable=False)  # ok | denied | invalid | error | proposed | applied | cancelled | failed
    result = Column(Text, nullable=True)
    via = Column(String, default="assistant", nullable=False)
    created_at = Column(DateTime(timezone=True), default=_now, index=True)


class AssistantProposal(Base):
    __tablename__ = "assistant_proposals"
    id = Column(String, primary_key=True, default=_id)
    workspace_id = Column(String, nullable=False, index=True)
    user_id = Column(String, nullable=False)
    tool = Column(String, nullable=False)
    arguments = Column(JSON, default=dict)
    summary = Column(Text, nullable=False)
    changes = Column(JSON, default=list)  # plain-words lines shown on the confirmation card
    status = Column(String, default="pending", nullable=False)  # pending | applied | cancelled | expired | failed
    result = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now)
    expires_at = Column(DateTime(timezone=True), nullable=False)


class AssistantMessage(Base):
    """Transcript lines. Written only while the workspace has history turned on. No audio is ever stored."""
    __tablename__ = "assistant_messages"
    id = Column(String, primary_key=True, default=_id)
    workspace_id = Column(String, nullable=False, index=True)
    user_id = Column(String, nullable=False, index=True)
    session_id = Column(String, nullable=False)
    role = Column(String, nullable=False)
    text = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), default=_now)
