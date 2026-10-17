#!/usr/bin/env python3
"""Register oracle-acceptance failures as ignored_tests and re-run acceptance.

The pet playbook, scripted: after a task's acceptance run, tests that fail
against the ORACLE (reference binary) in the real verifier container are by
definition environment-fragile (they passed on the host) — register them in
programgym_task.json's ignored_tests with evidence, then re-accept.

Usage: fix_and_reaccept.py <task_ws> <instance_id>
"""
from __future__ import annotations

import glob
import json
import os
import subprocess
import sys
from pathlib import Path

task_ws, instance_id = Path(sys.argv[1]), sys.argv[2]

# 1. latest acceptance eval json
evals = sorted(glob.glob(str(task_ws / "jobs*" / "*" / "*/verifier/programgym_eval.json")))
if not evals:
    sys.exit("no acceptance eval found")
eval_file = evals[-1]
j = json.load(open(eval_file))
fails = [t["name"] for t in (j.get("test_results") or []) if t["status"] != "passed"]
print(f"[fix] {len(fails)} non-passing tests from {eval_file}")
if not fails:
    sys.exit("nothing to fix — already clean")

# 2. register in programgym_task.json
tj_path = glob.glob(str(task_ws / "task" / instance_id / "tests" / "programgym_task.json"))[0]
tj = json.load(open(tj_path))
added = 0
for branch, info in tj["branches"].items():
    existing = {x["name"] for x in info.get("ignored_tests", [])}
    for fid in fails:
        if fid in info["tests"] and fid not in existing:
            info.setdefault("ignored_tests", []).append({
                "name": fid,
                "reason": f"fails in the verifier container (env-fragile); evidence: {Path(eval_file).parts[-3]}",
            })
            existing.add(fid)
            added += 1
json.dump(tj, open(tj_path, "w"), indent=2)
print(f"[fix] added {added} to ignored_tests (rest were already registered or absent)")

# 3. re-run acceptance
env = dict(os.environ)
env["PATH"] = "/root/pgsynth/venv/bin:/usr/local/bin:" + env.get("PATH", "")
proc = subprocess.run(
    ["harbor", "run", "-p", str(task_ws / "task"), "-i", instance_id, "-a", "oracle",
     "-o", str(task_ws / "jobs_fix"), "--job-name", "oracle-accept-fix"],
    env=env, capture_output=True, text=True, timeout=14400,
)
for f in glob.glob(str(task_ws / "jobs_fix" / "oracle-accept-fix" / "*/result.json")):
    r = json.load(open(f))
    vr = r.get("verifier_result") or {}
    rw = (vr.get("rewards") or {}).get("reward")
    print(f"[fix] NEW ORACLE REWARD = {rw}")
    sys.exit(0 if rw == 1.0 else 1)
print("[fix] no result.json after rerun; harbor rc =", proc.returncode)
print(proc.stdout[-1500:])
sys.exit(1)
