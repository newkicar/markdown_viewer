"""Text search for Ctrl+F functionality."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SearchResult:
    line_no: int
    column: int
    text: str


def find_in_text(content: str, query: str, case_sensitive: bool = False) -> list[SearchResult]:
    """Find occurrences of query in content.

    Uses casefold() matching rather than regex because search input is variable-format.
    """
    if not query:
        return []

    lines = content.splitlines(keepends=True)
    results: list[SearchResult] = []
    search_query = query if case_sensitive else query.casefold()

    for i, line in enumerate(lines, start=1):
        text = line if case_sensitive else line.casefold()
        idx = 0
        while True:
            pos = text.find(search_query, idx)
            if pos == -1:
                break
            end = pos + len(query)
            display = line.rstrip("\r\n")[pos:end]
            results.append(SearchResult(line_no=i, column=pos + 1, text=display))
            idx = end

    return results
