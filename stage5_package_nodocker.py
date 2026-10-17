#!/usr/bin/env python3
"""Sandbox stage-5a: assemble the task skeleton + package blobs + task.json.

No Docker / no harbor acceptance here (the server does that). Mirrors
synthesize_task.sh's skeleton assembly plus stage5_package.package().
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


HERE = Path(__file__).parent
validator = _load("validator", HERE / "stage4_validator.py")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--task", required=True)
    ap.add_argument("--stage4-out", required=True)
    ap.add_argument("--plan", required=True)
    ap.add_argument("--commit", required=True)
    ap.add_argument("--repo-name", required=True)
    ap.add_argument("--instance-id", required=True)
    ap.add_argument("--src", default="/root/work/src")
    ap.add_argument("--ref", default="/root/work/execgen/executable")
    ap.add_argument("--go-tarball", default="/root/work/programgym-go.tar.gz")
    ap.add_argument("--template-dir", default="/root/pg/template",
                    help="dir with the task template files (Dockerfiles etc.)")
    a = ap.parse_args()

    task = Path(a.task)
    src = Path(a.src)
    ref = Path(a.ref)
    tmpl = Path(a.template_dir)
    name = a.instance_id            # owner--repo.commit
    inst_id = name.replace("--", "__")
    tool = a.repo_name.split("/")[-1]

    # ---------- skeleton ----------
    if not (task / "task.toml").exists():
        task.mkdir(parents=True, exist_ok=True)
        for side in ("environment", "tests", "solution"):
            (task / side).mkdir(exist_ok=True)
        # docs-only workspace from the repo
        ws_tar = "/root/work/workspace.tar.gz"
        subprocess.run(
            ["bash", "-c",
             f"cd {src} && tar czf {ws_tar} README.md LICENSE docs man 2>/dev/null "
             f"|| tar czf {ws_tar} README.md LICENSE 2>/dev/null "
             f"|| tar czf {ws_tar} README.md"], check=True)
        for side in ("environment", "tests"):
            shutil.copy2(ref, task / side / "executable")
            shutil.copy2(a.go_tarball, task / side / "programgym-go.tar.gz")
            shutil.copy2(tmpl / side / "Dockerfile", task / side / "Dockerfile")
        os.chmod(task / "environment/executable", 0o111)
        os.chmod(task / "tests/executable", 0o755)
        shutil.copy2(ws_tar, task / "environment/workspace.tar.gz")
        shutil.copy2(ws_tar, task / "tests/workspace.tar.gz")
        shutil.copy2(tmpl / "tests/test.sh", task / "tests/test.sh")
        shutil.copy2(tmpl / "tests/programgym_evaluator.py", task / "tests/programgym_evaluator.py")
        shutil.copy2(tmpl / "solution/solve.sh", task / "solution/solve.sh")
        shutil.copy2(tmpl / "instruction.md", task / "instruction.md")
        # task.toml from the template, re-targeted
        toml = (tmpl / "task.toml").read_text()
        toml = toml.replace("mvdan--sh.0e8ea6f", name)
        toml = toml.replace("mvdan__sh.0e8ea6f", inst_id)
        toml = toml.replace("mvdan/sh", a.repo_name)
        toml = toml.replace("0e8ea6fccd96", a.commit)
        toml = toml.replace("shfmt", tool)
        toml = toml.replace('network_mode = "allowlist"', 'network_mode = "public"')
        toml = re.sub(r"^allowed_hosts = .*\n", "", toml, flags=re.M)
        (task / "task.toml").write_text(toml)
        # China-network Dockerfile patches
        for side in ("environment", "tests"):
            df = task / side / "Dockerfile"
            txt = df.read_text()
            txt = txt.replace('GOPROXY="https://proxy.golang.org,direct"',
                              'GOPROXY="https://goproxy.cn,direct"')
            txt = txt.replace('PIP_INDEX_URL="https://pypi.org/simple"',
                              'PIP_INDEX_URL="https://pypi.tuna.tsinghua.edu.cn/simple"')
            df.write_text(txt)
        # managed download.sh from go.mod (both contexts)
        subprocess.run(
            ["python3", str(HERE / "gen_download.py"),
             str(src / "go.mod"), str(task / "environment/download.sh"), name],
            check=True)
        shutil.copy2(task / "environment/download.sh", task / "tests/download.sh")
        print(f"[s5a] skeleton assembled at {task}")

    # ---------- blobs + task.json (package.py logic, no acceptance) ----------
    plan = json.loads(Path(a.plan).read_text())
    s4 = Path(a.stage4_out)
    xi = plan["complexity"]["xi"]
    difficulty = "easy" if xi < 2 else "medium" if xi < 4 else "hard"

    blobs = task / "tests/blobs/tests"
    if blobs.exists():
        shutil.rmtree(task / "tests/blobs")
    blobs.mkdir(parents=True)

    branches, total_tests, total_ignored = {}, 0, 0
    mods = plan["modules"] + ([{"name": "test_reuse"}] if plan.get("test_reuse") else [])
    for mod in mods:
        mname = mod["name"]
        mws = s4 / mname
        if not (mws / "eval/run.sh").exists():
            continue
        with tempfile.TemporaryDirectory() as td:
            v = validator.validate_module(mws, task / "environment/executable", Path(td))
        if "error" in v:
            print(f"[s5a] {mname}: {v['error']}")
            continue
        rejected = {t for t, x in v["tests"].items() if x["verdict"] == "REJECT"}
        total_tests += len(v["tests"])
        total_ignored += len(rejected)
        print(f"[s5a] {mname}: {len(v['tests']) - len(rejected)} kept, {len(rejected)} ignored")
        subprocess.run(["tar", "czf", str(blobs / f"{mname}.tar.gz"),
                        "-C", str(mws), "eval"], check=True)
        branches[mname] = {
            "ignore_reason": "",
            "ignored": False,
            "ignored_tests": [{"name": t} for t in sorted(rejected)],
            "tests": sorted(v["tests"].keys()),
        }

    task_json = {
        "branches": branches,
        "commit": a.commit,
        "data_source": "program-pipeline-synthesis",
        "difficulty": difficulty,
        "difficulty_score": round(xi, 4),
        "eval_clean_hashes": [],
        "input_record": {},
        "instance_id": inst_id,
        "language": plan["complexity"]["language"],
        "module_iterations": {k: 1 for k in branches},
        "repository": a.repo_name,
    }
    (task / "tests/programgym_task.json").write_text(json.dumps(task_json, indent=2))

    toml = (task / "task.toml").read_text()
    toml = re.sub(r"test_branches = \d+", f"test_branches = {len(branches)}", toml)
    toml = re.sub(r"test_count = \d+", f"test_count = {total_tests}", toml)
    toml = re.sub(r'difficulty = "\w+"', f'difficulty = "{difficulty}"', toml)
    (task / "task.toml").write_text(toml)
    print(f"[s5a] packaged {len(branches)} branches, {total_tests} tests "
          f"({total_ignored} ignored) -> {task}")


if __name__ == "__main__":
    main()
