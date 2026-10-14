#!/usr/bin/env python3
"""Stage 1 — Repository Collection (paper: Comprehensive Search → Metadata
Validation → Commit Locking → Build Config Detection).

Selects candidate repositories for environment synthesis:

* language in {C, C++, Go, Rust} (primary language per GitHub API)
* star count in the paper's six mutually exclusive buckets:
  [200,499] [500,999] [1000,1999] [2000,9999] [10000,49999] [50000,inf)
* not a fork, not archived
* non-empty SPDX license identifier
* a build config file present (Cargo.toml / go.mod / CMakeLists.txt / Makefile / meson.build)
* NOT already used by ProgramBench (200 instances) or ProgramGym-1648 (the
  released training set) — the disjointness guarantee
* pinned to the default-branch HEAD commit

Usage:
  python3 collect_repos.py --candidates owner1/repo1 owner2/repo2 ... [--out candidates.json]
  # or with a GitHub search query per language/star bucket:
  python3 collect_repos.py --search --github-token $GITHUB_TOKEN [--out candidates.json]

Output: JSON list of {repo, language, stars, license, default_branch, commit,
build_config}, one entry per accepted repository (single commit per repo, per the paper).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.parse
import urllib.request

STAR_BUCKETS = [(200, 499), (500, 999), (1000, 1999), (2000, 9999), (10000, 49999), (50000, None)]
LANGUAGES = ["C", "C++", "Go", "Rust"]
BUILD_CONFIGS = ["Cargo.toml", "go.mod", "CMakeLists.txt", "Makefile", "meson.build"]

EXCLUSION_DATASETS = [
    # owner/repo sets that new tasks must be disjoint from
    ("programbench/ProgramBench-Tests", "__"),
    ("ProgramGym/programgym-1648", "--"),
]


def http_json(url: str, headers: dict | None = None, timeout: int = 60):
    req = urllib.request.Request(url, headers={"User-Agent": "program-pipeline-synthesis", **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r), r.headers


def hf_list_dirs(repo_id: str) -> list[str]:
    dirs, url = [], f"https://huggingface.co/api/datasets/{repo_id}/tree/main?limit=1000"
    while url:
        data, headers = http_json(url)
        dirs += [i["path"] for i in data if i["type"] == "directory"]
        nxt = None
        for part in headers.get("Link", "").split(","):
            if 'rel="next"' in part:
                nxt = part.split(">")[0].lstrip("< ")
        url = nxt
    return dirs


def build_exclusion_pool() -> set[str]:
    """owner/repo pairs from both released sets (must not be reused)."""
    pool: set[str] = set()
    for ds, sep in EXCLUSION_DATASETS:
        for d in hf_list_dirs(ds):
            name = d.split(".")[0]
            parts = name.split(sep)
            if len(parts) == 2:
                pool.add(f"{parts[0]}/{parts[1]}".lower())
    return pool


def star_in_bucket(stars: int) -> bool:
    return any(lo <= stars <= (hi if hi else 10**9) for lo, hi in STAR_BUCKETS)


def github_repo_info(full: str, token: str | None) -> dict | None:
    headers = {"Authorization": f"token {token}"} if token else {}
    try:
        data, _ = http_json(f"https://api.github.com/repos/{full}", headers)
    except Exception as e:
        print(f"  !! {full}: {e}", file=sys.stderr)
        return None
    return data


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--candidates", nargs="*", default=[], help="owner/repo candidates to validate")
    ap.add_argument("--search", action="store_true", help="run the paper's language x star-bucket search")
    ap.add_argument("--github-token", default=os.environ.get("GITHUB_TOKEN"))
    ap.add_argument("--out", default="candidates.json")
    args = ap.parse_args()

    print("building exclusion pool (ProgramBench-200 + ProgramGym-1648)...")
    pool = build_exclusion_pool()
    print(f"  {len(pool)} owner/repos excluded")

    gh_headers = {"Authorization": f"token {args.github_token}"} if args.github_token else {}

    candidates = list(args.candidates)
    if args.search:
        for lang in LANGUAGES:
            for lo, hi in STAR_BUCKETS:
                q = f"language:{lang} stars:{lo}..{hi if hi else 999999} fork:false archived:false"
                url = ("https://api.github.com/search/repositories?per_page=100&q="
                       + urllib.parse.quote(q))
                try:
                    data, headers = http_json(url, gh_headers)
                    items = data.get("items", [])
                    print(f"search {lang} [{lo},{hi}]: {len(items)}")
                    candidates += [r["full_name"] for r in items]
                except Exception as e:
                    print(f"  !! search failed: {e}", file=sys.stderr)

    accepted = []
    for full in dict.fromkeys(candidates):  # dedup by full_name
        if full.lower() in pool:
            print(f"  skip (exclusion pool): {full}")
            continue
        info = github_repo_info(full, args.github_token)
        if info is None:
            continue
        lic = (info.get("license") or {}).get("spdx_id")
        problems = []
        if info.get("fork") or info.get("archived"):
            problems.append("fork/archived")
        if info.get("language") not in LANGUAGES:
            problems.append(f"language={info.get('language')}")
        if not star_in_bucket(info.get("stargazers_count", 0)):
            problems.append(f"stars={info.get('stargazers_count')} outside buckets")
        if not lic:
            problems.append("no SPDX license")
        if problems:
            print(f"  reject {full}: {', '.join(problems)}")
            continue
        # commit locking: default-branch HEAD
        branch = info["default_branch"]
        try:
            head, _ = http_json(f"https://api.github.com/repos/{full}/commits/{branch}", gh_headers)
            commit = head["sha"]
        except Exception as e:
            print(f"  !! {full}: commit lock failed: {e}", file=sys.stderr)
            continue
        # build config detection
        try:
            tree, _ = http_json(f"https://api.github.com/repos/{full}/git/trees/{commit}?recursive=1", gh_headers)
            files = {t["path"] for t in tree.get("tree", []) if t["type"] == "blob"}
            cfg = next((c for c in BUILD_CONFIGS if any(f.endswith(c) for f in files)), None)
        except Exception:
            cfg = None
        if not cfg:
            print(f"  reject {full}: no build config found")
            continue
        accepted.append({
            "repo": full,
            "language": info["language"],
            "stars": info["stargazers_count"],
            "license": lic,
            "default_branch": branch,
            "commit": commit,
            "build_config": cfg,
        })
        print(f"  accept {full} ({info['language']}, {info['stargazers_count']}*, {lic}, {commit[:7]})")

    with open(args.out, "w") as f:
        json.dump(accepted, f, indent=2)
    print(f"\n{len(accepted)} repositories accepted -> {args.out}")


if __name__ == "__main__":
    main()
