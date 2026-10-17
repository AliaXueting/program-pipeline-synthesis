#!/bin/bash
# sandbox_boot.sh — boot INSIDE a PPIO synth-hard-8c8g sandbox.
# Template already has: node20 + claude-code + pytest stack (root).
# This adds: go toolchain, format-example, task templates, repo clone.
# Args: $1 = owner/repo
set -euo pipefail
REPO="$1"
W=/root/work
PG=/root/pg
mkdir -p "$W" "$PG"
cd "$W"

echo "== boot: verify template deps =="
claude --version | head -1
python3 -c 'import pytest; print("pytest ok")'

echo "== boot: go toolchain (hf-mirror, direct) =="
if [ ! -x /usr/local/go/bin/go ]; then
  curl -sSL --max-time 600 -o /tmp/go.tgz \
    "https://hf-mirror.com/datasets/ProgramGym/programgym-1648/resolve/main/a8m--envsubst.795eb83/environment/programgym-go.tar.gz"
  tar -C /usr/local -xzf /tmp/go.tgz && rm /tmp/go.tgz
fi
/usr/local/go/bin/go version

echo "== boot: repo clone (via proxy) =="
if [ ! -d src ]; then
  git clone -q --depth 1 "https://github.com/$REPO" src
fi
(cd src && git rev-parse --short=7 HEAD)

echo "== boot: format-example =="
if [ ! -d format-example ]; then
  curl -sSL --max-time 300 -o fx.tar.gz \
    "https://hf-mirror.com/datasets/ProgramGym/programgym-1648/resolve/main/a8m--envsubst.795eb83/tests/blobs/tests/generated_module_01.tar.gz"
  mkdir -p format-example && tar xzf fx.tar.gz -C format-example && rm fx.tar.gz
fi
echo "BOOT_COMPLETE"
