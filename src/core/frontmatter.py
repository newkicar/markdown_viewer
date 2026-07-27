"""
YAML front matter extraction for Markdown documents.

Front matter is the YAML block wrapped by '---' at the top of a document,
commonly used in Hugo/Jekyll/static site generators.
"""
from __future__ import annotations

from typing import Tuple

import yaml


def extract_frontmatter(content: str) -> Tuple[dict | None, str]:
    """
    Extract YAML front matter from the beginning of content.

    Returns (frontmatter_dict, remaining_body).
    If no valid front matter is found, returns (None, original_content).

    ponytail: Uses simple string scanning + yaml.safe_load rather than regex
    because front matter boundaries are structurally fixed (delimited by ---),
    but the inner YAML values are variable format and must be parsed semantically.
    """
    stripped = content.lstrip("\ufeff")  # strip BOM if present

    if not stripped.startswith("---"):
        return None, content

    # Find the closing '---' delimiter.
    # We scan line by line to avoid regex overuse on structural delimiters.
    lines = stripped.splitlines(keepends=True)
    if len(lines) < 3:
        return None, content

    # First line must be exactly '---\n' or '---\r\n'
    first_line = lines[0].rstrip("\r\n")
    if first_line != "---":
        return None, content

    # Search for closing delimiter on line 2+
    close_idx: int | None = None
    for i in range(1, len(lines)):
        if lines[i].rstrip("\r\n") == "---":
            close_idx = i
            break

    if close_idx is None:
        return None, content

    yaml_block = "".join(lines[1:close_idx])
    try:
        parsed = yaml.safe_load(yaml_block)
    except yaml.YAMLError:
        return None, content

    if isinstance(parsed, dict):
        body_lines = lines[close_idx + 1:]
        body = "".join(body_lines)
        # Strip leading blank lines after front matter
        body = body.lstrip("\n\r")
        return parsed, body

    return None, content
