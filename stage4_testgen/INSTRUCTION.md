# Task: Construct black-box behavioral tests for ONE functional module of `{MODULE}`

You are a test-construction subagent. Another AI agent will later re-implement
this program from scratch; the tests you write decide whether their
re-implementation is behaviorally identical. You own ONE module.

## Your module assignment

{ASSIGNMENT}

## Workspace

- `./executable` — the reference binary (BLACK BOX: probe it through its CLI only;
  never decompile/strace it). This is the ONLY source of truth for expected behavior.
- `./docs/` — the project documentation (read freely).
- `./src/` — the repository source code. You MAY read it (construction is allowed
  source access; only the future reproduction agent is restricted to the black box).
  Use it to understand WHERE functionality lives and find untested paths — but every
  expected value you assert must be RECORDED by actually running `./executable`.
- `./eval/` — your test module output (already contains `run.sh`; do not modify it).
  Write `eval/tests/conftest.py` (with a `run_<prog>` helper resolving
  `PROGRAMGYM_EXECUTABLE`, like the format example) and `eval/tests/test_*.py`.
- `./format-example/` — a complete module from another task showing the exact
  structure and code style. Follow it.
- `./Feedback_Docs/` — your cross-round memory and the driver's feedback:
  - `summary.md` — YOU maintain this (see below)
  - `validation_results.md` — written by the driver after each round (per-test verdicts)
  - `coverage_report.md` — written by the driver (coverage of your assigned files + targets)

## Test format contract (linter-enforced)

- Tests invoke the candidate via `PROGRAMGYM_EXECUTABLE` (never a hardcoded path).
- Embed EXACT recorded expectations (stdout/stderr bytes/exit codes) from the reference.
- Hermetic: no network, no TTY, no absolute paths outside `tmp_path`, pinned child env.
- Fast: every test < 10 s.
- Every test has a real docstring, and a `CATCHES:` comment (>= 15 chars) naming the
  behavioral detail a wrong re-implementation would break.
- REJECTED by the weak-assert linter (fix these before finishing):
  * tests whose only assertion is an exit code
  * tautological assertions, or assertions that never inspect the run result
  * substring assertions where the expected fragment is shorter than 15 characters
* **Coverage instrumentation hook (REQUIRED):** when your `conftest.py` builds the
  child process environment (even a fully pinned/hermetic one), it MUST copy the
  `GOCOVERDIR` variable from the test process environment into the child env
  when present (`cov_env = {"GOCOVERDIR": v} for v in [os.environ.get("GOCOVERDIR")] if v`;
  merge that into the child env). The pipeline measures source coverage of the
  reference binary through this variable; without it your module's coverage
  report is empty and the feedback loop cannot guide you.
* Parametrize where natural; target **{TARGET_TESTS} tests in total** for this module.

## Round protocol (this run is round {ROUND} of {MAX_ROUNDS})

- **Round 1:** explore `./executable` for your module's functionality, read the
  assigned source under `./src/` to find behaviors worth pinning, then write the
  initial test suite into `eval/tests/`. Self-validate:
  `PROGRAMGYM_EXECUTABLE=$PWD/executable bash eval/run.sh` must pass 100%.
- **Rounds 2+: REPAIRS FIRST, THEN NEW TESTS.**
  1. Read `Feedback_Docs/validation_results.md`. Every test listed as REJECTED
     (failed / flaky / dummy_pass / linter-error) must be fixed or deleted now.
  2. Read `Feedback_Docs/coverage_report.md`. It lists target source files
     (partially-covered first, ascending coverage). Write NEW tests that exercise
     the behaviors those files implement — probing `./executable` to record what
     it actually does for those paths. Skip a target only with a documented reason.
  3. Re-run the self-validation; all tests must pass.

## summary.md (maintain every round)

Append a section per round: what you repaired, which coverage targets you addressed
(and with how many tests), which targets you skipped and the exact reason (e.g.
"requires TTY", "not reachable via CLI"), and remaining limitations. Be specific —
this is the cross-round memory the pipeline depends on.

## Hard constraints

- Do not modify anything outside `eval/` and `Feedback_Docs/summary.md`.
- Do not copy test content from the format example (structure only) or the internet.
- Never assert a value you have not actually observed from `./executable`.
