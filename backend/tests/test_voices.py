"""Preset voices: only commercially licensed ones, one assigned per account, cloning honestly off."""
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
from app import database, models, publishing_models, voices  # noqa: F401
from app.database import Base, SessionLocal
from app.deps import get_admin_user, get_current_user, get_data_user, get_manager_user
from app.main import app

atexit.register(database.engine.dispose)
NON_COMMERCIAL = ("NC", "non-commercial", "ryan", "hfc")


class VoicesTest(unittest.TestCase):
    def setUp(self):
        Base.metadata.drop_all(database.engine)
        Base.metadata.create_all(database.engine)
        with SessionLocal() as db:
            owner = models.User(email="a@example.com", full_name="A", hashed_password="x")
            db.add(owner)
            db.flush()
            account = models.LinkedInAccount(user_id=owner.id, name="Ada", status="active")
            db.add(account)
            db.commit()
            self.owner_id, self.account_id = owner.id, account.id

        def current():
            with SessionLocal() as db:
                return db.get(models.User, self.owner_id)
        for dep in (get_data_user, get_manager_user, get_admin_user, get_current_user):
            app.dependency_overrides[dep] = current
        self.addCleanup(app.dependency_overrides.clear)
        self.client = TestClient(app)

    def test_no_voice_is_non_commercial_and_every_voice_states_its_licence(self):
        for voice in voices.VOICES:
            self.assertTrue(voice["licence"], voice["id"])
            self.assertFalse(any(word.lower() in (voice["licence"] + voice["model"]).lower() for word in NON_COMMERCIAL), voice["id"])

    def test_the_catalogue_says_cloning_is_off_and_india_english_is_unavailable_with_reasons(self):
        data = self.client.get("/linkedin-accounts/voices/catalogue").json()
        self.assertFalse(data["clone"]["available"])
        self.assertTrue(data["clone"]["reason"])
        india = [a for a in data["accents"] if a["label"] == "English (India)"][0]
        self.assertFalse(india["available"])
        self.assertTrue(india["reason"])

    def test_a_voice_can_be_assigned_changed_removed_and_an_unknown_one_is_refused(self):
        url = f"/linkedin-accounts/{self.account_id}"
        self.assertIsNone(self.client.get(url + "/details").json()["voiceId"])
        self.assertEqual(self.client.put(url + "/voice", json={"voiceId": "cori"}).status_code, 200)
        self.assertEqual(self.client.get(url + "/details").json()["voiceId"], "cori")
        self.assertEqual(self.client.put(url + "/voice", json={"voiceId": "ryan"}).status_code, 422)
        self.assertEqual(self.client.get(url + "/details").json()["voiceId"], "cori")
        self.client.put(url + "/voice", json={"voiceId": None})
        self.assertIsNone(self.client.get(url + "/details").json()["voiceId"])


if __name__ == "__main__":
    unittest.main()
