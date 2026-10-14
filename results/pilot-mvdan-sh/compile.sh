#!/usr/bin/env bash
# compile.sh — OFFLINE compilation of the mvdan/sh repository into ./executable.
#
# Runs in a sandbox with no network access and no package manager, against a
# workspace prepared by download.sh. Everything the build consumes is already
# inside the workspace:
#
#   .toolchain/  the Go release that sh-src/go.mod requires (GOTOOLCHAIN=local,
#                so no toolchain is ever fetched)
#   sh-src/      the pinned source tree, including sh-src/vendor/ with the
#                dependency sources (-mod=vendor, so no proxy is consulted)
#   .vcsbin/     a portable git, used to stamp the pinned revision into the
#                binary so ./executable --version reports the real version
#
# The environment inherited from download.sh carries host paths, and this
# sandbox sees the same workspace at a different location, so every
# path-valued Go variable is re-derived here from this script's location.

set -euo pipefail

WS="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
SRC="$WS/sh-src"
TOOLCHAIN_DIR="$WS/.toolchain"
VCSBIN_DIR="$WS/.vcsbin"
EXECUTABLE="$WS/executable"

# --- offline Go environment -------------------------------------------------
# GOPROXY=off and GOSUMDB=off guarantee that any attempt to reach the network
# fails immediately instead of hanging or silently fetching something.
export PATH="$TOOLCHAIN_DIR/bin:/usr/local/go/bin:/usr/bin:/bin"
export GOROOT="$TOOLCHAIN_DIR"
export GOPATH="$WS/.gopath"
export GOMODCACHE="$WS/.gopath/pkg/mod"
export GOCACHE="$WS/.gocache"
export GOTOOLCHAIN=local
export GOFLAGS=-mod=vendor
export GOPROXY=off
export GOSUMDB=off
export CGO_ENABLED=0

# --- prepared state ---------------------------------------------------------
if [ ! -x "$TOOLCHAIN_DIR/bin/go" ]; then
  printf 'compile.sh: %s/bin/go is missing; source download.sh first\n' "$TOOLCHAIN_DIR" >&2
  exit 1
fi
if [ ! -f "$SRC/go.mod" ] || [ ! -d "$SRC/cmd/shfmt" ]; then
  printf 'compile.sh: %s is not the mvdan/sh repository; source download.sh first\n' "$SRC" >&2
  exit 1
fi
if [ ! -f "$SRC/vendor/modules.txt" ]; then
  printf 'compile.sh: %s/vendor is missing; source download.sh first\n' "$SRC" >&2
  exit 1
fi

# --- VCS stamping -----------------------------------------------------------
# go embeds the pinned revision (and derives the version string from it) when
# it can query the repository. Stamping is enabled only when the query
# provably works and the tree matches the pinned commit exactly, so the binary
# never carries a misleading version; otherwise it falls back to "(devel)"
# with a loud warning.
BUILDVCS_ARGS=(-buildvcs=false)
VCS_NOTE="no .git directory in the source tree"
if [ -d "$SRC/.git" ]; then
  if [ -x "$VCSBIN_DIR/git" ]; then
    PATH="$VCSBIN_DIR:$PATH"
    export PATH
  fi
  if command -v git >/dev/null; then
    if ! TREE_STATE="$(git -C "$SRC" status --porcelain)"; then
      VCS_NOTE="git cannot query the repository"
    elif [ -n "$TREE_STATE" ]; then
      VCS_NOTE="the source tree differs from the pinned commit"
    elif ! PINNED_REV="$(git -C "$SRC" -c log.showsignature=false log -1 --format=%H)"; then
      VCS_NOTE="git cannot read the pinned revision"
    else
      BUILDVCS_ARGS=()
      VCS_NOTE="pinned revision $PINNED_REV"
    fi
  else
    VCS_NOTE="no git available in this sandbox"
  fi
fi
if [ "${#BUILDVCS_ARGS[@]}" -eq 0 ]; then
  printf 'compile.sh: VCS stamping enabled (%s)\n' "$VCS_NOTE"
else
  printf 'compile.sh: WARNING: VCS stamping disabled (%s); ./executable --version will report "(devel)"\n' "$VCS_NOTE" >&2
fi

# --- build ------------------------------------------------------------------
printf 'compile.sh: building cmd/shfmt with %s\n' "$("$TOOLCHAIN_DIR/bin/go" version)"
rm -f "$EXECUTABLE"
"$TOOLCHAIN_DIR/bin/go" -C "$SRC" build -mod=vendor -trimpath "${BUILDVCS_ARGS[@]}" -o "$EXECUTABLE" ./cmd/shfmt

# --- verify the result ------------------------------------------------------
if [ ! -f "$EXECUTABLE" ]; then
  printf 'compile.sh: the build did not produce %s\n' "$EXECUTABLE" >&2
  exit 1
fi
chmod +x "$EXECUTABLE"
ELF_MAGIC="$(head -c 4 "$EXECUTABLE" | od -An -tx1 | tr -d '[:space:]')"
if [ "$ELF_MAGIC" != "7f454c46" ]; then
  printf 'compile.sh: %s is not an ELF binary\n' "$EXECUTABLE" >&2
  exit 1
fi
VERSION_OUTPUT="$("$EXECUTABLE" --version)"
if [ -z "$VERSION_OUTPUT" ]; then
  printf 'compile.sh: %s --version produced no output\n' "$EXECUTABLE" >&2
  exit 1
fi
FORMAT_CHECK="$(printf 'echo   hi\n' | "$EXECUTABLE")"
if [ "$FORMAT_CHECK" != "echo hi" ]; then
  printf 'compile.sh: %s does not format shell scripts correctly\n' "$EXECUTABLE" >&2
  exit 1
fi
printf 'compile.sh: built %s\n' "$EXECUTABLE"
printf 'compile.sh: %s --version -> %s\n' "$EXECUTABLE" "$VERSION_OUTPUT"
printf 'compile.sh: smoke test -> %s\n' "$FORMAT_CHECK"
