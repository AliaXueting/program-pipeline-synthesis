#!/usr/bin/env python3
"""PPIO sandbox fleet manager — 9 hard tasks, one 8C/8G sandbox each, FULL
synthesis (stages 1-5) inside every sandbox.

  py ppio_fleet.py launch     # create 9 sandboxes + upload + boot
  py ppio_fleet.py start      # start synthesis where boot is complete
  py ppio_fleet.py status     # per-sandbox stage markers
  py ppio_fleet.py keepalive  # extend all timeouts by ~1h
  py ppio_fleet.py get <name> <remote> <local>
  py ppio_fleet.py exec <name> "CMD"
  py ppio_fleet.py kill-all
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

os.environ.setdefault("PPIO_API_KEY", "sk_9tCfzpuQxCwYrA9kHApeRddVht3Y_5SARLvwvPBWVbw")
DOMAIN = "cn-beijing-1.sandbox.ppio.com"
TEMPLATE = "synth-hard-8c8g-v3"
STATE = Path(__file__).parent / ".ppio_fleet.json"
ANTHROPIC_KEY = "f2b1208374a64bd6892461ac31a75de2.47Ij4BSjLmXszabJ"

TASKS = [
    ("rclone/rclone", "."),
    ("trufflesecurity/trufflehog", "."),
    ("aquasecurity/trivy", "./cmd/trivy"),
    ("gohugoio/hugo", "."),
    ("anchore/syft", "./cmd/syft"),
    ("cli/cli", "./cmd/gh"),
    ("kopia/kopia", "."),
    ("helm/helm", "./cmd/helm"),
    ("restic/restic", "./cmd/restic"),
]

PROXY_ENVS = {
    "http_proxy": "http://10.1.80.46:1181",
    "https_proxy": "http://10.1.80.46:1181",
    "no_proxy": "open.bigmodel.cn,goproxy.cn,pypi.tuna.tsinghua.edu.cn,hf-mirror.com,.cn",
}


def _load():
    if STATE.exists():
        return json.loads(STATE.read_text())
    return {}


def _save(d):
    STATE.write_text(json.dumps(d, indent=1))


def _sdk():
    from ppio_sandbox.code_interpreter import Sandbox
    return Sandbox


def _attach(sid):
    return _sdk().connect(sid, domain=DOMAIN)


def _name(repo):
    return repo.replace("/", "--")


def _run(sb, cmd, timeout=900):
    from ppio_sandbox.core.exceptions import CommandExitException
    try:
        r = sb.commands.run(cmd, timeout=timeout)
        return r.exit_code, r.stdout or "", r.stderr or ""
    except CommandExitException as e:
        return (getattr(e, "exit_code", 1), getattr(e, "stdout", "") or "",
                (getattr(e, "stderr", "") or "") + f"\n[exit {getattr(e, 'exit_code', 1)}]")
    except Exception as e:
        return 1, "", str(e)


def _lf(p: Path) -> bytes:
    """Read a local file and normalize CRLF -> LF (for shell scripts)."""
    return p.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")


UPLOADS = [
    ("sandbox_boot.sh", "/root/sandbox_boot.sh"),
    ("synth_sandbox.sh", "/root/synth.sh"),
    ("driver_sandbox.sh", "/root/pg/driver_sandbox.sh"),
    ("accept_sandbox.sh", "/root/pg/accept_sandbox.sh"),
    ("gen_download.py", "/root/pg/gen_download.py"),
    ("stage5_package_nodocker.py", "/root/pg/stage5_package_nodocker.py"),
    ("repo-recovered/stage2_execgen/INSTRUCTION.md", "/root/pg/stage2-instruction.md"),
    ("repo-recovered/stage3_dispatcher/INSTRUCTION.md", "/root/pg/stage3-instruction.md"),
    ("repo-recovered/stage3_dispatcher/dispatcher.py", "/root/pg/stage3_dispatcher.py"),
    ("repo-recovered/stage4_testgen/INSTRUCTION.md", "/root/pg/stage4-instruction.md"),
    ("repo-recovered/stage4_testgen/orchestrator.py", "/root/pg/stage4_orchestrator.py"),
    ("repo-recovered/stage4_testgen/linter.py", "/root/pg/stage4_linter.py"),
    ("repo-recovered/stage4_testgen/coverage.py", "/root/pg/stage4_coverage.py"),
    ("repo-recovered/stage4_testgen/validator.py", "/root/pg/stage4_validator.py"),
]


def cmd_launch():
    S = _sdk()
    state = _load()
    here = Path(__file__).parent
    for repo, main in TASKS:
        name = _name(repo)
        if name in state:
            print(f"[fleet] {name}: exists ({state[name]})")
            continue
        sb = S.create(timeout=3500, domain=DOMAIN, template=TEMPLATE, envs=PROXY_ENVS)
        state[name] = sb.sandbox_id
        _save(state)
        print(f"[fleet] created {name}: {sb.sandbox_id}")
        for local, remote in UPLOADS:
            sb.files.write(remote, _lf(here / local))
        _run(sb, "chmod +x /root/sandbox_boot.sh /root/synth.sh /root/pg/*.sh; mkdir -p /root/pg /root/work")
        _run(sb, f"nohup bash /root/sandbox_boot.sh {repo} > /root/boot.log 2>&1 & echo boot-started")
        print(f"[fleet] {name}: boot launched")
        time.sleep(20)


def cmd_start():
    state = _load()
    for repo, main in TASKS:
        name = _name(repo)
        sid = state.get(name)
        if not sid:
            continue
        try:
            sb = _attach(sid)
        except Exception as e:
            print(f"{name}: attach failed {str(e)[:60]}")
            continue
        rc, out, _ = _run(sb, "grep -c BOOT_COMPLETE /root/boot.log 2>/dev/null || echo 0; "
                              "tail -1 /root/boot.log 2>/dev/null | head -c 70", timeout=60)
        lines = out.strip().splitlines()
        booted = lines and lines[0] == "1"
        if not booted:
            print(f"{name}: booting ({lines[1] if len(lines) > 1 else '?'})")
            continue
        rc, out2, _ = _run(sb, "test -f /root/.synth_started && echo yes || echo no", timeout=30)
        if "yes" in out2:
            print(f"{name}: synthesis running")
            continue
        _run(sb, f"nohup env ANTHROPIC_AUTH_TOKEN={ANTHROPIC_KEY} "
                 f"bash /root/synth.sh {repo} {main} > /root/synth-run.log 2>&1 & echo started",
             timeout=60)
        _run(sb, "touch /root/.synth_started", timeout=30)
        print(f"{name}: synthesis STARTED")


def cmd_status():
    state = _load()
    for repo, _ in TASKS:
        name = _name(repo)
        sid = state.get(name)
        if not sid:
            print(f"{name}: not created")
            continue
        try:
            sb = _attach(sid)
            rc, out, _ = _run(sb,
                "pgrep -cf 'synth.sh|claude|orchestrator' ; "
                "for m in execgen/executable dispatch/plan.json .stage4_complete; do "
                "test -e /root/work/$m && echo -n 'ok ' || echo -n '-- '; done; echo; "
                "grep -oE 'SANDBOX_ORACLE_REWARD=[0-9.]+' /root/work/synthesis.log 2>/dev/null | tail -1; "
                "tail -1 /root/work/synthesis.log 2>/dev/null | head -c 60", timeout=90)
            print(f"{name}: {' | '.join(out.strip().splitlines())}")
        except Exception as e:
            print(f"{name}: attach failed {str(e)[:60]}")


def cmd_keepalive():
    state = _load()
    for name, sid in state.items():
        try:
            sb = _attach(sid)
            sb.set_timeout(3500)
            print(f"{name}: extended")
        except Exception as e:
            print(f"{name}: keepalive failed {str(e)[:60]}")


def cmd_kill_all():
    state = _load()
    for name, sid in state.items():
        try:
            _attach(sid).kill()
            print(f"{name}: killed")
        except Exception as e:
            print(f"{name}: kill failed {str(e)[:60]}")
    _save({})


def cmd_get(name, remote, local):
    sb = _attach(_load()[name])
    data = sb.files.read(remote)
    if isinstance(data, str):
        data = data.encode()
    Path(local).parent.mkdir(parents=True, exist_ok=True)
    Path(local).write_bytes(data)
    print(f"[get] {name}:{remote} -> {local} ({len(data)} bytes)")


def cmd_exec(name, cmd, timeout=900):
    sb = _attach(_load()[name])
    rc, out, err = _run(sb, cmd, timeout=timeout)
    print(out)
    if err:
        print("--- stderr ---", file=sys.stderr)
        print(err, file=sys.stderr)
    print(f"[exitcode] {rc}")


if __name__ == "__main__":
    action = sys.argv[1] if len(sys.argv) > 1 else ""
    if action == "launch":
        cmd_launch()
    elif action == "start":
        cmd_start()
    elif action == "status":
        cmd_status()
    elif action == "keepalive":
        cmd_keepalive()
    elif action == "kill-all":
        cmd_kill_all()
    elif action == "get":
        cmd_get(sys.argv[2], sys.argv[3], sys.argv[4])
    elif action == "exec":
        cmd_exec(sys.argv[2], sys.argv[3])
    else:
        print(__doc__)
        sys.exit(1)
