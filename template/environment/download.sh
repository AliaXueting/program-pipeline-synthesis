#!/usr/bin/env bash
# PROGRAMGYM-MANAGED-GO-DOWNLOAD: v1
# Generated deterministically from repository module metadata; do not edit.
set -u
export GOTOOLCHAIN=auto
mkdir -p /workspace/.programgym_build_env/go-prefetch
cat > /workspace/.programgym_build_env/go-prefetch/go.mod <<'PROGRAMGYM_GO_MOD_EOF'
module github.com/a8m/envsubst

go 1.25.5
PROGRAMGYM_GO_MOD_EOF
PROGRAMGYM_INTERNAL_GO_PRIMARY_PROXY="${GOPROXY:-direct}"
PROGRAMGYM_INTERNAL_GO_FALLBACK_PROXY=""
case "$PROGRAMGYM_INTERNAL_GO_PRIMARY_PROXY" in
  *"|"*|*","*)
    PROGRAMGYM_INTERNAL_GO_FIRST_PROXY="${PROGRAMGYM_INTERNAL_GO_PRIMARY_PROXY%%[,|]*}"
    PROGRAMGYM_INTERNAL_GO_PROXY_REMAINDER="${PROGRAMGYM_INTERNAL_GO_PRIMARY_PROXY#*[,|]}"
    if [[ "$PROGRAMGYM_INTERNAL_GO_FIRST_PROXY" =~ [^[:space:]] ]] && [[ "$PROGRAMGYM_INTERNAL_GO_PROXY_REMAINDER" =~ [^[:space:]] ]]; then
      PROGRAMGYM_INTERNAL_GO_FALLBACK_PROXY="${PROGRAMGYM_GO_PUBLIC_FALLBACK_PROXY:-${PROGRAMGYM_INTERNAL_GO_PROXY_REMAINDER}}"
    fi
    ;;
esac
if ! [[ "$PROGRAMGYM_INTERNAL_GO_FALLBACK_PROXY" =~ [^[:space:]] ]]; then
  PROGRAMGYM_INTERNAL_GO_FALLBACK_PROXY=""
fi
cat > /workspace/.programgym_build_env/go-prefetch/.programgym_go_timeout_supervisor.py <<'PROGRAMGYM_GO_TIMEOUT_SUPERVISOR_EOF'
import os
import signal
import subprocess
import sys
import time

sentinel_path, timeout_text, grace_text, proxy, *command = sys.argv[1:]
if not command:
    raise SystemExit(125)
environment = os.environ.copy()
environment["GOPROXY"] = proxy
process = subprocess.Popen(command, env=environment, start_new_session=True)
try:
    returncode = process.wait(timeout=float(timeout_text))
except subprocess.TimeoutExpired:
    with open(sentinel_path, "w", encoding="utf-8") as sentinel:
        sentinel.write("expired\n")
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    deadline = time.monotonic() + float(grace_text)
    group_alive = True
    while time.monotonic() < deadline:
        process.poll()
        try:
            os.killpg(process.pid, 0)
        except ProcessLookupError:
            group_alive = False
            break
        time.sleep(0.05)
    if group_alive:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    process.wait()
    raise SystemExit(124)
if returncode < 0:
    returncode = 128 - returncode
raise SystemExit(returncode)
PROGRAMGYM_GO_TIMEOUT_SUPERVISOR_EOF
PROGRAMGYM_INTERNAL_GO_NEXUS_TIMEOUT_SECONDS="${PROGRAMGYM_GO_NEXUS_ATTEMPT_TIMEOUT_SECONDS:-90}"
if ! [[ "$PROGRAMGYM_INTERNAL_GO_NEXUS_TIMEOUT_SECONDS" =~ ^[1-9][0-9]*$ ]]; then
  printf '%s\n' "download.sh: invalid PROGRAMGYM_GO_NEXUS_ATTEMPT_TIMEOUT_SECONDS=${PROGRAMGYM_INTERNAL_GO_NEXUS_TIMEOUT_SECONDS}" >&2
  rm -f /workspace/.programgym_build_env/go-prefetch/.programgym_go_timeout_supervisor.py
  if [ "${BASH_SOURCE[0]}" != "$0" ]; then
    return 1
  else
    exit 1
  fi
fi
if ! command -v python3 >/dev/null 2>&1; then
  printf '%s\n' 'download.sh: python3 is required for bounded Nexus Go downloads' >&2
  rm -f /workspace/.programgym_build_env/go-prefetch/.programgym_go_timeout_supervisor.py
  if [ "${BASH_SOURCE[0]}" != "$0" ]; then
    return 1
  else
    exit 1
  fi
fi
_programgym_go_with_nexus_timeout() {
  local programgym_go_rc
  local programgym_go_timeout_sentinel
  if ! programgym_go_timeout_sentinel="$(mktemp "${TMPDIR:-/tmp}/programgym-go-timeout.XXXXXX")"; then
    return 1
  fi
  if python3 /workspace/.programgym_build_env/go-prefetch/.programgym_go_timeout_supervisor.py "$programgym_go_timeout_sentinel" "$PROGRAMGYM_INTERNAL_GO_NEXUS_TIMEOUT_SECONDS" "5" "$PROGRAMGYM_INTERNAL_GO_PRIMARY_PROXY" "$@"; then
    programgym_go_rc=0
  else
    programgym_go_rc=$?
  fi
  if [ ! -s "$programgym_go_timeout_sentinel" ]; then
    rm -f "$programgym_go_timeout_sentinel"
    return "$programgym_go_rc"
  fi
  rm -f "$programgym_go_timeout_sentinel"
  if [ -z "$PROGRAMGYM_INTERNAL_GO_FALLBACK_PROXY" ]; then
    printf '%s\n' "download.sh: primary Go request exceeded ${PROGRAMGYM_INTERNAL_GO_NEXUS_TIMEOUT_SECONDS}s; GOPROXY has no explicit non-empty fallback remainder" >&2
    return "$programgym_go_rc"
  fi
  printf '%s\n' "download.sh: Nexus-first Go request exceeded ${PROGRAMGYM_INTERNAL_GO_NEXUS_TIMEOUT_SECONDS}s; retrying with GOPROXY=${PROGRAMGYM_INTERNAL_GO_FALLBACK_PROXY}" >&2
  env GOPROXY="$PROGRAMGYM_INTERNAL_GO_FALLBACK_PROXY" "$@"
}
PROGRAMGYM_GO_BASE_GOROOT="$(GOTOOLCHAIN=local go env GOROOT)"
if ! PROGRAMGYM_GO_RESOLVED_GOROOT="$(cd /workspace/.programgym_build_env/go-prefetch && _programgym_go_with_nexus_timeout env GOTOOLCHAIN=auto go env GOROOT)"; then
  printf '%s\n' 'download.sh: Go toolchain resolution failed' >&2
  rm -f /workspace/.programgym_build_env/go-prefetch/.programgym_go_timeout_supervisor.py
  if [ "${BASH_SOURCE[0]}" != "$0" ]; then
    return 1
  else
    exit 1
  fi
fi
if [ "$PROGRAMGYM_GO_RESOLVED_GOROOT" != "$PROGRAMGYM_GO_BASE_GOROOT" ]; then
  PROGRAMGYM_GO_TOOLCHAIN_ROOT=/opt/programgym-go-toolchain
  mkdir -p "$PROGRAMGYM_GO_TOOLCHAIN_ROOT"
  cp -a "$PROGRAMGYM_GO_RESOLVED_GOROOT/." "$PROGRAMGYM_GO_TOOLCHAIN_ROOT/"
  export GOROOT="$PROGRAMGYM_GO_TOOLCHAIN_ROOT"
else
  export GOROOT="$PROGRAMGYM_GO_BASE_GOROOT"
fi
export PATH="$GOROOT/bin:$PATH"
export GOTOOLCHAIN=local
# No external Go module dependencies to prefetch.
rm -f /workspace/.programgym_build_env/go-prefetch/.programgym_go_timeout_supervisor.py
unset -f _programgym_go_with_nexus_timeout
unset PROGRAMGYM_INTERNAL_GO_PRIMARY_PROXY
unset PROGRAMGYM_INTERNAL_GO_FALLBACK_PROXY
unset PROGRAMGYM_INTERNAL_GO_FIRST_PROXY
unset PROGRAMGYM_INTERNAL_GO_PROXY_REMAINDER
unset PROGRAMGYM_INTERNAL_GO_NEXUS_TIMEOUT_SECONDS
