#!/usr/bin/env python3
"""Four-check validation (paper Eq.3): pass / double / dummy / weak-assert.

pass  — the test must pass against the reference implementation
double — two runs in isolated working dirs must agree
dummy — replacing the program with a no-output dummy must NOT pass the test
linter — static weak-assert rules (stage4_linter)

A test survives only if all four checks are green.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import importlib.util

_spec = importlib.util.spec_from_file_location(
    "linter", Path(__file__).parent / "linter.py")
linter = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(linter)


def run_suite(eval_dir: Path, exe: Path, work_root: Path, tag: str) -> dict[str, str]:
    """Run the module suite in an ISOLATED copy; return {test_id: status}."""
    branch = work_root / f"{eval_dir.parent.name}__{tag}"
    if branch.exists():
        shutil.rmtree(branch)
    branch.mkdir(parents=True)
    shutil.copytree(eval_dir, branch / "eval")
    shutil.copy2(exe, branch / "executable")
    os.chmod(branch / "executable", 0o755)
    env = dict(os.environ)
    env["PROGRAMGYM_EXECUTABLE"] = str(branch / "executable")
    env["PROGRAMGYM_PYTEST_WORKERS"] = "2"
    try:
        subprocess.run(["bash", "eval/run.sh"], cwd=branch, env=env,
                       capture_output=True, timeout=1800)
    except subprocess.TimeoutExpired:
        return {}
    xmlp = branch / "eval/results.xml"
    out: dict[str, str] = {}
    if xmlp.exists():
        for tc in ET.parse(xmlp).getroot().iter("testcase"):
            tid = f"{tc.get('classname','')}.{tc.get('name','')}".lstrip(".")
            if tc.find("failure") is not None or tc.find("error") is not None:
                out[tid] = "failure"
            elif tc.find("skipped") is not None:
                out[tid] = "skipped"
            else:
                out[tid] = "passed"
    return out


def make_dummy(path: Path) -> Path:
    path.write_text("#!/bin/sh\nexit 0\n")
    os.chmod(path, 0o755)
    return path


def validate_module(module_ws: Path, ref: Path, work_root: Path) -> dict:
    """Returns {tests, verdicts, stats} and writes validation_results.md."""
    eval_dir = module_ws / "eval"
    docs = module_ws / "Feedback_Docs"
    docs.mkdir(exist_ok=True)
    if not (eval_dir / "run.sh").exists() or not list((eval_dir / "tests").glob("test_*.py")):
        return {"error": "no tests written yet"}

    r1 = run_suite(eval_dir, ref, work_root, "pass1")
    r2 = run_suite(eval_dir, ref, work_root, "pass2")
    with tempfile.TemporaryDirectory() as td:
        dummy = make_dummy(Path(td) / "dummy")
        rd = run_suite(eval_dir, dummy, work_root, "dummy")

    lint_out = {}
    for f in sorted((eval_dir / "tests").glob("test_*.py")):
        try:
            # nested per-file (lint_test_file returns {test_name: findings});
            # do NOT flatten with update() — lint_errors_for expects file keys
            lint_out[str(f)] = linter.lint_test_file(f)
        except SyntaxError as e:
            lint_out[str(f)] = {"__file__": [{"level": "E0", "msg": f"syntax error: {e}"}]}

    def lint_errors_for(tid: str) -> list[dict]:
        # tid = eval.tests.test_file.test_name[param]
        errs = []
        for fname, tests in lint_out.items():
            base = Path(fname).stem
            if f".test_{base}." not in tid and not tid.startswith(f"eval.tests.{base}."):
                continue
            for tname, finds in tests.items():
                if tid.startswith(f"eval.tests.{base}.{tname}") or tid.startswith(f"eval.tests.{base}.{tname}["):
                    errs += [f for f in finds if str(f["level"]).startswith("E")]
        return errs

    verdicts = {}
    for tid in r1:
        reasons = []
        if r1[tid] != "passed":
            reasons.append(f"pass-check failed ({r1[tid]})")
        if r2.get(tid) != r1.get(tid):
            reasons.append(f"double-check unstable ({r1[tid]} vs {r2.get(tid)})")
        if rd.get(tid) == "passed":
            reasons.append("dummy-check: still passes against no-output dummy")
        le = lint_errors_for(tid)
        if le:
            reasons.append("linter: " + "; ".join(f"{x['level']} {x['msg']}" for x in le))
        verdicts[tid] = {"verdict": "OK" if not reasons else "REJECT",
                         "reasons": reasons}

    n_ok = sum(1 for v in verdicts.values() if v["verdict"] == "OK")
    lines = [f"# Validation results — {module_ws.name}", "",
             f"- tests collected: {len(verdicts)}",
             f"- OK: {n_ok}",
             f"- REJECTED: {len(verdicts) - n_ok}", ""]
    for tid, v in sorted(verdicts.items()):
        mark = "OK    " if v["verdict"] == "OK" else "REJECT "
        lines.append(f"- {mark} `{tid}`" + (f" — {'; '.join(v['reasons'])}" if v["reasons"] else ""))
    (docs / "validation_results.md").write_text("\n".join(lines) + "\n")
    return {"tests": verdicts, "n_ok": n_ok, "n_total": len(verdicts)}


if __name__ == "__main__":
    ws, ref = Path(sys.argv[1]), Path(sys.argv[2])
    print(json.dumps(validate_module(ws, ref, Path(tempfile.mkdtemp())), indent=1))
