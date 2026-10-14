# Summary — expansion_globbing

## Module reality (established round 1, still true)

`./executable` is **shfmt v3.0.0-dev** (the mvdan/sh formatter), NOT `gosh`.
It never executes shell code, so runtime expansion/globbing behavior
(`$VAR` values, IFS splitting, `set -u` errors, glob *matching*) is not
observable through this CLI. What IS observable is everything word-level at
the parse/format layer: the exact syntax, tree shape and JSON serialisation
of parameter/tilde/brace/arithmetic/command/process substitution, quoting,
glob and extglob patterns, field/word structure, and the diagnostics for
malformed words. Round 1 built the suite around that surface (124 tests).

## Round 1 (no summary was written then — reconstructed)

- 124 tests across 10 files, all OK in round-2 validation (0 REJECTED).
- Weak spots found later by coverage measurement: no compound statements at
  all (if/while/for/case/[[ ]]/function/let/declare bodies), no `--from-json`
  beyond one small tree, no printer options (-bn/-i/-kp/-sr/-mn compound),
  no zsh word forms, no backquote-escape handling.

## Round 2

### Repairs (step 1 of the round protocol)

- **REJECTED tests: none** — validation_results.md lists 124/124 OK.
- **Coverage instrumentation (the report's REPAIR IT FIRST item): the
  conftest already complies.** `eval/tests/conftest.py` copies `GOCOVERDIR`
  from the test-process env into the pinned child env (`PASSTHROUGH_ENV`).
  I verified this end-to-end: running the suite with
  `PROGRAMGYM_EXECUTABLE=<instrumented binary>` + `GOCOVERDIR=<dir>` writes
  `covcounters.*`/`covmeta.*` files into that dir (hundreds of files for the
  full run), and `go tool covdata textfmt` produces a full profile. Nothing
  was changed in conftest.py because nothing was missing.
- **Why the driver still collected nothing — pipeline-side, two causes:**
  1. `eval/run.sh` line 8 unconditionally sets
     `PROGRAMGYM_EXECUTABLE="${BRANCH_ROOT}/executable"`, overriding the
     driver's `PROGRAMGYM_EXECUTABLE=<out>/executable.cov`. The tests
     therefore always run the NON-instrumented binary and no counters are
     written. run.sh is pipeline-managed ("Test agents must not modify this
     file"), so I cannot fix this from `eval/`. Fix on the driver side:
     either make run.sh use `${PROGRAMGYM_EXECUTABLE:-...}`, or copy the
     instrumented binary over each module's `executable` before the
     coverage run.
  2. Even with (1) fixed, **the assigned source files can never appear in
     the profile**: `go list -deps ./cmd/shfmt` shows the binary links only
     `fileutil`, `syntax`, `syntax/typedjson` (plus its own main). None of
     the assigned packages (`expand`, `pattern`, `shell`, `internal`,
     `internal/arithm`) are linked in, and Go coverage only reports
     instrumented code that is actually in the binary. Verified empirically:
     a full-suite profile contains zero files under those directories.

### Coverage targets addressed (step 2)

With no driver-computed targets (no data) and the assigned packages
structurally unreachable, I selected targets myself: the word-relevant,
CLI-reachable code in `syntax/` + `typedjson`, measured against
`executable.cov` (the instrumented build) with the same method the driver
uses. 64 new test functions / 70 collected items in 5 new files:

| new file | tests | primary targets |
|---|---|---|
| test_case_test_clauses.py | 13 | case item operators (`;&` `;;&`, `;|` rejected), case layout, `[[ ]]` operator vocabulary, regex-operand lexing (advanceLitRe), chained-comparison error |
| test_compound_word_contexts.py | 18 | if/while/until/for(c-style)/select/function/coproc/time/let/declare word contexts, heredoc bodies with expansions, `<<-` tab stripping, unclosed-heredoc recovery, redirect fd forms (isLitRedir), comment alignment |
| test_zsh_word_forms.py | 5 | zsh numeric range globs (zshNumRange), extglob-as-literal in zsh, subscript flags (zshSubFlags), `${(j:,:)array}` param flags |
| test_legacy_and_json_forms.py | 25 | nested/escaped backticks (bquoteEscaped), `$[...]`→`$((...))`, `@` transform alphabet, arithmetic operator zoo + base prefixes + error wording, `${!prefix*}`/`@` JSON Names field, `--from-json` round-trip of every operator enum (tokens_parse.go UnmarshalText), typed decode errors for bad enum values |
| test_printer_word_layout.py | 9 | escaped-newline continuations (bslashNewl), -bn, -i, -kp, -sr, -mn on compound statements (semiOrNewl, spaces, spacePad) |

Measured per-file movement of the suite (old → new, statement coverage of
the reference source via the instrumented binary):

- syntax/lexer.go 63.0% → 76.0% (bquoteEscaped 0→67%, zshNumRange 0→82%, advanceLitRe 0→82%, isLitRedir 38→100%)
- syntax/parser.go 58.8% → 75.3% (ifClause/whileClause/selectClause/timeClause 0→100%, caseClause 0→71%, letClause 0→83%, zshSubFlags 0→90%, testClause 0→90%)
- syntax/printer.go 57.2% → 79.6% (bslashNewl 0→100%, semiOrNewl 0→80%)
- syntax/nodes.go 50.0% → 68.3%
- syntax/tokens_parse.go 1.7% → 46.2% (all 12 operator UnmarshalText enums now exercised; ParExpOperator 0→65%, testDecl @test 0→71%)
- syntax/tokens.go 91.7% → 100%, typedjson/json.go 75.6% → 78.6%, parser_arithm.go 81.5% → 83.7%, walk.go 32.0% → 39.4%

### Skipped targets (with reasons)

- `expand/`, `pattern/`, `shell/`, `internal/`, `internal/arithm` (all
  assigned files): **not linked into ./executable** — runtime packages used
  only by gosh/interp, which is not shipped. Unreachable via this CLI by
  construction; module coverage will read 0.0% under the driver's
  computation regardless of test content.
- `syntax/braces.go` (`SplitBraces`) and `syntax/quote.go`: exported
  library helpers; their only callers are in `expand/`, `shell/` and
  `interp/` (unlinked). Note `BraceExp` nodes can never appear in a parsed
  tree via shfmt, so the round-1 brace tests correctly assert braces stay
  literal.
- `syntax/parser.go` library entry points (`Parser.Words/Arithmetic/
  Document/Stmts/StmtsSeq/Interactive/InteractiveSeq`, `StopAt`,
  `IsIncomplete`, `IsKeyword`): not exposed by any shfmt flag.
- `syntax/walk.go` `DebugPrint` (+debugPrinter): debug helper, no CLI flag.
- `syntax/nodes.go` interface marker methods (`commandNode`,
  `wordPartNode`, `loopNode`, `arithmExprNode`...): never called at
  runtime; only satisfy compile-time interfaces.
- `Pos.IsRecovered` / parser recovery paths: recovery nodes are not
  produced by the CLI's fail-fast parsing (the `--exp.recover=1` flag
  exists but did not change diagnostics for the cases probed in round 1).

### Remaining limitations / notes for round 3

- If the driver fixes the coverage plumbing (run.sh override), this
  module's report will still show 0% because of the unlinked assigned
  packages (see above) — treat syntax/* percentages, not the module
  number, as the real signal for this module.
- Remaining dark word-relevant areas worth a look if the driver starts
  listing syntax/* targets: lexer `regToken`/`dqToken` branch tails
  (exotic operator spellings), `advanceLitHdoc`/`quotedHdocWord` branch
  tails (heredoc escape combinations), `unclosedHdoc` (33%), printer
  `wantsNewline`/`spacedToken` tails, `coprocClause` (48%),
  `bashFuncDecl` (59%), typedjson `decodeValue` node kinds not present in
  RICH_SRC (e.g. DeclClause variants, TimeClause with pipeline,
  CoprocClause, TestDecl in --from-json).
- Full suite: 194 tests, 1.0 s wall clock, all passing against the
  reference; weak-assert linter clean.

## Round 3

### Repairs (step 1 of the round protocol)

- **REJECTED tests: none** — validation_results.md lists 194/194 OK.
- **The coverage hook (the report's REPAIR IT FIRST item): FIXED for
  real this round.** Round 2 proved the conftest already propagated
  `GOCOVERDIR` and blamed `eval/run.sh` line 8 (it force-resets
  `PROGRAMGYM_EXECUTABLE` to the uninstrumented `./executable`, so the
  driver's `executable.cov` never runs). run.sh is pipeline-managed, so
  the repair had to live in the conftest: `shfmt_executable()` now probes
  whether the resolved binary writes covcounters (one `--version` run
  against a throwaway GOCOVERDIR, lru-cached), and during a coverage run
  (`GOCOVERDIR` set in the test-process env) falls back to the
  instrumented build the driver stages next to the module workspaces
  (`../executable.cov`, i.e. `stage4/executable.cov`). This is the same
  workaround the shfmt_cli_io module already validated in its round 2
  (their round-2 report is the only one with real data). Verified
  end-to-end from this module: `GOCOVERDIR=<dir> bash eval/run.sh` now
  writes 443 counter files (was 0) and still passes 264/264; without
  `GOCOVERDIR` nothing changes (fallback inert, normal binary used).
- Consequence for the driver's round-4 report: counters will flow, but
  `select_targets` matches only the assigned paths (expand/, pattern/,
  shell/, internal/), which are **not linked into the shfmt binary** —
  the report will show 0.0% / 0 assigned files. That is a build-graph
  fact, not a test gap; see round 2.

### Coverage targets addressed (step 2)

No driver targets again (no data), so targets were self-selected from a
per-function dark map computed against `stage4/executable.cov` with the
driver's own method (`go tool covdata textfmt` over a full-suite run).
The round-2 "remaining dark areas" list drove the selection. 66 new test
functions / 70 items in 11 new files:

| new file | tests | primary targets (function: before → after) |
|---|---|---|
| test_test_operator_vocabulary.py | 4 | lexer `testUnaryOp` 26→100%, `testBinaryOp` 73→100%: full 27-entry unary vocabulary, `-a`→`-e` and `-h`→`-L` alias normalisation, `= -le -nt -ot -ef`, invalid-operator wording |
| test_cmdsubst_value_forms.py | 8 | printer `cmdSubst` 33→100%: mksh `${ stmts;}` / `${|stmts;}`, backquote `` `# comment` `` special case, `$( (subshell) )` vs `$(((ls)))` disambiguation, backquote-ending-in-heredoc newline forcing, `-kp` padding (`stmtsPos`) |
| test_heredoc_bodies.py | 7 | lexer `quotedHdocWord`/`advanceLitHdoc`/`hdocBody` 75→100%, `writeEscapingTabs` 40→90%: quoted/unquoted backslash handling, `<<-` tab stripping + mid-line tabs, `-i=2` keeps body tabs (closing word even keeps one), EOF-truncated bodies |
| test_assign_index_forms.py | 6 | parser `getAssign` 67→91%: `a[i]+=v`, naked `a[1]` in declare/export, `a[1]=(...)` bash error vs zsh OK, `a[b]`/`a[b]+`/`a[]=1` diagnostics, `${#-fallback}` ambiguity, `${10}` |
| test_nested_and_special_params.py | 4 | parser `paramExpParameter` 70→83%: zsh `${#${x}}`/`${#$(ls)}`/`${${x}}`, bash LangError position, `cannot combine multiple parameter expansion operators` |
| test_coproc_function_forms.py | 6 | parser `coprocClause` 48→100%, `bashFuncDecl` 59→88%: every coproc shape, multi-name/anonymous function zsh gating, `function foo(` / `foo(` paren errors, `((` in argument position |
| test_arith_error_wording.py | 6 | parser_arithm `arithmMatchingErr` 33→67%, `isArithName` 57→71%: operator/ternary/bracket/comma wording, assignability (`$x = 1` rejected, `a[0] = 1` OK), zsh float gating |
| test_redirect_spellings.py | 4 | lexer `regToken` 62→85%: the `&`-tail — `&>` `&>>` `<<<` `>&` `<>`, zsh clobbers `>!`→`>\|` `>>!`→`>>\|` `&>!`/`&>\|` `&>>!`/`&>>\|`, `&\|`/`&!` statement split, posix rejection |
| test_json_enum_matrix.py | 10f/14i | tokens_parse `UnmarshalText` 46→84%: **every enum case arm in the file is now covered** — pipes/case terminators/extglobs/redirects/no-colon par-exp ops/zsh `:# :| :*`/`=( `/arith zoo/[[ ]] ops via --to-json→--from-json round-trips; JSON-only `**= &&= \|\|= ^^^=` decode; `decodeValue`+`jsonTypeName` type-mismatch messages (bool/number/array/object/null) |
| test_word_layout_edges.py | 6 | printer `elemJoin` 64→91%, `flushComments` 64→91%, `casePatternJoin`: multi-line array literals + comments, case comment placement |
| test_loop_case_edges.py | 5 | parser `wordIter` 67→78%, `caseClause` 71→82%: `for x;`, numeric loop name, word-list errors, mksh `case x {`→`in`/`esac` canonicalisation, case structure errors |

Per-file movement of the whole suite (statement coverage via the
instrumented binary, round-2 → round-3):

- syntax/tokens_parse.go 46.2% → **83.8%** (all enum spellings covered)
- syntax/lexer.go 76.0% → **85.7%**
- syntax/printer.go 79.6% → **86.4%**
- syntax/parser_arithm.go 83.7% → **88.0%**
- syntax/parser.go 75.3% → **80.8%**
- syntax/typedjson/json.go 78.6% → **83.3%**
- syntax/nodes.go 68.3% → **72.0%**
- syntax/walk.go 39.4% → 40.0% (Walk dark branches are DebugPrint + node kinds the printer never visits)

### Skipped targets (with reasons)

- Assigned packages (`expand/ pattern/ shell/ internal/ internal/arithm`):
  still not linked into `./executable` (unchanged from round 2; verified
  again — the cov binary's profile contains only syntax/*, cmd/shfmt,
  fileutil). Unreachable via this CLI by construction.
- `--from-json` with `"Args": [null]` or `"Args": null`: the reference
  **panics** (nil-pointer in `CallExpr.Pos`, exit 2, Go goroutine dump) —
  same class of bug dialect_parsing_json documented. Not pinned: forcing
  a re-implementation to reproduce a crash trace is brittle.
- printer `SingleLine`/`Write`/`sink`, parser library entry points
  (`Words/Arithmetic/Document/Stmts*/Interactive*`, `StopAt`,
  `IsIncomplete`, `IsKeyword`), `walk.DebugPrint`, `Pos.IsRecovered`:
  no CLI flag reaches them (unchanged from round 2).
- `syntax/braces.go`, `syntax/quote.go` (0%): library helpers, callers
  only in unlinked packages (unchanged).
- `fileutil/file.go` (30.8%): file-walking paths are the
  shfmt_file_discovery module's scope.

### Remaining limitations / notes for round 4

- Full suite: **264 tests (66 new functions / 70 items), ~1.2 s**, all
  passing against the reference; weak-assert linter clean (empty
  findings dict).
- Still-dark word-relevant spots if round 4 lists syntax/* targets:
  lexer `quotedHdocWord` (68% — zsh heredoc-word quoting tails), `dqToken`
  (77%), parser `callExpr` (78%), `unquotedWordPart` (77%), `unclosedHdoc`
  (33% — recovery-only), printer `staysOnSameLine` (18% — layout paths
  needing multi-line nested compounds), `stmtsForceNewline`/`blockNewline`
  tails, typedjson `decodeValue` (80% — remaining node kinds:
  DeclClause variants, TimeClause with pipeline, CoprocClause, TestDecl
  via --from-json), `jsonTypeName` null/default arms, nodes.go `End`
  methods for rarely-built nodes.
- The `-ln=auto` suffix (" (parsed as bash via -ln=auto)") appears on
  LangError diagnostics when no explicit dialect is given; new tests pin
  the explicit-dialect form (the suffix itself is pinned by round-1/2
  tests).

## Round 4

### Repairs (step 1 of the round protocol)

- **REJECTED tests: none** — validation_results.md lists 398/398 OK.
- **Coverage hook (the report's REPAIR IT FIRST item): no repair was
  possible or needed — the premise no longer holds.** The round-4 report
  still claims the conftest strips `GOCOVERDIR`; in fact the conftest has
  propagated it since round 2 (`PASSTHROUGH_ENV` in `build_child_env`),
  and the driver's *current* `run_suite_instrumented` does not rely on the
  env override at all anymore: it swaps `stage4/executable.cov` into the
  module's own `./executable` (backup + restore) and sets `GOCOVERDIR`
  itself, so every test run through `eval/run.sh` exercises the
  instrumented binary directly. The round-3 conftest fallback
  (`shfmt_executable` probing for covcounters and resolving
  `../executable.cov`) is therefore redundant but harmless — during a
  coverage run the resolved `./executable` already writes counters, so the
  fallback is never taken. Verified empirically: the driver's round-3
  coverage run wrote 844 counter files and left `profile.txt` at the
  module root; a fresh instrumented run of the current suite through the
  current conftest wrote 946 counter files. **Data collection works.**
- **Why the report still says NO COVERAGE DATA: a false positive from
  `select_targets`, not a data problem.** It matched 0 *assigned* files
  because the assigned packages are not linked into the shfmt binary.
  Verified twice this round: (a) `go list -deps ./cmd/shfmt` links
  exactly `mvdan.cc/sh/v3/{fileutil, syntax, syntax/typedjson,
  cmd/shfmt}` (plus `mvdan.cc/editorconfig`) — no `expand`, `pattern`,
  `shell`, `internal` anywhere; (b) both the driver's own `profile.txt`
  and my fresh `covdata textfmt` profile contain zero entries under those
  directories. No test content can change this; it is a build-graph fact
  (see round 2). Nothing outside `eval/` was touched.

### Coverage targets addressed (step 2)

No driver targets again (0 assigned files), so targets were self-selected
from a per-function dark map computed against `stage4/executable.cov`
with the driver's own method (`go tool covdata textfmt`, then diffing
uncovered ranges against Go source function spans). The round-3
"remaining dark areas" list drove the selection. 59 new test functions /
79 items in 7 new files:

| new file | tests | primary targets (before → after) |
|---|---|---|
| test_simplify_node_kinds.py | 9 | walk.go `Walk` node-kind arms, reached by running `-s` (Simplify → Preorder → Walk) over pipes, subshells, loops, declare/let/time/coproc, extglobs, process substitution and comment-bearing nodes: walk.go 44.6→**64.0%**, simplify.go 92.8→93.5% (arith negation reformat, comment reattachment across node kinds) |
| test_stmt_keyword_errors.py | 8 | parser `gotStmtPipe` keyword guards (`then`/`fi`/`do`/`done`/`esac` "can only be used in an \`if\`" family, block-close `}` at 1:10, `! !` multi-negation error), backquote → `$( )` normalisation, zsh anonymous function `() { echo; }`, invalid func name at 1:1, mksh `\|&` split, nested subshell indentation |
| test_zsh_param_tail_forms.py | 6 | parser `paramExp` zsh tails: `${+x}` set-ness, unterminated `${(x` and `${foo:U` each with their own EOF wording, `${foo:U:u}` modifier chain, `${=}` empty short prefix, "nested parameter expansion cannot be followed by a word" at 1:12 |
| test_from_json_decode_errors.py | 10f/14i | typedjson `decodePos`/`jsonTypeName`/`decodeValue` error arms: json.go 83.9→**93.5%** — position given as number/null/boolean/string/array, position object with extra/missing fields, string position-field value, out-of-range values (incl. the `4.294967296e+09` rendering), redirect fd `N` as scalar vs `*syntax.Lit`, `"N": null` + `>`/`>>` round-trips, unknown field naming `syntax.File`, wrong-slot node, missing `"Type"` for `syntax.Command`, operator given as number, non-object top-level JSON |
| test_position_overflow.py | 4 | nodes.go `Pos` bit clamps: column past 16383 and line past 262143 render as `?` in diagnostics (`1:?` / `?:6`), while the over-long valid inputs still format byte-exact; nodes.go 76.6→77.5% |
| test_word_lexer_tails.py | 13 | lexer.go 93.3→**95.4%**: `dqToken` (`$((` after a double quote), `advanceLitOther` tails (multibyte first rune, `#` inside `[[ ]]`), `zshNumRange` buffer-boundary refill (`<5-10>` landing on the last of 4096 buffered bytes), comment ended by escaped newline, `quotedHdocWord`, `regToken` zsh `>>&`/`>>&|`/`>>&!` aliases; parser for-braces→do/done, word-list paren error, case head word/`in` errors |
| test_comment_layout_tails.py | 9 | printer.go 87.1→**89.0%**: `comments`/`stmt` tails — comment-only case and array bodies, comment re-attached above the first case pattern, blank line kept before a comment, `-kp` padded comment, `-mn` keeping only the shebang, semicolon on its own indented line after a continuation, comment inside a then-block, `then` without a statement list |

Per-file movement of the whole suite (statement coverage via the
instrumented binary; baselines re-measured on the suite *as it entered
round 4* — 398 items, which already includes tests added after the
round-3 summary was written, hence higher than round 3's "after" numbers):

- syntax/walk.go 44.6% → **64.0%** (93 previously-dark blocks newly lit)
- syntax/typedjson/json.go 83.9% → **93.5%**
- syntax/lexer.go 93.3% → **95.4%**
- syntax/parser.go 82.4% → **85.5%**
- syntax/printer.go 87.1% → **89.0%**
- syntax/nodes.go 76.6% → 77.5%
- syntax/simplify.go 92.8% → 93.5%
- syntax/* overall 81.5% → **84.4%** (3672 → 3806 of 4507 statements)

### Skipped targets (with reasons)

- Assigned packages (`expand/ pattern/ shell/ internal/ internal/arithm`):
  still not linked into `./executable` (`go list -deps` proof above);
  unreachable via this CLI by construction, so module coverage reads 0%
  regardless of test content (unchanged since round 2).
- `syntax/braces.go`, `syntax/quote.go` (0%): library helpers whose only
  callers live in the unlinked packages (unchanged).
- walk.go remaining dark (~36%): `DebugPrint`/`debugPrinter` and its
  `print`/`printf`/`newline` helpers (no CLI flag), plus `Walk` arms for
  node kinds the parser never builds in this configuration.
- typedjson remaining dark: `panic` arms and the decode-from-arbitrary-
  decoder library paths, not reachable through the `--from-json` CLI.
- printer `-fn` combined with `-bn` (the "binaryNextLine requires
  binary" error arm): probing the reference shows the CLI **accepts**
  the combination without erroring, so the arm is dead via the CLI and
  pinning it would assert a non-existent message.
- `--from-json` `"N"` given as a position *object* (`{"Offset":…}`): the
  error names a random field of the object ("unknown field for
  syntax.Lit: \"Offset\"" vs \"Col\") because Go map iteration order is
  nondeterministic — deliberately not pinned.
- zsh numeric range whose digits straddle the 4096-byte read boundary
  (`"a"*4093 + "<5-10>"` fails with `1:4099: \`>\` must be followed by a
  word`): a real lexer boundary bug (the range digits are never peeked
  after a refill; upstream TODO). Only the stable working boundary
  variant (`"a"*4095`) is pinned; pinning the buggy error would couple
  the test to buffer-internals.
- Library entry points (`Words`/`Arithmetic`/`Document`/`Stmts`/
  `Interactive*`, `StopAt`, `IsIncomplete`, `IsKeyword`), printer
  `SingleLine`/`Write`/`sink`, `Pos.IsRecovered`: no CLI flag reaches
  them (unchanged since round 2).

### Remaining limitations / notes for round 5

- Full suite: **477 items (59 new functions / 79 items), ~1.3 s**, all
  passing against the reference; weak-assert linter findings dict empty.
- Still-dark word-relevant spots, if round 5 lists syntax/* targets:
  printer `staysOnSameLine` (~18%, needs multi-line nested compounds),
  parser `callExpr`/`unquotedWordPart` branch tails, lexer `unclosedHdoc`
  (recovery-only), nodes.go `End` methods for rarely-built nodes,
  walk.go DebugPrint family (unreachable).
- If round 5's report again shows NO COVERAGE DATA / 0.0%, that is the
  unlinked-assigned-packages false positive documented since round 2 —
  the syntax/* percentages above are this module's real signal.
