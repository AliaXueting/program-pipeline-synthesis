# shfmt_cli_io — cross-round summary

Module: how the `shfmt` binary is invoked and how it reports results
(flags/usage/version, stdin-vs-path routing, `-l`/`-w`/`-d`/`-f`/`--to-json`
dispositions, exit codes, diff coloring). Assigned sources: `cmd/shfmt`
(main.go). Not maintained in round 1 — created in round 2, reconstructed below.

## Round 1 (retrospective)

- Wrote 234 test IDs across 9 files in `eval/tests/` (flag parsing, help/usage,
  version, input routing, output disposition, diff output, tty behavior,
  validation errors, flag interactions).
- Driver validation: 231 OK, 3 REJECTED (all "dummy-check: still passes against
  no-output dummy"). No coverage data was collected (see round 2 findings).

## Round 2

### Repairs (done first)

1. **3 REJECTED tests repaired** (each passed against the no-output dummy
   because its assertions held on empty output):
   - `test_input_routing.test_to_json_and_from_json_round_trip_identically` —
     compared two live runs, so a dummy produced `b"" == b""`. Now pins the
     exact recorded tree for empty input (`{\n\t"Type": "File"\n}\n`) before
     round-tripping, so a no-output binary cannot pass.
   - `test_output_disposition.test_ignored_files_are_skipped_while_walking_directories`
     — only asserted silence/exit 0. Now adds a kept shebang file (`sub/kept`,
     no `.sh` extension so the `[*.sh]` ignore rule misses it) and asserts
     `-l sub` prints exactly `sub/kept\n` with exit 1; the ignored sibling
     must not appear in the exact-match output.
   - `test_output_disposition.test_write_is_skipped_for_an_explicitly_ignored_path`
     — only asserted the ignored file stayed unchanged. Now also passes a
     non-ignored sibling (`sub/plain.txt`) in the same `--apply-ignore -w`
     run and asserts the sibling IS rewritten while the ignored file is not.
2. **Coverage instrumentation hook repaired** (`eval/tests/conftest.py`):
   - GOCOVERDIR passthrough into the child env was already present; the real
     blocker was that the pipeline-managed `eval/run.sh` unconditionally does
     `export PROGRAMGYM_EXECUTABLE="${BRANCH_ROOT}/executable"`, clobbering
     the instrumented binary path the coverage driver sets
     (`stage4_coverage.run_suite_instrumented`). Every run therefore executed
     the uninstrumented copy and wrote zero counter files (round-1 `gocover/`
     was empty; all modules reported 0.0%).
   - conftest now detects a coverage run (GOCOVERDIR present, assigned binary
     not instrumented — probed once per worker via `--version` against a
     throwaway GOCOVERDIR) and falls back to the instrumented build staged at
     `<workspace>/../executable.cov`. That file only exists in the stage4
     module layout, so validation/release runs are untouched (validator
     branches under `_val/` never see it; no GOCOVERDIR is set there).
   - Verified: simulated driver run (`GOCOVERDIR=… PROGRAMGYM_EXECUTABLE=
     <stage4>/executable.cov bash eval/run.sh`) now writes 248 counter files
     and the whole suite passes; `executable.cov` was byte-compared against
     `./executable` on --version/-h/-d/-w output and parse errors first.

### New tests (11 new IDs, suite now 245)

Chosen from locally measured uncovered blocks of `cmd/shfmt/main.go` (the
round-1 coverage report listed no targets — see pipeline findings):

- `test_tojson_deprecated_alias_prints_the_same_tree` — `--tojson` alias
  still encodes the exact tree (flag registration, main.go:97).
- `test_filename_bashrc_selects_bash_over_the_shebang` — `.bashrc` name picks
  bash over a `#!/bin/sh` shebang (`langFromFilename`, main.go:406).
- `test_filename_zprofile_selects_zsh` — `.zprofile` picks zsh, accepting
  `${(j: :)x}` (main.go:409, `editorConfigLangs` zsh branch).
- `test_list_with_filename_prints_that_name` [3 params] — `-l`/`-l=0` with
  `--filename` print the given name, both flag spellings.
- `test_dangling_symlink_argument_reports_a_stat_error` — explicit symlink
  resolution uses `stat` wording (main.go:316-322).
- `test_write_error_beats_the_ignore_rules_on_standard_input` — the `-w`
  stdin check runs before the ignore lookup (`formatStdin` ordering).
- `test_parse_error_names_the_dialect_it_tried_on_standard_input` —
  `(parsed as posix via -ln=auto)` suffix (main.go:567).
- `test_parse_error_names_the_dialect_from_editorconfig` —
  `(parsed as posix via EditorConfig)` suffix (main.go:564-565).
- `test_explicit_symlink_to_a_directory_prints_nothing` — resolved dir entry
  is discarded as a non-script while the real dir prints its files.

Self-validation: `PROGRAMGYM_EXECUTABLE=$PWD/executable bash eval/run.sh` →
245 passed; driver's own validator (pass/double/dummy/lint) → 245/245 OK;
linter clean.

### Coverage of cmd/shfmt/main.go (measured locally this round)

87.5% → **90.7%** (255/281 statements), via `executable.cov` + the repaired
conftest + `go tool covdata textfmt`. Remaining uncovered blocks and why:

- `165` (`mod.Replace` in --version): build-info detail, unreachable via CLI.
- `286` (vcs-dir pruning), `306` (ignored directory → SkipDir), `330-340`
  (`--detect exec/all` shebang fallback), `492/494/498` (short-file shebang
  reads while walking): **shfmt_file_discovery module's scope** ("which files
  are picked when walking directories") — deliberately not duplicated here.
- `433/435` (editorconfig indent_style/IndentSize), `465` (legacy property
  spellings), `546` (propsOptions Find error), `574` (`-s`/Simplify):
  **format_style_config / dialect_parsing_json scope**.
- `302/376` (ecQuery.Find error propagation): probed — a broken glob in
  `.editorconfig` does NOT make Find error (it is tolerated), so no known CLI
  trigger; likely unreachable.
- `384` (stdin ReadAll error), `474` (os.Open error after walk — dangling
  symlinks are filtered earlier by CouldBeScript2, and root ignores permission
  bits), `518` (mid-file read error), `596` (Lstat error in `-w` after a
  successful read), `604` (WriteFile error — root bypasses permission
  failures): not deterministically reachable through the CLI harness as root.
- `539` (`editorConfigLangs` returning nil): defensive default for an unknown
  variant, unreachable.

### Pipeline findings the operator should fix (affects ALL modules)

1. `eval/run.sh` (copied from the pipeline template) clobbers
   `PROGRAMGYM_EXECUTABLE`, so `run_suite_instrumented`'s instrumented binary
   never runs. Worked around in this module's conftest (see above); a proper
   fix is to make run.sh respect a pre-set `PROGRAMGYM_EXECUTABLE`
   (`export PROGRAMGYM_EXECUTABLE="${PROGRAMGYM_EXECUTABLE:-${BRANCH_ROOT}/executable}"`).
2. `stage4_coverage.per_file_coverage` skips any profile line whose file name
   does not start with `/`, but `go tool covdata textfmt` emits
   module-relative names (`mvdan.cc/sh/v3/cmd/shfmt/main.go` — see this
   workspace's `profile.txt`). Result: even with counters flowing, the report
   computes 0% and no targets. Fix the filter (or build with paths that
   resolve absolutely).

**Note for round 3+:** until bug 2 is fixed, `coverage_report.md` will still
say "NO COVERAGE DATA" even though the conftest hook now works. Re-measure
locally instead:
`rm -rf gocover && mkdir gocover && GOCOVERDIR=$PWD/gocover PROGRAMGYM_EXECUTABLE=../executable.cov PROGRAMGYM_PYTEST_WORKERS=2 bash eval/run.sh && go tool covdata textfmt -i gocover -o profile.txt`
then grep `profile.txt` for `cmd/shfmt/main.go` blocks with count 0.

### Remaining limitations

- No TTY-stdin tests beyond the existing ones (usage-on-terminal, `-` from a
  terminal); the pty helper covers stdout-coloring cases.
- Write-failure paths (disk full, read-only FS) untestable as root.
- Tests that depend on EditorConfig lookups walking up from `tmp_path` could
  in principle be disturbed by a stray `/tmp/.editorconfig` created by a
  parallel module agent; the driver's validator runs under `stage4/_val`
  (clean ancestors), so verdicts are unaffected.
