#!/usr/bin/env bash
# Pipeline-managed ProgramGym runner. Test agents must not modify this file.
set -euo pipefail
umask 0002

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BRANCH_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
export PROGRAMGYM_EXECUTABLE="${BRANCH_ROOT}/executable"
export PYTEST_ADDOPTS="${PYTEST_ADDOPTS:--n ${PROGRAMGYM_PYTEST_WORKERS:-16}}"
# The deadline covers fixture setup, test call and teardown. Thread mode also
# interrupts blocking pipe/socket reads; Docker reaps children after worker exit.
# programgym-pytest-timeout-guard: v1
export PROGRAMGYM_TEST_TIMEOUT_SECONDS="${PROGRAMGYM_TEST_TIMEOUT_SECONDS:-120}"
export PYTEST_TIMEOUT="$PROGRAMGYM_TEST_TIMEOUT_SECONDS"
export PYTEST_ADDOPTS="$PYTEST_ADDOPTS --timeout=$PROGRAMGYM_TEST_TIMEOUT_SECONDS --timeout-method=thread --max-worker-restart=0 -o timeout_func_only=false"
export PYTHONPYCACHEPREFIX="${PYTHONPYCACHEPREFIX:-/tmp/programgym-python-cache}"

programgym_restore_group_write() {
  chmod -R g+rwX "${BRANCH_ROOT}" 2>/dev/null || true
}
trap programgym_restore_group_write EXIT

cd "${BRANCH_ROOT}"
set +e
python3 -m pytest "eval/tests" \
  -o cache_dir=/tmp/programgym-pytest-cache \
  --junitxml="eval/results.xml"
status=$?
set -e

exit "${status}"
