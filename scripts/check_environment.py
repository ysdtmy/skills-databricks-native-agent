#!/usr/bin/env python3
"""Check local environment prerequisites for Databricks Agent Bricks development."""

from __future__ import annotations

import argparse
import json
import locale
import os
import platform
import re
import shutil
import socket
import subprocess
import sys


def check_python() -> bool:
    v = sys.version_info
    print(f"[*] Python version: {v.major}.{v.minor}.{v.micro}", end=" ")
    if (v.major, v.minor) >= (3, 11):
        print("[OK]")
        return True
    print("[FAIL] (Requires Python >= 3.11)")
    return False


def check_command(cmd: str, name: str, required: bool = True) -> bool:
    path = shutil.which(cmd)
    if path:
        print(f"[*] {name}: found at {path} [OK]")
        return True
    status = "[FAIL]" if required else "[WARN]"
    print(f"[*] {name}: not found {status}")
    return not required


def check_databricks_cli() -> tuple[bool, list[str]]:
    valid_profiles: list[str] = []
    if not shutil.which("databricks"):
        print("[*] Databricks CLI: not found [FAIL]")
        return False, valid_profiles

    print("[*] Databricks CLI: found [OK]")
    try:
        proc = subprocess.run(
            ["databricks", "auth", "profiles"],
            capture_output=True,
            text=True,
            check=False,
        )
        lines = proc.stdout.splitlines()
        for line in lines[1:]:  # skip header
            parts = line.split()
            if len(parts) >= 3 and parts[-1].upper() == "YES":
                valid_profiles.append(parts[0])

        if valid_profiles:
            print(f"[*] Databricks active profiles: {', '.join(valid_profiles)} [OK]")
            return True, valid_profiles
        else:
            print("[*] Databricks active profiles: None found [WARN] (Run 'databricks auth login')")
            return False, valid_profiles
    except Exception as exc:
        print(f"[*] Databricks CLI check error: {exc} [WARN]")
        return False, valid_profiles


def check_uv() -> bool:
    path = shutil.which("uv")
    if path:
        print(f"[*] uv (Fast package manager): found at {path} [OK]")
        return True
    print("[*] uv: not found [WARN] (Strongly recommended to avoid pip backtracking!)")
    print("    -> Install uv: curl -LsSf https://astral.sh/uv/install.sh | sh")
    return False


def check_agentbricks_package() -> bool:
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "pip", "show", "databricks-agentbricks"],
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode == 0:
            for line in proc.stdout.splitlines():
                if line.startswith("Version:"):
                    print(f"[*] databricks-agentbricks: {line.split(':', 1)[1].strip()} [OK]")
                    return True
        print("[*] databricks-agentbricks: not installed in current python [WARN]")
        print("    -> Install via uv (recommended):")
        print("       uv pip install \"databricks-agentbricks[langgraph]\"")
        print("    -> Or pip (warning: may encounter resolver backtracking):")
        print("       pip install \"databricks-agentbricks[langgraph]\"")
        return False
    except Exception:
        print("[*] databricks-agentbricks: check failed [WARN]")
        return False


def check_filesystem() -> bool:
    """Warn when the working directory is on WSL's Windows mount (slow `.venv`, no hardlinks)."""
    cwd = os.getcwd()
    if cwd.startswith("/mnt/") and "microsoft" in platform.uname().release.lower():
        print(f"[*] Working dir {cwd} is on the Windows mount (WSL) [WARN]")
        print("    -> `agentbricks dev` / `uv sync` build .venv with full file copies here (minutes).")
        print("    -> Prefer a project path on the WSL filesystem (~/...), or set UV_LINK_MODE=copy.")
        return False
    print("[*] Working dir filesystem: OK")
    return True


def port_in_use(port: int) -> bool:
    """Definitive, cross-platform (Windows/Linux/macOS) check using sockets only.

    A listener on the port accepts a loopback connection; if nothing accepts, a bind attempt on all
    interfaces is the second signal (covers listeners bound to a non-loopback address).
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        if s.connect_ex(("127.0.0.1", port)) == 0:
            return True
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            if os.name == "nt" and hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
                s.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            s.bind(("0.0.0.0", port))
            return False
        except OSError:
            return True


def _run(cmd: list[str]) -> str:
    """Run a command and decode its output. Windows tools emit the console code page (e.g. cp932 on
    Japanese Windows), not UTF-8, so never assume UTF-8."""
    try:
        raw = subprocess.run(cmd, capture_output=True, check=False, timeout=15).stdout
    except (OSError, subprocess.SubprocessError):
        return ""
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode(locale.getpreferredencoding(False), errors="replace")


def _owner_pid(port: int) -> int | None:
    """PID listening on ``port``: netstat on Windows, ss then lsof on Linux/macOS."""
    if os.name == "nt":
        for line in _run(["netstat", "-ano", "-p", "TCP"]).splitlines():
            cols = line.split()
            # state text can be localized, so also accept "remote address is ...:0" (= listening socket)
            listening = cols[3].upper() == "LISTENING" or cols[2].endswith(":0") if len(cols) >= 5 else False
            if listening and cols[1].rsplit(":", 1)[-1] == str(port):
                return int(cols[4])
        return None
    m = re.search(r"pid=(\d+)", _run(["ss", "-ltnpH", f"sport = :{port}"]))
    if m:
        return int(m.group(1))
    m = re.search(r"^p(\d+)", _run(["lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN", "-Fp"]), re.M)
    return int(m.group(1)) if m else None


def process_info(pid: int) -> dict[str, str]:
    """Best-effort description of a process: ``cmd``, ``exe`` and ``cwd`` ('' when the OS hides it)."""
    info = {"cmd": "", "exe": "", "cwd": ""}
    if os.name == "nt":
        ps = (
            f"Get-CimInstance Win32_Process -Filter 'ProcessId={pid}' | "
            "Select-Object ExecutablePath,CommandLine | ConvertTo-Json -Compress"
        )
        out = _run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps]).strip()
        try:
            d = json.loads(out) if out else {}
            info["exe"], info["cmd"] = d.get("ExecutablePath") or "", d.get("CommandLine") or ""
        except json.JSONDecodeError:
            pass
        return info
    try:
        info["cwd"] = os.readlink(f"/proc/{pid}/cwd")
        info["cmd"] = open(f"/proc/{pid}/cmdline", "rb").read().replace(b"\0", b" ").decode(errors="replace")
        return info
    except OSError:
        pass
    info["cmd"] = _run(["ps", "-o", "command=", "-p", str(pid)]).strip()  # macOS / no /proc
    m = re.search(r"^n(.+)$", _run(["lsof", "-a", "-p", str(pid), "-d", "cwd", "-Fn"]), re.M)
    info["cwd"] = m.group(1) if m else ""
    return info


def port_owner(port: int) -> dict[str, str] | None:
    """Return ``{"pid","cmd","exe","cwd"}`` of the listener, or None when the port is free.

    "In use" is always decided by :func:`port_in_use`; the owner details are extra context.
    """
    if not port_in_use(port):
        return None
    pid = _owner_pid(port)
    info = process_info(pid) if pid else {"cmd": "", "exe": "", "cwd": ""}
    info["pid"] = str(pid) if pid else "?"
    return info


def check_port(port: int) -> bool:
    owner = port_owner(port)
    if owner is None:
        print(f"[*] Port {port}: free [OK]")
        return True
    print(f"[*] Port {port}: IN USE by pid {owner['pid']} [WARN]")
    for key in ("cmd", "exe", "cwd"):
        if owner[key]:
            print(f"    {key}: {owner[key][:140]}")
    print("    -> A stale server here makes tests pass against the WRONG agent.")
    print("    -> Stop it (if it is yours) or run `agentbricks dev --app-port <free port>`.")
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, action="append", help="Local app port(s) to check (e.g. 8000)")
    args = parser.parse_args()

    print("=" * 60)
    print("Databricks Native Agent Development - Environment Check")
    print("=" * 60)

    py_ok = check_python()
    uv_ok = check_uv()
    db_ok, profiles = check_databricks_cli()
    ab_ok = check_agentbricks_package()
    check_filesystem()
    port_ok = all([check_port(p) for p in (args.port or [])])

    print("-" * 60)
    ready = py_ok and db_ok
    if ready:
        if not port_ok:
            print("Status: prerequisites OK, but a requested port is already in use (see above).")
            return 2
        print("Status: Core prerequisites satisfied!")
        if not ab_ok:
            print("Note: Run 'uv pip install \"databricks-agentbricks[langgraph]\"' when ready.")
        return 0
    else:
        print("Status: Missing prerequisites. Please resolve above items.")
        return 1



if __name__ == "__main__":
    sys.exit(main())
