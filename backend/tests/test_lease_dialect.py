"""The browser lease upsert must use the PostgreSQL ON CONFLICT insert on every server database: the hosted one is
CockroachDB, whose dialect is named "cockroachdb", not "postgresql". Only SQLite (local use and tests) takes the SQLite insert."""
import os
import tempfile
import unittest

TEMP = tempfile.TemporaryDirectory()
os.environ["DATABASE_URL"] = "sqlite:///" + TEMP.name.replace("\\", "/") + "/test.db"
os.environ["SECRET_KEY"] = "test-secret-not-for-production-0123456789"
os.environ["ENCRYPTION_KEY"] = "test-encryption-not-for-production-0123456789"
os.environ["AUTH_PROVIDER"] = "local"
import safety
safety.assert_isolated_database(os.environ["DATABASE_URL"])
from sqlalchemy.dialects.postgresql import insert as postgres_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from app import database, outreach_results

import atexit
atexit.register(database.engine.dispose)


class LeaseDialectTest(unittest.TestCase):
    def test_insert_for_each_database(self):
        self.assertIs(outreach_results.insert_for("sqlite"), sqlite_insert)
        for name in ("postgresql", "cockroachdb"):
            self.assertIs(outreach_results.insert_for(name), postgres_insert, name)


if __name__ == "__main__":
    unittest.main()
