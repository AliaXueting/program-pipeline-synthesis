#!/bin/bash
# Stage 2 driver: Executable & Sandbox Generation outer feedback loop (paper: <=4 attempts)
set -u
# workspace = directory containing this driver (override with PG_WS)
WS="${PG_WS:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}"
FB=$WS/FEEDBACK.md
LOG=$WS/driver.log

mkdir -p "$WS"
cd "$WS"

write_feedback() {  # $1 status, $2 reason, $3 remediation
  cat > "$FB" <<EOF
# Verification Feedback (attempt $1)

## Status: $2

## Failure reason
$3

## Required remediation
$4

## Linter markers
$5
EOF
}

lint_scripts() {
  local v=()
  for s in download.sh compile.sh; do
    [ -f "$s" ] || { v+=("$s: MISSING"); continue; }
    grep -n '|| true' "$s" && v+=("$s: '|| true' masks failures (line above)")
    grep -n 'set +e' "$s" && v+=("$s: 'set +e' swallows failures (line above)")
    grep -n '2>/dev/null' "$s" && v+=("$s: '2>/dev/null' masks errors (line above)")
    grep -nE 'TODO|FIXME|placeholder' "$s" && v+=("$s: placeholder content (line above)")
  done
  grep -nE 'apt-get|apt install|pip3? install|npm install|go get|go mod download|cargo (fetch|add)|git clone|curl |wget ' compile.sh 2>/dev/null \
    && v+=("compile.sh: network/package-manager activity forbidden in offline phase (line above)")
  grep -nE 'go build|go install|go run|cargo build|make|cmake|gcc|g\+\+' download.sh 2>/dev/null \
    && v+=("download.sh: build commands forbidden in online phase (line above)")
  LINT_OUT=$(printf '%s\n' "${v[@]:-LINT_OK}")
  [ ${#v[@]} -eq 0 ]
}

verify() {
  local attempt=$1
  echo "=== driver: verify attempt $attempt ===" | tee -a "$LOG"
  rm -f executable
  [ -f download.sh ] && [ -f compile.sh ] || { write_feedback $attempt FAILED "download.sh or compile.sh missing" "Write both scripts per INSTRUCTION.md" "-"; return 1; }
  if ! lint_scripts; then
    write_feedback $attempt FAILED "Static linter violations" "Remove the flagged constructs; fail loudly instead of masking errors." "$LINT_OUT"
    return 1
  fi
  # ---- online phase (host, scratch build env inside workspace) ----
  rm -rf .buildenv && mkdir -p .buildenv/gopath .buildenv/gocache
  local ONLINE_ENV="PATH=/usr/local/go/bin:/usr/bin:/bin GOPATH=$WS/.buildenv/gopath GOMODCACHE=$WS/.buildenv/gopath/pkg/mod GOCACHE=$WS/.buildenv/gocache GOPROXY=${GO_PROXY:-https://proxy.golang.org,direct} GOFLAGS=-mod=mod HOME=$WS/.buildenv"
  if ! bash -c "set -a; source ./download.sh; set +a; env" > env.snapshot.raw 2> online.stderr < /dev/null; then
    write_feedback $attempt FAILED "download.sh (online phase) exited non-zero" "Fix the online preparation; see stderr below." "$(tail -5 online.stderr)"
    return 1
  fi
  # filter env snapshot (ignore host-specific vars, mirror template's rule)
  python3 - <<'PY'
import re
lines = open('env.snapshot.raw').read().splitlines()
ignored = {'PWD', 'OLDPWD', 'SHLVL', '_'}
out = []
for line in lines:
    if '=' not in line: continue
    k = line.split('=', 1)[0]
    if k in ignored or k.startswith('BASH_FUNC_') or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', k):
        continue
    out.append(line)
open('env.filtered', 'w').write('\n'.join(out) + '\n')
PY
  # ---- offline phase (docker, network disabled) ----
  if ! docker run --rm --network none -v "$WS":/work -w /work --env-file env.filtered \
       pgtoolchain:latest bash -c 'cd /work && bash compile.sh' > offline.stdout 2> offline.stderr; then
    write_feedback $attempt FAILED "compile.sh failed under the REAL offline contract (docker --network none)" "Stderr tail: $(tail -3 offline.stderr | tr '\n' ' ') — the offline phase must not need network. Fix compile.sh (prepare everything in download.sh instead)." "-"
    return 1
  fi
  [ -f executable ] || { write_feedback $attempt FAILED "compile.sh succeeded but ./executable missing" "compile.sh must produce ./executable at workspace root" "-"; return 1; }
  file executable | grep -q ELF || { write_feedback $attempt FAILED "./executable is not an ELF binary" "Build the real binary from source" "-"; return 1; }
  VER=$(docker run --rm --network none -v "$WS":/work -w /work pgtoolchain:latest ./executable --version 2>&1 | head -1)
  echo "version check: $VER" >> "$LOG"
  [ -n "$VER" ] || { write_feedback $attempt FAILED "./executable --version produced no output" "The executable must be runnable" "-"; return 1; }
  LDD=$(docker run --rm --network none -v "$WS":/work -w /work pgtoolchain:latest sh -c 'ldd ./executable 2>&1 || true' | head -2)
  echo "ldd: $LDD" >> "$LOG"
  write_feedback $attempt PASSED "all checks green" "-" "-"
  echo "=== STAGE2 PASSED (attempt $attempt) ===" | tee -a "$LOG"
  return 0
}

# ---- build the pinned-toolchain image once ----
if ! docker image inspect pgtoolchain:latest >/dev/null 2>&1; then
  docker build -t pgtoolchain:latest - <<'DOCKER'
FROM debian:bookworm-slim
COPY programgym-go.tar.gz /tmp/go.tgz
RUN tar -C /usr/local -xzf /tmp/go.tgz && rm /tmp/go.tgz && \
    echo 'export PATH=/usr/local/go/bin:$PATH' > /etc/profile.d/go.sh
ENV PATH=/usr/local/go/bin:/usr/bin:/bin
DOCKER
fi

ATTEMPTS=${1:-4}
for i in $(seq 1 "$ATTEMPTS"); do
  if [ "$i" -eq 1 ]; then
    PROMPT='Read INSTRUCTION.md in the current working directory and do the task it describes: write download.sh and compile.sh for the repository. Self-test before finishing.'
  else
    PROMPT="Attempt $i of 4. The previous attempt FAILED verification. Read FEEDBACK.md in the current directory for the failure diagnostics, then REVISE download.sh and/or compile.sh accordingly. Do not start from scratch unless necessary; fix the specific issues. Self-test again before finishing."
  fi
  echo "=== driver: agent attempt $i ===" | tee -a "$LOG"
  export ANTHROPIC_BASE_URL=https://open.bigmodel.cn/api/anthropic
  export ANTHROPIC_AUTH_TOKEN=f2b1208374a64bd6892461ac31a75de2.47Ij4BSjLmXszabJ
  export ANTHROPIC_MODEL=glm-5.3
  export ANTHROPIC_SMALL_FAST_MODEL=glm-5.3-flash
  export CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1 IS_SANDBOX=1
  claude --verbose --output-format=stream-json --max-turns 60 --permission-mode=bypassPermissions \
    --print "$PROMPT" > "attempt$i.log" 2>&1
  if verify "$i"; then exit 0; fi
done
echo "=== STAGE2 FAILED after $ATTEMPTS attempts ===" | tee -a "$LOG"
exit 1
