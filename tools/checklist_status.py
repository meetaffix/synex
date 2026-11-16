"""Count checklist lines per area, reproducibly: python tools/checklist_status.py [path] [--markdown].

An area is the number before the first dot of a line's ID (3.A01 -> area 3). A line is ticked [x], partial [~] or open [ ] ("blocked:" is counted as open and listed).
LinkedIn-dependent lines carry a tag: "[LV:mock]" built and tested on the mock site only, "[LV:real]" verified on real LinkedIn. Lines with neither tag are not LinkedIn-dependent.
"Done" for an area means ticked == total."""
import re
import sys
from collections import defaultdict
from pathlib import Path

LINE = re.compile(r"^\s*- \[( |x|X|~)\]\s+(\d+)\.([A-Za-z0-9]+)\b(.*)$")


def count(text: str):
    areas = defaultdict(lambda: {"ticked": 0, "partial": 0, "open": 0, "mock": 0, "real": 0, "blocked": []})
    for line in text.splitlines():
        m = LINE.match(line)
        if not m:
            continue
        mark, area, ident, rest = m.groups()
        a = areas[int(area)]
        a["ticked" if mark in "xX" else "partial" if mark == "~" else "open"] += 1
        if "[LV:real]" in rest:
            a["real"] += 1
        elif "[LV:mock]" in rest:
            a["mock"] += 1
        if "blocked:" in rest.lower():
            a["blocked"].append(f"{area}.{ident}")
    return dict(sorted(areas.items()))


def render(areas, markdown=False) -> str:
    head = ["Area", "Ticked", "Partial", "Open", "Total", "Done", "LV mock-tested", "LV verified real"]
    rows = []
    totals = [0] * 6
    for area, a in areas.items():
        total = a["ticked"] + a["partial"] + a["open"]
        rows.append([str(area), a["ticked"], a["partial"], a["open"], total, "yes" if a["ticked"] == total else "no", a["mock"], a["real"]])
        for i, v in enumerate((a["ticked"], a["partial"], a["open"], total, a["mock"], a["real"])):
            totals[i] += v
    rows.append(["all", *totals[:4], "", totals[4], totals[5]])
    sep = " | " if markdown else "  "
    lines = [sep.join(str(c) for c in head)] + ([" | ".join(["---"] * len(head))] if markdown else []) + [sep.join(str(c) for c in r) for r in rows]
    blocked = [b for a in areas.values() for b in a["blocked"]]
    if blocked:
        lines.append("Blocked: " + ", ".join(blocked))
    return "\n".join(f"| {l} |" if markdown else l for l in lines)


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    path = Path(args[0]) if args else Path(__file__).resolve().parent.parent / "docs" / "CHECKLIST.md"
    print(render(count(path.read_text(encoding="utf8")), "--markdown" in sys.argv))
