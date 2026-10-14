# Pilot result: mvdan/sh (shfmt) — synthesized task, oracle-accepted

**Pipeline run:** 2026-10-14, on the synthesis server, all 5 stages per the
ProgramGym paper's Program-Env methodology (mini reproduction).

## Headline

| Metric | Value |
|---|---|
| Oracle acceptance (`harbor run -a oracle`) | **reward 1.0 / resolved 1.0 / almost_resolved 1.0** |
| Test branches (modules) | 7 (6 functional + 1 test-reuse) |
| Validated tests | 3,454 (2 in `ignored_tests` after merged re-validation) |
| Module coverage (reachable modules) | 81.9% – 92.9% (mean 87.9%) |
| Complexity score | xi = 3.29 (medium → 6-module budget) |
| Source | mvdan/sh @ 0e8ea6f (BSD-3, 9.1k stars, Go) |
| Disjointness | verified against ProgramBench-200 + ProgramGym-1648 (1,848 owner/repos) |

## Per-module outcomes

| Module | Interaction cats | Tests | Coverage | Rounds |
|---|---|---|---|---|
| shfmt_cli_io | Args, Help, I/O | 245 | 90.75% | 2 |
| shfmt_file_discovery | I/O, Args, Config | 117 | 85.71% | 3 |
| dialect_parsing_json | Args, I/O | 686 | 81.90% | 3 |
| format_style_config | Config, Args, I/O | 273 | 92.89% | 3 |
| gosh_execution | I/O, Args, Subcommand | 344 | 0%* | 5 |
| expansion_globbing | I/O, Args | 556 | 0%* | 5 |
| test_reuse (native suite rewrite) | I/O | 1,233 | n/a** | 5 |

\* genuinely unreachable through the shfmt binary (interp/expand code paths
belong to the gosh shell interpreter, which shfmt does not execute); the
modules terminated at the round limit exactly as the paper's design intends.
\** ownership `"."` coverage was not computed during the pilot run (fixed
afterwards in coverage.py).

## Files in this directory

- `plan.json` / `modules.json` — stage-3 dispatcher output (decomposition)
- `stage4_state.json` — orchestrator final state
- `download.sh` / `compile.sh` / `FEEDBACK.md` — stage-2 agent artifacts
  (note: this download.sh targets the stage-2 workspace; the task package
  ships a pipeline-managed prefetch-only variant — see the stage-2
  INSTRUCTION "final-image contract")
- `<module>/validation_results.md`, `<module>/coverage_report.md`,
  `<module>/summary.md` — the full Feedback_Docs trail per module
- `oracle_acceptance_result.json` — the acceptance run (rewards 1.0)

The packaged task itself lives in the companion repository
(`synthesized-data-program`), in ProgramGym-1648 layout.

## Issues found by the pilot (all fixed in this repo)

1. Coverage instrumentation: hermetic test envs strip `GOCOVERDIR`, and
   `eval/run.sh` resets `PROGRAMGYM_EXECUTABLE` — fixed by the
   GOCOVERDIR-propagation contract + instrumented-binary swap during
   coverage runs.
2. Stage-2 download.sh assumed a source tree in the final image — contract
   now forbids that (prefetch-only).
3. CRLF corruption from Windows checkouts broke the verifier's shebang —
   `.gitattributes` added; LF enforced for scripts.
4. Import-path bugs across the repo layout, dispatcher paren bug,
   `--acceptance` argparse flag, `--start-round`/`--skip-modules` resume.
