"""Verify SQLite migration on a copy, optionally back up and apply locally.

Run from backend: python verify_upgrade.py [--apply]. No external API calls.
"""
import argparse
import hashlib
import os
import sqlite3
import subprocess
import sys
import tempfile
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

CHANGED = {
    "linkedin_accounts": {"agent_token", "li_at_encrypted", "jsessionid_encrypted", "harvest_session_requested", "status", "execution_mode"},
    "campaigns": {"status", "updated_at"}, "import_jobs": {"status", "detail", "updated_at"}, "agent_tasks": {"status"},
}


def q(name):
    return '"' + name.replace('"', '""') + '"'


def snapshot(conn, schema):
    summary = {}
    for table, columns in schema.items():
        digest = hashlib.sha256(); count = 0
        for row in conn.execute(f"SELECT {','.join(map(q,columns))} FROM {q(table)} ORDER BY rowid"):
            digest.update(repr(row).encode("utf-8")); count += 1
        summary[table] = count, digest.hexdigest()
    return summary


def main(apply=False):
    from app.config import settings
    if settings.database_url not in ("sqlite:///./synex.db", "sqlite:///synex.db"):
        raise SystemExit("This helper supports only the local backend/synex.db. Back up and migrate other databases separately.")
    source = Path("synex.db").resolve(strict=True)
    with tempfile.TemporaryDirectory() as folder:
        copy = Path(folder) / "migration-copy.db"
        with closing(sqlite3.connect(source.as_uri() + "?mode=ro", uri=True)) as src, closing(sqlite3.connect(copy)) as dest:
            src.backup(dest)
            names = [r[0] for r in src.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
            schema = {t: [c[1] for c in src.execute(f"PRAGMA table_info({q(t)})") if c[1] not in CHANGED.get(t,set())] for t in names}
            baseline = snapshot(src, schema)
        env = dict(os.environ, DATABASE_URL="sqlite:///" + copy.as_posix())
        for _ in range(2):
            subprocess.run([sys.executable,"-m","app.migrations"],check=True,env=env)
        with closing(sqlite3.connect(copy)) as db:
            if snapshot(db, schema) != baseline or db.execute("PRAGMA foreign_key_check").fetchone():
                raise SystemExit("Verification failed; the source database was not changed.")
        print(f"Verified two migrations against a copy of {len(names)} original tables: counts and preserved-column hashes match; no foreign-key violations.")
    if apply:
        backup_dir = source.parent / "backups"; backup_dir.mkdir(exist_ok=True)
        backup = backup_dir / ("pre-publishing-" + datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S") + ".db")
        with closing(sqlite3.connect(source.as_uri() + "?mode=ro", uri=True)) as src, closing(sqlite3.connect(backup)) as dest:
            src.backup(dest)
            # Never retain deprecated LinkedIn browser credentials in a new backup.
            dest.execute("PRAGMA secure_delete=ON")
            columns = {r[1] for r in dest.execute("PRAGMA table_info(linkedin_accounts)")}
            secrets = columns.intersection({"li_at_encrypted","jsessionid_encrypted","agent_token"})
            if secrets:
                dest.execute("UPDATE linkedin_accounts SET " + ",".join(q(c)+"=NULL" for c in secrets))
                dest.commit(); dest.execute("VACUUM")
        from app.migrations import migrate
        migrate()
        with closing(sqlite3.connect(source.as_uri() + "?mode=ro", uri=True)) as db:
            if snapshot(db,schema) != baseline:
                raise SystemExit("Source data changed during upgrade. Stop concurrent writers and inspect the backup.")
        print(f"Local upgrade verified. Business-data backup: {backup}")


if __name__ == "__main__":
    parser=argparse.ArgumentParser();parser.add_argument("--apply",action="store_true");main(parser.parse_args().apply)
