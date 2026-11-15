"""The test-safety guard itself: runs that could touch the real database must refuse to start."""
import os
import subprocess
import sys
import unittest
from pathlib import Path

import safety

BACKEND = Path(__file__).resolve().parent.parent


class DatabaseGuardTest(unittest.TestCase):
    def test_the_real_database_is_refused_however_it_is_written(self):
        for url in (
            "sqlite:///./synex.db",
            "sqlite:///synex.db",
            "sqlite:///" + str(BACKEND / "synex.db").replace("\\", "/"),
            "sqlite:///C:/anywhere/else/SYNEX.DB",
            "sqlite:///../backend/synex.db",
        ):
            with self.assertRaises(RuntimeError, msg=url):
                safety.assert_isolated_database(url)

    def test_temporary_databases_are_allowed(self):
        for url in ("sqlite:///C:/Temp/tmp123/test.db", "sqlite:///./browser-test.db", "sqlite:////tmp/x/test.db"):
            safety.assert_isolated_database(url)

    def test_a_test_run_that_loaded_the_real_settings_first_stops_at_import(self):
        """Deliberate attempt: import the app's settings (which read backend/.env and point at synex.db), then
        import a test module. The module must refuse instead of running."""
        code = "import sys; sys.path.insert(0, 'tests'); import app.config; import test_linkedin_session"
        env = {**os.environ}
        env.pop("DATABASE_URL", None)
        result = subprocess.run([sys.executable, "-c", code], cwd=str(BACKEND), env=env, capture_output=True, text=True, timeout=120)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Refusing to run tests", result.stderr)


if __name__ == "__main__":
    unittest.main()
