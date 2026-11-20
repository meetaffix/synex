"""The API and both workers run migrate() on boot, and a hosted deploy starts them together: a table another process created
a moment earlier must not stop this one from starting."""
import atexit
import os
import tempfile
import unittest
from unittest import mock

TEMP = tempfile.TemporaryDirectory()
os.environ["DATABASE_URL"] = "sqlite:///" + TEMP.name.replace("\\", "/") + "/test.db"
os.environ["SECRET_KEY"] = "test-secret-not-for-production-0123456789"
os.environ["ENCRYPTION_KEY"] = "test-encryption-not-for-production-0123456789"
os.environ["AUTH_PROVIDER"] = "local"
import safety
safety.assert_isolated_database(os.environ["DATABASE_URL"])
from sqlalchemy.exc import ProgrammingError
from app import database, migrations
from app.database import Base

atexit.register(database.engine.dispose)


class MigrateRaceTest(unittest.TestCase):
    def test_a_table_created_by_another_process_is_retried(self):
        real = Base.metadata.create_all
        calls = []

        def racing(bind, *args, **kwargs):
            calls.append(1)
            if len(calls) == 1:
                raise ProgrammingError("CREATE TABLE voice_audio", {}, Exception('relation "voice_audio" already exists'))
            return real(bind, *args, **kwargs)

        with mock.patch.object(Base.metadata, "create_all", side_effect=racing), mock.patch.object(migrations.time, "sleep"):
            migrations.migrate()
        self.assertEqual(len(calls), 2)

    def test_a_real_error_still_stops_the_start(self):
        boom = ProgrammingError("CREATE TABLE x", {}, Exception("syntax error"))
        with mock.patch.object(Base.metadata, "create_all", side_effect=boom), mock.patch.object(migrations.time, "sleep"):
            with self.assertRaises(ProgrammingError):
                migrations.migrate()


if __name__ == "__main__":
    unittest.main()
