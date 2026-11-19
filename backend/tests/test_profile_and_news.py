"""Profile settings (name, phone, designation, company) and the what's new list."""
import unittest

from test_integrations import Case, SessionLocal, models  # noqa: E402  (sets the isolated environment)
from test_outreach import OutreachCase  # noqa: E402


class ProfileTest(OutreachCase):  # a real signed-in session: updating the profile refreshes the row it loaded
    def test_phone_and_designation_are_saved_trimmed_cleared_and_limited(self):
        r = self.client.put("/auth/me", json={"fullName": "Ada L", "company": "Engines", "phone": " +65 1234 5678 ", "designation": "Founder"})
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertEqual((body["fullName"], body["company"], body["phone"], body["designation"]), ("Ada L", "Engines", "+65 1234 5678", "Founder"))
        again = self.client.put("/auth/me", json={"phone": "  ", "designation": ""}).json()
        self.assertEqual((again["phone"], again["designation"], again["company"]), (None, None, "Engines"))  # blank clears; untouched fields stay
        self.assertEqual(self.client.put("/auth/me", json={"phone": "1" * 41}).status_code, 422)
        self.assertEqual(self.client.put("/auth/me", json={"designation": "x" * 121}).status_code, 422)
        self.assertEqual(self.client.put("/auth/me", json={"email": "other@example.com"}).status_code, 409)  # still not changeable here


class WhatsNewTest(Case):
    def test_the_list_is_newest_first_unread_until_opened_and_read_per_person(self):
        first = self.client.get("/integrations/whats-new").json()
        self.assertTrue(first["unread"])
        self.assertEqual(first["items"][0]["id"], first["latestId"])
        self.assertTrue(all({"id", "date", "title", "body"} <= set(i) for i in first["items"]))
        self.assertEqual(self.client.post("/integrations/whats-new/seen").json(), {"ok": True})
        self.assertFalse(self.client.get("/integrations/whats-new").json()["unread"])
        with SessionLocal() as db:
            row = db.get(models.WorkspaceSetting, (self.owner_id, "whats_new_seen"))
            row.value = {"id": "an-older-entry"}
            db.commit()
        self.assertTrue(self.client.get("/integrations/whats-new").json()["unread"])  # a newer entry makes it unread again


if __name__ == "__main__":
    unittest.main()
