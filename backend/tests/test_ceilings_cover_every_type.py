"""Every action type that can reach LinkedIn has a hard daily ceiling. Fails if a new type is added without one."""
import re
import unittest
from pathlib import Path

from app.config import DAILY_TYPE_CEILINGS

APP = Path(__file__).resolve().parents[1] / "app"


def _types_in_code() -> set[str]:
    found: set[str] = set()
    worker = (APP / "outreach_worker.py").read_text(encoding="utf-8")
    found |= set(re.findall(r'task\.type == "([a-z_]+)"', worker))
    router = (APP / "routers" / "outreach.py").read_text(encoding="utf-8")
    literal = re.search(r"task_type: Literal\[(.*?)\]", router)
    if literal:
        found |= set(re.findall(r'"([a-z_]+)"', literal.group(1)))
    for name in ("engine.py", "planner.py"):
        found |= set(re.findall(r'emit_task\([^)]*?"([a-z_]+)"', (APP / name).read_text(encoding="utf-8")))
    return found


class CeilingCoverage(unittest.TestCase):
    def test_every_action_type_has_a_ceiling(self):
        types = _types_in_code()
        self.assertGreaterEqual(len(types), 6, f"type scan found too little: {types}")
        missing = sorted(t for t in types if t not in DAILY_TYPE_CEILINGS)
        self.assertEqual(missing, [], f"action types without a hard ceiling: {missing}")

    def test_collection_has_a_ceiling_and_all_are_positive(self):
        self.assertIn("collect_leads", DAILY_TYPE_CEILINGS)
        self.assertTrue(all(isinstance(v, int) and v > 0 for v in DAILY_TYPE_CEILINGS.values()))


if __name__ == "__main__":
    unittest.main()
