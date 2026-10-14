# gosh_execution — cross-round summary

## Standing context (discovered in round 1, still true)

The workspace reference `./executable` is **shfmt v3.0.0** (built from
`./cmd/shfmt` of the mvdan/sh tree), not the `gosh` interpreter binary. It
contains no interpreter at all: `-c` is an undefined flag (exit 2 with the
shfmt usage), script arguments are parsed and re-printed rather than run, and
non-terminal stdin is formatted rather than executed. Every gosh *engine*
behaviour in the module description (interp package, runner semantics,
builtins' output, exit-status mirroring) is therefore unreachable through the
shipped reference, and asserting any of it would violate the "only assert
observed behaviour" rule. What IS observable about the statement layer
through this binary: which statement forms parse, how statements are
normalised when re-printed (line joining, tab indentation, operator and
terminator spacing), the exact parse diagnostics for statement-level
mistakes, and the fact that nothing ever executes. The suite pins that.

## Round 1 (recap)

- `test_gosh_cli_surface.py`: 21 tests pinning the driver-level CLI surface
  of the shipped binary (`-c` rejected, script args formatted not run, stdin
  passthrough, no side effects). All 21 validated OK.
- Seven further files (202 tests) asserted full gosh interpreter semantics
  (recorded against a gosh binary the round-1 agent built from `./src` as an
  oracle) and were wrapped in a `require_gosh()` skip guard that skipped them
  whenever `PROGRAMGYM_EXECUTABLE` was not a working gosh engine.

## Round 2 — repairs first

1. **Deleted all 202 REJECTED tests** (the seven files
   `test_gosh_builtins/control_flow/driver/options/redirection/resolution/state.py`).
   Reason: the pass-check runs against the shipped reference (shfmt), where
   gosh semantics cannot occur, so the tests can never pass there; and the
   validator rejects skipped tests ("pass-check failed (skipped)"). Deleting
   is the only honest repair — keeping them as skips just re-rejects them,
   and rewriting them to pass would mean asserting unobserved behaviour.
2. **Repaired the conftest coverage hook** (driver's explicit demand): the
   run helpers now propagate `GOCOVERDIR` from the test process environment
   into the child env
   (`cov_env = {"GOCOVERDIR": v for v in [os.environ.get("GOCOVERDIR")] if v}`),
   merged into every child environment including the fully pinned one.
   Removed the `require_gosh`/skip machinery from conftest at the same time.
3. Self-validation after repairs: `PROGRAMGYM_EXECUTABLE=$PWD/executable bash
   eval/run.sh` → 87/87 pass; weak-assert linter clean (0 errors/warnings);
   all 87 tests fail against a no-output `exit 0` dummy (dummy-check safe);
   repeated runs agree (deterministic).

## Round 2 — new tests (coverage targets)

The coverage report listed **zero targets** ("NO COVERAGE DATA was
collected"), so there was no target list to work from; I repaired the hook it
named and wrote new tests for the module's statement-level functionality as
far as it is observable through the shipped binary:

- `test_gosh_statements.py` — 37 test items (25 functions, 3 parametrised):
  if/elif/else (`then` re-joining, else-if not collapsed to elif), while/
  until, for-in and bare `for`, C-style `for ((;;))` (incl. the `for (( ; ;
  ))` empty-clause spacing), select, case (terminator ` ;;` spacing, `;&`/
  `;;&` fallthrough operators, `in` re-joining, multiline layout), brace
  groups and subshells (exploded to lines vs single-statement inline),
  function definition forms (`f()`, `function f`, `function f()`,
  subshell body), nested indentation, `;` splitting, `&` binding (incl.
  after compound bodies), `!` negation (incl. the `cannot negate a command
  multiple times` parse error), `time`/`coproc` prefixes, `|&`, `[[ ]]`/
  `(( ))`, classic `[ ]`/`test`, a full builtin-surface round-trip, the
  empty-program → single-newline quirk, final-newline completion, and
  script-file-argument formatting.
- `test_gosh_redirection_forms.py` — 29 test items (17 functions, 4
  parametrised): operator/target spacing collapse for `>`/`>>`/`<>`/`>|` and
  digit-prefixed forms, fd duplication (`2>&1`, `>&2`, `3<&0`) and closing
  (`2>&-`, `0<&-`), `&>`/`&>>`, `{var}>file` named fds, leading redirects on
  simple commands (but rejected before compound commands — the zsh-feature
  diagnostic), missing-target parse errors (`>`/`>&` "must be followed by a
  word"), redirect order preservation, quoted targets, here-string word
  quoting, per-pipeline-stage redirects, redirects attached to compound
  statements (fi/esac/}/)/done), two heredocs on one command, heredoc after
  `done`, process substitution words, `exec` fd statements, and redirect
  together with `&`/`!`.

Suite total after round 2: **87 tests, 87 passing** (21 CLI-surface + 37
statement + 29 redirection).

## Targets skipped, with reasons

- All `interp/*`, `cmd/gosh`, `x/coreutils` source paths: **not reachable via
  the shipped CLI** — the reference binary is the shfmt formatter, which does
  not link the interpreter at all (probe: `-c` → "flag provided but not
  defined"). No execution semantics (builtin output, exit-status mirroring,
  traps, options effects) can be recorded from it.
- Interactive REPL behaviour (`$ ` prompt, `> ` continuations): requires a
  TTY; the test contract forbids TTYs, and shfmt has no REPL regardless.

## Known limitations (for the pipeline operator)

1. **Module coverage will stay 0% even with the conftest hook fixed.** Two
   independent causes, both outside what agents may modify:
   - `eval/run.sh` (marked "Test agents must not modify this file")
     unconditionally re-exports
     `PROGRAMGYM_EXECUTABLE="${BRANCH_ROOT}/executable"`, so during
     `run_suite_instrumented` the suite still runs the *plain* workspace
     binary, never `executable.cov`; no counters are written. Verified:
     running the suite with `PROGRAMGYM_EXECUTABLE=executable.cov` directly
     (bypassing run.sh) + `GOCOVERDIR` produces 95 counter files — the
     conftest hook itself works.
   - Even with the instrumented binary running, the assigned packages
     (`cmd/gosh`, `interp`, `x/coreutils`) are not linked into the shfmt
     binary, so they cannot appear in a coverage profile at all. To get
     meaningful coverage for this module the pipeline would need to ship the
     gosh binary (`go build ./cmd/gosh`) as `./executable` and build
     `executable.cov` from the same main package.
2. Because the shipped reference differs from the module description, this
   suite pins the *observable* statement layer (parse/reprint/diagnostics/no
   execution) rather than interpreter semantics. If a later round ships a
   real gosh reference, these tests will fail loudly — that is the signal
   that the module assignment and the reference binary have been reconciled,
   and the interpreter-semantics tests should be rewritten then.

## Round 3 — repairs first

1. **Test repairs: none required.** `validation_results.md` after round 2
   lists 87/87 OK, 0 REJECTED.
2. **Coverage hook: made the effective repair.** The round-2 report still
   said "NO COVERAGE DATA was collected … your conftest run helper strips
   the child environment and drops GOCOVERDIR", but the round-2 conftest
   already propagated GOCOVERDIR (the report's boilerplate fires whenever
   `assigned_files == 0`). The real reason no counters were written:
   `eval/run.sh` force-resets `PROGRAMGYM_EXECUTABLE` to the module's
   uninstrumented `executable` before pytest starts, so the driver's
   `executable.cov` never ran. Repaired by adopting the pattern the one
   successfully-measured module (`shfmt_cli_io`, 90.75%) uses: when
   `GOCOVERDIR` is present and the assigned binary does not itself write
   covcounters (probed against a throwaway GOCOVERDIR), the run helpers fall
   back to the driver-staged `../executable.cov`, verified to write counters.
   Validator pass/double/dummy runs are unaffected: they never set
   GOCOVERDIR, and the staged file only exists in the pipeline layout.
   Verified end-to-end by replaying `run_suite_instrumented` exactly
   (`PROGRAMGYM_EXECUTABLE=…/executable.cov GOCOVERDIR=… bash eval/run.sh`):
   166/166 pass and 191 covcounters files land in GOCOVERDIR (round 2: 0).
3. **Why the report will still show 0% / 0 targets — root cause, verified.**
   The plan assigns this module `cmd/gosh, interp, x, x/coreutils`, but the
   reference (and `executable.cov`, built from `./cmd/shfmt`) links only
   `cmd/shfmt`, `fileutil`, `syntax`, `syntax/typedjson` (checked: the
   imports of `cmd/shfmt/main.go`; and the profile from the working
   shfmt_cli_io run lists exactly those four packages). None of the assigned
   paths can ever appear in a coverage profile of this binary, so
   `select_targets` matches 0 files. I deliberately did **not** try to work
   around this by building an instrumented `./cmd/gosh` myself and running
   the suite against it during coverage runs: the suite pins the shipped
   reference's behavior and would fail wholesale against gosh, so the
   resulting numbers would measure inputs reaching code the tests never
   assert on — a fabricated signal. The fix belongs to the pipeline: build
   the reference and `executable.cov` from `./cmd/gosh` (the repo contains
   it), or reassign this module. Note `expansion_globbing` (assigned
   `expand, pattern, shell, internal`) has the same structural gap.

## Round 3 — new tests (coverage targets)

The coverage report listed **0 targets** ("NO COVERAGE DATA"), so there was
no target list to work from; per the documented root cause above none can be
listed for this module's assigned files. I therefore continued pinning the
module's statement-layer functionality as far as it is observable through the
shipped binary, in four new files (79 new test items; suite 87 → 166):

- `test_gosh_heredoc_forms.py` (16 items): `<<-` strips exactly one tab from
  the terminator and normalises bodies to tab indentation (adding a tab to
  plain lines); space-indented terminators never match `<<-` (the heredoc
  then runs to EOF and is auto-closed with a fresh terminator — as is any
  unterminated `<<` heredoc, rc 0); quoted delimiters `<<'EOF'`/`<<"EOF"`
  preserved; `<< EOF` space collapse; blank lines inside a body preserved
  (unlike between statements); terminator must match the delimiter word
  exactly (`EOFx` is body) and only the first word after `<<` is the
  delimiter (`cat <<E O F` → `cat O F <<E`); heredoc operators are deferred
  to the end of the word list while file redirects keep their place among
  the first two words; a tab-indented `EOF` fails to terminate a plain `<<`
  heredoc inside a function/if, surfacing as the unclosed-`if`/unclosed-
  `{` diagnostics.
- `test_gosh_words_and_expansions.py` (14 items): backticks rewritten to
  `$( )` (including nested escaped backquotes); `$[1+2]` rewritten to
  `$((1 + 2))`; arithmetic operator spacing normalised (incl. inside
  assignment values); inter-word space/tab runs collapsed; single/double/
  ANSI-C quoting round-trips byte for byte; arrays (`a=(…)`, `a+=(…)`,
  `${a[@]}`/`${#a[@]}`/`${a[0]}`), parameter-expansion operators, special
  parameters and tilde forms verbatim; `[[ ( … ) ]]` paren hugging; `((
  i++, j = 5 ))` → `((i++, j = 5))`; `a = 5` is not an assignment.
- `test_gosh_parse_diagnostics.py` (34 items): exact wording and positions
  for unclosed `'`/`"`/backtick, `[[`/`((`/`{`/`(` ("reached EOF without
  matching X with Y"), unterminated `if`/`case` ("must end with fi/esac"),
  all nine stray clause keywords (fi/done/esac/elif/then/do/}/)/;;), empty
  `then`/`do` bodies, missing `then`/`do`/`in` headers, leading and
  dangling `|`/`&&`/`||`/`;`/`&`; `else` and `in` alone are plain words;
  only the FIRST parse error is reported and valid statements before it
  produce no output; `line:column` positions track real coordinates.
- `test_gosh_script_io.py` (15 items): a parse error inside a script file is
  prefixed with the file path and does not stop later files (either side of
  it); any extension is parsed for an explicit argument; an empty file and
  whitespace-only stdin print exactly one newline; the same file twice is
  processed twice; `-` alone means stdin, but beside another argument it is
  a missing path (`lstat -:`) and stdin stays unread; stdin is ignored once
  file arguments are given; CRLF and lone CR stripped; NUL bytes silently
  dropped; blank-line runs collapse to one separator and leading/trailing
  blanks vanish.

Self-validation: `PROGRAMGYM_EXECUTABLE=$PWD/executable bash eval/run.sh` →
166/166 pass; a second run agrees (deterministic); all 166 tests fail
against a no-output `exit 0` dummy (dummy-check safe); the weak-assert
linter reports 0 findings; and the suite also passes 166/166 when the
coverage fallback runs the instrumented build.

## Round 3 — addendum (re-invoked session)

The round-3 slot was re-run by the driver: the previous round-3 session
wrote the four files above plus the two round-3 summary sections, but was
replaced before the driver validated it (`stage4_state.json` still showed
`rounds: 2, n_ok: 87` at re-invocation, and `validation_results.md` /
`coverage_report.md` were still the round-2 feedback).  This session
inherited that disk state.  What it did:

1. **Repairs (per `validation_results.md`): none required** — the round-2
   feedback lists 87/87 OK, 0 REJECTED.
2. **Vetted the predecessor's 79 never-validated tests** as the real risk
   area: full suite 166/166 pass against `./executable`; all 166 fail
   against the no-output `exit 0` dummy (the driver's own dummy shape,
   replicated from `_val/gosh_execution__dummy`); the pipeline linter
   (`pipeline/stage4_linter.py`) reports 0 findings; no fixes needed.
3. **Coverage hook re-verified against the freshly staged
   `../executable.cov`** (staged by the driver at re-invocation time):
   `./executable` writes no covcounters, the staged cov build does, so the
   conftest fallback engages exactly as designed; instrumented replay
   (`GOCOVERDIR=… bash eval/run.sh`) passed 166/166 and wrote 191 counter
   files.  Cross-checked the fallback pattern against `shfmt_cli_io`'s
   conftest (the module that measured 90.75% in round 2 with the same
   pattern and still passed its dummy/pass validation) — identical logic.
   The produced profile lists only `cmd/shfmt`, `fileutil`, `syntax`,
   `syntax/typedjson`, re-confirming with live data that none of this
   module's assigned paths (`cmd/gosh`, `interp`, `x`, `x/coreutils`) can
   appear in a coverage profile of this binary; 0 listed targets is
   structural, not a hook defect (see the root-cause note above).
4. **New tests (54 items, suite 166 → 220)** — the coverage report lists 0
   targets, so per the documented structural reason these continue pinning
   the statement layer as far as the shipped binary exposes it.  Every
   expectation was recorded by probing `./executable` this session:
   - `test_gosh_statement_edges.py` (37 items): case quirks (clause-less
     `case x in\nesac` two-line layout; empty item body `a) ;;`; the
     optional final `;;` before `esac` always re-inserted; a column-0 `;;`
     on its own line re-indented with the body's tab), empty-compound
     rejections (`{ }` / `f() { }` → `` `{` must be followed by a statement
     list ``), bodyless functions (`()`, `f()`, `function f` all share the
     `` `foo()` must be followed by a statement `` wording), `f()` + `{` on
     separate lines rejoined, `function f ()` space dropped, multiline
     subshell function body kept, two definitions split by `;`, pipelines
     of compounds (`{ }`/`while`/`if` stages inline, `(a; b) | c` explodes
     with `| c` after the `)`, `a | b &`), `&&`/`|` continuation lines
     gaining a tab (also inside an `if` header), `!` before subshell/brace/
     background, `time` over pipelines/subshells and bare, bare `select`,
     empty and `$( )` assignment values, one-element-per-line array
     literal, `${!x}` / `${x:1:2}`, backslash-newline continuation kept
     (with tab indent), escaped `\&\&` and a lone `""` command word,
     legacy `>&f` / `<&2`, here-string + file redirect order, `2>&1` inside
     a pipeline, persistent `exec >f 2>&1` / `exec {fd}<file`, empty quoted
     redirect target `>""` accepted, mixed `<<-A <<B` heredocs (only the
     `<<-` one de-tabs its terminator), heredoc on a pipeline stage and
     inside a subshell (forcing the multi-line `(` layout), comment
     round-trips (own-line/trailing/`#nospace`, comment-only program gains
     the final newline), the if-header comment migrating to `if a; then #
     c`, comments not collapsed like blank lines, comments inside
     function/case bodies, a stdin `#!/bin/sh` preserved but NOT switching
     the grammar off bash, and a 59-line `set -`/`shopt`/builtin-flag
     word surface round-trip (`set -a..-x`, `-o` long forms, `shopt
     -s/-u/-p`, `read`/`getopts`/`readarray`/`mapfile` flag words,
     `IFS=`-prefixed reads, `cd -L/-P`, `wait`, `eval`, `printf -v`,
     `trap ''`/`-l`, `local`/`export`/`readonly`/`declare -n`).
   - `test_gosh_parse_diagnostics.py` (+16 items): unclosed `$(` (bracket
     wording at the `$`), unclosed `${` (the newline itself reported as
     `not a valid parameter expansion operator: "\n"` — a literal
     backslash-n in the message), dangling arithmetic operator in `$((1+`;
     `for`/`select` missing `do` with the `foo` placeholder wording;
     unclosed `while`/`until`/`select` naming `done` and item-less `case`
     naming `esac`; `case x in a echo` → `` case patterns must be
     separated with `|` `` at 1:13; empty `elif` condition (`elif` must be
     followed by a statement list at 1:15) and `else c fi` surfacing as the
     generic unclosed-`if` error; lone `!` (`` `!` cannot form a statement
     alone ``); lone `coproc` (`` coproc clause requires a command ``);
     invalid UTF-8 on stdin (`1:6: invalid UTF-8 encoding`).
   - `test_gosh_script_io.py` (+1): invalid UTF-8 inside a script file is
     reported with the file-path prefix, exit 1, empty stdout.

Self-validation (final): `PROGRAMGYM_EXECUTABLE=$PWD/executable bash
eval/run.sh` → **220/220 pass** (0.99 s); a second, instrumented run
(`GOCOVERDIR=… bash eval/run.sh`, exercising the `executable.cov`
fallback) also passes 220/220 and writes 253 covcounter files; all 220
tests fail against the no-output `exit 0` dummy; the pipeline linter
reports 0 findings.  Suite composition: cli_surface 21, statements 37,
redirection_forms 29, heredoc_forms 16, words_and_expansions 14,
parse_diagnostics 50, script_io 16, statement_edges 37.

Per-file counts after this round: 8 files, 220 tests, all passing.

## Round 4 — repairs first

1. **Test repairs: none required.** `validation_results.md` after round 3
   lists 220/220 OK, 0 REJECTED.
2. **Coverage hook re-verified end-to-end** (the round-3 report still shows
   the `NO COVERAGE DATA … REPAIR IT FIRST` boilerplate): the conftest
   propagates `GOCOVERDIR` and, during a coverage run, falls back to the
   driver-staged `../executable.cov`.  Replayed exactly as the driver does
   (`GOCOVERDIR=… bash eval/run.sh`): **292/292 pass and 333 covcounter
   files** are written (round 3: 253 — the new tests exercise more code).
   The report's boilerplate fires because `assigned_files == 0`, which is
   structural: the reference (and `executable.cov`, built from
   `./cmd/shfmt`) links only `cmd/shfmt`, `fileutil`, `syntax`,
   `syntax/typedjson`, none of which is in this module's assignment
   (`cmd/gosh`, `interp`, `x`, `x/coreutils`).  See the round-3 root-cause
   note; nothing further to repair from this side.

## Round 4 — new tests (coverage targets)

The coverage report lists **0 targets** (the structural reason above), so per
the documented skip these continue pinning the module's statement layer as
far as the shipped binary exposes it.  Every expectation was recorded by
probing `./executable` this session; 72 new test items in two new files
(suite 220 → 292):

- `test_gosh_conditional_validation.py` (27 items) — the `[[ ]]` conditional
  and `(( ))` arithmetic **validation surface** (test.go semantics, named in
  the module description, previously only round-tripped): `[[ a = b = c ]]`
  → `expected `&&`, `||` or `]]` after complex expr` at the stray operand; a
  trailing unary/binary operator (`[[ -f ]]`, `[[ a == ]]`) **eats the `]]`
  as its operand** and surfaces as the generic unclosed-`[[` EOF error at
  1:1; `[[ ! ]]` → `` `!` must be followed by an expression``; `-a`, `|` and
  a plain word in operand position all share `not a valid test operator:
  `<word>`` at the offending column; `[[ ( a ]]` → the quirky `reached
  LitWord without matching `(` with `)`; empty `[[ ]]`/`(( ))`/`((;))` share
  `` `<opener>` must be followed by an expression`` at 1:1; `((1+))` /
  `((a=))` → the operator wording at column 4; `((,))` → `` `,` must follow
  an expression``; `echo $(( ))` names `$((` at the `$` column (6); the
  contrast pin — classic `[ a -a b ]`, `[ a = b = c ]`, `[ ! a = b ]`,
  `[ -f ]`, `test a = b = c` are **not validated at all** (verbatim
  round-trips); valid operator sets (`=~`, `! -f x`, `<`/`>` with `&&`,
  `-z || -n`) round-trip byte for byte; `]]` on its own input line is
  rejoined; a broken `&&` continuation gains one tab.
- `test_gosh_statement_grammar.py` (45 items) — statement-form gates and
  normalisations: the optional `(` before a case pattern is **always
  dropped** (`(a)` → `a)`, also in the multi-line layout where a column-0
  `;;` gains the body tab); `a|b)` → `a | b)`; five coproc forms round-trip
  (NAME + brace body, NAME + simple command with redirect, bare subshell,
  NAME + subshell, `&` after the command); `time` takes any flag-looking
  words (`time -x ls` is fine); a redirect-only statement (`>f`) is valid
  and splits from a following statement; `FOO=1 > f cmd` keeps the redirect
  between assignments and command; `cmd > >(tr …)` process-substitution
  redirect target; `a & ! b` splits into `a &` / `! b`; `! x=1 cmd` negates
  a command with inline assignments while `x=1 ! cmd` **degrades `!` to a
  plain word**; `f() { :; } && g` (function definition as the left side of
  `&&`) is accepted; `a+=3` / `a+=1 cmd`; empty `$( )` collapses to `$()`
  even mid-word; bare `for i; do`; `a[0]=1; a[b]+=1` split onto lines; two
  `if`s on one line split; `exec -a name cmd`, `let a=1 b=2`,
  `dirs -c; pushd sub; popd` word surfaces.  Rejections: mid-statement `!`
  (`a | ! b` at 1:5, `time ! ls` at 1:6 → `` `!` can only be used in full
  statements``); empty clause conditions (`if;`/`while;`/`until;` → `` `kw`
  must be followed by a statement list``); `for "i"` / `select;` → `` `kw`
  must be followed by a literal``; `for i a;` → the `` `for foo` must be
  followed by `in`, `do`, `;`, or a newline`` wording; `case;` → `` `case`
  must be followed by a word``; `a[b] c=1` → `` `a[b]` must be followed by
  `=`` and `a[]=1` → `` `[` must be followed by an expression``; `a[0]=1
  cmd` → `inline variables cannot be arrays`; `function 'f'` → `` `function`
  must be followed by a name`` (while `function 1f` and `declare "x"` are
  accepted); lone `let`; `;;`/`;;&`/`;&` after a complete statement →
  `can only be used in a case clause` at the terminator column; `a & & b` →
  `` `&` can only immediately follow a statement``; `a && | b` and `a |&` →
  `` `<op>` must be followed by a statement``; `case x in a) b)` → `a
  command can only contain words and redirects; encountered `)`` at 1:15;
  `echo ${}` → `invalid parameter name` at the `}` column.

Deliberate scope choice this round: dialect flags (`-ln …`) and simplify
(`-s`) were **not** tested here — the sibling modules `dialect_parsing_json`
(dialect gating, simplify) and `format_style_config` own those surfaces, and
`shfmt_cli_io` owns the generic flag-CLI behaviour, so new tests here stayed
on the default-interface statement layer.

Self-validation (final): `PROGRAMGYM_EXECUTABLE=$PWD/executable bash
eval/run.sh` → **292/292 pass** (1.0 s), a second run agrees (deterministic);
the instrumented replay (`GOCOVERDIR=… bash eval/run.sh`, exercising the
`executable.cov` fallback) also passes 292/292 and writes 333 covcounter
files; **all 292 tests fail** against the driver's no-output `exit 0` dummy
(`_val/gosh_execution__dummy/executable`, run via pytest directly because
`eval/run.sh` force-resets `PROGRAMGYM_EXECUTABLE`); the pipeline linter
(`pipeline/stage4_linter.py`) reports 0 findings.

Per-file counts after this round: 10 files, 292 tests (cli_surface 21,
conditional_validation 27, heredoc_forms 16, parse_diagnostics 50,
redirection_forms 29, script_io 16, statement_edges 37, statement_grammar
45, statements 37, words_and_expansions 14).

## Round 5 — repairs first

1. **Test repairs: none required.** `validation_results.md` after round 4
   lists 292/292 OK, 0 REJECTED.
2. **Coverage hook re-verified end-to-end** (the round-4 report still shows
   the `NO COVERAGE DATA … REPAIR IT FIRST` boilerplate): the conftest
   propagates `GOCOVERDIR` and, during a coverage run, falls back to the
   driver-staged `../executable.cov`.  Replayed exactly as the driver does
   (`GOCOVERDIR=… bash eval/run.sh`): **344/344 pass and 407 covcounter
   files** are written (round 4: 333 — the new tests exercise more code).
   Cross-checked the staged build's `covmeta` live: it embeds exactly
   `mvdan.cc/sh/v3/cmd/shfmt`, `…/fileutil`, `…/syntax`,
   `…/syntax/typedjson` — none of this module's assigned paths (`cmd/gosh`,
   `interp`, `x`, `x/coreutils`), re-confirming that `assigned_files == 0`
   and the report's boilerplate are structural (root cause in the round-3
   note).  Nothing further to repair from this side.

## Round 5 — new tests (coverage targets)

The coverage report lists **0 targets** (the structural reason above), so
per the documented skip these continue pinning the module's statement
layer as far as the shipped binary exposes it.  Every expectation was
recorded by probing `./executable` this session; 52 new test items in four
new files (suite 292 → 344):

- `test_gosh_control_bytes.py` (9 items) — control bytes inside words and
  what the printer's aligning writer does with them.  Discovered live: the
  re-printed program goes through an aligning (tab)writer, so bytes the
  parser keeps inside word literals reshape the *output*: a **form feed
  (0x0c) terminates the printed line** — mid-word (`x\fy` → `x\ny`),
  inside single/double quotes, inside heredoc bodies and inside comments,
  with the following word-separator space landing at the start of the new
  line (`echo a\fb` → `echo a\n b`), no re-indentation inside function
  bodies or `<<-` bodies, and **no blank-line collapsing** (each of two
  leading form feeds prints its own blank line, unlike real blank runs).
  A **vertical tab (0x0b) acts as an aligned tab stop**: alone it prints
  one space (`x\vy` → `x y`), an empty cell between two vtabs is discarded
  (`x\v\vy` → `x y`), a trailing one pads (`a\v` → `a `), but across lines
  the cells align — `x\vy\naaaa\vy` → `x    y\naaaa y`, and a vtab after
  word-separator spaces stacks pad+space (`echo a\v b\v c` →
  `echo a  b  c`).  Because alignment spans ALL output lines of a program,
  the multi-case vtab test runs each case in its own program (first draft
  combined them and the empty cell padded to the neighbouring column's
  width — `x   y`).  A **UTF-8 BOM is not whitespace**: preserved at the
  start of the program and mid-word, and other raw control bytes (0x0f)
  round-trip byte for byte.
- `test_gosh_expr_gates.py` (12 items) — expression gates beyond the
  round-4 conditional-validation surface: a stray word in `(( ))` →
  `` not a valid arithmetic operator: `b` `` at 1:6; `(( 1 = 2 ))` →
  `` `=` must follow a name ``; `(( a )` → `` reached `)` without matching
  `((` with `))` `` at 1:1; the same dangling-operator error inside `let`;
  `#` inside arithmetic (`(( a # b ))` at 1:6, `$((a #b))` at 1:11) is an
  invalid operator, **not** a comment — while a *spaced* `#` inside
  `[[ ]]` **does** start a comment and swallows the `]]` (unclosed-`[[`
  EOF error), and an unspaced `a#b` is literal operand text (verbatim
  round-trip); dangling `&&`/`||` inside `[[ ]]` reported at the operator
  column; unclosed array literal (`a=(1 2` → `(` wording at 1:3) and
  subscript (`a[b` → `[` wording at 1:2); `cat <<` with no delimiter →
  `` `<<` must be followed by a word `` at 1:5; `if() { :; }` → the zsh
  anonymous-function gate (`` anonymous functions are a zsh feature; tried
  parsing as bash (parsed as bash via -ln=auto) `` at 1:3); chained
  `((x = y = 1))` / `a[i]+=1` / `$((a[0] + 1))` round-trip as valid forms.
- `test_gosh_statement_layout.py` (20 items) — statement gates and layout
  normalisations: a space-separated `2` before `>f` stays a command word
  (only glued digits are fd prefixes); a `(( ))` loop condition hugs its
  parens (`until (( i > 3 ))` → `until ((i > 3));`) while a `[[ ]]`
  condition keeps its spaces; a multi-line C-style `for` header is
  re-joined with backslash continuations leaving **two spaces before each
  `\`** (`for ((i = 0;  \…`), and a break right after `((` joins with a
  bare `\`; multi-line `then` re-joining applies to `elif` clauses too; a
  newline after a bare `in` normalises to `; do` (for/select) and after an
  `until` condition as well — but once `in` has a word the list **cannot**
  span a newline (`for i in a\nb\ndo` → the `` must be followed by `do` ``
  error, likewise select); the optional final `;;&` before `esac` is kept
  with the ` ;;` spacing; extglob case patterns (`@(a|b))`, `*(a)b)`)
  round-trip verbatim; all five compound forms (brace/if/for/function/
  case) parse as inline pipeline stages; lone assignments are valid
  operands of `&&`/`||`; `coproc` takes a full `if`; `time` prefixes
  stack and combine with `&`; an escaped newline before a here-string word
  is kept and gains a tab (`cmd <<< \\\n\tword`); a heredoc inside `$( )`
  forces the `$(\n\t…` multiline substitution layout; `< <(cmd)`,
  `2> >(tr x)` and `done < <(gen)` redirect forms; array-literal inner
  spaces collapse while wrapped elements gain a tab; `foo-bar()` and
  `foo.bar()` names; a quoted `declare "x"=1` name.
- `test_gosh_word_surface_extras.py` (11 items) — word and builtin-argument
  forms not in the earlier word-surface rounds: `$(<file)` redirect-only
  substitution; `${x: -1}` (space after the colon), `${!x[@]}`, `${x^}`,
  `${x,}`; the `$-`/`${-}` flags parameter; `$"…"` locale quoting;
  ANSI-C escapes round-trip and a trailing `\'` escapes the closing quote
  (unclosed-quote error at the `$'` column); `a[$i]=x`, `unset a[0]`,
  `declare -A x=([a]=1 [b]=2)`, `local -n ref=x`; arithmetic inside
  builtin arguments is normalised (`shift $((n+1))` → `$((n + 1))`, same
  for `exit`); `set -euo pipefail`, `set +x`, `unalias -a`, `hash -r`,
  `cd -`; `export -f`, `wait -n`, `eval "a=1; b=2"`; a heredoc-fed `read`.

Self-validation (final): `PROGRAMGYM_EXECUTABLE=$PWD/executable bash
eval/run.sh` → **344/344 pass** (1.1 s), a second run agrees
(deterministic); the instrumented replay (`GOCOVERDIR=… bash eval/run.sh`,
exercising the `executable.cov` fallback) also passes 344/344 and writes
407 covcounter files; **all 344 tests fail** against a no-output `exit 0`
dummy (run via pytest directly, since `eval/run.sh` force-resets
`PROGRAMGYM_EXECUTABLE`); the pipeline linter
(`pipeline/stage4_linter.py`) reports 0 findings.

Per-file counts after this round: 14 files, 344 tests (cli_surface 21,
conditional_validation 27, control_bytes 9, expr_gates 12, heredoc_forms
16, parse_diagnostics 50, redirection_forms 29, script_io 16,
statement_edges 37, statement_grammar 45, statement_layout 20, statements
37, word_surface_extras 11, words_and_expansions 14).
