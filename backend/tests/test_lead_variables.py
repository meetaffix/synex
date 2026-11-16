"""Custom campaign variables on a lead: saved, validated, and filled into messages."""
import atexit
import os
import tempfile
import unittest

TEMP = tempfile.TemporaryDirectory()
os.environ["DATABASE_URL"] = "sqlite:///" + TEMP.name.replace("\\", "/") + "/test.db"
os.environ["SECRET_KEY"] = "test-secret-not-for-production-0123456789"
os.environ["ENCRYPTION_KEY"] = "test-encryption-not-for-production-0123456789"
os.environ["AUTH_PROVIDER"] = "local"
os.environ.setdefault("DEEPGRAM_API_KEY", "dg-SENTINEL-never-leak-9f3a7c")
import safety
safety.assert_isolated_database(os.environ["DATABASE_URL"])
from fastapi.testclient import TestClient
from app import database, models, providers, publishing_models  # noqa: F401
from app.database import Base, SessionLocal
from app.deps import get_current_user, get_data_user, get_manager_user
from app.main import app

atexit.register(database.engine.dispose)


class LeadVariablesTest(unittest.TestCase):
    def setUp(self):
        Base.metadata.drop_all(database.engine)
        Base.metadata.create_all(database.engine)
        with SessionLocal() as db:
            owner = models.User(email="a@example.com", full_name="A", hashed_password="x")
            db.add(owner)
            db.commit()
            self.owner_id = owner.id

        def current():
            with SessionLocal() as db:
                return db.get(models.User, self.owner_id)
        for dep in (get_data_user, get_manager_user, get_current_user):
            app.dependency_overrides[dep] = current
        self.addCleanup(app.dependency_overrides.clear)
        self.client = TestClient(app)

    def create(self, variables):
        return self.client.post("/leads", json={"action": "create", "firstName": "Ada", "lastName": "L", "linkedinUrl": "https://www.linkedin.com/in/ada-l/", "variables": variables})

    def test_variables_are_saved_returned_updated_and_filled_into_text(self):
        r = self.create({"eventName": "SaaStr", "offer": "free audit"})
        self.assertEqual(r.status_code, 200, r.text)
        lead = r.json()
        self.assertEqual(lead["variables"], {"eventName": "SaaStr", "offer": "free audit"})
        self.assertEqual(self.client.post("/leads", json={"action": "update", "id": lead["id"], "variables": {"eventName": "Web Summit"}}).json()["variables"], {"eventName": "Web Summit"})
        with SessionLocal() as db:
            text = providers.render_variables("Hi {{first_name}}, see you at {{eventName}}! {{offer}}", db.get(models.Lead, lead["id"]))
        self.assertEqual(text, "Hi Ada, see you at Web Summit! {{offer}}")  # an unset variable is left visible, never silently blank

    def test_bad_names_reserved_names_and_oversize_values_are_refused_with_the_reason(self):
        for variables, word in (({"1bad": "x"}, "valid variable name"), ({"first_name": "x"}, "already filled"), ({"linkedin_company": "x"}, "already filled"),
                                ({"ok": "x" * 501}, "500 characters"), ({f"v{i}": "x" for i in range(21)}, "at most 20")):
            r = self.create(variables)
            self.assertEqual(r.status_code, 422, variables)
            self.assertIn(word, r.text)

    def test_a_lead_without_variables_still_works(self):
        r = self.client.post("/leads", json={"action": "create", "firstName": "Bo", "lastName": "B", "linkedinUrl": "https://www.linkedin.com/in/bo-b/"})
        self.assertEqual(r.json()["variables"], {})


if __name__ == "__main__":
    unittest.main()
