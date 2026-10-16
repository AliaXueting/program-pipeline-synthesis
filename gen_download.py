#!/usr/bin/env python3
"""Generate the pipeline-MANAGED download.sh for a Go task package.

Reads the repository's go.mod and emits a prefetch-only online-preparation
script (module cache warm-up + toolchain auto-resolution). This mirrors the
released ProgramGym-1648 tasks, whose download.sh is "generated
deterministically from repository module metadata".

Usage: gen_download.py <go.mod> <out_download.sh> <module_name>
"""
from __future__ import annotations

import re
import sys


def parse_gomod(text: str):
    module = re.search(r"^module\s+(\S+)", text, re.M).group(1)
    m = re.search(r"^go\s+(\S+)", text, re.M)
    goversion = m.group(1) if m else "1.25"
    directs = []
    for block in re.findall(r"^require\s*\((.*?)\)", text, re.M | re.S):
        for line in block.splitlines():
            line = line.strip()
            if not line or line.startswith("//"):
                continue
            if "// indirect" in line:
                continue
            parts = line.split()
            if len(parts) >= 2 and parts[1].startswith("v"):
                directs.append((parts[0], parts[1]))
    return module, goversion, directs


TEMPLATE = '''#!/usr/bin/env bash
# download.sh — ONLINE dependency preparation for the offline build.
#
# This file is SOURCED, not executed. It warms the Go module cache with the
# dependency modules a {module} implementation needs and lets the Go toolchain
# auto-resolve the release required by the module. No source tree is
# required: the reproduction agent writes its own source and compiles it
# offline with compile.sh against this prepared cache.
#
# This file is pipeline-managed (generated deterministically from the
# repository's go.mod). Do not edit.

set -u
export GOTOOLCHAIN=auto
export GOFLAGS=-mod=mod

WS="$(cd -- "$(dirname -- "${{BASH_SOURCE[0]}}")" && pwd)" || return 1
BUILD_ENV="$WS/.programgym_build_env"
PREFETCH="$BUILD_ENV/go-prefetch"
mkdir -p "$PREFETCH"

export GOPATH="$BUILD_ENV/gopath"
export GOMODCACHE="$GOPATH/pkg/mod"
export GOCACHE="$BUILD_ENV/gocache"
mkdir -p "$GOMODCACHE" "$GOCACHE"

cat > "$PREFETCH/go.mod" <<'PROGRAMGYM_GO_MOD_EOF'
module {module}

go {goversion}
{requires}
PROGRAMGYM_GO_MOD_EOF

# Resolve the toolchain the scratch module asks for (auto-downloaded through
# GOPROXY into the module cache). Pin PATH to it for the offline phase.
if _RESOLVED_GOROOT="$(cd "$PREFETCH" && go env GOROOT 2>/dev/null)" && [ -n "$_RESOLVED_GOROOT" ]; then
  if [ "$_RESOLVED_GOROOT" != "$(GOTOOLCHAIN=local go env GOROOT 2>/dev/null)" ]; then
    export GOROOT="$_RESOLVED_GOROOT"
    export PATH="$GOROOT/bin:$PATH"
  fi
fi

# Warm the module cache with every dependency (and its transitive tree).
if ! (cd "$PREFETCH" && go mod download all); then
  printf 'download.sh: dependency prefetch failed\\n' >&2
  return 1
fi

printf 'download.sh: dependencies and toolchain prepared\\n'
'''


def main():
    gomod_path, out_path, module_hint = sys.argv[1], sys.argv[2], sys.argv[3]
    module, goversion, directs = parse_gomod(open(gomod_path).read())
    # prefer the go.mod's declared module path over the hint
    requires = ""
    if directs:
        requires = "\nrequire (\n" + "".join(f"\t{m} {v}\n" for m, v in directs) + ")\n"
    script = TEMPLATE.format(module=module, goversion=goversion, requires=requires)
    with open(out_path, "w", newline="\n") as f:
        f.write(script)
    print(f"generated {out_path}: module={module} go={goversion} deps={len(directs)}")


if __name__ == "__main__":
    main()
