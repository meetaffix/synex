"""Additive publishing tables. Legacy business records remain untouched."""
from sqlalchemy import Column, String, Text, Integer, DateTime, ForeignKey, JSON, UniqueConstraint, LargeBinary, Boolean
from .database import Base
from .models import _uuid, _now


class OAuthState(Base):
    __tablename__ = "oauth_states"
    digest = Column(String, primary_key=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=True)
    actor_id = Column(String, ForeignKey("users.id"))
    target_id = Column(String)
    browser_digest = Column(String, nullable=False)
    nonce = Column(String, nullable=False)
    purpose = Column(String, nullable=False)
    scopes = Column(String, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)


class Connection(Base):
    __tablename__ = "oauth_connections"
    __table_args__ = (UniqueConstraint("user_id", "subject"),)
    id = Column(String, primary_key=True, default=_uuid)
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    subject = Column(String, nullable=False)
    name = Column(String, nullable=False)
    picture = Column(String)
    email = Column(String)
    access_token = Column(Text)
    expires_at = Column(DateTime(timezone=True))
    scopes = Column(JSON, default=list)
    status = Column(String, default="connected")
    checked_at = Column(DateTime(timezone=True), default=_now)


class LinkedInIdentity(Base):
    __tablename__ = "linkedin_identities"
    subject = Column(String, primary_key=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)


class SessionToken(Base):
    __tablename__ = "app_sessions"
    digest = Column(String, primary_key=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)


class Post(Base):
    __tablename__ = "content_posts"
    id = Column(String, primary_key=True, default=_uuid)
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    account_id = Column(String, ForeignKey("oauth_connections.id"))
    title = Column(String, default="")
    body = Column(Text, default="")
    status = Column(String, default="draft", nullable=False, index=True)
    scheduled_at = Column(DateTime(timezone=True), index=True)
    timezone = Column(String, default="UTC")
    version = Column(Integer, nullable=False, default=1)
    attempts = Column(Integer, nullable=False, default=0)
    claimed_at = Column(DateTime(timezone=True))
    linkedin_id = Column(String)
    has_image = Column(Boolean, default=False)
    error = Column(Text)
    created_at = Column(DateTime(timezone=True), default=_now)
    updated_at = Column(DateTime(timezone=True), default=_now, onupdate=_now)


class Execution(Base):
    __tablename__ = "publishing_executions"
    id = Column(String, primary_key=True, default=_uuid)
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    post_id = Column(String, ForeignKey("content_posts.id"), nullable=False, index=True)
    status = Column(String, nullable=False)
    detail = Column(Text)
    created_at = Column(DateTime(timezone=True), default=_now)


class PostImage(Base):
    __tablename__ = "content_post_images"
    post_id = Column(String, ForeignKey("content_posts.id", ondelete="CASCADE"), primary_key=True)
    content_type = Column(String, nullable=False)
    data = Column(LargeBinary, nullable=False)


class WorkerHeartbeat(Base):
    __tablename__ = "publishing_workers"
    id = Column(String, primary_key=True)
    checked_at = Column(DateTime(timezone=True), default=_now)


class Preference(Base):
    __tablename__ = "publishing_preferences"
    user_id = Column(String, ForeignKey("users.id"), primary_key=True)
    timezone = Column(String, default="UTC")


class Migration(Base):
    __tablename__ = "schema_migrations"
    version = Column(String, primary_key=True)
    applied_at = Column(DateTime(timezone=True), default=_now)


class ReviewLink(Base):
    """A private link that lets one named person read a post and leave feedback, without an account. Only a hash of the token is stored."""
    __tablename__ = "post_review_links"
    id = Column(String, primary_key=True, default=_uuid)
    post_id = Column(String, ForeignKey("content_posts.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    reviewer = Column(String, nullable=False)
    token_hash = Column(String, nullable=False, unique=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    revoked_at = Column(DateTime(timezone=True))
    last_seen_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), default=_now)


class ReviewFeedback(Base):
    """One message in a post's feedback thread: from the owner, or from a reviewer through their link."""
    __tablename__ = "post_review_feedback"
    id = Column(String, primary_key=True, default=_uuid)
    post_id = Column(String, ForeignKey("content_posts.id", ondelete="CASCADE"), nullable=False, index=True)
    link_id = Column(String, ForeignKey("post_review_links.id", ondelete="SET NULL"))
    author = Column(String, nullable=False)
    decision = Column(String, default="comment")  # comment | approve | changes
    body = Column(Text, default="")
    post_version = Column(Integer)
    created_at = Column(DateTime(timezone=True), default=_now)
