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



