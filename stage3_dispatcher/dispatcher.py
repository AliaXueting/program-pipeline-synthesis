#!/usr/bin/env python3
"""Stage 3 — Dispatcher (paper: task decomposition).

1. Complexity score  xi = clip[0,10](log10(loc) + log10(1+deps) - 2)
   where loc = production lines of code, deps = runtime dependencies.
   easy (xi<2) -> 4 modules; medium (2<=xi<4) -> 6; hard (xi>=4) -> 8.
2. Decomposition agent (Claude Code harness) reads the repository source and
   produces modules.json: per module {name, source_paths, functional_description,
   interaction_categories in {Args, Config, Help, I/O, Subcommand, TUI}}.
3. Native test suites add one extra test-reuse module (per the paper).

Usage: python3 dispatcher.py --repo /path/to/repo --ws /path/to/workdir
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import subprocess
import sys
from pathlib import Path

VALID_CATEGORIES = {"Args", "Config", "Help", "I/O", "Subcommand", "TUI"}
PROD_SUFFIXES = {".go", ".c", ".cc", ".cpp", ".h", ".hpp", ".rs"}
TEST_MARKERS = ("_test.go", ".test.go", "/tests/", "/test/", "_test.py", ".spec.")


def production_loc(repo: Path, language: str) -> int:
    total = 0
    for p in repo.rglob("*"):
        if not p.is_file() or ".git" in p.parts:
            continue
        if p.suffix not in PROD_SUFFIXES:
            continue
        if any(m in str(p) for m in TEST_MARKERS):
            continue
        try:
            total += sum(1 for _ in p.open(errors="ignore"))
        except OSError:
            pass
    return total


def runtime_deps(repo: Path, language: str) -> int:
    go_mod = repo / "go.mod"
    if go_mod.exists():
        n = 0
        for line in go_mod.read_text().splitlines():
            if line.startswith(("\t", " ") and not line.strip().startswith("//")):
                if re.match(r"\s+\S+\s+v\S+", line) and " indirect" not in line:
                    n += 1
        return n
    cargo = repo / "Cargo.toml"
    if cargo.exists():
        txt = cargo.read_text()
        return len(re.findall(r"^\s*\w+\s*=\s*[\{\"]", txt.split("[dependencies]")[-1].split("[")[0], re.M))
    return 0


def has_native_tests(repo: Path) -> bool:
    return any(
        p.is_file() and any(m in p.name or m in str(p) for m in TEST_MARKERS)
        for p in repo.rglob("*") if ".git" not in p.parts
    )


def module_budget(xi: float) -> int:
    return 4 if xi < 2 else 6 if xi < 4 else 8


def run_agent(ws: Path, prompt: str, max_turns: int = 60) -> int:
    env = dict(os.environ)
    env.setdefault("ANTHROPIC_BASE_URL", "https://open.bigmodel.cn/api/anthropic")
    if "ANTHROPIC_AUTH_TOKEN" not in env:
        sys.exit("set ANTHROPIC_AUTH_TOKEN")
    env.setdefault("ANTHROPIC_MODEL", "glm-5.3")
    env.setdefault("ANTHROPIC_SMALL_FAST_MODEL", "glm-5.3-flash")
    env["CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC"] = "1"
    env["IS_SANDBOX"] = "1"
    return subprocess.run(
        ["claude", "--verbose", "--output-format=stream-json", "--max-turns", str(max_turns),
         "--permission-mode=bypassPermissions", "--print", prompt],
        cwd=ws, env=env,
    ).returncode


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--ws", required=True)
    args = ap.parse_args()
    repo, ws = Path(args.repo), Path(args.ws)
    ws.mkdir(parents=True, exist_ok=True)

    lang = "go" if (repo / "go.mod").exists() else "rust" if (repo / "Cargo.toml").exists() else "c-family"
    loc = production_loc(repo, lang)
    deps = runtime_deps(repo, lang)
    xi = max(0.0, min(10.0, math.log10(max(loc, 1)) + math.log10(1 + deps) - 2))
    n = module_budget(xi)
    print(f"loc={loc} deps={deps} xi={xi:.3f} -> {n} modules ({lang})")
    reuse = has_native_tests(repo)
    print(f"native tests present -> test_reuse={reuse}")

    tmpl = Path(__file__).parent / "INSTRUCTION.md"
    if not tmpl.exists():  # allow co-located template
        tmpl = Path(__file__).with_name("stage3-instruction.md")
    (ws / "INSTRUCTION.md").write_text(
        tmpl.read_text().replace("{N_MODULES}", str(n))
    )
    if not (ws / "sh-src").exists():
        os.symlink(repo.resolve(), ws / "sh-src")

    rc = run_agent(ws, "Read INSTRUCTION.md in the current working directory and do the task it describes.")
    modules_json = ws / "modules.json"
    if rc != 0 or not modules_json.exists():
        sys.exit(f"decomposition agent failed (rc={rc})")

    plan = json.loads(modules_json.read_text())
    mods = plan["modules"]
    problems = []
    if len(mods) != n:
        problems.append(f"module count {len(mods)} != budget {n}")
    names = set()
    for m in mods:
        if m["name"] in names:
            problems.append(f"duplicate module name {m['name']}")
        names.add(m["name"])
        if not m.get("source_paths"):
            problems.append(f"{m['name']}: empty source_paths")
        bad = set(m.get("interaction_categories", [])) - VALID_CATEGORIES
        if bad:
            problems.append(f"{m['name']}: invalid categories {bad}")
        if len(m.get("functional_description", "")) < 40:
            problems.append(f"{m['name']}: description too thin")
    if problems:
        print("PLAN PROBLEMS:", *problems, sep="\n  ")
        sys.exit(1)

    out = {
        "complexity": {"loc": loc, "deps": deps, "xi": xi, "budget": n, "language": lang},
        "test_reuse": bool(plan.get("test_reuse", reuse)),
        "modules": mods,
    }
    (ws / "plan.json").write_text(json.dumps(out, indent=2))
    print(f"plan written: {len(mods)} modules + test_reuse={out['test_reuse']} -> {ws/'plan.json'}")


if __name__ == "__main__":
    main()
