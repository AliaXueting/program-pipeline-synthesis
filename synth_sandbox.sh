#!/bin/bash
# synth_sandbox.sh — FULL synthesis (stages 1-5) inside one PPIO sandbox.
# 8 vCPU / 8 GB template; stage-4 agents run in PARALLEL; stage-2 offline
# verification is GOPROXY=off (no docker); acceptance runs the task's own
# evaluator in single-container mode.
set -euo pipefail

REPO="$1"
MAIN_PKG="$2"
NAME="$(echo "$REPO" | sed 's|/|--|')"
TOOL="$(echo "$REPO" | sed 's|.*/||')"
W=/root/work
PIPE=/root/pg
export PATH=/usr/local/go/bin:/usr/local/bin:$PATH
export GOPROXY=https://goproxy.cn,direct
export ANTHROPIC_BASE_URL=https://open.bigmodel.cn/api/anthropic
export ANTHROPIC_AUTH_TOKEN="${ANTHROPIC_AUTH_TOKEN:?}"
export ANTHROPIC_MODEL=glm-5.3
export ANTHROPIC_SMALL_FAST_MODEL=glm-5.3-flash
export CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1 IS_SANDBOX=1

log() { echo "[$(date '+%m-%d %H:%M:%S')] $*" | tee -a "$W/synthesis.log"; }
norm() { sed -i 's/\r$//' "$@"; }
cd "$W"

# ---------------- stage 1: repo pinned ----------------
[ -d src ] || git clone -q --depth 1 "https://github.com/$REPO" src
COMMIT="$(cd src && git rev-parse --short=7 HEAD)"
COMMIT12="$(cd src && git rev-parse --short=12 HEAD)"
INSTANCE="$NAME.$COMMIT"
log "stage1: $REPO @ $COMMIT ($INSTANCE)"

# ---------------- stage 2: executable & sandbox generation ----------------
if [ ! -x execgen/executable ]; then
  mkdir -p execgen && cd execgen
  cp "$PIPE/stage2-instruction.md" INSTRUCTION.md
  cp "$PIPE/driver_sandbox.sh" driver.sh
  norm INSTRUCTION.md driver.sh && chmod +x driver.sh
  [ -e sh-src ] || ln -s "$W/src" sh-src
  PG_WS="$W/execgen" GO_PROXY="$GOPROXY" bash driver.sh 4 2>&1 | tee -a "$W/synthesis.log" \
    || true
  cd "$W"
fi
[ -x execgen/executable ] || { log "stage2 FAILED — see execgen/FEEDBACK.md"; exit 1; }
log "stage2: reference executable verified (GOPROXY=off contract)"

# instrumented reference (in-sandbox; 8GB is enough for the big builds)
if [ ! -x executable.cov ]; then
  (cd src && go build -cover -coverpkg=./... -o "$W/executable.cov" "$MAIN_PKG") \
    2>&1 | tail -2 | tee -a "$W/synthesis.log"
fi
[ -x executable.cov ] || { log "cov build FAILED"; exit 1; }
log "stage2b: instrumented reference built"

# ---------------- stage 3: dispatcher ----------------
if [ ! -f dispatch/plan.json ]; then
  python3 "$PIPE/stage3_dispatcher.py" --repo "$W/src" --ws "$W/dispatch" \
    2>&1 | tee -a "$W/synthesis.log"
fi
log "stage3: decomposition plan ready"

# ---------------- stage 4: parallel test construction ----------------
if [ ! -f "$W/.stage4_complete" ]; then
  python3 "$PIPE/stage4_orchestrator.py" \
    --plan "$W/dispatch/plan.json" \
    --repo "$W/src" \
    --ref "$W/execgen/executable" \
    --main-pkg "$MAIN_PKG" \
    --out "$W/stage4" \
    --format-example "$W/format-example" \
    --run-sh "$W/format-example/eval/run.sh" \
    --instruction "$PIPE/stage4-instruction.md" \
    --rounds 5 --threshold 0.8 --target-tests 60 --max-turns 120 \
    2>&1 | tee -a "$W/synthesis.log"
  touch "$W/.stage4_complete"
fi
log "stage4: test construction complete"

# ---------------- stage 5: package + in-sandbox acceptance ----------------
python3 "$PIPE/stage5_package_nodocker.py" \
  --task "$W/task/$INSTANCE" \
  --stage4-out "$W/stage4" \
  --plan "$W/dispatch/plan.json" \
  --commit "$COMMIT12" \
  --repo-name "$REPO" \
  --instance-id "$INSTANCE" \
  2>&1 | tee -a "$W/synthesis.log"

bash "$PIPE/accept_sandbox.sh" "$W/task/$INSTANCE" 2>&1 | tee -a "$W/synthesis.log" \
  && log "DONE-SANDBOX: $INSTANCE reward=1.0" \
  || log "ACCEPTANCE-NEEDS-FIX: $INSTANCE (run fix_and_reaccept flow)"

# package for retrieval
tar czf "$W/$INSTANCE-pkg.tar.gz" -C "$W/task" "$INSTANCE"
log "package ready: $W/$INSTANCE-pkg.tar.gz"
