import os
import sys
from collections.abc import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker, Session

from .config import DB_CONNECTION_BUDGET, DB_POOLS, settings

# SQLite needs a special flag for multi-threaded FastAPI access.
def process_role() -> str:
    """Which Synex process this is, for sizing its connection pool: the API or one of the two workers."""
    role = os.environ.get("SYNEX_ROLE", "").strip().lower()
    if role in DB_POOLS:
        return role
    argv = " ".join(sys.argv)
    for name in ("outreach_worker", "publishing_worker"):
        if name in argv:
            return name
    return "api"


def connection_budget(s=settings) -> tuple[int, int]:
    """(connections all Synex processes may hold at once, the budget). Pools have no overflow."""
    return sum(DB_POOLS.values()), DB_CONNECTION_BUDGET


def _engine_options(url: str) -> dict:
    if url.startswith("sqlite"):
        return {"connect_args": {"check_same_thread": False}, "pool_pre_ping": True}
    # A managed cloud database: a small fixed pool, a short wait for a free connection, and connections recycled
    # before the provider or a proxy closes them.
    return {"pool_size": DB_POOLS[process_role()], "max_overflow": 0, "pool_timeout": 10, "pool_recycle": 1800, "pool_pre_ping": True}


try:
    engine = create_engine(settings.database_url, **_engine_options(settings.database_url))
except (ImportError, ValueError, TypeError) as exc:  # a missing driver or an unknown scheme
    if not os.environ.get("SYNEX_CHECK_ENV"):
        raise
    engine = create_engine("sqlite://")  # python -m app.check_env still runs, and reports DATABASE_URL by name

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


# Enforce foreign keys (and cascades) on SQLite, which disables them by default.
if settings.database_url.startswith("sqlite"):

    @event.listens_for(Engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, _):  # pragma: no cover
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA secure_delete=ON")
        cursor.close()


class Base(DeclarativeBase):
    pass


def run_simple_migrations() -> None:
    """Add columns that are in the models but missing from an existing DB.

    ``create_all`` only creates new tables; this covers additive column
    changes so an existing synex.db keeps its data across upgrades.
    """
    from sqlalchemy import inspect, text

    inspector = inspect(engine)
    with engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
            if not inspector.has_table(table.name):
                continue
            existing = {c["name"] for c in inspector.get_columns(table.name)}
            for column in table.columns:
                if column.name in existing:
                    continue
                ddl = column.type.compile(engine.dialect)
                conn.execute(
                    text(f'ALTER TABLE {table.name} ADD COLUMN "{column.name}" {ddl}')
                )


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
