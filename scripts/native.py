#!/usr/bin/env python3
"""Manage Frenchia's native (Metal) inference services as launchd user agents.

    native.py up|down|restart|status [llm|tts ...]

Plists are generated into var/launchd/ (not ~/Library/LaunchAgents), so nothing starts at
login and only labels prefixed ca.amii.frenchia.* are ever touched. Stdlib only.
"""

from __future__ import annotations

import json
import os
import plistlib
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LAUNCHD_DIR = ROOT / "var" / "launchd"
LOG_DIR = ROOT / "var" / "log"
DOMAIN = f"gui/{os.getuid()}"
LABEL_PREFIX = "ca.amii.frenchia."


def read_env(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    if path.exists():
        for line in path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                env[key.strip()] = value.strip()
    return env


DOTENV = read_env(ROOT / ".env")


@dataclass
class Service:
    name: str
    program: list[str]
    env: dict[str, str]
    health_url: str
    startup_timeout_s: int

    @property
    def label(self) -> str:
        return LABEL_PREFIX + self.name

    @property
    def plist_path(self) -> Path:
        return LAUNCHD_DIR / f"{self.label}.plist"


def llm_service() -> Service:
    version = read_env(ROOT / "services/llm/ollama.version")["OLLAMA_VERSION"]
    env = read_env(ROOT / "services/llm/ollama.env")
    if models := DOTENV.get("OLLAMA_MODELS"):
        env["OLLAMA_MODELS"] = os.path.expanduser(models)
    host = env["OLLAMA_HOST"]
    return Service(
        name="llm",
        program=[str(ROOT / f".tools/ollama/{version}/ollama"), "serve"],
        env=env,
        health_url=f"http://{host}/api/version",
        startup_timeout_s=60,
    )


def tts_service() -> Service:
    env = {k: v for k, v in DOTENV.items() if k.startswith("TTS_")}
    env.setdefault("TTS_HOST", "127.0.0.1")
    env.setdefault("TTS_PORT", "8791")
    env["HF_HUB_OFFLINE"] = DOTENV.get("TTS_HF_HUB_OFFLINE", "1")
    return Service(
        name="tts",
        program=[str(ROOT / "services/tts/.venv/bin/python"), "-m", "frenchia_tts"],
        env=env,
        health_url=f"http://{env['TTS_HOST']}:{env['TTS_PORT']}/health",
        startup_timeout_s=120,
    )


SERVICES = {"llm": llm_service, "tts": tts_service}


def launchctl(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["launchctl", *args], capture_output=True, text=True)


def job_info(svc: Service) -> dict[str, str] | None:
    """Parse `launchctl print` for state and pid; None when the job is not loaded."""
    proc = launchctl("print", f"{DOMAIN}/{svc.label}")
    if proc.returncode != 0:
        return None
    info: dict[str, str] = {}
    for line in proc.stdout.splitlines():
        line = line.strip()
        for key in ("state", "pid", "last exit code"):
            if line.startswith(f"{key} = "):
                info.setdefault(key, line.split(" = ", 1)[1])
    return info


def write_plist(svc: Service) -> None:
    LAUNCHD_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log = str(LOG_DIR / f"{svc.name}.log")
    plist = {
        "Label": svc.label,
        "ProgramArguments": svc.program,
        "EnvironmentVariables": {"PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "HOME": str(Path.home()), **svc.env},
        "WorkingDirectory": str(ROOT),
        "StandardOutPath": log,
        "StandardErrorPath": log,
        "RunAtLoad": True,
        # Restart after crashes, but not after a clean exit.
        "KeepAlive": {"SuccessfulExit": False},
        "ThrottleInterval": 10,
        # Interactive: no background-QoS throttling of CPU/GPU work.
        "ProcessType": "Interactive",
    }
    with svc.plist_path.open("wb") as f:
        plistlib.dump(plist, f)


def healthy(svc: Service) -> bool:
    try:
        with urllib.request.urlopen(svc.health_url, timeout=3) as resp:
            return resp.status == 200
    except (urllib.error.URLError, TimeoutError, ConnectionError):
        return False


def wait_healthy(svc: Service) -> bool:
    deadline = time.monotonic() + svc.startup_timeout_s
    while time.monotonic() < deadline:
        if healthy(svc):
            return True
        info = job_info(svc)
        if info is None:
            return False
        time.sleep(1)
    return False


def up(svc: Service) -> bool:
    if not Path(svc.program[0]).exists():
        print(f"✗ {svc.name}: {svc.program[0]} not found; run 'just setup-native'")
        return False
    if job_info(svc) is None:
        write_plist(svc)
        proc = launchctl("bootstrap", DOMAIN, str(svc.plist_path))
        if proc.returncode != 0:
            print(f"✗ {svc.name}: launchctl bootstrap failed: {proc.stderr.strip()}")
            return False
    # RunAtLoad spawns can be deferred ("pended nondemand spawn = speculative"); start now.
    if job_info(svc).get("state") != "running":  # type: ignore[union-attr]
        launchctl("kickstart", f"{DOMAIN}/{svc.label}")
    ok = wait_healthy(svc)
    print(f"{'✓' if ok else '✗'} {svc.name}: {'healthy' if ok else 'not healthy'} ({svc.health_url}); log: var/log/{svc.name}.log")
    return ok


def down(svc: Service) -> None:
    if job_info(svc) is None:
        print(f"• {svc.name}: not running")
        return
    launchctl("bootout", f"{DOMAIN}/{svc.label}")
    # bootout returns before the process has exited; wait so a following start is clean.
    deadline = time.monotonic() + 15
    while job_info(svc) is not None and time.monotonic() < deadline:
        time.sleep(0.25)
    print(f"• {svc.name}: stopped" if job_info(svc) is None else f"⚠ {svc.name}: still stopping")


def restart(svc: Service) -> bool:
    if job_info(svc) is None:
        return up(svc)
    write_plist(svc)  # launchd re-reads the plist only on bootstrap
    down(svc)
    return up(svc)


def status(svc: Service) -> None:
    info = job_info(svc)
    if info is None:
        print(f"{svc.name:4s}  stopped")
        return
    detail = ""
    if svc.name == "llm" and healthy(svc):
        try:
            with urllib.request.urlopen(svc.health_url.replace("/api/version", "/api/ps"), timeout=3) as r:
                models = json.load(r).get("models", [])
            detail = ", ".join(f"{m['name']} loaded ({m['size'] / 1e9:.1f} GB)" for m in models) or "no model loaded"
        except (urllib.error.URLError, TimeoutError, ValueError):
            pass
    elif svc.name == "tts" and healthy(svc):
        try:
            with urllib.request.urlopen(svc.health_url, timeout=3) as r:
                h = json.load(r)
            detail = f"{h.get('model')}, metal {h.get('metal_active_mb', 0):.0f} MB"
        except (urllib.error.URLError, TimeoutError, ValueError):
            pass
    state = "healthy" if healthy(svc) else info.get("state", "?")
    print(f"{svc.name:4s}  {state:9s} pid {info.get('pid', '-'):>6s}  {detail}")


def main() -> int:
    if len(sys.argv) < 2 or sys.argv[1] not in {"up", "down", "restart", "status"}:
        print(__doc__)
        return 2
    action, names = sys.argv[1], sys.argv[2:] or list(SERVICES)
    unknown = [n for n in names if n not in SERVICES]
    if unknown:
        print(f"Unknown service(s): {', '.join(unknown)}; choose from {', '.join(SERVICES)}")
        return 2
    ok = True
    for name in names:
        svc = SERVICES[name]()
        if action == "up":
            ok &= up(svc)
        elif action == "down":
            down(svc)
        elif action == "restart":
            ok &= restart(svc)
        else:
            status(svc)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
