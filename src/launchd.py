"""Launchd integration for pycron-cli."""

import os
import plistlib
import subprocess
from pathlib import Path
from typing import Any

from src.cron_parse import ParsedCron, StartCalendarInterval, StartInterval
from src.paths import ensure_directories, get_label, get_log_path, get_plist_path, get_wrapper_path


class LaunchdError(Exception):
    pass


def create_wrapper(name: str, script: Path, workdir: Path, python: str = "/usr/bin/python3") -> Path:
    ensure_directories()
    wrapper = get_wrapper_path(name)
    log = get_log_path(name)

    esc = lambda s: str(s).replace("'", "'\\''")

    wrapper.write_text(f"""#!/bin/bash
set -euo pipefail

LOG='{esc(log)}'
echo "[$(date '+%Y-%m-%d %H:%M:%S')] START" >> "$LOG"

cd '{esc(workdir)}'
'{esc(python)}' -u '{esc(script.resolve())}' >> "$LOG" 2>&1
EXIT_CODE=$?

if [ $EXIT_CODE -eq 0 ]; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] END (success)" >> "$LOG"
else
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] END (error: $EXIT_CODE)" >> "$LOG"
fi

exit $EXIT_CODE
""")
    os.chmod(wrapper, 0o755)
    return wrapper


def create_plist(name: str, wrapper: Path, schedule: ParsedCron) -> Path:
    ensure_directories()
    plist_path = get_plist_path(name)
    log = get_log_path(name)

    data: dict[str, Any] = {
        "Label": get_label(name),
        "ProgramArguments": [str(wrapper)],
        "StandardOutPath": str(log),
        "StandardErrorPath": str(log),
        "RunAtLoad": False,
    }

    if isinstance(schedule, StartInterval):
        data["StartInterval"] = schedule.seconds
    elif isinstance(schedule, StartCalendarInterval):
        data["StartCalendarInterval"] = [
            {"Minute": e.minute, "Hour": e.hour} | ({"Weekday": e.weekday} if e.weekday is not None else {})
            for e in schedule.entries
        ]

    with open(plist_path, "wb") as f:
        plistlib.dump(data, f)
    return plist_path


def validate_plist(path: Path) -> None:
    result = subprocess.run(["plutil", "-lint", str(path)], capture_output=True, text=True)
    if result.returncode != 0:
        raise LaunchdError(f"Invalid plist: {result.stderr.strip()}")


def get_status(name: str) -> dict[str, Any]:
    label = get_label(name)
    plist = get_plist_path(name)
    wrapper = get_wrapper_path(name)

    status: dict[str, Any] = {
        "label": label,
        "loaded": False,
        "pid": None,
        "exit_status": None,
        "plist_exists": plist.exists(),
        "wrapper_exists": wrapper.exists(),
    }

    result = subprocess.run(["launchctl", "list"], capture_output=True, text=True)
    for line in result.stdout.splitlines():
        parts = line.split()
        if len(parts) >= 3 and parts[2] == label:
            status["loaded"] = True
            if parts[0] != "-":
                status["pid"] = int(parts[0])
            if parts[1] != "-":
                status["exit_status"] = int(parts[1])
            break
    return status


def load(name: str) -> None:
    plist = get_plist_path(name)
    if not plist.exists():
        raise LaunchdError(f"Plist not found: {plist}")
    result = subprocess.run(["launchctl", "load", str(plist)], capture_output=True, text=True)
    if result.returncode != 0 and "already loaded" not in result.stderr.lower():
        raise LaunchdError(f"Load failed: {result.stderr.strip()}")


def unload(name: str) -> None:
    plist = get_plist_path(name)
    if plist.exists():
        subprocess.run(["launchctl", "unload", str(plist)], capture_output=True)


def stop(name: str) -> None:
    subprocess.run(["launchctl", "stop", get_label(name)], capture_output=True)


def remove(name: str, keep_logs: bool = False) -> None:
    unload(name)
    plist = get_plist_path(name)
    wrapper = get_wrapper_path(name)
    log = get_log_path(name)

    if plist.exists():
        plist.unlink()
    if wrapper.exists():
        wrapper.unlink()
    if not keep_logs and log.exists():
        log.unlink()
