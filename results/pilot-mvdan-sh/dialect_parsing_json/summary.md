# dialect_parsing_json — cross-round summary

## Round 1 (2026-10-14)

### What was built

Initial test suite for shfmt's dialect/parsing/JSON module:
**116 test functions / 235 parametrized pytest items, all passing**
(`PROGRAMGYM_EXECUTABLE=$PWD/executable bash eval/run.sh` → 235 passed,
~2.2 s wall time with 16 xdist workers; also verified serially and on
repeat runs).

Note: the `format-example` symlink in this workspace is broken (points to
`/root/pgsynth/format-example`, which does not exist), so conftest.py was
built from the contract in INSTRUCTION.md: a module-level
`run_shfmt(args, input_text, cwd, timeout)` helper resolving
`PROGRAMGYM_EXECUTABLE`, plus a same-named pytest fixture that defaults
cwd to an empty per-test `tmp_path` (so no stray `.editorconfig` can
influence a run unless the test writes one). Every expected value below
was recorded by running `./executable`; the assigned sources under
`./src/` were only read to locate interesting paths.

### Files and what they pin

| test file | functions | covers |
|---|---|---|
| `test_dialect_flags.py` | 13 | `-ln`/`--language-dialect` accepted values (bash/posix/mksh/bats/zsh/auto) + undocumented aliases `sh`/`dash`; exact `unknown shell language variant: "X"` rejection (exit 2 + full usage); `-ln` without value; space-separated `-ln zsh`; `-p` shorthand; `-p`+`-ln` conflict (`-p and -ln=lang cannot coexist`, exit 1); last `-ln` wins; `-ln=auto` still autodetects; no auto suffix with explicit `-ln`; unknown flag handling |
| `test_auto_detection.py` | 18 | detection order: extension (.bash/.zsh/.mksh/.bats; `.sh` deliberately skipped) → config names (.bashrc/.bash_profile/.bash_logout/.zshenv/.zprofile/.zshrc/.zlogin/.zlogout, plus dotless spellings via base-name dot trimming) → shebang (`/bin/sh`, `/bin/dash`, `#!/usr/bin/env bash`, `#! /bin/zsh` spacing; `#!/bin/zsh5` and `#!/usr/bin/perl` fall through) → bash fallback; precedence (ext > shebang, config name > shebang); `(parsed as LANG via -ln=auto)` suffix; `<standard input>` vs `--filename` prefixes; explicit file arguments |
| `test_dialect_gating.py` | 20 | per-dialect accept/reject matrix with exact LangError text and columns: `function` builtin, arrays, `${a[0]}`, herestrings, `&>`, slicing, `${!a}` (bash/mksh only — zsh rejects), `${a/b/c}`, c-style fors (bash/zsh; mksh rejects), `{varname}>` redirects, `select` (posix rejects); zsh-only: `${=a}` (plain parse error under others), `${(e)a}`, `${+a}`, multi-name/anonymous functions, `foo &|`/`&!`, float arithmetic; mksh-only: `case $a {` (printed canonicalized to `in`/`esac`), `foo |&` coprocess (vs `|&` pipe-all in bash/zsh); bats-only `@test`; `${a^}` bash-only; `=~` absent in mksh; `[[` itself is *not* gated (parses as a command in posix); "bash" hides the internal bash/bats group |
| `test_parse_errors.py` | 13 | missing-keyword messages (`if/until/for/case/while`), `reached EOF without matching X with Y` family, `reached EOF without closing quote`, `not a valid arithmetic operator:` / `not a valid parameter expansion operator:` (incl. Go %q rendering of `\n`), stray keywords (`fi`/`then`/`done`/`do`/`;;`), multi-line line:col positions, stderr-only routing, first-error-wins (an unterminated `if` swallows following lines, so the *case* error on line 2 is reported); heredoc lexer: unterminated heredoc is silently completed (exit 0, delimiter emitted), `<<-` strips the closing delimiter's tab, `<<`/`<<<` must be followed by a word |
| `test_recover.py` | 13 | `--exp.recover N`: unterminated quote recovered (closing quote inserted after the final newline); `case x)` completed to `;; esac`; `(foo |` needs budget 2 (prints `(foo |)`); budget exhaustion changes the message (`reached EOF without matching `(` with `)``); recovered positions print as `?:?:`; 0 = default, negative ignored; non-numeric value → `invalid value "abc" for flag -exp.recover: parse error` (exit 2); LangErrors are NOT recoverable; recovered nodes visible in `--to-json` (`"Y": {}`); recover does not disable EditorConfig |
| `test_simplify.py` | 15 | `-s`: redundant arith parens (incl. idempotence), `$(($a + ${b}))` → `$((a + b))`, `${foo[(1)]}` → `${foo[1]}`, slices, `a[(1)]=2`; NOT simplified: `${a[$b]}`, `${a[x,$b]}`, `${a[@]}`, `${a["x"]}`; test-expr rewrites (`[[ "$foo" == "bar" ]]` → LHS unquoted only, `! -n` → `-z`, double negation, `foo = bar` → `==`); NOT: `[[ ! -e foo ]]`, `[[ foo =~ "$bar" ]]`, `[[ -n a$b ]]`; `$( (sts))` → `$(sts)` vs `( (sts) >f)` kept; `"fo\$o"` → `'fo$o'` re-quoting vs `"foo$bar"` kept; off by default; `-mn` implies `-s` (but keeps spaces around arithmetic operators); `simplify = true` via EditorConfig, disabled by any `-ln` |
| `test_json_trees.py` | 16 | `--to-json` exact bytes for `echo hi` (tab-indented, `"Type"` first, Offset/Line/Col) and for empty input (`{"Type": "File"}`); zsh `Split`/`IsSet` ParamExp fields; byte-offset semantics; round trips (`echo   hi` → `echo hi`; zsh tree needs no dialect flag; re-encode identical); `-s` before encode and after decode; decode errors (`invalid character 'o' in literal null (expecting 'u')`, `EOF`, `unknown type: "Bogus"`, `cannot decode JSON array into syntax.Node`); stdin-only enforcement for both flags; `--to-json --from-json` conflict; legacy `--tojson` alias; empty file name in `--to-json` errors |
| `test_editorconfig.py` | 8 | `shell_variant`/`language_dialect` selection, `[[shell]]`/`[*]`/`[[bash]]` sections, `(parsed as LANG via EditorConfig)` suffix, EC beats `.zsh` filename, invalid EC value ignored (reverts to `-ln=auto` suffix), `-p` disables EC lookup |

### Verification of test strength

Six mutation wrappers were run against the suite (column off-by-one in an
error position; invalid `-ln` accepted; simplify always on; parse-error
exit code changed to 2; `--filename` ignored; `--to-json` compacted).
Each was caught: 2 / 44 / 5 / 98 / 16 / 3 failing tests respectively.

### Coverage targets addressed

- `syntax/parser.go` — dialect gates (checkLang call sites), LangError
  text, recover, `@test`/`function`/`select` clauses: covered.
- `syntax/lexer.go` — quote/EOF errors, `<<`/`<<<`, heredoc completion,
  redirect operators: covered.
- `syntax/parser_arithm.go` — arithmetic operator errors, float/base
  arithmetic gates: covered.
- `syntax/nodes.go` + `syntax/tokens.go` — exercised through every
  parse/format/JSON path (LangVariant Set/String, token names in errors).
- `syntax/simplify.go` — covered via `-s`, `-mn`, and EditorConfig.
- `syntax/typedjson` — encode (exact bytes, dialect fields, recovered
  nodes) and decode (four error classes, round trips).
- `cmd/shfmt/main.go` — flag surface, `formatStdin`/`formatBytes`
  detection order, LangError suffixes, stdin-only JSON modes, `-p`/`-ln`
  conflict, useEditorConfig flag list.
- `fileutil/file.go` — `Shebang` variants and extension handling.

### Targets skipped (with reasons)

- `syntax/braces.go` — `SplitBraces` is only called from
  `expand/expand.go`; not reachable through shfmt's CLI (runtime brace
  expansion belongs to the expansion_globbing module via gosh).
- `syntax/quote.go` — the `Quote` API is used by interp/expand, not by
  `cmd/shfmt`; no CLI-observable behavior.
- `syntax/walk.go` — internal traversal; no distinct CLI surface beyond
  what simplify/print already exercise.
- `doc/` — contains only `plan-v4.md` documentation; no runtime behavior.

### Remaining limitations

- Tests depend on no `.editorconfig` existing in the ancestor chain of
  the pytest tmp dir (`/tmp`, `/`); each test's cwd is a fresh empty
  `tmp_path`, so only a stray `/tmp/.editorconfig` or `/.editorconfig`
  could interfere.
- zsh support is experimental upstream; only stable constructs were
  pinned (no glob qualifiers, no `${a:flags}` beyond `${(e)a}`).
- `-l`/`-d`/`-w`/`--find`/`--detect` behavior is mostly out of module
  scope (shfmt_file_discovery); only the stdin-related errors
  (`-w cannot be used on standard input`) were left untested on purpose.
- Heredoc bodies spanning dialect-specific constructs and `Pos.IsRecovered`
  JSON rendering beyond the `(foo |` case are not exhaustively pinned.

## Round 2 (2026-10-14)

### Repairs

- `validation_results.md`: **0 REJECTED** (235/235 OK) — nothing to repair.
- `coverage_report.md`: "NO COVERAGE DATA" — **fixed `eval/tests/conftest.py`**:
  the pinned `CHILD_ENV` now also carries `GOCOVERDIR` copied from the test
  process environment when present (see the `CHILD_ENV.update` block), per the
  coverage instrumentation hook in INSTRUCTION.md. Verified the suite passes
  both with and without `GOCOVERDIR` set. Note for the driver: the `./executable`
  in this workspace is NOT coverage-instrumented (no Go coverage runtime
  strings in the binary; a run with `GOCOVERDIR` writes no covermeta files),
  so coverage could not be self-measured locally — the pipeline's instrumented
  build is what will record data through this hook from now on.

### Coverage targets addressed

The round-2 report listed 0 targets (no data), so targets were self-selected
by reading the assigned sources (`syntax/parser.go`, `syntax/lexer.go`,
`syntax/parser_arithm.go`, `syntax/simplify.go`, `syntax/tokens.go`,
`syntax/typedjson/json.go`, `cmd/shfmt/main.go`, `fileutil/file.go`) and
diffing their CLI-reachable behaviors against the round-1 suite. 156 new
pytest items in 77 new test functions / 5 new files (module total now
**193 functions / 391 items, all passing** in ~1.2 s):

| new file | functions | covers |
|---|---|---|
| `test_dialect_gating2.py` | 36 | every round-1-untested `checkLang` site in parser.go/lexer.go: mksh value-of `` ${\|stmts;} ``/`${ stmts;}` (bash/mksh accept, zsh/posix reject with exact LangError; `ReplyVar`/`TempFile` CmdSubst JSON fields; multi-stmt bodies reindented); `${%foo}` width (mksh); `${!foo^}`/`${!foo*}` bash-only under mksh; zsh array ops `${a:#pat}`/`:|`/`:*`; the `${x@op}` matrix (Q ok bash+mksh but not zsh/posix, E not zsh, # mksh-only, invalid/needs-literal errors); extglobs `!(x)` (posix rejects, zsh parses as Lit vs bash ExtGlob node); `for ...; { }` canonicalized to `do/done` (zsh rejects); zsh `{}` empty Block vs bash word; zsh-only clobbers `>>\|`/`&>\|`/`&>>\|` and posix `&>>`; zsh `=(cmd)` procsubst; DeclClause builtins (declare/local/typeset/export/readonly/nameref; `declare` is a plain CallExpr in mksh); coproc (bash-only clause, requires-command error, Name field, plain in zsh); let (LetClause with Exprs, bare-`let` error, plain in posix); time (TimeClause, `time -p` PosixFormat JSON, plain in posix); select in mksh/zsh; `$((#expr))` unsigned (mksh reprints as `# a`, bash/zsh reject); mksh `[[ ]]`+stray `]]`; posix `]]` as plain word; `a.b()` invalid func name in posix only; quoted func names; `! !` "cannot negate a command multiple times"; stray `elif`/`esac`/`}`; zsh `${:-word}` empty param name; `$a[1]` zsh Index vs bash ParamExp; `${a:u}` zsh Modifiers vs bash Slice; `${@[0]}` "cannot index a special parameter name"; zsh nested expansions `${${a}}`/`${#$(cmd)}`/`${(f)"$(x)"}`; zsh glob qualifiers `*(N)`/`*.(:a)`; mksh-only unclosed-heredoc rejection vs bash completion |
| `test_parse_errors2.py` | 14 | parser_arithm.go error paths: ternary (`missing `:` after `?``, `missing `?` before `:``), `` `[` must follow a name like a[i] ``, comma, "must be followed by an expression", and the `reached `)` without matching` variant; parser.go test-expr errors (invalid op word, `-qq`, `== !`, glued `==n`, empty `[[ ]]`, "expected `&&`, `\|\|` or `]]` after complex expr", "`==` must be followed by a word"); array/case validation ("arrays cannot be nested", "array element values must be words", "inline variables cannot be arrays", "case patterns must be separated with `\|`", "case patterns must consist of words", "expansions not allowed in heredoc words"); CaseOperator set `;&`/`;;&` (bash) and `;\|` (mksh-only, canonicalized with a leading space; bash errors at the `;`); lexer.go "invalid UTF-8 encoding" (via a file argument, path-prefixed), valid UTF-8 passthrough, nesting-depth limit (exactly 10000: 10001 parens → "nesting is deeper than 10000 levels" at col 10002, 9999 formats back), backquote→`$()` canonicalization, `$'...'`/`$"..."`/`$(<file)` preserved, backslash-newline continuation joins lines, comments preserved |
| `test_json_trees2.py` | 13 | typedjson decode: position validation on embedded fields (OpPos as number/string/missing-Col/wrong-type/negative/fraction — "Pos"/"End" keys themselves are skipped, garbage there still formats); type mismatches naming Go types (`[]*syntax.Word`, `syntax.WordPart`, bool); missing/wrong "Type" on Command; unknown-field errors (`syntax.File`, `syntax.CallExpr`); operator enums (number refused with "a string is required", `invalid RedirOperator: "Bogus"`, valid `>>` decode changes output); `null` root; arith operator string encodings (`?`/`:`/`+=`/`**`/`,`/unary `!~++`); round trips of 14 new constructs (let/coproc/time/declare/ternary/extglob/`${\|...}`/case `;;&` `;\|`/zsh ops/mksh `# ` unsigned and `${%a}`) with canonical case-terminator spacing; ParenTest node shape |
| `test_simplify2.py` | 6 | simplify.go cases that must NOT fire: single quote blocks requoting (`"fo'o"`), non-simple params kept (`${a[0]}`, `${#a}`, nested `$((2))`), negated subshell kept (`$( !(a))` → `$(!(a))`), multi-statement subshell kept (reindented `$(\n\t(a)\n\t(b)\n)`); index-paren removal in both assign target and expansion; `--simplify` long flag |
| `test_stdin_mode.py` | 8 | cmd/shfmt/main.go argument surface: `-` as the stdin argument (errors keep `<standard input>` + `-ln=auto` suffix), flags must precede `-` (`-ln=posix -`, `-s -`, `--to-json -`), `-- -` still stdin, `-` plus a second positional makes both lstat file paths (exact two-line stderr), `--filename`+`-` detection, shebang detection through `-`, fileutil extension matching is case-sensitive (`.BASH`/`.Bash` fall back to bash with the auto suffix) |

### Targets skipped (with reasons)

- **JSON null word (`"Args": [null]`) deliberately not pinned**: the reference
  binary panics there (nil-pointer SIGSEGV, exit 2, Go panic trace). Forcing a
  re-implementation to reproduce a crash and its goroutine dump would be
  brittle and pins an unintended bug; recorded here instead.
- `syntax/braces.go`, `syntax/quote.go`, `syntax/walk.go`, `doc/` — unchanged
  from round 1: no CLI-reachable surface through shfmt (braces.go is only
  called from expand/, quote.go from interp/expand, walk.go is internal
  traversal, doc/ is markdown).
- `fileutil.CouldBeScript`/`CouldBeScript2` — file-discovery scope
  (shfmt_file_discovery module).
- `fileutil.Shebang`/`HasShebang` — no new surface beyond round 1's coverage;
  the one additional case found (case-sensitive extension matching) is pinned
  in `test_stdin_mode.py`.
- Local coverage measurement was impossible (see Repairs) — the round-3
  report should now populate and can name any remaining cold spots precisely.

### Verification

`PROGRAMGYM_EXECUTABLE=$PWD/executable bash eval/run.sh` → **391 passed**
(xdist, 1.1–1.2 s), also verified serially (1.6 s), with `GOCOVERDIR` set,
and on repeated runs. All new expectations were recorded by probing
`./executable` this round (roughly 120 probe runs across 12 batches);
no expected value was inferred from source reading without an observed run.

### Remaining limitations

- Same `.editorconfig` ancestor-chain caveat as round 1 (fresh `tmp_path`
  cwd per test; only a stray `/tmp/.editorconfig` or `/.editorconfig`
  could interfere).
- zsh remains experimental upstream: glob qualifiers are pinned only as
  literal passthrough, and `${x:modifiers}` only for the probed forms.
- `--exp.recover` interaction with the newly added gates (e.g. recovering
  past a `let` clause error) is not pinned.
- The round-1 mutation-wrapper spot checks were not repeated (no Go
  toolchain in this workspace to rebuild mutated binaries); the new tests
  assert exact bytes observed from the reference instead.

## Round 3 (2026-10-14)

### Repairs

- `validation_results.md`: **0 REJECTED** (391/391 OK) — nothing to
  repair from the validator.
- An earlier, interrupted pass of this round had left six new test files
  in `eval/tests/` with **5 failing items** against the reference; all
  were repaired before new tests were written:
  - `test_json_decode_errors.py::test_wrong_scalar_shapes` (4 params):
    the hand-written f-string JSON document was malformed (one closing
    brace short), so the reference rejected the *document* instead of the
    field under test. Rebuilt with `json.dumps` from a dict; re-probed
    the messages (`cannot decode JSON {number|object|array|boolean} into
    string`, exit 1, stderr-only).
  - `test_syntax_corners.py::test_line_continuations[arith]`:
    `echo $((a +\<newline>b))` gains a space before the backslash —
    expectation corrected to `echo $((a + \<newline>b))` after probing.
- **5 linter E-findings** in existing files (E1 in
  `test_dialect_gating.py::test_double_brackets_are_words_in_posix`;
  E4 ×2 in `test_dialect_gating2.py`; E4 ×2 in `test_json_trees2.py`):
  run results were consumed inline (`json.loads(run_shfmt(...).stdout)`);
  rewritten as `proc = run_shfmt(...)`, `assert proc.returncode == 0,
  proc.stderr`, then `json.loads(proc.stdout)`. The linter now reports
  **0 E findings / 0 W1 warnings** over all 22 test files.

### Coverage hook (the round-2 "NO COVERAGE DATA" root cause)

`eval/run.sh` (pipeline-managed, not modified) force-resets
`PROGRAMGYM_EXECUTABLE` to this module's uninstrumented `./executable`
before pytest starts, so round 2's `GOCOVERDIR` forwarding was wired
correctly but the binary it reached never writes counters. `conftest.py`
now:

- probes the assigned binary with a throwaway `GOCOVERDIR` (`--version`
  run) and keeps it only if it drops covcounters files;
- during a coverage run (`GOCOVERDIR` present), when the assigned binary
  is not instrumented, falls back to the instrumented build the driver
  stages next to the module workspaces (`../../executable.cov`). That
  path only exists in the pipeline layout, so validation copies (which
  run elsewhere) are unaffected;
- `run_shfmt` gained an `env=` parameter so a test can layer individual
  variables (`FORCE_COLOR`, `NO_COLOR`) onto the pinned child
  environment.

Verified end-to-end: with `GOCOVERDIR` set, the whole suite runs against
the instrumented build (identical behavior, same `--version`
v3.0.0-20261012132700-0e8ea6fccd96) and writes 955 counter files; 686/686
pass.

### Coverage targets addressed

With the repaired hook, real coverage was measured for the first time
(`go tool covdata textfmt` over the assigned packages): **80.73%** after
the repaired files, **81.90%** after the new targets below (pipeline
threshold 0.8). 295 new pytest items in 91 new test functions / 9 new
files (module total now **284 functions / 686 items, all passing** in
~1.1 s):

| new file | funcs/items | covers |
|---|---|---|
| `test_construct_zoo.py` | 12/12 | one "zoo" script per dialect (bash/mksh/bats/zsh) driving (nearly) every syntax node through format, `-s` (exercising each Walk arm) and a `--to-json`/`--from-json` round trip, pinning the node-type set of each encoding |
| `test_from_json_operators.py` | 6/140 | the typed-JSON decoder's operator-enum tables: every legal spelling of redirect/param-expansion, unary/binary arithmetic and unary/binary test operators decoded through `--from-json`, each pinned by its formatted output |
| `test_json_decode_errors.py` | 5/35 | decode rejections: bogus operator spellings, malformed documents, wrong container shapes, wrong scalar shapes (`cannot decode JSON {kind} into …`), plus the lenient arms where a missing or null field is accepted |
| `test_lex_torture.py` | 25/33 | lexer token tables far beyond the gating tests: arithmetic operators in every context (incl. zsh floats/subscripts, `^` xor, the JSON-only assign ops bash rejects), param-expansion and `@`-operator sets, test-operator torture, heredoc delimiter styles and CRLF stripping, redirect spellings, quoting/assignment torture, glob and regex patterns, unicode, zsh subscript flags |
| `test_main_modes.py` | 13/20 | shfmt's own surface: `--version` bytes, `-fn` conflict, optional-value flag validation, `-l`/`-l=0`/`-d` applied to stdin, `-w` rejected on stdin, `--filename` with file args, `--apply-ignore` matrix, EditorConfig language sections per dialect |
| `test_syntax_corners.py` | 15/27 | zsh `!`-clobbers and aliases, procsubst gate, heredocs buried in case items/subshells, comments inside array literals, special parameter names, extglob case patterns, brace/regex literals, parenthesised function names, triple backquotes, line continuations, EOF-corner errors |
| `test_walk_directories.py` | 11/16 | `fileutil.CouldBeScript2` triage and `main.go` walkPath/formatPath/formatBytes: directory walks (hidden entries, non-shell extensions, `.git` skip, symlinks, too-short files, no-shebang fallback), parse errors naming the walked file and continuing with the `-ln=auto` suffix, explicit-argument dialect from the shebang, unknown-shebang fallback to bash, lstat error, `-l`/`-l=0` naming walked files, `-w` rewriting files and refusing to replace a symlink |
| `test_simplify_walk_arms.py` | 1/9 | the Walk arms only `-s` reaches (ParamExp search-and-replace, zsh subscript flags, case-item/array-element comments, bats TestDecl, extglob, coproc name), each paired with a marker that `-s` must still rewrite |
| `test_diff_color.py` | 3/3 | the `FORCE_COLOR`/`NO_COLOR` decision for `-d` diffs: exact ANSI-colored hunk bytes, FORCE_COLOR winning over NO_COLOR, plain output with NO_COLOR alone (via the new `env=` helper; pinned env keeps `TERM=dumb`) |

Coverage effect on the targeted files: `fileutil/file.go` 30.8% →
**84.6%**, `cmd/shfmt/main.go` 75.4% → **88.3%**, `syntax/walk.go` 62.9%
→ **69.7%**; module total 80.73% → **81.90%**.

### Targets skipped (with reasons)

- `syntax/braces.go` (0%) and `syntax/quote.go` (0%) — unchanged from
  rounds 1–2: only called from `expand/`/`interp/`, no CLI surface
  through shfmt.
- `syntax/walk.go` remaining ~30% — `DebugPrint`/`debugPrinter`
  (debug-only, never invoked by the CLI), the `!f(node)` early-return
  arm and the panic default.
- `syntax/printer.go` cold code — `-kp` binary-prefix and `colCounter`
  line-wrapping paths: layout territory (format_style_config module).
- `fileutil/file.go` remaining 2 blocks — `HasShebang` and the
  deprecated `CouldBeScript` are never called by `cmd/shfmt`.
- `cmd/shfmt/main.go` remaining 33 statements — TTY-only arms
  (usage-on-TTY, isatty color probe), `--find`/`--detect` walk arms
  (shfmt_file_discovery scope), `indent_style=space` (format scope), and
  error arms unreachable as root (stdin read error, `os.Open` failure,
  the version `mod.Replace` arm).
- The round-2 JSON null-word panic note stands (not pinned on purpose).

### Verification

`PROGRAMGYM_EXECUTABLE=$PWD/executable bash eval/run.sh` → **686 passed**
(xdist, 1.10–1.12 s across three consecutive runs), also verified
serially (2.80 s) and with `GOCOVERDIR` set against the instrumented
build (686 passed). All new expectations were recorded by probing
`./executable`; no expected value was inferred from source reading
without an observed run.

### Remaining limitations

- Same `.editorconfig` ancestor-chain caveat as rounds 1–2 (fresh
  `tmp_path` cwd per test).
- `test_diff_color.py` pins the colored and plain diffs byte-for-byte;
  the TTY path itself (color without `FORCE_COLOR`) is not pinnable
  hermetically.
- Walk tests depend on WalkDir's deterministic lexical order and on
  symlink support in the tmp filesystem (both verified on repeated
  runs).
