#!/usr/bin/env python3
"""Stage 5 — Merge, re-validate, package, and run the oracle acceptance.

Paper: after merging all module suites, validate again and keep only tests that
pass every check; package as a Harbor task (schema 1.3) and confirm the oracle
(solution/solve.sh, the released ceiling-check mechanism) scores reward = 1.0.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import importlib.util

_VALIDATOR = Path(__file__).parent / "validator.py"
if not _VALIDATOR.exists():
    _VALIDATOR = Path(__file__).parent.parent / "stage4_testgen" / "validator.py"
_spec = importlib.util.spec_from_file_location("validator", _VALIDATOR)
validator = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(validator)


def package(task: Path, stage4_out: Path, plan: Path, commit: str, repo_name: str,
            instance_id: str) -> dict:
    plan_data = json.loads(Path(plan).read_text())
    state = json.loads((stage4_out / "stage4_state.json").read_text())
    xi = plan_data["complexity"]["xi"]
    difficulty = "easy" if xi < 2 else "medium" if xi < 4 else "hard"

    blobs = task / "tests/blobs/tests"
    if (task / "tests/blobs").exists():
        shutil.rmtree(task / "tests/blobs")
    blobs.mkdir(parents=True)

    branches, total_tests, total_ignored = {}, 0, 0
    for mod in plan_data["modules"] + ([{"name": "test_reuse"}] if plan_data.get("test_reuse") else []):
        name = mod["name"]
        mws = stage4_out / name
        eval_dir = mws / "eval"
        if not (eval_dir / "run.sh").exists():
            print(f"[stage5] {name}: no eval dir, skipping")
            continue

        # final merged validation (pass/double/dummy) in a scratch dir
        with tempfile.TemporaryDirectory() as td:
            v = validator.validate_module(mws, task / "environment/executable", Path(td))
        if "error" in v:
            print(f"[stage5] {name}: {v['error']}")
            continue
        rejected = {t for t, x in v["tests"].items() if x["verdict"] == "REJECT"}
        kept = [t for t in v["tests"] if t not in rejected]
        total_tests += len(v["tests"])
        total_ignored += len(rejected)
        print(f"[stage5] {name}: {len(kept)} kept, {len(rejected)} -> ignored_tests")

        # bundle: eval/ exactly as the released blob layout
        arc = blobs / f"{name}.tar.gz"
        subprocess.run(["tar", "czf", str(arc), "-C", str(mws), "eval"], check=True)

        branches[name] = {
            "ignore_reason": "",
            "ignored": False,
            "ignored_tests": [{"name": t} for t in sorted(rejected)],
            "tests": sorted(v["tests"].keys()),
        }

    task_json = {
        "branches": branches,
        "commit": commit,
        "data_source": "program-pipeline-synthesis",
        "difficulty": difficulty,
        "difficulty_score": round(xi, 4),
        "eval_clean_hashes": [],
        "input_record": {},
        "instance_id": instance_id.replace("--", "__"),
        "language": plan_data["complexity"]["language"],
        "module_iterations": {k: state["state"].get(k, {}).get("rounds", 0) for k in branches},
        "repository": repo_name,
    }
    (task / "tests/programgym_task.json").write_text(json.dumps(task_json, indent=2))

    toml = (task / "task.toml").read_text()
    toml = re.sub(r"test_branches = \d+", f"test_branches = {len(branches)}", toml)
    toml = re.sub(r"test_count = \d+", f"test_count = {total_tests}", toml)
    toml = re.sub(r'difficulty = "\w+"', f'difficulty = "{difficulty}"', toml)
    (task / "task.toml").write_text(toml)
    print(f"[stage5] packaged {len(branches)} branches, {total_tests} tests "
          f"({total_ignored} ignored) -> {task}")
    return {"branches": len(branches), "tests": total_tests, "ignored": total_ignored}


def acceptance(task_parent: Path, task_name: str, jobs_dir: Path) -> float:
    """harbor run -a oracle — the released ceiling-check acceptance."""
    env = dict(os.environ)
    # keep the caller PATH: the venv harbor (>=0.20) must win over any
    # uv-tool harbor shim in ~/.local/bin
    pass
    env.setdefault("ANTHROPIC_BASE_URL", "https://open.bigmodel.cn/api/anthropic")
    if "ANTHROPIC_AUTH_TOKEN" not in env:
        sys.exit("set ANTHROPIC_AUTH_TOKEN (oracle agent may not need it, harbor defaults may)")
    proc = subprocess.run(
        ["harbor", "run", "-p", str(task_parent), "-i", task_name, "-a", "oracle",
         "-o", str(jobs_dir), "--job-name", "stage5-acceptance"],
        env=env, capture_output=True, text=True, timeout=7200,
    )
    print(proc.stdout[-3000:])
    # find the reward
    import glob
    for rj in glob.glob(str(jobs_dir / "stage5-acceptance" / "*/result.json")):
        r = json.loads(open(rj).read())
        vr = (r.get("verifier_result") or {}).get("rewards") or {}
        return vr.get("reward", -1)
    return -1


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--task", required=True, help="task package dir")
    ap.add_argument("--stage4-out", required=True)
    ap.add_argument("--plan", required=True)
    ap.add_argument("--commit", required=True)
    ap.add_argument("--repo-name", default="mvdan/sh")
    ap.add_argument("--instance-id", default="mvdan--sh.0e8ea6f")
    ap.add_argument("--jobs", default="/root/pgsynth/jobs")
    ap.add_argument("--acceptance", action="store_true",
                    help="run harbor oracle acceptance after packaging")
    a = ap.parse_args()
    task = Path(a.task)
    stats = package(task, Path(a.stage4_out), Path(a.plan), a.commit, a.repo_name, a.instance_id)
    if a.acceptance:
        reward = acceptance(task.parent, task.name, Path(a.jobs))
        print(f"[stage5] ORACLE REWARD = {reward}")
        sys.exit(0 if reward == 1.0 else 1)
