"""Numbers a user can type are bounded by the server, not only by the form: working hours, wait lengths and how many leads one import may take."""
import atexit
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
from fastapi.testclient import TestClient
from app.database import Base, engine as db_engine
from app.main import app, _attempts
from app.migrations import migrate

atexit.register(db_engine.dispose)
ORIGIN = {"Origin": "http://localhost:5173"}
PASSWORD = "Strong-Test-Password!"


class InputBoundsTest(unittest.TestCase):
    def setUp(self):
        Base.metadata.drop_all(db_engine)
        migrate()
        _attempts.clear()
        self.client = TestClient(app, headers=ORIGIN)
        self.addCleanup(self.client.close)
        r = self.client.post("/auth", json={"action": "register", "email": "owner@example.com", "fullName": "Olive Owner", "password": PASSWORD})
        self.assertEqual(r.status_code, 200, r.text)
        self.campaign = self.client.post("/campaigns", json={"action": "create", "name": "Bounds"}).json()["id"]

    def update(self, **fields):
        return self.client.post("/campaigns", json={"action": "update", "id": self.campaign, **fields})

    def test_working_hours_are_real_hours_in_order(self):
        for bad in ({"startHour": -1}, {"startHour": 24}, {"endHour": 0}, {"endHour": 25}, {"startHour": 17, "endHour": 9}):
            self.assertEqual(self.update(**bad).status_code, 422, bad)
        self.assertEqual(self.update(startHour=9, endHour=17).status_code, 200)

    def test_a_wait_cannot_be_negative_or_longer_than_ninety_days(self):
        step = lambda hours: [{"type": "wait", "order": 0, "delayHours": hours}]
        self.assertEqual(self.update(steps=step(-5)).status_code, 422)
        self.assertEqual(self.update(steps=step(24 * 90 + 1)).status_code, 422)
        self.assertEqual(self.update(steps=step(48)).status_code, 200)

    def test_one_import_cannot_ask_for_millions_of_leads(self):
        r = self.client.post("/lead-collections", json={"source": "urls", "limit": 10_000_000, "params": {"urls": ["https://www.linkedin.com/in/ada"]}})
        self.assertEqual(r.status_code, 422, r.text)

    def test_text_fields_have_sensible_lengths(self):
        lead = lambda **f: self.client.post("/leads", json={"action": "create", "firstName": "Ada", "lastName": "L", **f})
        self.assertEqual(lead(firstName="x" * 201).status_code, 422)
        self.assertEqual(lead(notes="n" * 5001).status_code, 422)
        self.assertEqual(lead(tags=["t"] * 51).status_code, 422)
        self.assertEqual(lead().status_code, 200)
        template = lambda **f: self.client.post("/templates", json={"action": "create", "name": "T", "category": "first_message", "body": "Hi", **f})
        self.assertEqual(template(body="b" * 5001).status_code, 422)
        self.assertEqual(template(name="n" * 201).status_code, 422)
        self.assertEqual(self.update(name="c" * 201).status_code, 422)
        self.assertEqual(self.update(description="d" * 2001).status_code, 422)

    def test_a_huge_request_is_refused_before_it_is_read(self):
        big = "x" * (3 * 1024 * 1024)
        r = self.client.post("/templates", content=('{"action": "create", "name": "T", "body": "%s"}' % big).encode(), headers={"Content-Type": "application/json"})
        self.assertEqual(r.status_code, 413, r.status_code)


if __name__ == "__main__":
    unittest.main()
