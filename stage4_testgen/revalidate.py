#!/usr/bin/env python3
"""Re-run validation + coverage for every module workspace (resume helper).

Used when restarting the orchestrator with --start-round N: gives every
module a complete, up-to-date Feedback_Docs/ before the next agent round.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import shutil
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


def _load(name: str):
    spec = importlib.util.spec_from_file_location(
        name, Path(__file__).parent / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def process_module(mod, repo, ref, cov_bin, out, rnd, threshold):
    validator = _load("validator")
    coverage = _load("coverage")
    name, mws = mod["name"], out / mod["name"]
    v = validator.validate_module(mws, ref, out / "_val")
    if "error" in v:
        return f"{name}: {v['error']}"
    line = f"{name}: tests {v['n_ok']}/{v['n_total']} OK"
    gocoverdir = mws / "gocover"
    if gocoverdir.exists():
        shutil.rmtree(gocoverdir)
    try:
        coverage.run_suite_instrumented(mws / "eval", cov_bin, gocoverdir, mws)
        cov = coverage.per_file_coverage(repo, gocoverdir)
        sel = coverage.select_targets(cov, mod["source_paths"])
        empty_warn = (
            "\n> **NO COVERAGE DATA was collected.** Your conftest run helper "
            "strips the child environment and drops `GOCOVERDIR`. REPAIR IT "
            "FIRST: propagate `GOCOVERDIR` from the test process env into the "
            "child env (see INSTRUCTION.md, \"Coverage instrumentation hook\").\n"
            if sel["assigned_files"] == 0 else ""
        )
        (mws / "Feedback_Docs/coverage_report.md").write_text(
            f"# Coverage report — after round {rnd}\n\n" + empty_warn +
            f"- module coverage (assigned files): **{sel['module_coverage_pct']}%**\n"
            f"- assigned files: {sel['assigned_files']} "
            f"(full {len(sel['full'])}, partial {len(sel['partial'])}, zero {len(sel['zero'])})\n\n"
            "## Partially covered (ascending)\n" +
            "".join(f"- {f}: {p}%\n" for f, p in sel["partial"].items()) +
            "\n## Zero coverage (deferred targets)\n" +
            "".join(f"- {f}\n" for f in sel["zero"]) +
            f"\n## THIS ROUND'S TARGETS ({len(sel['targets'])}) — write tests exercising these\n" +
            "".join(f"- {f}\n" for f in sel["targets"])
        )
        line += f", coverage {sel['module_coverage_pct']}%"
        if sel["module_coverage_pct"] >= threshold * 100:
            line += " [THRESHOLD REACHED]"
    except Exception as e:
        line += f", coverage error: {e}"
    return line


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", required=True)
    ap.add_argument("--repo", required=True)
    ap.add_argument("--ref", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--round", type=int, default=1, help="round label for the reports")
    ap.add_argument("--threshold", type=float, default=0.8)
    args = ap.parse_args()

    plan = json.loads(Path(args.plan).read_text())
    repo, ref, out = Path(args.repo), Path(args.ref), Path(args.out)
    cov_bin = out / "executable.cov"
    modules = plan["modules"] + ([{
        "name": "test_reuse", "source_paths": ["."],
        "functional_description": "native test suite rewrite",
        "interaction_categories": ["I/O"],
    }] if plan.get("test_reuse") else [])

    with ThreadPoolExecutor(max_workers=len(modules)) as ex:
        futs = [ex.submit(process_module, m, repo, ref, cov_bin, out,
                          args.round, args.threshold) for m in modules]
        for f in futs:
            print(f.result(), flush=True)


if __name__ == "__main__":
    main()
