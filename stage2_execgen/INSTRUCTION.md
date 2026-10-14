# Task: Generate build scripts for a repository (Executable & Sandbox Generation)

You are a build engineer agent. Your job: produce TWO scripts that together build the
repository at `./sh-src` into a working `./executable`, following a strict
online/offline separation contract.

## The two scripts (write them at the workspace root)

### 1. `download.sh` — ONLINE dependency preparation
- Runs WITH network access, BEFORE compilation.
- Purpose: fetch/prepare everything the offline build will need (module downloads,
  vendored deps, prebuilt assets). Pin exact versions where possible.
- Contract:
  - It will be **sourced** (`source download.sh`), not executed. It must `export`
    every environment variable the offline build relies on.
  - It MUST NOT compile, build, or produce the executable. Preparation only.
  - It must fail loudly (non-zero) if a dependency cannot be prepared.

### 2. `compile.sh` — OFFLINE compilation
- Runs with **network completely disabled**, in a fresh shell where `download.sh`
  has been sourced beforehand.
- Purpose: compile the repository source into `./executable` at the workspace root.
- Contract:
  - MUST NOT use the network at all (no downloads, no package-manager installs,
    no `go get`/`cargo fetch`/`apt-get`).
  - MUST NOT install system packages.
  - Must work from a clean state: `rm -f executable && bash compile.sh` succeeds.
  - Must fail loudly on any build error. Never mask errors.

## Hard constraints (a linter will check these — violations fail the attempt)

- No `|| true`, no `set +e` to swallow failures, no error-masking redirections
  like `2>/dev/null` on build/critical commands.
- No placeholder content, TODOs, or stub implementations.
- `download.sh` must not contain build commands; `compile.sh` must not contain
  network/package-install commands.
- The produced `./executable` must run (`./executable --version` must work) and be
  a real build of the repository (not a copy of some prebuilt binary).

## Repository facts

- Repo: mvdan/sh (the `shfmt` shell-script formatter), at `./sh-src`, pinned commit.
- Language: Go. The pinned Go toolchain is at `/usr/local/go` (already on PATH or
  add it: `export PATH=/usr/local/go/bin:$PATH`). Use `GOTOOLCHAIN=local`.
- Main package: `./sh-src/cmd/shfmt`. The module has a `go.mod` with dependencies.
- The executable must be built from the repo source, at the workspace root as
  `./executable`.

## Workflow

1. Inspect `./sh-src` (go.mod, cmd/shfmt, build docs) to decide what the online
   phase must prepare and how the offline phase compiles.
2. Write `download.sh` and `compile.sh`.
3. Self-test locally (you have network here): `source download.sh` then
   `bash compile.sh` in a clean state, and `./executable --version`.
4. The driver will then verify the scripts under the REAL contract (including a
   network-disabled compile). If verification fails you will receive the
   diagnostics — revise the scripts accordingly. You have at most 4 attempts.
