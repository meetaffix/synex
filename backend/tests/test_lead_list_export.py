"""Exporting one lead list: its people as CSV, formula-safe, and only for the list's own workspace."""
import csv
import io
import unittest

from test_integrations import Case, SessionLocal, models  # noqa: E402  (sets the isolated environment)


class ExportTest(Case):
    def test_a_list_exports_its_people_neutralised_and_another_workspaces_list_is_not_found(self):
        with SessionLocal() as db:
            lead = db.query(models.Lead).filter_by(first_name="=Evil").one()
            lead.company, lead.phone = "@cmd", "+65 1234"
            other = models.LeadList(user_id=self.other_id, name="Theirs")
            db.add(other)
            db.commit()
            other_id = other.id
        r = self.client.get(f"/lead-lists/{self.list_id}/export")
        self.assertEqual(r.status_code, 200)
        self.assertIn("text/csv", r.headers["content-type"])
        self.assertIn("synex-list-Prospects.csv", r.headers["content-disposition"])
        rows = list(csv.DictReader(io.StringIO(r.text)))
        self.assertEqual(len(rows), 3)
        self.assertEqual({row["first_name"] for row in rows}, {"Ada", "Bo", "'=Evil"})
        for row in rows:
            for value in row.values():
                self.assertNotIn(value[:1], ("=", "@", "-", "\t", "\r"), value)
        self.assertEqual(self.client.get(f"/lead-lists/{other_id}/export").status_code, 404)
        self.assertEqual(self.client.get("/lead-lists/nope/export").status_code, 404)


if __name__ == "__main__":
    unittest.main()
