#!/bin/bash
# synthesize_task.sh <owner/repo> <main_pkg>
#
# Full Program-Env pipeline for ONE repository -> an oracle-accepted Harbor
# task package (ProgramGym-1648 layout). Stages are idempotent; re-running
# the script resumes at the first incomplete stage.
#
#   stage 1  clone + pin commit
#   stage 2  executable & sandbox generation (agent + offline verification)
#   stage 3  dispatcher (complexity score, module decomposition)
#   stage 4  parallel test construction (coverage-guided, 4-check validation)
#   stage 5  task packaging + managed download.sh + oracle acceptance
set -euo pipefail

REPO="$1"
MAIN_PKG="$2"
NAME="$(echo "$REPO" | sed 's|/|--|')"
TOOL="$(echo "$REPO" | sed 's|.*/||')"

ROOT=/root/pgsynth
PIPE=$ROOT/program-pipeline-synthesis
VENV=$ROOT/venv
WS=$ROOT/tasks/$NAME
mkdir -p "$WS"
cd "$WS"

export ANTHROPIC_BASE_URL=https://open.bigmodel.cn/api/anthropic
export ANTHROPIC_AUTH_TOKEN="${ANTHROPIC_AUTH_TOKEN:?set the Zhipu API key}"
export ANTHROPIC_MODEL=glm-5.3
export ANTHROPIC_SMALL_FAST_MODEL=glm-5.3-flash
export GOPROXY=https://goproxy.cn,direct
export PATH=$VENV/bin:/usr/local/bin:$PATH

log() { echo "[$(date '+%m-%d %H:%M:%S')] $*" | tee -a "$WS/synthesis.log"; }

# strip any CRLF that sneaks in from Windows-side uploads (text files only)
norm() { sed -i 's/\r$//' "$@"; }

# ---------------- stage 1: clone + pin ----------------
if [ ! -d src ]; then
  git clone -q --depth 1 "https://github.com/$REPO" src
fi
COMMIT="$(cd src && git rev-parse --short=7 HEAD)"
COMMIT12="$(cd src && git rev-parse --short=12 HEAD)"
INSTANCE="$NAME.$COMMIT"
INST_ID="$(echo "$NAME" | sed 's|--|__|').$COMMIT"
TASK="$WS/task/$INSTANCE"
log "stage1: $REPO pinned at $COMMIT (instance $INSTANCE)"

# ---------------- stage 2: executable & sandbox generation ----------------
if [ ! -x execgen/executable ]; then
  mkdir -p execgen
  cd execgen
  [ -f INSTRUCTION.md ] || cp "$PIPE/stage2_execgen/INSTRUCTION.md" .
  cp "$PIPE/stage2_execgen/driver.sh" driver.sh
  norm INSTRUCTION.md driver.sh
  chmod +x driver.sh
  [ -e sh-src ] || ln -s "$WS/src" sh-src
  [ -f programgym-go.tar.gz ] || cp "$ROOT/template-dl/programgym-go.tar.gz" .
  PG_WS="$WS/execgen" GO_PROXY="$GOPROXY" bash driver.sh 4 2>&1 | tee -a "$WS/synthesis.log"
  cd "$WS"
fi
log "stage2: reference executable verified (offline contract)"

# ---------------- stage 3: dispatcher ----------------
if [ ! -f dispatch/plan.json ]; then
  "$VENV/bin/python" "$PIPE/stage3_dispatcher/dispatcher.py" \
    --repo "$WS/src" --ws "$WS/dispatch" 2>&1 | tee -a "$WS/synthesis.log"
fi
log "stage3: decomposition plan ready"

# ---------------- stage 4: parallel test construction ----------------
if [ ! -f "$WS/.stage4_complete" ]; then
  "$VENV/bin/python" "$PIPE/stage4_testgen/orchestrator.py" \
    --plan "$WS/dispatch/plan.json" \
    --repo "$WS/src" \
    --ref "$WS/execgen/executable" \
    --main-pkg "$MAIN_PKG" \
    --out "$WS/stage4" \
    --format-example "$ROOT/format-example" \
    --run-sh "$PIPE/template/blob_run_sh/eval/run.sh" \
    --rounds 5 --threshold 0.8 --target-tests 60 --max-turns 120 \
    2>&1 | tee -a "$WS/synthesis.log"
  touch "$WS/.stage4_complete"
fi
log "stage4: test construction complete"

# ---------------- stage 5a: task skeleton ----------------
mkdir -p "$TASK/environment" "$TASK/tests" "$TASK/solution"
if [ ! -f "$TASK/task.toml" ]; then
  # docs-only workspace
  (cd src && tar czf "$WS/workspace.tar.gz" README.md LICENSE docs man 2>/dev/null \
    || tar czf "$WS/workspace.tar.gz" README.md LICENSE 2>/dev/null \
    || tar czf "$WS/workspace.tar.gz" README.md)
  for side in environment tests; do
    cp "$WS/execgen/executable" "$TASK/$side/executable"
    cp "$ROOT/template-dl/programgym-go.tar.gz" "$TASK/$side/programgym-go.tar.gz"
    cp "$PIPE/template/$side/Dockerfile" "$TASK/$side/Dockerfile"
  done
  chmod 111 "$TASK/environment/executable"; chmod 755 "$TASK/tests/executable"
  mv "$WS/workspace.tar.gz" "$TASK/environment/workspace.tar.gz"
  cp "$TASK/environment/workspace.tar.gz" "$TASK/tests/workspace.tar.gz"
  cp "$PIPE/template/tests/test.sh" "$PIPE/template/tests/programgym_evaluator.py" "$TASK/tests/"
  cp "$PIPE/template/solution/solve.sh" "$TASK/solution/"
  cp "$PIPE/template/instruction.md" "$TASK/instruction.md"
  # task.toml from the accepted pilot's (proven layout), re-targeted
  cp "$ROOT/task/mvdan--sh.0e8ea6f/task.toml" "$TASK/task.toml"
  sed -i -e "s|mvdan--sh.0e8ea6f|$INSTANCE|g" \
         -e "s|mvdan__sh.0e8ea6f|$INST_ID|g" \
         -e "s|mvdan/sh|$REPO|g" \
         -e "s|0e8ea6fccd96|$COMMIT12|g" \
         -e "s|shfmt|$TOOL|g" "$TASK/task.toml"
  sed -i 's/^network_mode = "allowlist"/network_mode = "public"/' "$TASK/task.toml"
  sed -i '/^allowed_hosts = /d' "$TASK/task.toml"
  # China-network patches in Dockerfiles
  sed -i 's|GOPROXY="https://proxy.golang.org,direct"|GOPROXY="https://goproxy.cn,direct"|; s|PIP_INDEX_URL="https://pypi.org/simple"|PIP_INDEX_URL="https://pypi.tuna.tsinghua.edu.cn/simple"|' \
    "$TASK/environment/Dockerfile" "$TASK/tests/Dockerfile"
  # CRLF hygiene on every text file we just assembled
  norm "$TASK"/task.toml "$TASK"/instruction.md "$TASK"/solution/solve.sh \
       "$TASK"/environment/Dockerfile "$TASK"/tests/Dockerfile \
       "$TASK"/tests/test.sh "$TASK"/tests/programgym_evaluator.py
fi
# managed download.sh (deterministic, from go.mod metadata) — both contexts
if [ ! -f "$TASK/environment/download.sh" ]; then
  "$VENV/bin/python" "$ROOT/gen_download.py" "$WS/src/go.mod" "$TASK/environment/download.sh" "$NAME"
  cp "$TASK/environment/download.sh" "$TASK/tests/download.sh"
fi
log "stage5a: task skeleton assembled"

# ---------------- stage 5b: package + oracle acceptance ----------------
"$VENV/bin/python" "$PIPE/stage5_package/package.py" \
  --task "$TASK" \
  --stage4-out "$WS/stage4" \
  --plan "$WS/dispatch/plan.json" \
  --commit "$COMMIT12" \
  --repo-name "$REPO" \
  --instance-id "$INSTANCE" \
  --jobs "$WS/jobs" \
  --acceptance 2>&1 | tee -a "$WS/synthesis.log"
log "DONE: $INSTANCE (see oracle reward above)"
