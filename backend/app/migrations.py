"""Versioned, repeatable migration; no business data is deleted."""
import logging
import time

from sqlalchemy import text
from sqlalchemy.exc import OperationalError, ProgrammingError

from .config import DAILY_ACTION_CEILING, DAILY_TYPE_CEILINGS
from .database import Base, engine, SessionLocal, run_simple_migrations
from . import models, publishing_models as p

log = logging.getLogger(__name__)


def create_tables(attempts: int = 5) -> None:
    """create_all, retried: the API and both workers run it at boot, and when a deploy starts them together two can try to create
    the same table at once. create_all checks what exists on each call, so a retry finds the other process's table and moves on."""
    for attempt in range(1, attempts + 1):
        try:
            Base.metadata.create_all(engine)
            return
        except (ProgrammingError, OperationalError) as exc:
            if attempt == attempts or "already exists" not in str(exc).lower():
                raise
            log.warning("another process created a table at the same time (attempt %s of %s): retrying", attempt, attempts)
            time.sleep(attempt)


def migrate():
    create_tables()
    run_simple_migrations()
    from . import plans
    with SessionLocal() as db:
        plans.ensure_plans(db)
    with SessionLocal() as db:
        if not db.get(p.Migration, "002_official_publishing"):
            # Deliberately remove credentials for the retired private API path.
            # Keep profile, leads, conversations, campaign and task history.
            db.query(models.LinkedInAccount).update({
                models.LinkedInAccount.agent_token: None,
                models.LinkedInAccount.li_at_encrypted: None,
                models.LinkedInAccount.jsessionid_encrypted: None,
                models.LinkedInAccount.harvest_session_requested: False,
                models.LinkedInAccount.status: "pending",
                models.LinkedInAccount.execution_mode: "disabled",
            })
            db.query(models.Campaign).filter_by(status="active").update({"status": "paused"})
            db.query(models.ImportJob).filter(models.ImportJob.status.in_(["pending", "processing"])).update({"status": "failed", "detail": "Private API import retired. Import an authorized CSV instead."})
            db.query(models.AgentTask).filter(models.AgentTask.status.in_(["pending", "running"])).update({"status": "cancelled"})
            db.add(p.Migration(version="002_official_publishing"))
            db.commit()
        if not db.get(p.Migration, "003_private_images_and_oauth_actor_binding"):
            db.add(p.Migration(version="003_private_images_and_oauth_actor_binding"))
            db.commit()
        if not db.get(p.Migration, "004_browser_sessions"):
            # Additive only: the new linkedin_accounts columns are added by
            # run_simple_migrations above; this adds the reconnect-token lookup index.
            db.execute(text("CREATE INDEX IF NOT EXISTS ix_linkedin_accounts_reconnect_digest "
                            "ON linkedin_accounts (reconnect_token_digest)"))
            db.add(p.Migration(version="004_browser_sessions"))
            db.commit()
        if not db.get(p.Migration, "005_sync_preferences"):
            # Columns are added by run_simple_migrations; default existing accounts to the private choice.
            db.query(models.LinkedInAccount).filter(models.LinkedInAccount.sync_mode.is_(None)).update({"sync_mode": "synex_only"})
            db.add(p.Migration(version="005_sync_preferences"))
            db.commit()
        if not db.get(p.Migration, "006_outreach_executor"):
            # Columns are added by run_simple_migrations. Runs move from step order to step id.
            db.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ux_agent_tasks_idempotency "
                            "ON agent_tasks (idempotency_key)"))
            for run in db.query(models.SequenceRun).filter(models.SequenceRun.current_step_id.is_(None)).all():
                steps = db.query(models.CampaignStep).filter_by(campaign_id=run.campaign_id).order_by(models.CampaignStep.order).all()
                step = next((s for s in steps if s.order >= (run.current_step_order or 0)), None)
                run.current_step_id = step.id if step else None
            db.add(p.Migration(version="006_outreach_executor"))
            db.commit()
        if not db.get(p.Migration, "007_limit_ceilings"):
            # A limit of 0 used to mean "no limit"; it now means stopped, and 0 stays 0. Anything above
            # a hard ceiling is lowered to it, and each change is logged.
            _lower_to_ceiling(db, models.LinkedInAccount, "daily_action_limit", DAILY_ACTION_CEILING)
            _lower_to_ceiling(db, models.Campaign, "daily_connection_limit", DAILY_TYPE_CEILINGS["send_invite"])
            _lower_to_ceiling(db, models.Campaign, "daily_message_limit", DAILY_TYPE_CEILINGS["send_message"])
            db.add(p.Migration(version="007_limit_ceilings"))
            db.commit()
        if not db.get(p.Migration, "008_clerk_user_id"):
            # The column itself is added by run_simple_migrations; this makes a Clerk user link to one row only.
            db.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ux_users_clerk_user_id ON users (clerk_user_id)"))
            db.add(p.Migration(version="008_clerk_user_id"))
            db.commit()
        if not db.get(p.Migration, "009_lead_collections"):
            # Tables lead_collections and lead_collection_items come from create_all; leads.connection_degree from run_simple_migrations.
            db.add(p.Migration(version="009_lead_collections"))
            db.commit()


def _lower_to_ceiling(db, model, field: str, ceiling: int) -> None:
    column = getattr(model, field)
    for row in db.query(model).filter(column > ceiling).all():
        log.warning("Lowered %s.%s for %s from %s to the ceiling %s", model.__tablename__, field, row.id, getattr(row, field), ceiling)
        setattr(row, field, ceiling)


if __name__ == "__main__":
    migrate()
