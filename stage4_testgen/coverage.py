#!/usr/bin/env python3
"""Coverage instrumentation + target selection (paper: Go uses -cover/-coverpkg).

The reference binary is rebuilt with -cover -coverpkg=./... so every execution
writes counter files to GOCOVERDIR. Running a module's test suite against the
instrumented binary yields per-file statement coverage of the REFERENCE source —
exactly the paper's dynamic program-analysis feedback.

Target selection (paper): target set G_t prefers partially-covered files (they
have execution evidence; zero-coverage files are deferred as blind search);
per round at most min(|G_t|, ceil(rho*|G_t|), B) targets, ascending coverage,
rho=0.1, B=300.
"""
from __future__ import annotations

import math
import os
import re
import shutil
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

RHO = 0.1
B = 300


def build_instrumented(repo: Path, main_pkg: str, out_bin: Path) -> Path:
    env = dict(os.environ)
    env["PATH"] = "/usr/local/go/bin:" + env.get("PATH", "")
    env["GOTOOLCHAIN"] = "local"
    env.setdefault("GOFLAGS", "-mod=mod")
    subprocess.run(
        ["go", "build", "-cover", "-coverpkg=./...", "-o", str(out_bin), main_pkg],
        cwd=repo, env=env, check=True,
    )
    return out_bin


def run_suite_instrumented(eval_dir: Path, cov_bin: Path, gocoverdir: Path,
                           branch_root: Path) -> bool:
    """Run a module suite against the instrumented binary; accumulate coverage."""
    gocoverdir.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    env["PROGRAMGYM_EXECUTABLE"] = str(cov_bin)
    env["GOCOVERDIR"] = str(gocoverdir)
    env["PROGRAMGYM_PYTEST_WORKERS"] = "2"
    proc = subprocess.run(["bash", "eval/run.sh"], cwd=branch_root, env=env,
                          capture_output=True, timeout=1800)
    return proc.returncode == 0


def per_file_coverage(repo: Path, gocoverdir: Path) -> dict[str, tuple[int, int]]:
    """file-relative-path -> (covered_statements, total_statements)."""
    textfmt = gocoverdir.parent / "profile.txt"
    env = dict(os.environ)
    env["PATH"] = "/usr/local/go/bin:" + env.get("PATH", "")
    subprocess.run(
        ["go", "tool", "covdata", "textfmt", "-i", str(gocoverdir), "-o", str(textfmt)],
        env=env, check=True, capture_output=True,
    )
    cov: dict[str, tuple[int, int]] = {}
    prefix = str(repo) + "/"
    for line in textfmt.read_text().splitlines():
        if not line.strip():
            continue
        # format: name.go:l.c,l.c numStmt count
        m = re.match(r"(\S+?\.go):\d+\.\d+,\d+\.\d+ (\d+) (\d+)", line)
        if not m:
            continue
        name, nstmt, count = m.group(1), int(m.group(2)), int(m.group(3))
        if not name.startswith("/"):
            continue
        rel = name[len(prefix):] if name.startswith(prefix) else name
        c, t = cov.get(rel, (0, 0))
        cov[rel] = (c + (nstmt if count > 0 else 0), t + nstmt)
    return cov


def select_targets(cov: dict[str, tuple[int, int]], assigned_paths: list[str]) -> dict:
    """Coverage over the module's assigned files + the next round's target list."""
    assigned = {}
    for rel, (c, t) in cov.items():
        if any(rel.startswith(p) or rel == p or ("/" + p) in ("/" + rel) for p in assigned_paths):
            assigned[rel] = (c, t)
    partial, zero, full = [], [], []
    for rel, (c, t) in assigned.items():
        if t == 0:
            continue
        pct = 100.0 * c / t
        if pct >= 99.9:
            full.append(rel)
        elif pct > 0:
            partial.append((pct, rel))
        else:
            zero.append(rel)
    partial.sort()
    g_t = [rel for _, rel in partial] + zero  # partial first (ascending), zero deferred
    n_targets = min(len(g_t), math.ceil(RHO * len(g_t)) if g_t else 0, B)
    covered_stmts = sum(assigned[r][0] for r in assigned)
    total_stmts = sum(assigned[r][1] for r in assigned)
    return {
        "assigned_files": len(assigned),
        "module_coverage_pct": round(100.0 * covered_stmts / total_stmts, 2) if total_stmts else 0.0,
        "full": full,
        "partial": {rel: round(p, 1) for p, rel in partial},
        "zero": zero,
        "targets": g_t[:n_targets],
    }
