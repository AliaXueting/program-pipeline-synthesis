# summary.md — test_reuse module

Black-box behavioural tests for `./executable` (the `shfmt` CLI), mined from
the repository's native test suite under `./src/` (`cmd/shfmt/testdata/script/*.txtar`
plus the Go table tests in `syntax/*_test.go`).

Harness: `eval/tests/conftest.py` exposes a `run` fixture that resolves
`PROGRAMGYM_EXECUTABLE`, pins the child environment (PATH/HOME/TMPDIR/
FORCE_COLOR only, plus `GOCOVERDIR` when the pipeline sets it), runs with
`cwd` inside `tmp_path`, and never touches paths outside it. A sentinel
`tmp_path/.editorconfig` (`root = true`, no properties) keeps EditorConfig
lookups from escaping into parent directories while leaving the default
tab formatting untouched.

## Round 1 — initial suite (273 tests)

Files and the native material they were ported from:

- `test_basic_io.py` — `basic.txtar`, `atomic.txtar` (stdin/dash/file args,
  `-l`, `-l -w`, `-w` on stdin, NUL bytes in input, atomic rewrite).
- `test_cli_flags.py` — `flags.txtar` (help/version, flag conflicts, the
  stdin-only utilities, `--detect` mode validation).
- `test_dialect_detection.py` — `flags.txtar` + `fileutil/file_test.go`
  (shebang/extension/known-filename detection, `-ln=auto` fallback).
- `test_diff.py` — `diff.txtar` (`-d` labels, hunks, colour decision).
- `test_parse_errors.py` — `syntax/parser_test.go` error cases.
- `test_printer_flags.py` / `test_print_table.py` / `test_source_equiv.py`
  — `syntax/printer_test.go` tables (`-i`, `-bn`, `-ci`, `-sr`, `-kp`,
  `-fn`, `-bl`, `-mn`, `-s`, canonical printing, idempotence, line
  continuations, CRLF).
- `test_simplify_table.py` — `syntax/simplify_test.go`.
- `test_to_json.py` — `tojson.txtar` (`--to-json`/`--from-json`).
- `test_walk_find.py` — `walk.txtar` (directory walking, `-f`, `-f=0`,
  symlinks, VCS dirs, hidden files).

Round 1 left one gap that mattered: the `run` fixture stripped the child
environment completely, dropping `GOCOVERDIR`, so no coverage data could be
collected (see round 2).

## Round 2 — repairs first, then new tests

### Repairs (all three REJECTED tests fixed)

1. `eval/tests/conftest.py` — **coverage instrumentation hook**: `pinned_env`
   now copies `GOCOVERDIR` from the test process environment into the child
   env (merged after `extra_env`, so it survives both paths). Verified by
   importing `pinned_env` with `GOCOVERDIR` set and unset.
   *Note for the driver:* the `./executable` shipped in this workspace is
   **not** Go-coverage-instrumented (no `GOCOVERDIR`/`coverage` strings in
   the binary; running it with `GOCOVERDIR` pointing at an existing
   directory produces no `covmeta`/`covcounters` files). The hook is now
   correct, but the coverage step needs an instrumented build of the
   reference for the report to be non-empty.
2. `test_to_json.test_to_json_of_a_single_call` — the hand-typed
   `SIMPLE_JSON` constant had the wrong tab depth inside the nested
   `Args`/`Parts` objects. Replaced with a byte-exact recording of
   `printf 'foo\n' | ./executable --to-json` (1162 bytes).
3. `test_to_json.test_to_json_of_a_lone_comment` — same class of error in
   `COMMENT_JSON`; replaced with a byte-exact recording of
   `printf '#\n' | ./executable --to-json`.
4. `test_to_json.test_old_tojson_flag_name_matches_the_new_one` — failed
   only because it compares against `SIMPLE_JSON`; fixed by the same
   re-recording (`-tojson` and `--to-json` verified byte-identical).

### Coverage targets addressed this round

The round 2 coverage report contained **no targets** (no data was collected,
0.0%), so targets were chosen from the reachable-but-untested surface of the
CLI, in this order of value:

| Target (source area) | Tests | Notes |
| --- | --- | --- |
| `cmd/shfmt/main.go` EditorConfig support (`editorconfig.txtar`) | 56 in new `test_editorconfig.py` | was entirely uncovered: round 1's sentinel `.editorconfig` disabled the feature. Now covers stdin/path lookups, `-l`/`-d` under config, the "any formatting flag disables EditorConfig" rule (21 flag spellings), nested-config merging, `indent_style`/`indent_size` defaults, dialect knobs (`language_dialect`, legacy `shell_variant`, precedence), all printer knobs, `simplify`/`minify` (and minify-implies-simplify), `ignore = true` during walks, `--apply-ignore` for explicit args, `[[shell]]`/`[[bash]]`/`[[zsh]]` language sections, and sibling configs not leaking into each other. |
| `--detect` modes `all`/`exec` (`detect.txtar`) | 5 in `test_walk_find.py` | round 1 only covered the invalid-mode error. Now: `--detect=default` equals no flag, `all` reads shebangs behind foreign extensions, `exec` requires the executable bit, the mode also applies to explicit `-f` args and to formatting/`-l -w` walks. |
| non-regular files during walks (`walk.txtar`) | 2 in `test_walk_find.py` | a FIFO is skipped without blocking (10 s cap so a wrong re-implementation fails fast instead of hanging the worker), and a symlink to a directory is not descended into while a symlink to a script is still found. |
| `-l=0` null separator (`-l[=0]` in the usage text) | 1 in `test_basic_io.py` | both `-l=0` and `--list=0`, and that non-differing files contribute nothing. |

Suite size: 273 → **337 tests**, all passing
(`PROGRAMGYM_EXECUTABLE=$PWD/executable bash eval/run.sh` → `337 passed`,
run twice to check for flakiness; ~1 s wall clock).

### Targets skipped this round (with reasons)

- `interp/`, `expand/`, `shell/`, `pattern/`, `x/coreutils`, `cmd/gosh` —
  not reachable through the `shfmt` CLI at all (`cmd/shfmt/main.go` imports
  only `syntax`, `syntax/typedjson` and `fileutil`); black-box CLI tests
  cannot exercise them.
- "no arguments + stdin is a terminal → usage, exit 2" and the
  "colour when stdout is a terminal" branch — require a TTY, which the
  hermetic contract forbids. The `FORCE_COLOR` branch of the colour
  decision is already covered in `test_diff.py`.
- `syntax` package internals that the CLI cannot observe separately from
  printing (e.g. `syntax/walk.go`, `syntax/braces.go` braces are reachable
  only via the `expand` package) — no CLI surface.

### Remaining limitations

- The `--to-json` dumps pin the full AST JSON (positions, `ValuePos`,
  `Last` comments) for three small programs only; larger trees are covered
  only through `--from-json` round trips.
- `-fn`/`-bl`/`-mn` are exercised over the printer tables, but their
  interaction with `-kp` (keep padding) is not parametrised together.
- Coverage percentages could not be measured this round (see the note above
  about the uninstrumented binary); next round's report should list real
  per-file targets.

## Round 3 — repairs first, then new tests

### Repairs

1. `eval/tests/test_editorconfig.py::test_sibling_configs_are_not_confused_by_a_shared_walk`
   — the only REJECTED test (dummy-check: it asserted an *empty* `-d` walk
   result, which a no-output dummy satisfies). Rebuilt with files that
   *mismatch* their own sibling configs, so the reference prints two exact
   diff hunks (`mc/bn` first, then `mc/sr`, status 1). Probed both confusion
   directions: applying either directory's config to the other's file makes
   the walk print nothing and exit 0, so the test now fails for a no-output
   dummy, a config-swapping walk, and a single-config-cached walk alike.
2. `eval/tests/conftest.py` — coverage instrumentation. The round-2 report
   still showed "no coverage data / conftest strips GOCOVERDIR", although
   `pinned_env` has propagated `GOCOVERDIR` since round 2 (re-verified:
   set → present in child env, unset → absent). Hardened the hook this
   round: a *relative* `GOCOVERDIR` is now absolutised against the test
   process cwd before being passed to the child, because the child runs
   with cwd inside `tmp_path` — a relative value would otherwise land the
   coverage files inside throwaway sandboxes instead of the driver's
   collection directory. Verified both directions again after the change.
   *Note for the driver (unchanged from round 2):* the `./executable`
   shipped in this workspace is **not** Go-coverage-instrumented — the
   binary contains no `GOCOVERDIR` string and produces no `covmeta`/
   `covcounters` files when run with `GOCOVERDIR` set. The hook is correct
   and complete on the test side; an instrumented reference build is needed
   for the report to be non-empty.

### Coverage targets addressed this round

The round-3 report again contained **no targets** (0.0%, no data collected),
so targets were picked from the reachable-but-untested surface of the CLI,
prioritised by source area. Suite size: 337 → **628 tests** (all passing,
run three times via `eval/run.sh`; all 628 fail against a no-output dummy
binary, i.e. there are no dummy-passes).

| Target (source area) | Tests | Notes |
| --- | --- | --- |
| `cmd/shfmt/main.go` `--exp.recover` (→ `syntax.RecoverErrors`, native `TestParseRecoverErrors` table) | 33 in new `test_exp_recover.py` | was entirely untested. Recovered-printing table (23 cases: unclosed quotes/blocks/subshells/`$()`/`$(())`/`${}`, missing `then`/`fi`/`do`, trailing `|`/`||`/`&&`/`>`, `$[...]`→`$((...))`, backquote→`$(...)`), budget exhaustion (=1 inner `{` error, =2 outer `(` error), zero/negative budgets behave like unset, non-numeric value → flag error + usage with status 2, file args + `-w` rewrite in place, `-d` diff including the `\ No newline at end of file` marker, recovery does NOT disable EditorConfig, unrecoverable `)` still fails identically, `--to-json` of a recovered tree (SglQuoted with no End/Value). |
| `syntax/printer.go` per-flag tables (`TestPrintBinaryNextLine`, `TestPrintSwitchCaseIndent`, `TestPrintFunctionNextLine`, `TestPrintBlockNextLine`, `TestPrintSpaceRedirects`, `TestPrintKeepPadding`, `TestPrintKeepPaddingSpaces`, `TestPrintMinify`, `TestPrintSpaces`) | 123 in new `test_printer_tables.py` | round 1 exercised each printer flag on ONE hand-written program only. Now the full native per-flag tables are ported: 29 `-bn` cases (operator placement with heredocs, comments between operators, `[[ ]]`/`(( ))` chains, dedented end-of-chain comments), 3 `-ci`, 6 `-fn`, 22 `-bl` (incl. `select`, `until`, `coproc` brace kept, subshell body kept), 9 `-sr`, 20 `-kp` (comment alignment, `keyword   padding` kept, leading tab stripped, multi-line block expansion), 5 `-kp -i=2`, 24 `-mn` (incl. `((\nfoo))` line continuations, `${0/$a/}`, inner shebang comments dropped, heredoc collapsing) and 5 `-i=N` cases (continuation doubling, comment column alignment). All 123 goldens verified against the binary in one batch before being embedded. |
| `syntax/parser.go` nesting limit (native `TestParseNestingLimit`) | 15 in new `test_nesting_limit.py` | the `nesting is deeper than 10000 levels` diagnostic was untested. 9 shapes at 10001 levels each pin the exact position prefix, including the shapes whose column prints as a literal `?` (`${a:-…}`, `f() f() …`, `[[ ! ! … ]]`); the boundary itself (10000 open `(\n` already fails at `path:10001:1`, 9999 succeeds) is pinned on a file argument, 1000-level command substitutions and parameter expansions round-trip byte-identically, 1000 nested subshells grow 2002 → 1004002 bytes over 2001 lines, and `--to-json` reports the error with no name label at all. |
| `syntax/lexer.go` chunk boundaries + sentinel runes (`bufSize` printTests entries, `TestParseHighControlRunes`) | 21 in new `test_lexer_edges.py` | the lexer reads 1024-byte chunks: runes landing at offsets 1021–1024 round-trip, a peek across the chunk edge (`…>(a)`) works, an escaped newline at the boundary re-prints as `a \\\n\tb`; U+0080/U+0081 (the lexer's EOF/escaped-newline sentinels) parse as ordinary characters in bare/single/double-quoted words; 8 non-ASCII literal shapes (word, quotes, `${…}`, comment, heredoc, `$'…'`, `${a/b//○}`) round-trip verbatim. |
| `cmd/shfmt/main.go` `langFromFilename` (rcfile names) + `fileutil.Shebang` table | 20 in new `test_dialect_names.py` | the bash/zsh startup filenames were only half-covered (`.zshrc`, `zprofile`). Now `bashrc`/`.bashrc`/`bash_profile`/`bash_logout` force bash and `zshrc`/`zshenv`/`zlogin`/`zlogout` force zsh — in both cases *overriding* the shebang inside the file, via `--filename`, as a file argument and during a directory walk (`-f` lists both files, formatting then fails only on `bashrc`); an unrecognised name defers to the shebang. Shebang spellings: `#!/usr/bin/env zsh`, `#!  /bin/zsh` (two spaces), `#! /bin/zsh true`, tab-separated `env` all select zsh, while a form feed, `bash4`, `envsh` and `sh5` fall back to bash; `#!/usr/bin/env dash` maps onto POSIX and rejects arrays. |
| `syntax/typedjson` decode errors + non-File roots (native `json_test.go` round trips) | 14 in new `test_from_json.py` | `--from-json` error table (not-JSON, unknown `"Type"`, missing `"Type"`, array, null, number, wrong field type) with the exact decoder messages; trailing bytes after the JSON value are ignored; a `File` root prints one newline while a `Lit` root prints its value with *no* trailing newline (and a valueless `Lit` prints nothing); the 19-statement all-node-types program, the zsh `${a[(r)foo]}` (FlagsArithm) and the bats `@test` (TestDecl) programs each survive a `--to-json` → `--from-json` round trip to their canonical form, and a decode/encode cycle reproduces the JSON byte-identically. |
| `main.go` `-l`/`-f` value grammar (`boolStringValue`) | 7 in `test_cli_flags.py` | untested until now: `-l=1`, `-l=`, `-f=1` etc. print `only -l and -l=0 allowed` / `only -f and -f=0 allowed` (status 1, no usage); `-l=true`/`-l=false` and `-f=true`/`-f=false` switch the modes on and off again; `--list=0`/`--find=0` match the short spellings. |
| `main.go` colour decision + `-l=0 -d` + dangling symlinks | 11 in `test_diff.py`, `test_walk_find.py` | `NO_COLOR` and `TERM=dumb` keep the diff plain, `FORCE_COLOR` wins over both (byte-exact coloured diff), an empty `NO_COLOR` is ignored, and a mere `TERM=xterm-256color` cannot enable colour without a TTY; `-l=0 -d` prints `path\0` followed by the diff with status 1; an explicit dangling symlink fails with `stat broken.sh: no such file or directory` for both formatting and `-f`, while the same link met during a walk is skipped silently. |
| `formatStdin` `--apply-ignore` branch (`main.go`) | 1 in `test_editorconfig.py` | stdin named via `--filename` that matches an `ignore = true` rule prints nothing with status 0 under `--apply-ignore`, while a non-matching name and the same name without the flag still format — the flag applies ignore rules to stdin, which is new this round. |
| `formatBytes` simplify-before-`--to-json` | 3 in `test_to_json.py` | `-s --to-json` dumps the simplified tree (DblQuoted→SglQuoted, original offsets kept); `--filename` labels `--to-json` parse errors; `--from-json --to-json` re-encodes byte-identically. |
| `formatBytes` `-w -d` interaction, `-l=0 -w` status, `maybeio.WriteFile` mode preservation, `--version` precedence, `--filename` diff sides | 6 in `test_diff.py`, `test_basic_io.py`, `test_cli_flags.py` | `-w -d` writes AND diffs (status 1); `-l=0 -w` prints `path\0` and exits 0; `-w` preserves mode 741 through the atomic replace; `--version` returns before any argument processing (file untouched); `--filename` names both stdin diff sides. |
| `editorConfigLangs` language-section mapping (`main.go`) | 2 in `test_editorconfig.py` | `[[bats]]` sections never match (bats files resolve to `[[bash]]`/`[[shell]]`, 2-space indent chosen over a 5-space `[[bats]]`); `[[mksh]]` never matches either (mksh file takes `[[shell]]`'s indent while `|&` still parses). |
| EditorConfig `propsOptions` edge values | 3 in `test_editorconfig.py` | invalid `language_dialect` is silently ignored (bash fallback, no "(parsed as ...)" suffix, arrays still parse); `indent_size = 0` and `indent_size = tab` with `indent_style = space` both keep the 8-space default. |
| `syntax/printer.go` / `lexer.go` surface | 11 new `PRINT_CASES` × 3 modes = 33 in `test_print_table.py` | case fallthrough `;;&`/`;&` (space-padded), `<<-` heredoc handling (one-tab dedent, less-indented lines clamped to the base indent, space-indented bodies gain a tab), `$'...'` keeps both escape sequences and raw bytes verbatim, process substitution round-trips, backticks become `$( )`, legacy `$[1+2]` becomes `$((1 + 2))`, a leading UTF-8 BOM is preserved, and five mixed-quoting shapes round-trip unchanged. |

### Targets skipped this round (with reasons)

- Same as round 2 (no per-file coverage data to steer by): `interp/`,
  `expand/`, `shell/`, `pattern/`, `x/coreutils`, `cmd/gosh` — not reachable
  through the shfmt CLI (`cmd/shfmt/main.go` imports only `syntax`,
  `syntax/typedjson` and `fileutil`).
- TTY-only branches ("no args + stdin is a terminal → usage, exit 2",
  "colour when stdout is a terminal") — the hermetic contract forbids a TTY;
  the `FORCE_COLOR`, `NO_COLOR` and `TERM` branches of the same decision are
  covered in `test_diff.py`.
- `syntax.Printer` `SingleLine` option (native `TestPrintSingleLine`) — not
  exposed by any shfmt flag, so unreachable through the CLI.
- Permission-denied error paths (e.g. chmod 000 files/directories during
  walks) — the suite runs as root, where mode bits do not block access, so
  such tests would be environment-dependent.
- EditorConfig lookups escaping above `tmp_path` (a config in a *parent*
  directory with no `root = true` in between) — would require writing
  outside `tmp_path`, which the hermetic contract forbids.

### Remaining limitations

- Coverage percentages remain unmeasurable (see the uninstrumented-binary
  note above); the target selection was again manual.
- The `--exp.recover` budget-exhaustion messages are pinned for the probed
  two-level nesting (`(one | { two >`); deeper nestings may surface other
  diagnostics not covered here.
- The recovered-`--to-json` dump is embedded for one shape only (unclosed
  single quote); other recovered-node JSON shapes (e.g. recovered `fi`)
  are not pinned.
- The all-node-types JSON round trip asserts the *printed* canonical form
  rather than embedding the 71 KB JSON dump; the per-node JSON shapes are
  pinned only through the three small dumps in `test_to_json.py`.
- The deep-nesting tests are the slowest in the suite (three runs of a
  ~100 MB reprint, ~0.5 s each); everything else stays in the
  milliseconds.

## Round 4 — repairs first, then new tests

### Repairs

1. `Feedback_Docs/validation_results.md` reported **628 tests, all OK,
   0 REJECTED** — no repairs were required this round.
2. Coverage hook — the round-4 `coverage_report.md` again says "NO
   COVERAGE DATA was collected … your conftest strips GOCOVERDIR". That
   claim is contradicted by the driver's own artifacts, so no test-side
   repair was possible or needed; instead the hook was re-verified with
   evidence:
   - `gocover/` at the workspace root holds **683 `covcounters` files
     plus one `covmeta`**, and a 3333-line `mode: set` `profile.txt`
     sits next to it — both written at **21:12 during the validation
     run**, i.e. the test suite's child processes demonstrably wrote
     coverage counters through the conftest hook.
   - A locally built instrumented binary (`go build -cover` from the
     same `src/`, byte-identical stdout/exit codes to `./executable`)
     run through the same `eval/tests/conftest.py` reproduces the
     driver's `profile.txt` per-file numbers **exactly** (same statement
     counts, same covered counts, same 69.8% total for the 628-test
     baseline) — so the hook cannot be dropping `GOCOVERDIR`.
   - Likely cause of the empty report, for the driver: the profile's
     paths are module-qualified (`mvdan.cc/sh/v3/cmd/shfmt/main.go`,
     `mvdan.cc/sh/v3/syntax/lexer.go`, …) while the workspace sources
     live at `src/cmd/shfmt/main.go`. A report generator matching
     `src/...` paths against those module paths would find no files and
     print 0.0%/"no data" despite the data being present.
   - The hook itself is unchanged (correct since round 2, hardened in
     round 3): `pinned_env` copies `GOCOVERDIR` (absolutised) from the
     test process env into the pinned child env.

### Coverage targets addressed this round

The report listed no targets (0.0%), so targets were taken from the
driver's own `profile.txt` — real per-file data collected during the
round-3 validation run. Every file below 100% with a reachable CLI
surface was attacked, prioritised by missing statements. Suite size:
628 → **1129 tests** (+501), all passing via
`PROGRAMGYM_EXECUTABLE=$PWD/executable bash eval/run.sh` (run twice;
1129 passed both times, ~2 s wall clock).

Per-file coverage, measured with a locally built instrumented binary
through the same conftest (baseline = the 628-test round-3 suite;
"after" = the full 1129-test suite):

| File | Before | After | New tests |
| --- | --- | --- | --- |
| `syntax/tokens_parse.go` (generated operator codecs) | 20.8% | **99.4%** (172/173 stmts) | 332 in new `test_operators.py` |
| `syntax/lexer.go` | 58.2% | **87.2%** | (shared) |
| `syntax/parser.go` | 72.5% | **82.7%** | (shared) |
| `syntax/parser_arithm.go` | 67.4% | **91.3%** | (shared) |
| `syntax/walk.go` | 44.6% | **68.0%** | 69 in new `test_node_walk.py` |
| `syntax/typedjson/json.go` | 81.5% | **90.5%** | 15 in new `test_json_positions.py` |
| `syntax/printer.go` | 85.7% | **88.8%** | (shared) |
| `syntax/nodes.go` | 87.2% | **89.0%** | (shared) |
| `cmd/shfmt/main.go` | 94.7% | 94.7% | — (rounds 1–3 already) |
| **Total (all 4801 statements)** | **69.8%** | **83.4%** | +30 in `test_zsh_syntax.py`, +55 in new `test_parse_gaps.py` |

What the new files cover:

- `test_operators.py` (332 tests) — the generated `UnmarshalText`
  operator decoders in `tokens_parse.go` were the single biggest gap
  (20.8%): every operator spelling now round-trips through
  `--to-json`/`--from-json`. Tables cover all 14 bash redirect
  spellings (incl. `>&`, `&>`, `&>>`, `<>`, `<<-`, fd merging), the 5
  zsh-only spellings (`>>|`, `&>|`, `&>>|` verbatim; `&>!`→`&>|` and
  `&>>!`→`&>>|` normalised on reprint), 16 parameter operators
  (`:-` `:=` `:+` `:` `::` `?` `#` `%` `/` `^` `,` …) plus the
  zsh-only `:# :| :*`, the bash-only case modifiers `^ ^^ , ,,` with
  their per-dialect gate messages, the `${a@X}` letters `QEPAaKk`
  (mksh accepting only `Q`), and `${!a*}`/`${!a@}` with per-dialect
  gates, all 32 bash binary arithmetic operators (with the spacing
  the printer applies: `$((a += b))`, `$((a ** b))`, …) plus the
  zsh-only `&&= ||= **= ^^=` (one per statement), 8 unary operators
  (`! a` spaced, `-x` unspaced), ternary/comma, 24 test operators with
  the `-a`→`-e` and `-h`→`-L` normalisation, all 4 case terminators
  per dialect, process substitution both directions (`<(`, `>(`, zsh
  `=(`, the mksh/posix redirect readings), and the 5 extglob forms.
  Invalid-operator rejection is tested via a
  parse-mutate-dumps pattern (encode real `--to-json` output, swap the
  `Op` field, re-feed) for 10 operator families, plus unknown-field
  and nil-`Word` decode failures.
- `test_node_walk.py` (69 tests) — one program per walked node type
  (28 shapes: if/elif/else, while, until, both for forms, case,
  select, both function forms, subshell, block, `(( ))`, `[[ ]]`,
  declare/local/assign arrays, extglob, procsubst, time, coproc, let,
  bats `@test`, redirects, comments, param expansions, zsh flags
  arithmetic `${a[(r)foo]}`, array/case comments) run under `-s` AND
  through the JSON round trip; backquote+heredoc recovery shapes and
  the plain-parser backquote EOF error; parser gates for inline
  arrays, indexed array assignment (bash vs zsh), `a[b]`-without-`=`,
  `((` in call position, and redirect-before-compound (zsh reorders,
  bash gates).
- `test_zsh_syntax.py` (30 tests) — zsh expansion flags `${(j.:.)a}`
  `${(q)a}` `${(ps.-.)a}` `${(U)a}` with trailing `:word` forms and
  their bash gate; the `= ~ ^` parameter prefixes single and doubled
  and combined, with bash's differing "invalid parameter name" error;
  anonymous functions, multi-name functions, coproc-with-name
  divergence, let clauses, time/select in both dialects.
- `test_parse_gaps.py` (55 tests) — zsh numeric range globs (`<->`,
  `<5->`, `<-10>`, `<5-10>`) and bash's redirect reading of `<->`; the
  `>>&`/`>>&|`/`>>&!` and `>&|`/`>&!` alias families with their
  canonical `&>>`/`&>>|`/`&>|` spellings; `&!`→`&|` normalisation;
  regex tests incl. the mksh gate, the complex-expr error, nested
  parens and the two-word "not a valid test operator" error; quoted
  heredoc delimiters; nested parameter expansions (`${#${a}}`,
  `${#$(a)}`) with the bash gate and the quoted-`"${a-${b}}"` accept;
  all six lone-keyword errors; for/c-style-for brace forms (bash/mksh
  expand to do/done, posix AND zsh gate); bare `let`; function
  spellings; the posix `function` gate; the 7 arithmetic operator
  errors (`=` must follow a name ×2, `?` must follow an expression,
  `?` must be followed by an expression, ternary missing `?` before
  `:`, `[` must be followed by an expression, `++` must follow a name)
  with their exact columns; `a[i]`/`a++` accepted; the
  subscript-flags bash gate.
- `test_json_positions.py` (15 tests) — every `decodePos` branch:
  position-as-string/number/null/boolean/array, wrong field count
  (missing `Col`, extra field), renamed field, non-number field
  (string/null/boolean), and out-of-range values (−1, 1.5, 2³²) with
  the exact `%v` float formatting (`4.294967296e+09`), plus 2³²−1
  accepted at the inclusive bound. These are parse-mutate-dumps tests
  on the `ValuePos` position of a real `--to-json` dump.

### Targets skipped this round (with reasons)

- `syntax/braces.go` (`SplitBraces`, 118 stmts) and `syntax/quote.go`
  (`Quote`, 62 stmts) — **0% in the driver's own profile after 1129
  tests** because they have no callers in the shfmt binary (they serve
  the `expand`/`interp` packages, which `cmd/shfmt` does not import).
  Not coverable through the CLI; excluded from the reachable target
  set.
- `syntax/walk.go` `DebugPrint` (lines ~234–319, ~85 statements of the
  remaining 32%) — a debug-only printer with no CLI surface; the rest
  of walk.go's walker cases are now covered via `-s`/JSON round trips.
- `syntax/parser.go` `WordsSeq` and `IsKeyword` — exported API for
  other packages, not called by the CLI.
- `cmd/shfmt/main.go` remaining 5.3% — TTY branches ("stdin is a
  terminal", "stdout is a terminal") which the hermetic contract
  forbids, plus permission-denied paths that do not trigger when the
  suite runs as root.
- `syntax/lexer.go` remaining ~12.8% — internal helpers reachable only
  through the exported Go API (e.g. the `next()`/`stopAt` machinery
  used by `WordsSeq`), unreachable via any flag combination.
- `interp/`, `expand/`, `shell/`, `pattern/`, `x/coreutils`,
  `cmd/gosh` — not linked into the shfmt binary at all (unchanged from
  rounds 2–3).

### Remaining limitations

- The coverage percentages above were measured locally (instrumented
  rebuild + the same conftest); the driver's report still prints 0.0%
  for the reasons documented in the repairs section — the data itself
  (`gocover/`, `profile.txt`) is present and correct.
- 83.4% overall is the practical ceiling for pure CLI testing: the
  residual gaps are dead code in this binary (braces/quote), debug
  printers, Go-API-only functions, TTY branches and root-only error
  paths.
- `tokens_parse.go` retains exactly 1 uncovered statement (173 total);
  it is an unreachable defensive arm of a generated decoder.
- The operator tables assert one representative program per spelling;
  combinations of two operators in one expression are covered only for
  the redirect/arith assignment chains probed in earlier rounds.

## Round 5 — repairs first, then new tests

### Repairs

1. `Feedback_Docs/validation_results.md` reported **1129 tests, all OK,
   0 REJECTED** — no repairs were required this round (fourth round in
   a row with zero rejections).
2. Coverage hook — the round-5 `coverage_report.md` repeats the same
   "NO COVERAGE DATA … conftest strips GOCOVERDIR" claim with 0 listed
   targets. Re-verified and unchanged from round 4's finding:
   - `gocover/` at the workspace root holds **1437 `covcounters` files
     plus `covmeta`** and a fresh `profile.txt` (3332 coverage blocks /
     4801 statements), both written during the round-4 validation run —
     the child processes demonstrably emitted coverage through the
     conftest hook.
   - The hook in `eval/tests/conftest.py` (`pinned_env`) is unchanged
     and correct: it copies `GOCOVERDIR` (absolutised) into the pinned
     child env whenever the pipeline sets it.
   - The report generator still appears to match module-qualified
     profile paths (`mvdan.cc/sh/v3/...`) against workspace `src/...`
     paths and finds nothing (round 4's diagnosis); the data itself is
     present and was used as this round's target list.

### Coverage targets addressed this round

The report listed 0 targets, so targets were again taken from the
driver's own `profile.txt`: every remaining uncovered block in the 15
profiled files with a reachable CLI surface. Suite size:
1129 → **1233 tests** (+104 in 7 new files), all passing via
`PROGRAMGYM_EXECUTABLE=$PWD/executable bash eval/run.sh`
(1233 passed in 2.38 s).

New files, each probe-verified against `./executable` first and
coverage-verified against a `go build -cover` rebuild afterwards:

- `test_simplify_edges.py` (22 tests) — `syntax/simplify.go`: subscript
  operator re-spacing (`a[i+1]` → `a[i + 1]`), the array-literal vs
  parameter-expansion asymmetry (parens kept in `a=([(i)]=v)`, dropped
  in `${foo[(1)]}`), negative-index touch, test-expression paren
  removal (`[[ ((a)) ]]` → `[[ a ]]`), negation folding for one and two
  `!` (`! -z` → `-n`, `! ! -z` → `-z`) and the unflippable `! -e` case,
  plus four quoting shapes that must survive `-s`, each with a
  stability re-pass.
- `test_arith_errors.py` (15 tests) — `syntax/parser_arithm.go`: 15
  distinct diagnostics with exact columns (ternary missing `?`, `[`
  after a literal, dangling `+`/`!`/`*`/`**`, `++` of a parameter,
  `+=` after a parenthesised expression and after a `$` name, two empty
  subscript shapes, a string literal in operator position, EOF inside
  `$((`, and the two `let` errors).
- `test_heredoc_edges.py` (6 tests) — `syntax/printer.go`: a heredoc
  whose input is truncated before the terminator is completed on output
  with a trailing newline; two stacked documents; the `\`-quoted
  delimiter spelling kept; a `\<newline>` line-continuation inside the
  delimiter word (delimiter becomes `EOFx`, the literal `EOF` line is
  body); and `<<-` per-line re-indentation where an empty body line
  stays byte-empty and an extra-tab line keeps its depth.
- `test_subst_forms.py` (7 tests) — lexer/printer: a backquote holding
  only a comment is kept, `$( (ls) )` keeps its space without `-s`,
  nested backquotes are promoted to `$( )` — including inside double
  quotes and inside a `let` assignment — and `-s` tightens `${| a; }`
  → `${|a;}` and `${ a; }` → `${ a;}`.
- `test_keyword_errors.py` (15 tests) — `syntax/parser.go`: declare
  (`invalid var name`, `must be followed by names or assignments`),
  the bash/posix/zsh `function` gates (missing name, anonymous-zsh,
  builtin-in-posix at col 10), both `@test` errors, `=(` procsub in
  bats, `((` after a word, the call-shaped `foo(` message with its
  generic placeholder wording (likewise `for foo` for two different
  bad `for` headers), `[[ (` without an operand, a two-part test
  operator word, and a quoted `"if"` treated as a plain word before a
  stray `)`.
- `test_node_edges.py` (28 tests) — nodes/parser/printer: bare
  `declare` and `declare [[`; all five coproc spellings; `time` alone /
  with `-p` / with an assignment; zsh-only anonymous `function { :; }`;
  the zsh `{ echo hi }` block gaining its `;` (and bash's
  unmatched-`{` error for the same bytes); `for` without `in` and over
  a `!` word; mksh's `case x {` header rewritten to `in`/`esac`;
  assignments after `!`, in `if` and `while` heads; zsh `a[i]=`;
  `a=([i]=)`; `a= cmd`; `esac` patterns kept parenthesised/quoted; the
  `-s` else-comment case where the next statement is pushed to a
  tab-indented line; and the two Pos bit-overflow renders (262 145
  lines → `many.sh:?:1:`; column 16 403 → `long.sh:1:?:`).
- `test_json_decoding.py` (11 tests) — `syntax/typedjson/json.go`:
  parse-mutate-refeed on a real `--to-json` dump; a Go string field
  rejects boolean/object/array with per-kind messages while JSON null
  decodes as `""` (printing ` a >b`); `RedirOperator` rejects a number
  naming the Go type; `Stmts` rejects an object and a `SglQuoted`
  element; positions past the bit-packed line/column bounds (300 000 /
  16 384) still decode and print; `Naked: true` prints `a[i]` without
  the `=`; and the unmutated dump round-trips.

Measured locally (instrumented rebuild + the same conftest, full
1233-test suite): **statement coverage 83.4% → 85.8%** (+117
statements) and block coverage 81.7% → 84.3% (+88 blocks) against the
round-4 baseline `profile.txt`. Per-file block gains: `parser.go`
79.7% → 83.5% (+35), `printer.go` 87.7% → 90.0% (+14),
`parser_arithm.go` 86.8% → 98.3% (+14), `simplify.go` 86.8% → 98.9%
(+11), `lexer.go` 87.5% → 88.3% (+5), `typedjson/json.go` 88.3% →
92.2% (+5), `nodes.go` 74.9% → 76.6% (+4).

### Targets skipped this round (with reasons)

- `syntax/braces.go` and `syntax/quote.go` — unchanged: 0% because no
  code in the shfmt binary calls them (they serve `expand`/`interp`).
- `syntax/walk.go` `DebugPrint` and `syntax/parser.go`'s exported Go
  APIs (`Stmts`, `StmtsSeq`, `Interactive`, `WordsSeq`, `Document`,
  `Arithmetic`, `StopAt`, `IsKeyword`, `Variant` panics) — no CLI
  surface.
- `cmd/shfmt/main.go` residuals — TTY branches (hermetic contract),
  and paths verified unreachable via CLI probes this round: a socket
  named `x.sh` passed as an explicit argument is silently skipped by
  `CouldBeScript2` before `os.Open` can fail, so the open-error branch
  never fires; a malformed `.editorconfig` is tolerated (no error), so
  `ecQuery.Find` error branches never fire; the `Lstat` race under
  `-w`, `WriteFile` failures, and the version `mod.Replace` branch are
  likewise not triggerable.
- `syntax/nodes.go` `NewPos` clamp arms — `--from-json` accepts
  `Line: 300000`/`Col: 16384` (tests pinned), but the printer never
  renders those positions, so the clamp arms do not flip; also
  `IsRecovered` (DebugPrint only), the empty-`wordLastEnd` arm, and
  `BraceExp` Pos/End arms.
- `syntax/printer.go` 149–154 (conflicting binary flags — rejected by
  `main.go` first), 535–542 (a heredoc nested inside a `<<-` heredoc
  cannot be produced by the parser), and the `singleLine` arm 1599–1604.
- `syntax/tokens_parse.go` 325–326 and `token_string.go` 163–165 —
  defensive arms of generated code, unreachable from any input.
- `syntax/typedjson/json.go` panic arms and the `Encode` shortcut — not
  reachable through the CLI.
- `syntax/lexer.go` residual internal helpers — exported-API-only
  (documented in round 4).

### Remaining limitations

- The driver's report still prints 0.0% for the path-mismatch reason
  documented in round 4; the local measurements above used the same
  instrumented-rebuild + conftest pipeline that reproduced the driver's
  `profile.txt` numbers exactly.
- 85.8% statement coverage is at the practical ceiling for pure CLI
  testing: the residual is dead code in this binary (braces/quote),
  debug printers, Go-API-only functions, TTY branches, root-only error
  paths, and defensive arms of generated decoders.
- The two Pos-overflow tests write ~0.5 MB fixtures into `tmp_path`
  (262 144 `:` lines / a 16 400-column line); both run in <0.1 s.
- During local coverage measurement only, the two `-version` tests fail
  against the instrumented rebuild (it reports a `+dirty` version and a
  `GOCOVERDIR` warning line); against `./executable` the full suite is
  1233/1233.
