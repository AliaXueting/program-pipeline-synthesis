#!/bin/bash
# In-sandbox oracle acceptance (no Docker): run the task's own evaluator
# directly against the oracle solution — the programgym_evaluator.py was
# designed for exactly this single-container mode.
# Usage: accept_sandbox.sh <task-package-dir>   (prints reward, exit 0 iff 1.0)
set -euo pipefail
TASK="$(cd "$1" && pwd)"

rm -rf /accept && mkdir -p /accept/tests /accept/workspace /logs/verifier /logs/artifacts
cd /accept

# --- verifier side ---
cp "$TASK"/tests/programgym_evaluator.py "$TASK"/tests/programgym_task.json tests/
cp -r "$TASK"/tests/blobs tests/blobs
cp "$TASK"/environment/executable tests/executable.ref   # oracle binary (readable copy)

# --- oracle solution in /workspace (mirrors solution/solve.sh contract) ---
cd /accept/workspace
cp "$TASK"/environment/executable ./executable
chmod u+rw ./executable
python3 - <<'PY'
import base64
from pathlib import Path
Path(".programgym_oracle_reference").write_bytes(
    base64.b64encode(Path("executable").read_bytes()))
PY
chmod u-r ./executable
cat > compile.sh <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
if [ -f ./.programgym_oracle_reference ]; then
  python3 - <<'PY'
import base64
from pathlib import Path
Path("executable").write_bytes(
    base64.b64decode(Path(".programgym_oracle_reference").read_bytes()))
PY
fi
chmod +x ./executable
EOF
chmod +x compile.sh

# --- run the evaluator (single-container mode) ---
export PATH=/usr/local/go/bin:$PATH
export PROGRAMGYM_WORKSPACE=/accept/workspace
export PROGRAMGYM_METADATA=/accept/tests/programgym_task.json
export PROGRAMGYM_LOG_DIR=/logs/verifier
export PROGRAMGYM_XDIST_WORKERS=4
cd /accept
python3 tests/programgym_evaluator.py || true

REWARD=$(cat /logs/verifier/reward.txt 2>/dev/null || echo "missing")
echo "SANDBOX_ORACLE_REWARD=$REWARD"
[ "$REWARD" = "1.0" ]
