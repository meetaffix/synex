"""Post review: a private, expiring, revocable reviewer link; feedback, approval and change requests; the owner's thread; and no access for anyone else."""
import unittest
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from test_publishing import ORIGIN, PublishingTest as Base  # noqa: E402  (sets the isolated environment)
from app.database import SessionLocal
from app.main import app
from app.publishing_models import ReviewLink


class ReviewTest(unittest.TestCase):
    serial = True

    def setUp(self):
        Base.setUp(self)
        self.post = Base.draft(self)
        self.public = TestClient(app, headers=ORIGIN)  # a reviewer has no account and no cookie
        self.addCleanup(self.public.close)

    register = Base.register
    connection = Base.connection

    def invite(self, name="Ravi"):
        r = self.client.post(f"/publishing/posts/{self.post['id']}/reviewers", json={"reviewer": name})
        self.assertEqual(r.status_code, 201, r.text)
        return r.json()

    def test_a_reviewer_reads_the_post_and_comments_approves_or_asks_for_changes_without_an_account(self):
        link = self.invite()
        self.assertIn("shown only once", link["note"])
        page = self.public.get(f"/review/{link['token']}").json()
        self.assertEqual((page["reviewer"], page["post"]["title"], page["post"]["body"]), ("Ravi", "Test post", "A real draft stored in the test database."))
        self.assertEqual(self.public.post(f"/review/{link['token']}/feedback", json={"decision": "comment", "body": ""}).status_code, 422)
        self.assertEqual(self.public.post(f"/review/{link['token']}/feedback", json={"decision": "changes", "body": ""}).status_code, 422)
        self.assertEqual(self.public.post(f"/review/{link['token']}/feedback", json={"decision": "changes", "body": "Shorter first line"}).status_code, 201)
        self.assertEqual(self.public.post(f"/review/{link['token']}/feedback", json={"decision": "approve"}).status_code, 201)
        owner = self.client.get(f"/publishing/posts/{self.post['id']}/reviews").json()
        self.assertEqual([(f["author"], f["decision"]) for f in owner["thread"]], [("Ravi", "changes"), ("Ravi", "approve")])
        self.assertEqual(owner["approvedBy"], ["Ravi"])
        self.assertEqual(owner["links"][0]["state"], "active")
        self.assertIsNotNone(owner["links"][0]["lastSeenAt"])
        self.assertNotIn("token", owner["links"][0])
        reply = self.client.post(f"/publishing/posts/{self.post['id']}/feedback", json={"body": "Done, have a look"})
        self.assertEqual(reply.status_code, 201)
        self.assertEqual(len(self.public.get(f"/review/{link['token']}").json()["thread"]), 3)  # the reviewer sees the reply

    def test_an_approval_is_for_one_version_and_never_publishes(self):
        link = self.invite()
        self.public.post(f"/review/{link['token']}/feedback", json={"decision": "approve"})
        edited = self.client.put(f"/publishing/posts/{self.post['id']}", json={"title": "Test post", "body": "Changed after approval", "accountId": self.account, "version": self.post["version"]})
        self.assertEqual(edited.status_code, 200, edited.text)
        self.assertEqual(self.client.get(f"/publishing/posts/{self.post['id']}/reviews").json()["approvedBy"], [])  # the new text has not been approved
        self.assertEqual(self.client.get("/publishing/posts").json()[0]["status"], "draft")

    def test_only_a_hash_is_stored_and_revoked_expired_or_wrong_links_stop_working(self):
        link = self.invite()
        with SessionLocal() as db:
            row = db.query(ReviewLink).one()
            self.assertNotEqual(row.token_hash, link["token"])
            self.assertNotIn(link["token"], row.token_hash)
        self.assertEqual(self.public.get("/review/not-a-real-token").status_code, 404)
        self.assertEqual(self.client.delete(f"/publishing/posts/{self.post['id']}/reviewers/{link['id']}").status_code, 204)
        self.assertEqual(self.public.get(f"/review/{link['token']}").status_code, 404)
        self.assertEqual(self.public.post(f"/review/{link['token']}/feedback", json={"decision": "approve"}).status_code, 404)
        second = self.invite("Mia")
        with SessionLocal() as db:
            row = db.get(ReviewLink, second["id"])
            row.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
            db.commit()
        self.assertEqual(self.public.get(f"/review/{second['token']}").status_code, 404)
        states = {l["reviewer"]: l["state"] for l in self.client.get(f"/publishing/posts/{self.post['id']}/reviews").json()["links"]}
        self.assertEqual(states, {"Ravi": "revoked", "Mia": "expired"})

    def test_another_workspace_cannot_see_or_invite_on_this_post(self):
        other = TestClient(app, headers=ORIGIN)
        self.addCleanup(other.close)
        Base.register(self, other, "other@example.com")
        for method, path, body in (("get", "reviews", None), ("post", "reviewers", {"reviewer": "X"}), ("post", "feedback", {"body": "hi"})):
            r = getattr(other, method)(f"/publishing/posts/{self.post['id']}/{path}", **({"json": body} if body else {}))
            self.assertEqual(r.status_code, 404, path)
        self.assertEqual(self.public.get(f"/publishing/posts/{self.post['id']}/reviews").status_code, 401)

    def test_a_post_has_at_most_ten_active_reviewers(self):
        for i in range(10):
            self.invite(f"R{i}")
        r = self.client.post(f"/publishing/posts/{self.post['id']}/reviewers", json={"reviewer": "Eleventh"})
        self.assertEqual(r.status_code, 409)


if __name__ == "__main__":
    unittest.main()
