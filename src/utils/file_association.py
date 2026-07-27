"""Windows file association management (.md/.yaml). HKCU only, reversible."""
from __future__ import annotations

import sys
import winreg
from pathlib import Path


EXTENSIONS = [".md", ".markdown", ".yaml", ".yml"]


def _get_exe_path() -> str:
    """Return the executable path for registry commands."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).as_posix().replace("\\", "/")
    # In dev mode, use python.exe so registry points to correct interpreter
    return Path(sys.executable).as_posix().replace("\\", "/")


def associate_files(exe_path: str | None = None) -> bool:
    """Register .md/.yaml files to open with this application (HKCU only)."""
    if exe_path is None:
        exe_path = _get_exe_path()

    command_template = f'"{exe_path}" "%1"'
    exe_name = Path(exe_path).name

    success = True
    for ext in EXTENSIONS:
        try:
            # Default double-click open command
            key = winreg.CreateKey(
                winreg.HKEY_CURRENT_USER,
                rf"Software\Classes\{ext}\shell\open\command",
            )
            winreg.SetValue(key, None, winreg.REG_SZ, command_template)  # type: ignore[arg-type]
            winreg.CloseKey(key)

            # Right-click "Open with" list
            winreg.CreateKey(
                winreg.HKEY_CURRENT_USER,
                rf"Software\Classes\{ext}\OpenWithList\{exe_name}",
            )
            winreg.CreateKey(
                winreg.HKEY_CURRENT_USER,
                rf"Software\Classes\{ext}\OpenWithProgids\markdown_viewer",
            )
        except OSError as e:
            print(f"Warning: failed to associate {ext}: {e}")
            success = False

    # Friendly display name for the executable in "Open with" lists
    try:
        app_key = winreg.CreateKey(
            winreg.HKEY_CURRENT_USER,
            rf"Software\Classes\Applications\{exe_name}",
        )
        winreg.SetValueEx(app_key, "FriendlyAppName", 0, winreg.REG_SZ, "Markdown Viewer")
        winreg.CloseKey(app_key)
    except OSError as e:
        print(f"Warning: failed to set friendly app name: {e}")
        success = False

    return success


def disassociate_files() -> bool:
    """Remove file associations set by this tool (HKCU only)."""
    for ext in EXTENSIONS:
        try:
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                rf"Software\Classes\{ext}",
                0,
                winreg.KEY_WRITE,
            ) as key:
                for sub in ("shell", "DefaultIcon", "openwith", "openwithlist"):
                    try:
                        winreg.DeleteKey(key, sub)
                    except FileNotFoundError:
                        pass
        except FileNotFoundError:
            pass
        except OSError:
            return False
    return True
