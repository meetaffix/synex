"""Environment validation, the connection budget and the bundle secret check. No finding, message or script output
may ever contain a value: every secret below is a sentinel the tests look for."""
import atexit
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

TEMP = tempfile.TemporaryDirectory()
os.environ["DATABASE_URL"] = "sqlite:///" + TEMP.name.replace("\\", "/") + "/test.db"
os.environ["SECRET_KEY"] = "test-secret-not-for-production-0123456789"
os.environ["ENCRYPTION_KEY"] = "test-encryption-not-for-production-0123456789"
os.environ["AUTH_PROVIDER"] = "local"
os.environ.setdefault("DEEPGRAM_API_KEY", "dg-SENTINEL-never-leak-9f3a7c")
import safety
safety.assert_isolated_database(os.environ["DATABASE_URL"])
from app import check_env, config, database
from app.assistant.config import assistant_config
from app.config import DB_CONNECTION_BUDGET, DB_POOLS, ENV_FILE, MAX_BROWSERS_CEILING, Settings, settings

atexit.register(database.engine.dispose)
BACKEND = Path(__file__).resolve().parents[1]
FRONTEND = BACKEND.parent / "frontend"
SENTINEL = "SENTINEL-must-never-be-printed-8d41"
CERT = Path(TEMP.name) / "root.crt"
CERT.write_text("-----BEGIN CERTIFICATE-----\nx\n-----END CERTIFICATE-----\n")


def base(**changes) -> Settings:
    s = Settings(_env_file=None, secret_key="s" * 40, encryption_key="e" * 40, database_url="sqlite:///./x.db")
    return s.model_copy(update=changes)


def findings(s=None, names=frozenset(), a=assistant_config):
    return check_env.validate(s or base(), a, set(names))


def errors(found):
    return {f.name for f in found if f.level == check_env.ERROR}


class RequiredTest(unittest.TestCase):
    def test_a_valid_local_setup_has_no_errors(self):
        self.assertEqual(errors(findings()), set())

    def test_secrets_must_exist_be_long_and_independent(self):
        self.assertEqual(errors(findings(base(secret_key="", encryption_key=""))), {"SECRET_KEY", "ENCRYPTION_KEY"})
        self.assertEqual(errors(findings(base(secret_key="short"))), {"SECRET_KEY"})
        self.assertEqual(errors(findings(base(secret_key="k" * 40, encryption_key="k" * 40))), {"ENCRYPTION_KEY"})

    def test_cors_origins_and_the_regex(self):
        self.assertEqual(errors(findings(base(cors_origins="https://app.example.com/"))), {"CORS_ORIGINS"})
        self.assertEqual(errors(findings(base(cors_origins="localhost:5173"))), {"CORS_ORIGINS"})
        self.assertEqual(errors(findings(base(cors_origin_regex="(unclosed"))), {"CORS_ORIGIN_REGEX"})
        self.assertEqual(errors(findings(base(cors_origin_regex=r"https://.*\.vercel\.app"))), {"CORS_ORIGIN_REGEX"})  # any Vercel site
        self.assertEqual(errors(findings(base(cors_origin_regex=r"https://synex(-[a-z0-9]+)*-team\.vercel\.app"))), set())


class DatabaseUrlTest(unittest.TestCase):
    def cockroach(self, query):
        return base(database_url=f"cockroachdb://user:{SENTINEL}@host.example.com:26257/synex{query}")

    def test_cockroach_needs_a_password_verify_full_and_an_existing_ca_certificate(self):
        ok = self.cockroach(f"?sslmode=verify-full&sslrootcert={CERT.as_posix()}")
        self.assertEqual(errors(findings(ok)), set())
        self.assertEqual(errors(findings(self.cockroach(f"?sslmode=require&sslrootcert={CERT.as_posix()}"))), {"DATABASE_URL"})
        self.assertEqual(errors(findings(self.cockroach("?sslmode=verify-full"))), {"DATABASE_URL"})
        self.assertEqual(errors(findings(self.cockroach("?sslmode=verify-full&sslrootcert=/no/such/root.crt"))), {"DATABASE_URL"})
        self.assertEqual(errors(findings(base(database_url="cockroachdb://user@host:26257/db?sslmode=verify-full&sslrootcert=" + CERT.as_posix()))), {"DATABASE_URL"})

    def test_a_console_url_gets_the_cockroachdb_dialect_and_other_urls_are_untouched(self):
        console = "postgresql://u:p@abc-123.x.aws-ap-south-1.cockroachlabs.cloud:26257/synex?sslmode=verify-full"
        self.assertTrue(database.engine_url(console).startswith("cockroachdb://u:p@abc-123"))
        for other in ("postgresql://u:p@db.example.com/x", "sqlite:///x.db", "cockroachdb://u:p@h/x"):
            self.assertEqual(database.engine_url(other), other)

    def test_a_serialization_error_is_retried_and_any_other_error_is_not(self):
        from sqlalchemy.exc import DBAPIError

        def failing(code):
            class Orig(Exception):
                pgcode = code
            return DBAPIError("stmt", {}, Orig())

        calls = []

        def flaky():
            calls.append(1)
            if len(calls) < 3:
                raise failing("40001")
            return "done"

        with patch("time.sleep"):
            self.assertEqual(database.with_retry(flaky), "done")
            self.assertEqual(len(calls), 3)
            other = []

            def broken():
                other.append(1)
                raise failing("23505")

            with self.assertRaises(DBAPIError):
                database.with_retry(broken)
            self.assertEqual(len(other), 1)
            always = []

            def never_works():
                always.append(1)
                raise failing("40001")

            with self.assertRaises(DBAPIError):
                database.with_retry(never_works, attempts=3)
            self.assertEqual(len(always), 3)

    def test_the_migration_needs_only_one_connection_so_the_workers_pool_of_one_is_enough(self):
        from sqlalchemy import create_engine, text
        from sqlalchemy.pool import QueuePool
        from app import models, publishing_models  # noqa: F401  (registers every table on Base)
        path = Path(TEMP.name) / "pool-of-one.db"
        one = create_engine(f"sqlite:///{path.as_posix()}", poolclass=QueuePool, pool_size=1, max_overflow=0, pool_timeout=1)
        try:
            database.Base.metadata.create_all(one)
            with one.begin() as conn:  # an older database: a column is missing
                conn.execute(text("ALTER TABLE users DROP COLUMN clerk_user_id"))
            with patch.object(database, "engine", one):
                database.run_simple_migrations()  # raises QueuePool TimeoutError if it needs a second connection
            with one.connect() as conn:
                self.assertIn("clerk_user_id", [r[1] for r in conn.execute(text("PRAGMA table_info(users)"))])
        finally:
            one.dispose()

    def test_an_unsupported_scheme_is_an_error_and_no_message_shows_the_password(self):
        self.assertEqual(errors(findings(base(database_url="mysql://u:p@h/db"))), {"DATABASE_URL"})
        text = check_env.render(findings(self.cockroach("?sslmode=disable")))
        self.assertNotIn(SENTINEL, text)


class ClerkAndAiTest(unittest.TestCase):
    def test_clerk_mode_needs_both_keys_and_a_well_formed_webhook_secret(self):
        found = errors(findings(base(auth_provider="clerk")))
        self.assertEqual(found, {"CLERK_SECRET_KEY", "VITE_CLERK_PUBLISHABLE_KEY"})
        import base64
        pk = "pk_test_" + base64.b64encode(b"curious-x-1.clerk.accounts.dev$").decode().rstrip("=")
        good = base(auth_provider="clerk", clerk_secret_key="sk_test_" + "a" * 30, clerk_publishable_key=pk)
        self.assertEqual(errors(findings(good)), set())
        self.assertEqual(errors(findings(good.model_copy(update={"clerk_webhook_secret": "nope"}))), {"CLERK_WEBHOOK_SECRET"})
        self.assertEqual(errors(findings(good.model_copy(update={"auth_provider": "both"}))), {"AUTH_PROVIDER"})

    def test_smtp_is_reported_unused_when_clerk_is_on(self):
        import base64
        pk = "pk_test_" + base64.b64encode(b"curious-x-1.clerk.accounts.dev$").decode().rstrip("=")
        s = base(auth_provider="clerk", clerk_secret_key="sk_test_" + "a" * 30, clerk_publishable_key=pk)
        note = [f for f in findings(s, {"SMTP_HOST", "SMTP_PORT"}) if f.name == "SMTP_*"]
        self.assertEqual(len(note), 1)
        self.assertIn("unused", note[0].message)

    def test_the_deepgram_key_shape_is_checked_and_an_empty_key_only_informs(self):
        bad = assistant_config.model_copy(update={"deepgram_api_key": "short key!"})
        self.assertEqual(errors(findings(a=bad)), {"DEEPGRAM_API_KEY"})
        empty = assistant_config.model_copy(update={"deepgram_api_key": ""})
        self.assertEqual(errors(findings(a=empty)), set())


class NamesInTheFileTest(unittest.TestCase):
    def test_old_removed_transient_and_unknown_names_are_flagged_by_name(self):
        found = {f.name: f for f in findings(names={"DEEPGRAM_APY_KEP", "ANTHROPIC_API_KEY", "ACCESS_TOKEN_EXPIRE_MINUTES", "COCKROACH_SQL_PASSWORD", "TYPO_NAME", "SECRET_KEY"})}
        self.assertIn("DEEPGRAM_API_KEY", found["DEEPGRAM_APY_KEP"].message)
        self.assertIn("remove", found["ANTHROPIC_API_KEY"].message)
        self.assertIn("remove", found["ACCESS_TOKEN_EXPIRE_MINUTES"].message)
        self.assertIn("DATABASE_URL", found["COCKROACH_SQL_PASSWORD"].message)
        self.assertIn("not read", found["TYPO_NAME"].message)
        self.assertNotIn("SECRET_KEY", found)  # a known name is fine

    def test_every_name_in_the_example_file_is_read_by_the_code(self):
        example = (config.ENV_FILE.parent / ".env.example").read_text(encoding="utf-8")
        import re
        names = {m.group(1) for line in example.splitlines() for m in [re.match(r"^\s*#?\s*([A-Z][A-Z0-9_]*)=", line)] if m}
        self.assertEqual(sorted(n for n in names if n not in check_env.known_names()), [])

    def test_the_removed_variables_are_gone_from_the_settings_and_the_example(self):
        self.assertNotIn("access_token_expire_minutes", Settings.model_fields)
        self.assertNotIn("anthropic_api_key", Settings.model_fields)
        example = (config.ENV_FILE.parent / ".env.example").read_text(encoding="utf-8")
        for gone in ("ANTHROPIC", "ACCESS_TOKEN_EXPIRE_MINUTES", "DEEPGRAM_APY_KEP"):
            self.assertNotIn(gone, example)
        self.assertFalse((config.ENV_FILE.parent / "backend" / ".env.example").exists())
        self.assertFalse((config.ENV_FILE.parent / "frontend" / ".env.example").exists())


class BrowserCapTest(unittest.TestCase):
    def test_the_browser_cap_has_a_hard_ceiling_that_no_setting_can_exceed(self):
        self.assertEqual(MAX_BROWSERS_CEILING, 5)
        self.assertEqual(base(linkedin_session_max_browsers=3).effective_max_browsers, 3)
        self.assertEqual(base(linkedin_session_max_browsers=50).effective_max_browsers, MAX_BROWSERS_CEILING)
        self.assertEqual(base(linkedin_session_max_browsers=0).effective_max_browsers, 1)
        self.assertEqual(errors(findings(base(linkedin_session_max_browsers=6))), {"LINKEDIN_SESSION_MAX_BROWSERS"})
        self.assertEqual(errors(findings(base(linkedin_session_max_browsers=0))), {"LINKEDIN_SESSION_MAX_BROWSERS"})
        self.assertEqual(errors(findings(base(linkedin_session_max_browsers=2))), set())

    def test_both_managers_are_built_with_the_capped_value(self):
        import inspect
        from app import outreach_worker
        from app.linkedin_session import service
        for module in (outreach_worker, service):
            self.assertIn("effective_max_browsers", inspect.getsource(module))
            self.assertNotIn("settings.linkedin_session_max_browsers", inspect.getsource(module))


class ConnectionBudgetTest(unittest.TestCase):
    def test_the_pools_of_the_api_and_both_workers_stay_within_the_budget(self):
        used, limit = database.connection_budget()
        self.assertEqual(limit, DB_CONNECTION_BUDGET)
        self.assertLessEqual(DB_CONNECTION_BUDGET, 4)  # a managed plan allows about 5; one stays free for migrations
        self.assertLessEqual(used, limit)
        self.assertEqual(set(DB_POOLS), {"api", "outreach_worker", "publishing_worker"})

    def test_a_configuration_above_the_budget_is_an_error(self):
        cockroach = base(database_url=f"cockroachdb://u:{SENTINEL}@h:26257/db?sslmode=verify-full&sslrootcert={CERT.as_posix()}")
        with patch.dict(DB_POOLS, {"api": 4, "outreach_worker": 2, "publishing_worker": 1}):
            self.assertIn("DB_POOL_*", errors(findings(cockroach)))
        self.assertNotIn("DB_POOL_*", errors(findings(cockroach)))

    def test_each_process_gets_its_own_pool_size_on_a_managed_database(self):
        url = "cockroachdb://u:p@h:26257/db"
        for role, size in DB_POOLS.items():
            with patch.dict(os.environ, {"SYNEX_ROLE": role}):
                options = database._engine_options(url)
            self.assertEqual((options["pool_size"], options["max_overflow"]), (size, 0))
            self.assertTrue(options["pool_pre_ping"])
            self.assertLessEqual(options["pool_timeout"], 10)
            self.assertLessEqual(options["pool_recycle"], 3600)
        self.assertNotIn("pool_size", database._engine_options("sqlite:///./x.db"))

    def test_the_role_comes_from_the_command_line_when_not_set(self):
        with patch.dict(os.environ, {"SYNEX_ROLE": ""}), patch.object(sys, "argv", ["C:/x/app/outreach_worker.py"]):
            self.assertEqual(database.process_role(), "outreach_worker")
        with patch.dict(os.environ, {"SYNEX_ROLE": ""}), patch.object(sys, "argv", ["C:/x/app/publishing_worker.py"]):
            self.assertEqual(database.process_role(), "publishing_worker")
        with patch.dict(os.environ, {"SYNEX_ROLE": ""}), patch.object(sys, "argv", ["uvicorn"]):
            self.assertEqual(database.process_role(), "api")


class StartupTest(unittest.TestCase):
    def run_cli(self, **env):
        full = {**os.environ, "PYTHONPATH": str(BACKEND), **env}
        return subprocess.run([sys.executable, "-m", "app.check_env"], cwd=BACKEND, env=full, capture_output=True, text=True, timeout=60)

    def test_the_command_exits_non_zero_names_the_problem_and_never_prints_a_value(self):
        done = self.run_cli(SECRET_KEY=SENTINEL[:12], DATABASE_URL=f"mysql://u:{SENTINEL}@h/db")
        self.assertEqual(done.returncode, 1)
        self.assertIn("SECRET_KEY", done.stdout)
        self.assertIn("DATABASE_URL", done.stdout)
        self.assertNotIn(SENTINEL, done.stdout + done.stderr)
        self.assertNotIn(SENTINEL[:12], done.stdout + done.stderr)

    def test_a_good_environment_exits_zero(self):
        self.assertEqual(self.run_cli().returncode, 0)

    def test_a_server_refuses_to_start_and_says_which_names_are_wrong(self):
        with patch.object(check_env, "validate", return_value=[check_env.Finding(check_env.ERROR, "SECRET_KEY", "too short")]):
            with self.assertRaises(SystemExit) as stopped:
                check_env.require_valid_env("The API")
        self.assertIn("SECRET_KEY", str(stopped.exception))
        self.assertNotIn(SENTINEL, str(stopped.exception))


@unittest.skipUnless(shutil.which("node"), "node is needed for the bundle check")
class BundleCheckTest(unittest.TestCase):
    def run_check(self, files, env_text=""):
        root = Path(tempfile.mkdtemp(dir=TEMP.name))
        dist = root / "dist"
        (dist / "assets").mkdir(parents=True)
        for name, text in files.items():
            (dist / name).write_text(text, encoding="utf-8")
        env = root / ".env"
        env.write_text(env_text, encoding="utf-8")
        return subprocess.run(["node", str(FRONTEND / "scripts" / "check-bundle.mjs"), str(dist), str(env)], capture_output=True, text=True, timeout=60)

    def test_a_clean_bundle_passes(self):
        done = self.run_check({"index.html": "<html>VITE public key pk_test_abc</html>", "assets/app.js": "console.log('hello')"}, f"CLERK_SECRET_KEY={SENTINEL}\nVITE_API_URL=http://x\n")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)

    def test_a_planted_env_value_fails_by_name_without_printing_the_value(self):
        done = self.run_check({"assets/app.js": f"const k='{SENTINEL}';"}, f"CLERK_SECRET_KEY={SENTINEL}\nVITE_API_URL=http://x\n")
        self.assertEqual(done.returncode, 1)
        self.assertIn("CLERK_SECRET_KEY", done.stderr)
        self.assertNotIn(SENTINEL, done.stdout + done.stderr)

    def test_secret_shaped_strings_fail_even_without_an_env_file(self):
        for planted in ("sk_live_" + "a" * 24, "whsec_" + "b" * 24, "-----BEGIN RSA PRIVATE KEY-----", "postgresql://user:hunter2pw@db.example.com/x"):
            done = self.run_check({"assets/app.js": planted})
            self.assertEqual(done.returncode, 1, planted)
            self.assertNotIn(planted, done.stdout + done.stderr)

    def test_a_vite_variable_in_the_bundle_is_allowed(self):
        done = self.run_check({"assets/app.js": "pk_test_publishableABC123"}, "VITE_CLERK_PUBLISHABLE_KEY=pk_test_publishableABC123\n")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)


class BrowserCheckTest(unittest.TestCase):
    """A server without its Chromium must say so at start, by name, instead of failing on the first LinkedIn sign-in."""

    def test_a_missing_browser_is_an_error_named_BROWSER_with_the_fix_and_a_working_one_is_not(self):
        self.assertIsNone(check_env.browser_finding())
        empty = tempfile.mkdtemp(prefix="no-browsers-")
        with patch.dict(os.environ, {"PLAYWRIGHT_BROWSERS_PATH": empty}):
            finding = check_env.browser_finding()
        self.assertEqual((finding.level, finding.name), (check_env.ERROR, "BROWSER"))
        self.assertIn("python -m playwright install chromium", finding.message)
        self.assertNotIn(SENTINEL, finding.message)

    def test_the_check_runs_only_where_the_images_ask_for_it(self):
        empty = tempfile.mkdtemp(prefix="no-browsers-")
        with patch.dict(os.environ, {"PLAYWRIGHT_BROWSERS_PATH": empty}):
            self.assertNotIn("BROWSER", {f.name for f in findings(base())})
            with patch.dict(os.environ, {"SYNEX_CHECK_BROWSER": "1"}):
                self.assertEqual(errors(findings(base())), {"BROWSER"})


if __name__ == "__main__":
    unittest.main()
