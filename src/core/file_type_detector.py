"""Detect whether a file is Markdown or YAML."""
from __future__ import annotations

from enum import Enum

MD_EXTS = {".md", ".markdown", ".mdx"}
YAML_EXTS = {".yaml", ".yml"}


class FileType(Enum):
    MARKDOWN = "markdown"
    YAML = "yaml"
    UNKNOWN = "unknown"


def detect_file(filepath: str) -> FileType:
    ext = "." + filepath.rsplit(".", 1)[-1].lower()
    if ext in MD_EXTS:
        return FileType.MARKDOWN
    if ext in YAML_EXTS:
        return FileType.YAML
    return FileType.UNKNOWN
