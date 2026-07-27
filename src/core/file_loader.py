"""Read files with fallback encodings."""
from __future__ import annotations

ENCODINGS = ["utf-8-sig", "utf-8", "gbk", "gb2312"]


def read_file(path: str) -> str:
    for enc in ENCODINGS:
        try:
            with open(path, "r", encoding=enc) as f:
                return f.read()
        except (UnicodeDecodeError, UnicodeError, FileNotFoundError):
            continue
    raise ValueError(f"Cannot decode {path} with any supported encoding")


def get_file_path_and_name(filepath: str) -> tuple[str, str]:
    """Split path into parent directory and filename."""
    from pathlib import PurePosixPath, PureWindowsPath
    if "\\" in filepath:
        p = PureWindowsPath(filepath)
    else:
        p = PurePosixPath(filepath)
    return str(p.parent), p.name
