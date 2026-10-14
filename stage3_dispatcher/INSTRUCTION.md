# Task: Decompose a repository into functional test-construction modules

You are the task-decomposition (dispatcher) agent. A test-construction team of
parallel subagents will each own ONE module of this repository; each subagent
writes black-box behavioral tests for the parts of the program its module covers.
Your job is to produce the module assignment plan.

## Input

- Repository source at `./sh-src` (read it; you have full source access).
- The reference executable is NOT available to you — decomposition is source-based.
- Module budget: **{N_MODULES} functional modules** (decided by the pipeline's
  complexity score; do not change the count).

## What to produce

Write `modules.json` at the workspace root with EXACTLY this schema:

```json
{{
  "modules": [
    {{
      "name": "short_snake_case_name",
      "source_paths": ["cmd/shfmt", "syntax/..."],
      "functional_description": "What this module's functionality is, which CLI
        flags/behaviors it governs, and what an external user observes from it.",
      "interaction_categories": ["I/O", "Args", "Help"]
    }}
  ],
  "test_reuse": true
}}
```

Rules:

1. **Coverage & disjointness.** The `{N_MODULES}` modules' `source_paths` together
   must cover the meaningful production code of the repository (every significant
   package/file appears in at least one module). Overlap is allowed where features
   genuinely interact, but each module must have a clear primary responsibility.
2. **External-behavior orientation.** Modules are organized by what the program's
   USER observes (flags, input/output behavior, error handling, file operations,
   language/dialect handling, configuration), not by internal class structure.
3. **Interaction categories.** For each module choose one or more from exactly
   these six labels (these steer the test-construction subagent):
   - `Args` — flag syntax, required/optional arguments, type checking
   - `Config` — environment variables and config files, precedence conflicts
   - `Help` — --help/-h output, per-subcommand help
   - `I/O` — stdin/file reading, stdout/stderr separation, exit codes, output format
   - `Subcommand` — routing, alias resolution, global vs subcommand flags
   - `TUI` — keyboard navigation, keybindings, screen updates, mode switching
4. **test_reuse.** If the repository ships a meaningful native test suite
   (e.g. `*_test.go`, `tests/`), set `"test_reuse": true` — the pipeline will add
   one extra subagent that rewrites native test cases as black-box behavioral
   tests. Otherwise set it to false.
5. Names must be unique; descriptions must be specific enough that a subagent who
   never sees the rest of this plan knows exactly what to test.

After writing `modules.json`, validate it yourself: `python3 -m json.tool modules.json`
must pass, module count must be exactly {N_MODULES}, and every top-level production
source directory of the repo must appear in some module's `source_paths`.
