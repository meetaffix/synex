"""The Smart sequence: steps arranged as a tree with If connection and Is active on LinkedIn branches. The engine follows the branch, the API refuses trees it cannot
run, the dry run follows the same branch, and share, import and duplicate keep the tree."""
import unittest
from datetime import datetime, timedelta, timezone

from test_outreach import MOCK, OutreachCase, SessionLocal  # noqa: E402  (sets the isolated environment)
from app import engine, models, planner, step_types
from app.config import DAILY_TYPE_CEILINGS


def tree(db, campaign, spec):
    """spec: list of (key, type, parent key or None, branch or None, extra fields). Returns {key: step}."""
    made = {}
    for order, (key, kind, parent, branch, extra) in enumerate(spec):
        step = models.CampaignStep(type=kind, order=order, parent_step_id=made[parent].id if parent else None,
                                   branch_condition={"branch": branch} if branch else None, **extra)
        campaign.steps.append(step)
        db.flush()
        made[key] = step
    return made


class GraphCase(OutreachCase):
    def graph_campaign(self, spec, users=("ann",), status="new", **fields):
        campaign_id = self.make_campaign([{"user": u, "status": status} for u in users], steps=[], launch=False, **fields)
        with SessionLocal() as db:
            campaign = db.get(models.Campaign, campaign_id)
            made = tree(db, campaign, spec)
            engine.launch_campaign(db, campaign)
            db.commit()
            ids = {k: s.id for k, s in made.items()}
        return campaign_id, ids

    def age_step(self, user, days):
        with SessionLocal() as db:
            run = db.query(models.SequenceRun).join(models.Lead).filter(models.Lead.first_name == user.title()).one()
            run.step_entered_at = datetime.now(timezone.utc) - timedelta(days=days)
            run.next_action_at = datetime.now(timezone.utc) - timedelta(minutes=1)
            if run.status == "awaiting_agent":  # the acceptance check found nothing: back to waiting
                run.status = "waiting_connection"
                for task in db.query(models.AgentTask).filter_by(type="check_connection", status="pending"):
                    task.status = "done"
            db.commit()


CONNECT_THEN_BRANCH = [
    ("c", "if_connected", None, None, {"config": {"waitDays": 15}}),
    ("yes", "message", "c", "yes", {"message": "Great to connect"}),
    ("no", "follow", "c", "no", {}),
]


class BranchTest(GraphCase):
    def test_a_connected_lead_takes_the_yes_branch(self):
        self.graph_campaign(CONNECT_THEN_BRANCH, status="connected")
        self.tick()
        sent = self.tasks("send_message")
        self.assertEqual([t.payload["message"] for t in sent], ["Great to connect"])
        self.assertEqual(self.tasks("follow_profile"), [])

    def test_an_unconnected_lead_waits_and_is_checked_then_takes_the_no_branch_after_the_wait(self):
        self.graph_campaign(CONNECT_THEN_BRANCH)
        self.tick()
        self.assertEqual(len(self.tasks("check_connection")), 1)  # still waiting: acceptance is polled, within limits
        self.assertEqual(self.tasks("follow_profile"), [])
        self.age_step("ann", 16)
        self.tick()
        self.assertEqual(len(self.tasks("follow_profile")), 1)  # 15 days passed without acceptance: the "not connected" branch
        self.assertEqual(self.tasks("send_message"), [])

    def test_acceptance_inside_the_wait_takes_the_yes_branch(self):
        self.graph_campaign(CONNECT_THEN_BRANCH)
        self.tick()
        with SessionLocal() as db:
            db.query(models.Lead).one().status = "connected"
            run = db.query(models.SequenceRun).one()
            run.status, run.next_action_at = "running", datetime.now(timezone.utc) - timedelta(minutes=1)
            db.commit()
        self.tick()
        self.assertEqual(len(self.tasks("send_message")), 1)

    def test_the_wait_is_the_configured_number_of_days(self):
        spec = [("c", "if_connected", None, None, {"config": {"waitDays": 3}}), ("no", "follow", "c", "no", {})]
        self.graph_campaign(spec)
        self.tick()
        self.age_step("ann", 2)
        self.tick()
        self.assertEqual(self.tasks("follow_profile"), [])
        self.age_step("ann", 4)
        self.tick()
        self.assertEqual(len(self.tasks("follow_profile")), 1)

    def test_an_empty_branch_ends_the_run(self):
        self.graph_campaign([("c", "if_connected", None, None, {"config": {"waitDays": 15}}), ("yes", "message", "c", "yes", {"message": "Hi"})])
        self.age_step("ann", 20)
        self.tick()
        run = self.run_of("ann")
        self.assertEqual((run.status, run.stop_reason), ("completed", "ended"))

    def test_after_the_last_step_of_a_branch_the_run_ends_and_never_jumps_to_another_list(self):
        spec = [("c", "if_connected", None, None, {}), ("v", "profile_visit", "c", "yes", {}), ("m", "message", "c", "yes", {"message": "Next"}), ("n", "follow", "c", "no", {})]
        self.graph_campaign(spec, status="connected")
        for _ in range(3):
            self.tick()
            with SessionLocal() as db:
                for task in db.query(models.AgentTask).filter(models.AgentTask.status == "pending", models.AgentTask.sequence_run_id.isnot(None)).all():
                    task.status = "done"
                    run = task.sequence_run
                    step = next(s for s in run.campaign.steps if s.id == (task.payload or {}).get("stepId"))
                    engine.move_past(list(run.campaign.steps), run, step, datetime.now(timezone.utc))
                db.commit()
        self.assertEqual(len(self.tasks("visit_profile")), 1)
        self.assertEqual(len(self.tasks("send_message")), 1)
        self.assertEqual(self.tasks("follow_profile"), [])
        self.assertEqual(self.run_of("ann").status, "completed")


class ActiveTest(GraphCase):
    SPEC = [("a", "if_active", None, None, {"config": {"days": 30}}), ("yes", "message", "a", "yes", {"message": "Saw you are active"}), ("no", "profile_visit", "a", "no", {})]

    def test_recent_activity_takes_the_yes_branch(self):
        self.graph_campaign(self.SPEC, status="connected")
        with SessionLocal() as db:
            lead = db.query(models.Lead).one()
            db.add(models.LeadEvent(user_id=lead.user_id, lead_id=lead.id, type="replied", detail="hi"))
            db.commit()
        self.tick()
        self.assertEqual(len(self.tasks("send_message")), 1)

    def test_old_or_no_activity_takes_the_no_branch(self):
        self.graph_campaign(self.SPEC, status="connected")
        with SessionLocal() as db:
            lead = db.query(models.Lead).one()
            event = models.LeadEvent(user_id=lead.user_id, lead_id=lead.id, type="replied", detail="old")
            db.add(event)
            db.flush()
            event.created_at = datetime.now(timezone.utc) - timedelta(days=90)
            db.commit()
        self.tick()
        self.assertEqual(len(self.tasks("visit_profile")), 1)
        self.assertEqual(self.tasks("send_message"), [])


class ActionNodeTest(GraphCase):
    def test_every_action_node_becomes_its_task_and_a_voice_note_carries_its_audio(self):
        spec = [("a", "profile_visit", None, None, {}), ("b", "follow", None, None, {}), ("c", "like_post", None, None, {}), ("d", "withdraw_invite", None, None, {}),
                ("e", "inmail", None, None, {"message": "Hello", "config": {"subject": "Quick question"}}),
                ("f", "voice_note", None, None, {"config": {"mode": "direct", "language": "en-GB", "audioId": "audio-1"}})]
        self.graph_campaign(spec, status="connected")
        seen = []
        for _ in range(len(spec)):
            self.tick()
            with SessionLocal() as db:
                for task in db.query(models.AgentTask).filter(models.AgentTask.status == "pending", models.AgentTask.sequence_run_id.isnot(None)).all():
                    seen.append((task.type, dict(task.payload or {})))
                    task.status = "done"
                    run = task.sequence_run
                    step = next(s for s in run.campaign.steps if s.id == task.payload["stepId"])
                    engine.move_past(list(run.campaign.steps), run, step, datetime.now(timezone.utc))
                    run.next_action_at = datetime.now(timezone.utc)
                db.commit()
        self.assertEqual([t for t, _ in seen], ["visit_profile", "follow_profile", "like_post", "withdraw_invite", "send_inmail", "send_voice_note"])
        inmail = seen[4][1]
        self.assertEqual((inmail["subject"], inmail["message"], inmail["free"]), ("Quick question", "Hello", False))
        self.assertEqual(seen[5][1]["audioId"], "audio-1")

    def test_a_voice_note_without_audio_stops_the_run_instead_of_sending_nothing(self):
        self.graph_campaign([("v", "voice_note", None, None, {"config": {"mode": "direct"}})], status="connected")
        self.tick()
        self.assertEqual(self.run_of("ann").stop_reason, "voice_note_missing")
        self.assertEqual(self.tasks("send_voice_note"), [])


class ValidationTest(GraphCase):
    def create(self, steps):
        return self.client.post("/campaigns", json={"action": "create", "name": "Smart", "sequenceMode": "smart", "steps": steps})

    def test_a_valid_tree_round_trips_with_temporary_ids_resolved(self):
        r = self.create([
            {"id": "t1", "type": "connection_request", "order": 0, "message": "Hi"},
            {"id": "t2", "type": "if_connected", "order": 1, "config": {"waitDays": 10}},
            {"id": "t3", "type": "message", "order": 0, "message": "Welcome", "parentStepId": "t2", "branchCondition": {"branch": "yes"}},
            {"id": "t4", "type": "follow", "order": 0, "parentStepId": "t2", "branchCondition": {"branch": "no"}}])
        self.assertIn(r.status_code, (200, 201), r.text)
        steps = {s["type"]: s for s in r.json()["steps"]}
        self.assertEqual(steps["message"]["parentStepId"], steps["if_connected"]["id"])
        self.assertEqual(steps["follow"]["branchCondition"], {"branch": "no"})
        self.assertEqual(steps["if_connected"]["config"], {"waitDays": 10})
        self.assertNotEqual(steps["message"]["parentStepId"], "t2")

    def test_trees_the_engine_cannot_run_are_refused_with_the_reason(self):
        cases = {
            "an If step with something after it": [{"id": "a", "type": "if_connected", "order": 0}, {"id": "b", "type": "message", "order": 1, "message": "x"}],
            "a branch under a step that is not an If": [{"id": "a", "type": "message", "order": 0, "message": "x"}, {"id": "b", "type": "follow", "order": 0, "parentStepId": "a", "branchCondition": {"branch": "yes"}}],
            "a branch with no yes or no": [{"id": "a", "type": "if_active", "order": 0}, {"id": "b", "type": "follow", "order": 0, "parentStepId": "a", "branchCondition": {"branch": "maybe"}}],
            "a branch pointing at nothing": [{"id": "b", "type": "follow", "order": 0, "parentStepId": "ghost", "branchCondition": {"branch": "yes"}}],
            "a step Synex does not know": [{"id": "a", "type": "teleport", "order": 0}],
            "a wait outside the range": [{"id": "a", "type": "if_connected", "order": 0, "config": {"waitDays": 99}}],
            "a script that is too long": [{"id": "a", "type": "voice_note", "order": 0, "config": {"mode": "ai", "script": "x" * 1001}}],
            "an unknown language": [{"id": "a", "type": "voice_note", "order": 0, "config": {"mode": "direct", "language": "fr-FR"}}],
        }
        for name, steps in cases.items():
            r = self.create(steps)
            self.assertEqual(r.status_code, 422, f"{name}: {r.text}")

    def test_nesting_is_limited(self):
        steps, parent = [], None
        for depth in range(step_types_depth() + 2):
            key = f"n{depth}"
            row = {"id": key, "type": "if_active", "order": 0}
            if parent:
                row.update(parentStepId=parent, branchCondition={"branch": "yes"})
            steps.append(row)
            parent = key
        self.assertEqual(self.create(steps).status_code, 422)

    def test_a_voice_note_that_is_not_ready_blocks_the_launch_with_the_reason(self):
        campaign_id, _ = self.graph_campaign([("v", "voice_note", None, None, {"config": {"mode": "ai", "language": "en-US"}})], status="connected")
        check = self.client.get(f"/campaigns/{campaign_id}/launch-check").json()
        reasons = [p["message"] for p in check["problems"] if p["kind"] == "voice_note_not_ready"]
        self.assertEqual(reasons, ["A voice note step is not ready. Write the script for the voice note."])

    def test_share_import_and_duplicate_keep_the_tree(self):
        campaign_id, _ = self.graph_campaign(CONNECT_THEN_BRANCH, status="connected")
        shared = self.client.get(f"/campaigns/{campaign_id}/share").json()
        imported = self.client.post("/campaigns", json={"action": "import", "sequence": shared})
        self.assertEqual(imported.status_code, 200, imported.text)
        for made in (imported.json(), self.client.post("/campaigns", json={"action": "duplicate", "id": campaign_id}).json()):
            by_type = {s["type"]: s for s in made["steps"]}
            self.assertEqual(by_type["message"]["parentStepId"], by_type["if_connected"]["id"])
            self.assertEqual(by_type["follow"]["branchCondition"], {"branch": "no"})
            self.assertEqual(by_type["if_connected"]["config"], {"waitDays": 15})


def step_types_depth():
    from app.routers import campaigns
    return campaigns.MAX_DEPTH


class PlanAndCeilingTest(GraphCase):
    def test_the_dry_run_follows_the_branch_the_lead_would_take(self):
        campaign_id, ids = self.graph_campaign(CONNECT_THEN_BRANCH, users=("ann", "bob"))
        with SessionLocal() as db:
            ann = db.query(models.Lead).filter_by(first_name="Ann").one()
            ann.status = "connected"
            db.commit()
        with SessionLocal() as db:
            plan = planner.plan_campaign(db, db.get(models.Campaign, campaign_id), datetime.now(timezone.utc))
        by_lead = {p.lead_name: p for p in plan}
        self.assertEqual(by_lead["Ann Test"].task_type, "send_message")
        self.assertEqual(by_lead["Bob Test"].task_type, "follow_profile")  # waits out the 15 days, then the "not connected" branch
        self.assertGreaterEqual((by_lead["Bob Test"].earliest_at - by_lead["Ann Test"].earliest_at), timedelta(days=14))

    def test_every_task_a_step_can_make_has_a_hard_ceiling(self):
        tasks = {spec[2] for spec in step_types.STEP_TYPES.values() if spec[2]}
        self.assertEqual(sorted(t for t in tasks if t not in DAILY_TYPE_CEILINGS), [])


if __name__ == "__main__":
    unittest.main()
