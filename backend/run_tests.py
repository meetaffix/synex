"""Run the backend tests in parallel processes: the same tests as ``python -m unittest discover -s tests``, faster.

    python run_tests.py                  # all tests
    python run_tests.py -j 4             # at most 4 parallel processes
    python run_tests.py --repeat 3       # run the whole suite 3 times and require identical results
    python run_tests.py test_env         # only some modules (or module.Class)

How it stays safe:

* ISOLATION. Every job (one test class) is a separate Python process with its own temporary directory: the runner
  points TMP, TEMP and TMPDIR at a fresh folder per job, and every test module creates its temporary database in
  ``tempfile.TemporaryDirectory()`` (``safety.assert_isolated_database`` refuses anything else), so no two jobs ever
  share a database file. Every mock server (LinkedIn, proxy, Deepgram) binds port 0, so the operating system gives each
  its own port. The runner fails if any test binds a fixed port.
* SERIAL GROUP. A class with ``serial = True`` is a concurrency test (leases, claims, two workers, kill mid-action,
  idempotency). Those always run first, one at a time, with nothing else running; only then does the parallel pool start.
* SAME TESTS. ``--repeat N`` runs the whole suite N times and requires every run to pass, to run exactly the number of
  tests the sequential loader counts, and to give identical per-class counts.

Exit code 0 only when everything above holds. For one process, in order: ``python -m unittest discover -s tests``.
"""
from __future__ import annotations

import argparse
import ast
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

BACKEND = Path(__file__).resolve().parent
TESTS = BACKEND / "tests"
# Modules whose tests are slow per test (real browsers, real worker processes): scheduled first.
WEIGHT = {"test_worker_process": 12, "test_linkedin_session": 3, "test_outreach": 2, "test_assistant": 2}
DEFAULT_JOBS = min(8, os.cpu_count() or 2)


def _is_serial(node: ast.ClassDef, classes: dict[str, ast.ClassDef], seen: frozenset = frozenset()) -> bool:
    for stmt in node.body:
        if isinstance(stmt, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "serial" for t in stmt.targets):
            return bool(getattr(stmt.value, "value", False))
    for base in node.bases:
        name = getattr(base, "id", None)
        if name in classes and name not in seen and _is_serial(classes[name], classes, seen | {node.name}):
            return True
    return False


def jobs_for(modules: list[str]) -> list[tuple[str, int, bool]]:
    """(unittest target, weight, serial), one per test class."""
    jobs: list[tuple[str, int, bool]] = []
    for path in sorted(TESTS.glob("test_*.py")):
        module = path.stem
        if modules and not any(m == module or m.startswith(module + ".") for m in modules):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        classes = {n.name: n for n in tree.body if isinstance(n, ast.ClassDef)}
        def tests_in(node: ast.ClassDef, seen: frozenset = frozenset()) -> int:
            """Test methods a class has: its own plus the ones it inherits from a base class in the same file."""
            own = sum(isinstance(n, ast.FunctionDef) and n.name.startswith("test_") for n in node.body)
            for base in node.bases:
                name = getattr(base, "id", None)
                if name in classes and name not in seen:
                    own += tests_in(classes[name], seen | {node.name})
            return own
        for node in classes.values():
            count = tests_in(node)
            if count:
                target = f"{module}.{node.name}"
                if not modules or any(m == module or m == target for m in modules):
                    jobs.append((target, count * WEIGHT.get(module, 1), _is_serial(node, classes)))
    return sorted(jobs, key=lambda j: -j[1])


def fixed_ports() -> list[str]:
    """Test files that bind a fixed port (a clash waiting to happen). Every mock server must bind port 0."""
    found = []
    bind = re.compile(r"(ThreadingHTTPServer|HTTPServer|serve|bind)\s*\(\s*\(?\s*[\"'][\w.]+[\"']\s*,\s*([1-9]\d*)\b")
    for path in sorted(TESTS.glob("*.py")):
        if path.name == "browser_server.py":
            continue  # started by Playwright on its own port, never by this runner
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if bind.search(line):
                found.append(f"{path.name}:{number}")
    return found


def run_job(target: str, index: int, root: Path) -> dict:
    started = time.monotonic()
    home = root / f"{index:03d}-{target}"
    home.mkdir(parents=True)
    env = {**os.environ, "PYTHONPATH": os.pathsep.join([str(TESTS), str(BACKEND)]), "PYTHONWARNINGS": "ignore",
           "TMP": str(home), "TEMP": str(home), "TMPDIR": str(home), "SYNEX_TEST_JOB": target}
    done = subprocess.run([sys.executable, "-m", "unittest", target], cwd=BACKEND, env=env, capture_output=True, text=True)
    output = done.stdout + done.stderr
    ran = re.search(r"^Ran (\d+) tests? in", output, re.M)
    databases = sorted(str(p.relative_to(root)) for p in home.rglob("*.db"))
    return {"target": target, "code": done.returncode, "ran": int(ran.group(1)) if ran else 0,
            "seconds": time.monotonic() - started, "output": output, "databases": databases}


def sequential_count() -> int:
    """How many different tests the ordinary loader finds: the reference every parallel run is compared with. A test is counted
    once by its id: a module that imports a base class to subclass it makes the loader find that base a second time."""
    code = """
import unittest
ids = set()
def walk(suite):
    for t in suite:
        walk(t) if isinstance(t, unittest.TestSuite) else ids.add(unittest.TestCase.id(t))
walk(unittest.defaultTestLoader.discover('tests'))
print(len(ids))
"""
    env = {**os.environ, "PYTHONPATH": os.pathsep.join([str(TESTS), str(BACKEND)]), "PYTHONWARNINGS": "ignore"}
    out = subprocess.run([sys.executable, "-c", code], cwd=BACKEND, env=env, capture_output=True, text=True).stdout.strip().splitlines()
    return int(out[-1]) if out and out[-1].isdigit() else -1


def run_suite(jobs: list[tuple[str, int, bool]], workers: int, label: str) -> dict:
    root = Path(tempfile.mkdtemp(prefix="synex-tests-"))
    started = time.monotonic()
    results: list[dict] = []
    serial = [j for j in jobs if j[2]]
    parallel = [j for j in jobs if not j[2]]
    index = 0
    print(f"-- {label}: {len(serial)} serial class(es) first, one at a time, then {len(parallel)} in parallel ({workers} processes)", flush=True)

    def show(r):
        status = "ok  " if r["code"] == 0 and r["ran"] else "FAIL"
        print(f"{status} {r['target']:70} {r['ran']:3} tests {r['seconds']:6.1f}s", flush=True)

    for target, _, _ in serial:  # nothing else runs while a concurrency test does
        index += 1
        r = run_job(target, index, root)
        results.append(r)
        show(r)
    with ThreadPoolExecutor(max_workers=max(workers, 1)) as pool:
        futures = []
        for target, _, _ in parallel:
            index += 1
            futures.append(pool.submit(run_job, target, index, root))
        for future in futures:
            r = future.result()
            results.append(r)
            show(r)
    databases = [d for r in results for d in r["databases"]]
    isolated = len(set(databases)) == len(databases)  # every database path starts with its own job folder
    shutil.rmtree(root, ignore_errors=True)
    return {"seconds": time.monotonic() - started, "results": results, "total": sum(r["ran"] for r in results),
            "failed": [r for r in results if r["code"] != 0 or not r["ran"]], "databases": len(databases), "isolated": isolated,
            "per_class": {r["target"]: r["ran"] for r in results}}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("modules", nargs="*", help="test modules or module.Class to run (default: all)")
    parser.add_argument("-j", "--jobs", type=int, default=DEFAULT_JOBS)
    parser.add_argument("--repeat", type=int, default=1, help="run the suite this many times and require identical results")
    args = parser.parse_args()
    jobs = jobs_for(args.modules)
    if not jobs:
        print("No tests found.")
        return 2
    clashes = fixed_ports()
    if clashes:
        print("FAILED: these tests bind a fixed port, which parallel runs would clash on (use port 0):", ", ".join(clashes))
        return 2
    print(f"ports: no test binds a fixed port (every mock server binds port 0, so each process gets its own)")
    expected = sequential_count() if not args.modules else None
    if expected is not None:
        print(f"reference: the sequential loader counts {expected} tests")
    runs = []
    for number in range(1, args.repeat + 1):
        run = run_suite(jobs, args.jobs, f"run {number} of {args.repeat}")
        runs.append(run)
        print(f"run {number}: {run['total']} tests in {run['seconds']:.1f}s, {len(run['failed'])} failed class(es), "
              f"{run['databases']} database file(s), each in its own job folder: {'yes' if run['isolated'] else 'NO'}", flush=True)
    problems = []
    for number, run in enumerate(runs, 1):
        for r in run["failed"]:
            problems.append(f"run {number}: {r['target']} failed")
            print(f"\n===== run {number}: {r['target']} =====")
            print("\n".join(l for l in r["output"].splitlines() if "ResourceWarning" not in l)[-5000:])
        if expected is not None and run["total"] != expected:
            problems.append(f"run {number}: ran {run['total']} tests, the sequential loader counts {expected}")
        if run["per_class"] != runs[0]["per_class"]:
            problems.append(f"run {number}: per-class counts differ from run 1")
        if not run["isolated"]:
            problems.append(f"run {number}: two jobs shared a database path")
    times = ", ".join(f"{r['seconds']:.0f}s" for r in runs)
    print(f"\n{len(runs)} run(s): {times}; tests per run: {[r['total'] for r in runs]}")
    if problems:
        print("NOT READY:\n  " + "\n  ".join(problems))
        return 1
    print("OK: every run passed, ran the same tests, and matched the sequential count" if expected is not None else "OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
