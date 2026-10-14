#!/usr/bin/env python3
"""Stage 4 — Test construction orchestrator (paper: parallel module subagents).

Per round, for every module IN PARALLEL: run the test-construction agent, then
validate (pass/double/dummy/linter) and compute instrumented coverage of the
module's assigned files, then write Feedback_Docs for the next round
("repairs first, then new tests"). A module terminates at the functionality
coverage threshold or the round limit.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import importlib.util

for name in ("stage4_coverage", "stage4_validator"):
    _spec = importlib.util.spec_from_file_location(name, Path(__file__).parent / f"{name}.py")
    _mod = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(_mod)
    globals()[name.split("_", 1)[1]] = _mod  # coverage, validator

CATEGORIES_DOC = {
    "Args": "flag syntax, required/optional arguments, type checking",
    "Config": "environment variables and config files, precedence conflicts",
    "Help": "--help/-h output and per-subcommand help",
    "I/O": "stdin/file reading, stdout/stderr separation, exit codes, output format",
    "Subcommand": "routing, alias resolution, global vs subcommand flags",
    "TUI": "keyboard navigation, keybindings, screen updates, mode switching",
}


def agent_env() -> dict:
    env = dict(os.environ)
    env.setdefault("ANTHROPIC_BASE_URL", "https://open.bigmodel.cn/api/anthropic")
    if "ANTHROPIC_AUTH_TOKEN" not in env:
        sys.exit("set ANTHROPIC_AUTH_TOKEN")
    env.setdefault("ANTHROPIC_MODEL", "glm-5.3")
    env.setdefault("ANTHROPIC_SMALL_FAST_MODEL", "glm-5.3-flash")
    env["CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC"] = "1"
    env["IS_SANDBOX"] = "1"
    return env


def setup_module(ws: Path, mod: dict, repo: Path, ref: Path, docs_dir: Path,
                 fmt_example: Path, run_sh: Path, instruction_tmpl: str,
                 target_tests: int, max_rounds: int, is_reuse: bool) -> Path:
    mws = ws / mod["name"]
    if mws.exists():
        return mws
    (mws / "Feedback_Docs").mkdir(parents=True)
    (mws / "eval/tests").mkdir(parents=True)
    shutil.copy2(run_sh, mws / "eval/run.sh")
    shutil.copy2(ref, mws / "executable")
    os.chmod(mws / "executable", 0o755)
    os.symlink(repo.resolve(), mws / "src")
    os.symlink(docs_dir.resolve(), mws / "docs")
    os.symlink(fmt_example.resolve(), mws / "format-example")
    cats = ", ".join(f"`{c}` ({CATEGORIES_DOC[c]})" for c in mod["interaction_categories"])
    assignment = (
        f"- name: {mod['name']}\n"
        f"- source_paths: {', '.join(mod['source_paths'])}\n"
        f"- functional_description: {mod['functional_description']}\n"
        f"- interaction_categories: {cats}\n"
        + ("- This is the TEST-REUSE module: mine the repository's NATIVE test suite "
           "under ./src/ (e.g. *_test.go) for behavioral cases, and rewrite them as "
           "black-box CLI tests of ./executable.\n" if is_reuse else "")
    )
    (mws / "INSTRUCTION.md").write_text(
        instruction_tmpl
        .replace("{MODULE}", mod["name"])
        .replace("{ASSIGNMENT}", assignment)
        .replace("{TARGET_TESTS}", str(target_tests))
        .replace("{MAX_ROUNDS}", str(max_rounds))
    )
    return mws


def run_round(agents: dict[str, subprocess.Popen]) -> None:
    while any(p.poll() is None for p in agents.values()):
        time.sleep(10)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", required=True)
    ap.add_argument("--repo", required=True)
    ap.add_argument("--ref", required=True, help="reference executable from stage 2")
    ap.add_argument("--main-pkg", default="./cmd/shfmt")
    ap.add_argument("--out", required=True)
    ap.add_argument("--docs", default=None)
    ap.add_argument("--format-example", default="/root/synth/format-example")
    ap.add_argument("--run-sh", default="/root/synth/format-example/eval/run.sh")
    ap.add_argument("--instruction", default=str(Path(__file__).parent / "INSTRUCTION.md"))
    ap.add_argument("--rounds", type=int, default=5)
    ap.add_argument("--threshold", type=float, default=0.8)
    ap.add_argument("--target-tests", type=int, default=60)
    ap.add_argument("--max-turns", type=int, default=120)
    args = ap.parse_args()

    plan = json.loads(Path(args.plan).read_text())
    repo, ref, out = Path(args.repo), Path(args.ref), Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    docs_dir = Path(args.docs) if args.docs else repo
    instr_tmpl = Path(args.instruction).read_text()
    env = agent_env()

    modules = plan["modules"] + ([{
        "name": "test_reuse",
        "source_paths": ["."],
        "functional_description": "Rewrite the repository's native test suite as black-box behavioral tests.",
        "interaction_categories": ["I/O"],
    }] if plan.get("test_reuse") else [])

    print(f"[stage4] {len(modules)} modules, {args.rounds} rounds max, "
          f"coverage threshold {args.threshold:.0%}")

    print("[stage4] building instrumented reference (-cover -coverpkg=./...) ...")
    cov_bin = out / "executable.cov"
    coverage.build_instrumented(repo, args.main_pkg, cov_bin)

    mws_map = {}
    for mod in modules:
        mws_map[mod["name"]] = setup_module(
            out, mod, repo, ref, docs_dir, Path(args.format_example),
            Path(args.run_sh), instr_tmpl, args.target_tests, args.rounds,
            mod["name"] == "test_reuse",
        )

    state = {m["name"]: {"done": False, "rounds": 0, "coverage_pct": None,
                         "n_ok": 0, "n_total": 0} for m in modules}
    verdicts_all: dict[str, dict] = {}

    for rnd in range(1, args.rounds + 1):
        pending = [n for n, s in state.items() if not s["done"]]
        if not pending:
            break
        print(f"\n[stage4] === round {rnd}/{args.rounds} — modules: {pending} ===")
        agents = {}
        for name in pending:
            mws = mws_map[name]
            if rnd == 1:
                prompt = (f"Read INSTRUCTION.md in the current working directory and do the "
                          f"task it describes. This is round 1 of {args.rounds}.")
            else:
                prompt = (f"Round {rnd} of {args.rounds}. REPAIRS FIRST, THEN NEW TESTS: read "
                          f"Feedback_Docs/validation_results.md and repair/delete every REJECTED "
                          f"test, then read Feedback_Docs/coverage_report.md and write new tests "
                          f"for the listed target files. Update Feedback_Docs/summary.md. "
                          f"Follow INSTRUCTION.md for the full contract.")
            log = open(mws / f"agent_round{rnd}.log", "w")
            agents[name] = subprocess.Popen(
                ["claude", "--verbose", "--output-format=stream-json",
                 "--max-turns", str(args.max_turns),
                 "--permission-mode=bypassPermissions", "--print", prompt],
                cwd=mws, env=env, stdout=log, stderr=subprocess.STDOUT,
            )
        run_round(agents)

        for name in pending:
            mws = mws_map[name]
            state[name]["rounds"] = rnd
            v = validator.validate_module(mws, ref, out / "_val")
            if "error" in v:
                print(f"  {name}: {v['error']}")
                continue
            state[name]["n_ok"], state[name]["n_total"] = v["n_ok"], v["n_total"]
            verdicts_all[name] = v["tests"]

            # coverage of assigned files
            gocoverdir = mws / "gocover"
            if gocoverdir.exists():
                shutil.rmtree(gocoverdir)
            try:
                coverage.run_suite_instrumented(mws / "eval", cov_bin, gocoverdir, mws)
                cov = coverage.per_file_coverage(repo, gocoverdir)
                mod = next(m for m in modules if m["name"] == name)
                sel = coverage.select_targets(cov, mod["source_paths"])
                state[name]["coverage_pct"] = sel["module_coverage_pct"]
                (mws / "Feedback_Docs/coverage_report.md").write_text(
                    f"# Coverage report — after round {rnd}\n\n"
                    f"- module coverage (assigned files): **{sel['module_coverage_pct']}%**\n"
                    f"- assigned files: {sel['assigned_files']} "
                    f"(full {len(sel['full'])}, partial {len(sel['partial'])}, zero {len(sel['zero'])})\n\n"
                    f"## Partially covered (ascending)\n" +
                    "".join(f"- {f}: {p}%\n" for f, p in sel["partial"].items()) +
                    "\n## Zero coverage (deferred targets)\n" +
                    "".join(f"- {f}\n" for f in sel["zero"]) +
                    f"\n## THIS ROUND'S TARGETS ({len(sel['targets'])}) — write tests exercising these\n" +
                    "".join(f"- {f}\n" for f in sel["targets"])
                )
                print(f"  {name}: tests {v['n_ok']}/{v['n_total']} OK, "
                      f"coverage {sel['module_coverage_pct']}%")
                if sel["module_coverage_pct"] >= args.threshold * 100:
                    state[name]["done"] = True
                    print(f"  {name}: coverage threshold reached — done")
            except Exception as e:
                print(f"  {name}: coverage failed: {e}")

        json.dump({"state": state, "verdicts": verdicts_all},
                  open(out / "stage4_state.json", "w"), indent=1)

    print("\n[stage4] final state:")
    for name, s in state.items():
        print(f"  {name}: rounds={s['rounds']} tests={s['n_ok']}/{s['n_total']} "
              f"coverage={s['coverage_pct']}% done={s['done']}")
    print("[stage4] complete ->", out / "stage4_state.json")


if __name__ == "__main__":
    main()
