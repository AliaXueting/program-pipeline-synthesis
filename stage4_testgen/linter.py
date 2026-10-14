#!/usr/bin/env python3
"""Weak-assert linter (reconstructed from the paper's 37-rule semantics).

Rejects (Error) / flags (Warning) per test function:
  E1 sole exit-code assertions (only returncode checks)
  E2 tautological assertions (X == X, assert <truthy constant>)
  E3 substring assertions with expected fragment < 15 chars
  E4 assertions that never inspect the program-run result
  E5 missing docstring, or docstring < 15 chars
  W1 missing CATCHES comment, or CATCHES text < 15 chars
"""
from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

MIN_FRAGMENT = 15


def _expr_key(node) -> str:
    try:
        return ast.dump(node)
    except Exception:
        return ""


def _is_truthy_const(node) -> bool:
    return isinstance(node, ast.Constant) and bool(node.value)


def _assigned_run_names(fn: ast.FunctionDef) -> set[str]:
    """Names assigned from calls that look like program-run helpers."""
    names = set()
    for node in ast.walk(fn):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
            callee = node.value.func
            cname = callee.id if isinstance(callee, ast.Attribute) is False and isinstance(callee, ast.Name) else (
                callee.attr if isinstance(callee, ast.Attribute) else "")
            if any(k in (cname or "").lower() for k in ("run", "exec", "invoke", "call", "spawn")):
                for t in node.targets:
                    if isinstance(t, ast.Name):
                        names.add(t.id)
    return names


FILE_EFFECT_CALLS = ("exists", "read_bytes", "read_text", "stat", "iterdir", "glob", "is_file", "is_dir")


def _taint_names(fn: ast.FunctionDef, run_names: set[str]) -> set[str]:
    """Names derived (transitively) from a program-run result."""
    tainted = set(run_names)
    changed = True
    while changed:
        changed = False
        for node in ast.walk(fn):
            if isinstance(node, ast.Assign):
                refs = {n.id for n in ast.walk(node.value) if isinstance(n, ast.Name)}
                if refs & tainted:
                    for t in node.targets:
                        if isinstance(t, ast.Name) and t.id not in tainted:
                            tainted.add(t.id)
                            changed = True
    return tainted


def _has_file_effect_call(node) -> bool:
    for n in ast.walk(node):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) \
                and n.func.attr in FILE_EFFECT_CALLS:
            return True
    return False


def _check_asserts(fn: ast.FunctionDef, run_names: set[str]) -> list[tuple[str, str]]:
    findings: list[tuple[str, str]] = []
    asserts = [n for n in ast.walk(fn) if isinstance(n, ast.Assert)]
    if not asserts:
        return [("E1", "no assertions at all")]
    tainted = _taint_names(fn, run_names)
    touches_result = False
    only_exit_code = True
    for a in asserts:
        src_seg = ast.dump(a.test)
        refs = {n.id for n in ast.walk(a.test) if isinstance(n, ast.Name)}
        is_result = bool(refs & tainted) or "stdout" in src_seg or "stderr" in src_seg
        if is_result:
            touches_result = True
            output_refs = refs & tainted
            inspects_output = (
                "stdout" in src_seg
                or "stderr" in src_seg
                or ("returncode" not in src_seg and bool(output_refs))
                or _has_file_effect_call(a.test)
            )
            if inspects_output:
                only_exit_code = False
        elif _has_file_effect_call(a.test):
            touches_result = True
            only_exit_code = False  # asserts an external (file) effect
        # E2: tautology
        if isinstance(a.test, ast.Compare) and len(a.test.ops) == 1:
            if _expr_key(a.test.left) == _expr_key(a.test.comparators[0]):
                findings.append(("E2", "tautological comparison"))
        if _is_truthy_const(a.test):
            findings.append(("E2", "assert on a constant"))
        # E3: short substring expectation
        if isinstance(a.test, ast.Compare):
            comp = a.test
            for opr, other in zip(comp.ops, comp.comparators):
                if isinstance(opr, ast.In) and isinstance(comp.left, ast.Constant) \
                        and isinstance(comp.left.value, str) and len(comp.left.value) < MIN_FRAGMENT:
                    findings.append(("E3", f"substring fragment '{comp.left.value}' < {MIN_FRAGMENT} chars"))
                if isinstance(opr, ast.In) and isinstance(other, ast.Constant) \
                        and isinstance(other.value, str) and len(other.value) < MIN_FRAGMENT:
                    findings.append(("E3", f"substring fragment '{other.value}' < {MIN_FRAGMENT} chars"))
    if not touches_result:
        findings.append(("E4", "no assertion inspects the program-run result"))
    elif only_exit_code:
        findings.append(("E1", "only exit-code assertions"))
    return findings


def lint_test_file(path: Path) -> dict[str, list[dict]]:
    tree = ast.parse(path.read_text(errors="ignore"))
    out: dict[str, list[dict]] = {}
    run_names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            pass
    # collect helper names from conftest-style run functions at module level too
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            run_names |= _assigned_run_names(node)
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if not node.name.startswith("test"):
            continue
        findings = []
        doc = ast.get_docstring(node) or ""
        if len(doc.strip()) < MIN_FRAGMENT:
            findings.append({"level": "E5", "msg": f"docstring missing or < {MIN_FRAGMENT} chars"})
        src = ast.get_source_segment(path.read_text(errors="ignore"), node) or ""
        catches = ""
        for line in src.splitlines():
            if "CATCHES:" in line:
                catches = line.split("CATCHES:", 1)[1].strip()
        if len(catches) < MIN_FRAGMENT:
            findings.append({"level": "W1", "msg": f"CATCHES comment missing or < {MIN_FRAGMENT} chars"})
        for code, msg in _check_asserts(node, run_names | _assigned_run_names(node)):
            findings.append({"level": code, "msg": msg})
        if findings:
            out[node.name] = findings
    return out


def main():
    results = {}
    for d in sys.argv[1:] or ["eval/tests"]:
        p = Path(d)
        files = [p] if p.is_file() else sorted(p.glob("test_*.py"))
        for f in files:
            try:
                res = lint_test_file(f)
            except SyntaxError as e:
                results[str(f)] = {"__file__": [{"level": "E0", "msg": f"syntax error: {e}"}]}
                continue
            if res:
                results[str(f)] = res
    print(json.dumps(results, indent=1))
    errs = sum(1 for f in results.values() for t in (f.values() if isinstance(f, dict) else [])
               for x in (t if isinstance(t, list) else []) if str(x.get("level", "")).startswith("E"))
    sys.exit(0 if errs == 0 else 1)


if __name__ == "__main__":
    main()
