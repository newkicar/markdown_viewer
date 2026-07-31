"""
YAML front matter extraction for Markdown documents.

Front matter is the YAML block wrapped by '---' at the top of a document,
commonly used in Hugo/Jekyll/static site generators.
"""
from __future__ import annotations

import yaml


def _scan_frontmatter(content: str) -> tuple[dict | None, str, int]:
    """
    Scan content once and return (frontmatter_dict, body, body_start_offset).

    ``body_start_offset`` is the number of source lines consumed before the
    body begins (the front matter block including its closing '---', plus any
    blank lines that were stripped from the body's start).  Callers that keep
    the full content in view (the source editor) add this offset to
    body-relative line numbers to get content-relative ones.

    ponytail: Uses simple string scanning + yaml.safe_load rather than regex
    because front matter boundaries are structurally fixed (delimited by ---),
    but the inner YAML values are variable format and must be parsed semantically.
    """
    stripped = content.lstrip("\ufeff")  # strip BOM if present

    if not stripped.startswith("---"):
        return None, content, 0

    # Find the closing '---' delimiter.
    # We scan line by line to avoid regex overuse on structural delimiters.
    lines = stripped.splitlines(keepends=True)
    if len(lines) < 3:
        return None, content, 0

    # First line must be exactly '---\n' or '---\r\n'
    first_line = lines[0].rstrip("\r\n")
    if first_line != "---":
        return None, content, 0

    # Search for closing delimiter on line 2+
    close_idx: int | None = None
    for i in range(1, len(lines)):
        if lines[i].rstrip("\r\n") == "---":
            close_idx = i
            break

    if close_idx is None:
        return None, content, 0

    yaml_block = "".join(lines[1:close_idx])
    try:
        parsed = yaml.safe_load(yaml_block)
    except yaml.YAMLError:
        return None, content, 0

    if not isinstance(parsed, dict):
        return None, content, 0

    body_lines = lines[close_idx + 1:]
    # Count leading blank lines after the delimiter: they exist in the full
    # content but were stripped from the body, so they shift body line numbers.
    blank = 0
    while blank < len(body_lines) and body_lines[blank].strip() == "":
        blank += 1
    body = "".join(body_lines[blank:])
    return parsed, body, close_idx + 1 + blank


def extract_frontmatter(content: str) -> tuple[dict | None, str]:
    """
    Extract YAML front matter from the beginning of content.

    Returns (frontmatter_dict, remaining_body).
    If no valid front matter is found, returns (None, original_content).
    """
    fm, body, _ = _scan_frontmatter(content)
    return fm, body


def frontmatter_line_offset(content: str) -> int:
    """
    Number of source lines the front matter shifts the body down by.

    0 when the document has no (valid) front matter.  Used to convert
    body-relative heading line numbers into full-document line numbers.
    """
    _, _, offset = _scan_frontmatter(content)
    return offset
