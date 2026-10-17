# program-pipeline-synthesis

A faithful, scaled-down reproduction of the **Program-Env** pipeline described in
[*ProgramGym: Scaling Training Environments for Long-Horizon Program Reproduction Agents*
(arXiv:2610.13395)](https://arxiv.org/abs/2610.13395): automatically synthesizing new
program-reproduction training tasks (Harbor task format) from real repositories.

The original pipeline is not open-sourced; this repo re-implements it strictly from the
paper's method description, using the released `ProgramGym-1648` task packages (MIT) as
the packaging-format reference. Every synthesized task is guaranteed **disjoint** from
both ProgramBench (200 instances) and the ProgramGym-1648 release.

## Pipeline (mapped to the paper)

| Stage | Paper section | This repo | Status |
|---|---|---|---|
| 1. Repository collection | Comprehensive Search → Metadata Validation → Commit Locking → Build Config Detection | `stage1_collect/collect_repos.py` (language × 6 star buckets, fork/archived filters, SPDX license check, exclusion pool, HEAD-commit pinning, build-config detection) | done |
| 2. Executable & sandbox generation | LLM agent writes `download.sh` (online deps) + `compile.sh` (offline build); ≤4-attempt feedback loop; static linter; sandbox freezing | `stage2_execgen/` (agent prompt + driver with linter / online phase / `docker --network none` offline verification) | done |
| 3. Dispatcher (task decomposition) | complexity ξ = clip[0,10](log₁₀ℓ + log₁₀(1+r) − 2); easy/medium/hard → 4/6/8 modules; decomposition agent assigns source paths + functional descriptions + interaction labels (Args/Config/Help/I/O/Subcommand/TUI); native test suites → extra test-reuse module | `stage3_dispatcher/` | in progress |
| 4. Test construction | k parallel module subagents; per round "repairs first, then new tests"; Feedback_Docs (summary / program analysis / validation); coverage instrumentation (Go `-cover`, gcov, `RUSTFLAGS=-C instrument-coverage`); validation = pass / double / dummy / weak-assert linter; coverage-guided targets ρ=0.1, B=300, partially-covered-first | `stage4_testgen/` | in progress |
| 5. Package & acceptance | merged-suite re-validation; Harbor task packaging; oracle ceiling check (reward = 1.0) | `stage5_package/` | in progress |

Paper values that are under-specified in the text, and the choices used here:

* test-construction round limit per module: **5**
* module functionality-coverage termination threshold: **80%** (paper reports median 81.63%)

## Requirements

* Linux x86_64 host (or a Modal VM sandbox) with **Docker** (build + `--network none` runs)
* Go toolchain tarball pinned per task (shipped inside each task package, same as the release)
* [`harbor >= 0.20.0`](https://github.com/harbor-framework/harbor) (`uv tool install 'harbor>=0.20.0'`) for acceptance
* `claude-code` CLI as the agent harness (the paper also uses a Claude Code harness)
* An Anthropic-compatible LLM endpoint. The paper built with DeepSeek-V4-Flash; this
  reproduction defaults to `glm-5.3` via a Zhipu endpoint — any compatible endpoint works:

```bash
export ANTHROPIC_AUTH_TOKEN=<your-api-key>
export ANTHROPIC_BASE_URL=https://open.bigmodel.cn/api/anthropic   # default
export ANTHROPIC_MODEL=glm-5.3                                     # default
```

## Usage

```bash
# 1. collect candidate repositories (validated + pinned + disjoint from both released sets)
python3 stage1_collect/collect_repos.py --candidates mvdan/sh itchyny/gojq ...

# 2. per repository: generate download.sh/compile.sh and verify (≤4 attempts)
cd workdir-for-repo && bash <repo>/stage2_execgen/driver.sh 4

# 3. dispatcher: complexity score + module decomposition            (stage3_dispatcher/)
# 4. test construction: parallel modules, coverage-guided rounds    (stage4_testgen/)
# 5. package + oracle acceptance: harbor run -a oracle -> reward 1.0 (stage5_package/)
```

## Task package format

Synthesized tasks are drop-in compatible with the released `ProgramGym-1648` harness
(Harbor task schema 1.3). See `template/` for the reference layout:
`task.toml`, `instruction.md` (agent-facing rules), `environment/` (Dockerfile +
pinned toolchain + docs-only workspace + execute-only reference binary),
`tests/` (verifier Dockerfile + evaluator + per-module test blobs),
`solution/solve.sh` (oracle ceiling check).

## Notes & honest deviations

* Static call-graph analysis (Joern/CodeQL in the paper) is replaced by dynamic
  coverage as the primary driver plus a light exported-entry listing for Go tasks;
  dynamic coverage follows the paper exactly.
* The 37-rule weak-assert linter is reconstructed from the rule semantics stated in
  the paper (reject sole exit-code checks, tautologies, <15-char substring
  assertions; require meaningful docstrings/CATCHES descriptions).
* Construction agents may read repository source (per the paper); only the
  reproduction agent is restricted to the black-box binary + docs.

## Credits

* Methodology: the ProgramGym paper (arXiv:2610.13395).
* Task packaging templates adapted from the MIT-licensed
  [ProgramGym-1648](https://huggingface.co/datasets/ProgramGym/programgym-1648) release.

## License

MIT

## Sandbox deployment (PPIO)

The pipeline also runs fully inside cloud sandboxes (tested on PPIO Sandbox):

- \ / \ — full stages 1-5 in one sandbox
- \ — stage-2 driver with GOPROXY=off offline verification
  (no docker) for sandbox hosts
- \ — oracle acceptance via the evaluator's native
  single-container mode (no docker)
- \ — packaging without harbor acceptance
- \ — 9-sandbox fleet manager (create/keepalive/status),
  8 vCPU / 8 GB custom template, PPIO egress proxy + China no_proxy split
- orchestrator \ / \ flags for constrained hosts
