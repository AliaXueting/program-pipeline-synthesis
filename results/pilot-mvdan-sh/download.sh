#!/usr/bin/env bash
# download.sh — ONLINE preparation for the offline mvdan/sh (shfmt) build.
#
# This file is SOURCED, not executed. It prepares every artifact the offline
# phase needs, entirely inside the workspace root (the directory holding this
# script), and exports the Go environment the offline build relies on:
#
#   sh-src/         the pinned mvdan/sh source tree, copied from the local
#                   checkout with its .git directory
#   .toolchain/     the Go release that sh-src/go.mod requires. The pinned
#                   toolchain under /usr/local/go is older than go.mod needs,
#                   so the required release is resolved through GOPROXY
#                   (automatic toolchain download) and copied into the
#                   workspace at a stable, writable path.
#   .gopath/        Go module cache, filled while the dependencies are vendored
#   .gocache/       Go build cache directory
#   .vcsbin/        a portable git (binary + dynamic loader + shared
#                   libraries) so the offline sandbox can stamp the pinned
#                   revision into ./executable
#   sh-src/vendor/  vendored dependency sources; the offline build compiles
#                   against these and reads nothing from the network
#
# Nothing here compiles the executable; compile.sh does that offline.
#
# PATHS: the exports at the end carry host paths. The offline phase runs this
# same workspace mounted at a different location, so compile.sh re-derives the
# path-valued variables from its own location; the variable NAMES below are
# the contract between the two phases.

set -u

fail() {
  printf 'download.sh: %s\n' "$*" >&2
  exit 1
}

WS="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)" || fail "cannot locate the workspace directory"
SRC="$WS/sh-src"
TOOLCHAIN_DIR="$WS/.toolchain"
GOPATH_DIR="$WS/.gopath"
CACHE_DIR="$WS/.gocache"
VCSBIN_DIR="$WS/.vcsbin"

# --- 1. pinned source tree --------------------------------------------------
SOURCE_ROOT="${SHFMT_SOURCE_DIR:-}"
if [ -z "$SOURCE_ROOT" ]; then
  for candidate in /root/pgsynth/sh-src /root/pgsynth/execgen/sh-src; do
    if [ -f "$candidate/go.mod" ] && [ -d "$candidate/cmd/shfmt" ]; then
      SOURCE_ROOT="$candidate"
      break
    fi
  done
fi
if [ -n "$SOURCE_ROOT" ] && [ -f "$SOURCE_ROOT/go.mod" ] && [ -d "$SOURCE_ROOT/cmd/shfmt" ]; then
  # pwd -P resolves symlinks, so the copy below can never become a link back
  # into the pinned checkout.
  SOURCE_ROOT="$(cd -- "$SOURCE_ROOT" && pwd -P)"
  if [ -d "$SRC" ] && [ "$(cd -- "$SRC" && pwd -P)" = "$SOURCE_ROOT" ]; then
    printf 'download.sh: source tree already in place at %s\n' "$SRC"
  else
    rm -rf "$SRC"
    cp -a "$SOURCE_ROOT" "$SRC" || fail "could not copy the pinned source tree from $SOURCE_ROOT"
    printf 'download.sh: copied the pinned source tree from %s\n' "$SOURCE_ROOT"
  fi
elif [ -f "$SRC/go.mod" ] && [ -d "$SRC/cmd/shfmt" ]; then
  printf 'download.sh: reusing the source tree already present at %s\n' "$SRC"
else
  fail "pinned mvdan/sh source tree not found; place it at $SRC or set SHFMT_SOURCE_DIR"
fi
[ -f "$SRC/go.mod" ] && [ -d "$SRC/cmd/shfmt" ] || fail "$SRC is not the mvdan/sh repository"

# --- 2. Go environment ------------------------------------------------------
# GOROOT from the calling environment would override the toolchain's own
# location, so drop it and let the go binaries locate themselves.
unset GOROOT
if ! command -v go >/dev/null; then
  export PATH="/usr/local/go/bin:$PATH"
fi
command -v go >/dev/null || fail "no Go toolchain found; expected /usr/local/go/bin/go"
export GOPROXY="${SHFMT_GO_PROXY:-https://goproxy.cn,direct}"
mkdir -p "$GOPATH_DIR" "$CACHE_DIR" || fail "cannot create the cache directories under $WS"
export GOPATH="$GOPATH_DIR"
export GOMODCACHE="$GOPATH_DIR/pkg/mod"
export GOCACHE="$CACHE_DIR"
export GOTOOLCHAIN=auto
export GOFLAGS=-mod=mod
export CGO_ENABLED=0
printf 'download.sh: proxy %s; pinned toolchain: %s\n' "$GOPROXY" "$(GOTOOLCHAIN=local go version)"

# --- 3. Go toolchain required by go.mod -------------------------------------
# With GOTOOLCHAIN=auto the go command fetches the release go.mod asks for
# through GOPROXY and runs it from the module cache. RESOLVED_GOROOT is where
# that release lives; it is copied to a stable, writable location so the
# offline phase never needs the module cache to find its compiler.
RESOLVED_GOROOT="$(go -C "$SRC" env GOROOT)" || fail "could not resolve the Go toolchain required by sh-src/go.mod"
printf 'download.sh: go.mod requires the toolchain at %s\n' "$RESOLVED_GOROOT"
rm -rf "$TOOLCHAIN_DIR"
cp -a "$RESOLVED_GOROOT" "$TOOLCHAIN_DIR" || fail "could not copy the resolved Go toolchain into the workspace"
chmod -R u+w "$TOOLCHAIN_DIR" || fail "could not set write permission on the prepared toolchain"
chmod +x "$TOOLCHAIN_DIR/bin/go" "$TOOLCHAIN_DIR/bin/gofmt" || fail "prepared toolchain binaries are not executable"
TOOLCHAIN_VERSION="$("$TOOLCHAIN_DIR/bin/go" version)" || fail "the prepared Go toolchain does not run"
printf 'download.sh: prepared %s\n' "$TOOLCHAIN_VERSION"

# --- 4. dependency sources --------------------------------------------------
# Vendoring records every dependency source the build needs under
# sh-src/vendor, so the offline build never consults a module proxy. It also
# fills the module cache under .gopath as a second offline copy.
go -C "$SRC" mod vendor || fail "could not vendor the module dependencies"

# Vendoring may append hashes for modules that go.sum did not cover yet. The
# offline build reads vendor/, never go.sum, so restore the committed file:
# VCS stamping below requires the tree to match the pinned commit exactly.
if [ -d "$SRC/.git" ] && [ -n "$(git -C "$SRC" status --porcelain -- go.sum)" ]; then
  git -C "$SRC" checkout -- go.sum || fail "could not restore go.sum to its committed state"
  printf 'download.sh: restored go.sum to its committed state\n'
fi
# The vendor directory is generated build input, not source; keep it out of
# VCS status for the same reason.
if [ -d "$SRC/.git" ]; then
  EXCLUDE_FILE="$SRC/.git/info/exclude"
  if [ ! -f "$EXCLUDE_FILE" ] || ! grep -qxF '/vendor/' "$EXCLUDE_FILE"; then
    printf '/vendor/\n' >> "$EXCLUDE_FILE"
  fi
fi
if [ -d "$SRC/.git" ]; then
  DIRTY="$(git -C "$SRC" status --porcelain)" || fail "git cannot inspect the prepared source tree"
  if [ -n "$DIRTY" ]; then
    printf 'download.sh: WARNING: the source tree differs from the pinned commit, so VCS stamping will be skipped:\n%s\n' "$DIRTY" >&2
  else
    printf 'download.sh: source tree matches the pinned commit %s\n' "$(git -C "$SRC" rev-parse --short HEAD)"
  fi
fi

# --- 5. portable git for offline VCS stamping --------------------------------
# go embeds the pinned revision in the binary when it can query the repo, but
# the offline sandbox has no git installed. A self-contained copy — the host
# binary plus the dynamic loader and shared libraries it needs, invoked
# through that loader so it also runs against an older libc — lets the
# offline build stamp the revision exactly as an online build would.
if command -v git >/dev/null; then
  HOST_GIT="$(command -v git)"
  rm -rf "$VCSBIN_DIR"
  mkdir -p "$VCSBIN_DIR" || fail "cannot create $VCSBIN_DIR"
  cp -a "$HOST_GIT" "$VCSBIN_DIR/git.bin" || fail "cannot copy $HOST_GIT"
  GIT_LOADER=""
  GIT_LIBS="$(ldd "$HOST_GIT" | awk '/=> \// {print $3} /^[[:space:]]*\// {print $1}')" || fail "ldd failed for $HOST_GIT"
  for lib in $GIT_LIBS; do
    # -L dereferences: the loader is usually reported as a symlink, and a
    # relocated symlink would dangle inside the offline sandbox.
    cp -aL "$lib" "$VCSBIN_DIR/" || fail "cannot copy $lib"
    case "$(basename -- "$lib")" in
      ld-*) GIT_LOADER="$(basename -- "$lib")" ;;
    esac
  done
  {
    printf '#!/bin/sh\n'
    printf 'd=$(dirname "$0")\n'
    printf 'd=$(cd "$d" && pwd)\n'
    if [ -n "$GIT_LOADER" ]; then
      printf 'exec "$d/%s" --library-path "$d" "$d/git.bin" "$@"\n' "$GIT_LOADER"
    else
      printf 'exec "$d/git.bin" "$@"\n'
    fi
  } > "$VCSBIN_DIR/git" || fail "cannot write the portable git launcher"
  chmod +x "$VCSBIN_DIR/git" "$VCSBIN_DIR/git.bin" || fail "cannot set the executable bit on the portable git"
  PORTABLE_GIT_VERSION="$("$VCSBIN_DIR/git" version)" || fail "the portable git does not run"
  printf 'download.sh: portable git ready (%s)\n' "$PORTABLE_GIT_VERSION"
else
  printf 'download.sh: WARNING: no git on this host, so VCS stamping cannot be prepared\n' >&2
fi

# --- 6. offline readiness check ----------------------------------------------
# Simulates the offline environment with the prepared assets only: vendored
# sources, the prepared toolchain, and every network access turned off. This
# loads the full package graph of cmd/shfmt without compiling anything.
if ! env GOPROXY=off GOSUMDB=off GOTOOLCHAIN=local GOROOT="$TOOLCHAIN_DIR" \
     GOFLAGS=-mod=vendor CGO_ENABLED=0 "$TOOLCHAIN_DIR/bin/go" -C "$SRC" list -deps ./cmd/shfmt \
     > "$WS/.offline-readiness.log"; then
  fail "offline readiness check failed: the vendored graph does not cover ./cmd/shfmt"
fi
printf 'download.sh: offline readiness check passed (%s packages)\n' "$(wc -l < "$WS/.offline-readiness.log")"

# --- 7. environment contract for the offline phase ---------------------------
export GOROOT="$TOOLCHAIN_DIR"
export GOPATH="$GOPATH_DIR"
export GOMODCACHE="$GOPATH_DIR/pkg/mod"
export GOCACHE="$CACHE_DIR"
export GOTOOLCHAIN=local
export GOFLAGS=-mod=vendor
export GOPROXY=off
export GOSUMDB=off
export CGO_ENABLED=0
export PATH="$TOOLCHAIN_DIR/bin:/usr/local/go/bin:/usr/bin:/bin"

unset WS SRC TOOLCHAIN_DIR GOPATH_DIR CACHE_DIR VCSBIN_DIR SOURCE_ROOT candidate \
      RESOLVED_GOROOT TOOLCHAIN_VERSION HOST_GIT GIT_LIBS GIT_LOADER EXCLUDE_FILE DIRTY \
      PORTABLE_GIT_VERSION lib
unset -f fail
printf 'download.sh: online preparation complete\n'
