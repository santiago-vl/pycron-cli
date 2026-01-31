"""Path configuration for pycron-cli."""

import getpass
from pathlib import Path

BASE_DIR = Path.home() / ".pycron"
WRAPPERS_DIR = BASE_DIR / "wrappers"
LOGS_DIR = BASE_DIR / "logs"
LAUNCH_AGENTS_DIR = Path.home() / "Library" / "LaunchAgents"


def get_username() -> str:
    return getpass.getuser()


def get_label(name: str) -> str:
    return f"com.{get_username()}.pycron.{name}"


def get_wrapper_path(name: str) -> Path:
    return WRAPPERS_DIR / f"{name}.sh"


def get_log_path(name: str) -> Path:
    return LOGS_DIR / f"{name}.log"


def get_plist_path(name: str) -> Path:
    return LAUNCH_AGENTS_DIR / f"{get_label(name)}.plist"


def ensure_directories() -> None:
    WRAPPERS_DIR.mkdir(parents=True, exist_ok=True)
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    LAUNCH_AGENTS_DIR.mkdir(parents=True, exist_ok=True)
