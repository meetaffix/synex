"""Every step type a campaign sequence can contain: what it is, which executor task it becomes, and how its configuration is checked.

The Classic builder uses a straight list of steps. The Smart builder uses the same steps arranged as a tree: a conditional step ("If connection", "Is active on LinkedIn")
has two branches, "yes" and "no"; each branch is a list of steps of its own (`parent_step_id` is the conditional, `branch_condition` is {"branch": "yes"|"no"}).
A conditional ends its list: what happens next is in its branches. A list that runs out of steps ends the run, so "End" is implicit and optional.
"""
from __future__ import annotations

VOICE_LANGUAGES = ("en-US", "en-GB", "en-IN")
CONDITIONALS = ("if_connected", "if_active")
BRANCHES = ("yes", "no")

# type -> (label, kind, executor task or None)
STEP_TYPES: dict[str, tuple[str, str, str | None]] = {
    "connection_request": ("Send connection request", "message", "send_invite"),
    "message": ("Send message", "message", "send_message"),
    "follow_up": ("Send follow-up", "message", "send_message"),
    "voice_note": ("Send voice note", "voice", "send_voice_note"),
    "inmail": ("Send InMail", "inmail", "send_inmail"),
    "free_inmail": ("Send free InMail", "inmail", "send_inmail"),
    "profile_visit": ("View profile", "action", "visit_profile"),
    "follow": ("Follow profile", "action", "follow_profile"),
    "follow_profile": ("Follow profile", "action", "follow_profile"),
    "like_post": ("Like a post", "action", "like_post"),
    "withdraw_invite": ("Withdraw invite", "action", "withdraw_invite"),
    "wait": ("Wait", "wait", None),
    "if_connected": ("If connection", "conditional", None),
    "if_active": ("Is active on LinkedIn", "conditional", None),
    "end": ("End", "end", None),
}

ACTION_TASKS = {t: spec[2] for t, spec in STEP_TYPES.items() if spec[1] == "action"}
MESSAGE_TYPES = tuple(t for t, spec in STEP_TYPES.items() if spec[1] == "message")
MIN_WAIT_MINUTES = 15
DEFAULT_CONNECTION_WAIT_DAYS = 15
DEFAULT_ACTIVE_DAYS = 30


def wait_minutes(step) -> int:
    """How long a wait step waits, in minutes: the exact figure when one was set, otherwise its hours."""
    minutes = (getattr(step, "config", None) or {}).get("minutes")
    return int(minutes) if minutes else int(step.delay_hours or 0) * 60


def known(step_type: str) -> bool:
    return step_type in STEP_TYPES


def check_config(step_type: str, config: dict | None) -> dict | None:
    """The configuration of a step, cleaned, or a ValueError that says what to fix."""
    config = dict(config or {})
    if step_type == "voice_note":
        mode = config.get("mode", "direct")
        if mode not in ("direct", "ai"):
            raise ValueError("A voice note is either recorded (direct) or written by AI from a script (ai).")
        language = config.get("language", "en-US")
        if language not in VOICE_LANGUAGES:
            raise ValueError("Choose English US, UK or India for the voice note.")
        out = {"mode": mode, "language": language}
        script = str(config.get("script") or "").strip()
        if len(script) > 1000:
            raise ValueError("The voice note script can be up to 1,000 characters.")
        if script:
            out["script"] = script
        if config.get("audioId"):
            out["audioId"] = str(config["audioId"])[:64]
        return out
    if step_type in ("inmail", "free_inmail"):
        subject = str(config.get("subject") or "").strip()
        if len(subject) > 200:
            raise ValueError("An InMail subject can be up to 200 characters.")
        return {"subject": subject} if subject else {}
    if step_type == "wait":
        minutes = config.get("minutes")
        if minutes is None:
            return None
        if not isinstance(minutes, int) or isinstance(minutes, bool) or not 15 <= minutes <= 60 * 24 * 90:
            raise ValueError("A wait in minutes is at least 15 minutes and at most 90 days.")
        return {"minutes": minutes}
    if step_type == "if_connected":
        days = config.get("waitDays", DEFAULT_CONNECTION_WAIT_DAYS)
        if not isinstance(days, int) or isinstance(days, bool) or not 1 <= days <= 30:
            raise ValueError("Wait between 1 and 30 days for the person to accept.")
        return {"waitDays": days}
    if step_type == "if_active":
        days = config.get("days", DEFAULT_ACTIVE_DAYS)
        if not isinstance(days, int) or isinstance(days, bool) or not 1 <= days <= 365:
            raise ValueError("Active means activity in the last 1 to 365 days.")
        return {"days": days}
    return None


def check_branch(step_type: str, parent_type: str | None, condition: dict | None) -> None:
    """A step inside a branch names its conditional parent and the branch; a root step names neither."""
    if parent_type is None:
        if condition:
            raise ValueError("A step outside a branch has no branch condition.")
        return
    if parent_type not in CONDITIONALS:
        raise ValueError("Only an If step has branches.")
    if (condition or {}).get("branch") not in BRANCHES:
        raise ValueError("Say which branch the step belongs to: yes or no.")


def needs_setup(step_type: str, message: str | None, ai_config: dict | None, config: dict | None) -> str | None:
    """Why a step is not ready to run, or None. The Smart builder keeps Next disabled while any step has a reason."""
    ai = (ai_config or {}).get("mode") == "ai"
    config = config or {}
    if step_type in ("message", "follow_up") and not (message or "").strip() and not ai:
        return "Write the message."
    if step_type in ("inmail", "free_inmail") and not (message or "").strip() and not ai:
        return "Write the InMail."
    if step_type == "voice_note":
        if config.get("mode", "direct") == "ai" and not config.get("script"):
            return "Write the script for the voice note."
        if config.get("mode", "direct") == "direct" and not config.get("audioId"):
            return "Record or upload the voice note."
    return None
