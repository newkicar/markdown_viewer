"""Configuration persistence using JSON."""
from __future__ import annotations

import json
import sys
from pathlib import Path

DEFAULT_CONFIG = {
    "window": {"width": 1400, "height": 800, "splitter": [280, 700, 350], "maximized": False},
    "theme": "light",
    "font_size": 12,
    "auto_associate": False,
}


def _find_config_dir() -> Path:
    """Find .markdown_viewer directory by searching upward from exe location."""
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).parent
        # Search upward from exe_dir for .markdown_viewer
        current = exe_dir
        while current != current.parent:  # Stop at root
            candidate = current / ".markdown_viewer"
            if candidate.exists():
                return candidate
            current = current.parent
        # Fallback: exe_dir/.markdown_viewer
        return exe_dir / ".markdown_viewer"
    else:
        # Running from source: use project root (src/utils/config.py -> 3 levels up)
        base = Path(__file__).resolve().parent.parent.parent
        return base / ".markdown_viewer"


# Public module-level references (backward compatible)
CONFIG_DIR = _find_config_dir()
CONFIG_FILE = CONFIG_DIR / "config.json"
HISTORY_FILE = CONFIG_DIR / "history.json"


def load_config() -> dict:
    """Load config from disk; return defaults if missing or invalid."""
    if not CONFIG_FILE.exists():
        return DEFAULT_CONFIG.copy()
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return DEFAULT_CONFIG.copy()
        # Merge with defaults so new keys don't break old configs
        merged = DEFAULT_CONFIG.copy()
        merged.update(data)
        return merged
    except (json.JSONDecodeError, OSError):
        return DEFAULT_CONFIG.copy()


def save_config(config: dict) -> None:
    """Persist config to JSON file."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)


def load_history() -> list[dict]:
    """Load file history from JSON."""
    if not HISTORY_FILE.exists():
        return []
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return data
    except (json.JSONDecodeError, OSError):
        pass
    return []


def save_history(history: list[dict]) -> None:
    """Persist file history. Max 50 entries; newest first."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    # Remove duplicates by path, keep newest
    seen: set[str] = set()
    unique: list[dict] = []
    for item in history:
        path = item.get("path", "")
        if path and path not in seen:
            seen.add(path)
            unique.append(item)
    # Sort by time descending, keep max 50
    unique.sort(key=lambda x: x.get("time", ""), reverse=True)
    trimmed = unique[:50]
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(trimmed, f, ensure_ascii=False, indent=2)
