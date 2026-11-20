"""The humanized rewrite keeps the user's {{variables}} and spintax, and falls back to a plain local cleanup with no AI service."""
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
from app import database, rewrite

atexit.register(database.engine.dispose)

STIFF = "I hope this message finds you well. I would like to leverage our shared interest — {{company}} — in order to connect."


class RewriteTest(unittest.TestCase):
    def test_the_local_cleanup_removes_stiff_phrasing_and_keeps_variables(self):
        out = rewrite.humanize(STIFF, provider="local")
        self.assertEqual(out["provider"], "local")
        self.assertTrue(out["changed"])
        self.assertIn("{{company}}", out["text"])
        for gone in ("hope this message", "leverage", "—", "in order to"):
            self.assertNotIn(gone, out["text"])

    def test_an_ai_rewrite_is_used_when_it_keeps_every_variable(self):
        with mock.patch.object(rewrite, "_ask", return_value="Hey {{first_name}}, loved your post. {Hi|Hello}!"):
            out = rewrite.humanize("Dear {{first_name}}, I enjoyed your post. {Hi|Hello}!", provider="deepgram")
        self.assertEqual((out["provider"], out["text"]), ("deepgram", "Hey {{first_name}}, loved your post. {Hi|Hello}!"))

    def test_an_ai_rewrite_that_drops_a_variable_is_refused(self):
        with mock.patch.object(rewrite, "_ask", return_value="Hey there, loved your post."):
            out = rewrite.humanize("Dear {{first_name}}, I enjoyed your post.", provider="deepgram")
        self.assertEqual(out["provider"], "local")
        self.assertIn("{{first_name}}", out["text"])

    def test_an_ai_failure_or_too_long_a_rewrite_falls_back(self):
        with mock.patch.object(rewrite, "_ask", side_effect=RuntimeError("down")):
            self.assertEqual(rewrite.humanize("Hi {{first_name}}", provider="deepgram")["provider"], "local")
        with mock.patch.object(rewrite, "_ask", return_value="x" * 300):
            self.assertEqual(rewrite.humanize("Hi", max_length=200, provider="ollama")["provider"], "local")


if __name__ == "__main__":
    unittest.main()
