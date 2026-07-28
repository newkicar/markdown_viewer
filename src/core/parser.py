"""
Markdown file analyzer: extracts titles, front matter, and renders HTML.

Central entry point for converting raw .md content into displayable structures.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

import mistletoe

from .frontmatter import extract_frontmatter


@dataclass(frozen=True)
class TitleInfo:
    level: int
    text: str
    line_no: int


class MarkdownAnalyzer:
    """Parse a Markdown document and expose its structure for rendering."""

    def __init__(self) -> None:
        self.frontmatter: dict | None = None
        self.titles: list[TitleInfo] = []
        self.html: str = ""
        self.body: str = ""  # markdown body without front matter

    def parse(self, content: str) -> None:
        """Parse content, extracting front matter and building renderable structures."""
        self.frontmatter, body = extract_frontmatter(content)
        self.body = body
        self.titles = self._extract_titles(body)
        self.html = self._render_html(body)

    @staticmethod
    def _extract_titles(content: str) -> list[TitleInfo]:
        """
        Extract heading levels from markdown source lines.

        ponytail: Uses line-by-line regex because heading syntax (ATX style)
        is a fixed-format dead data pattern — it does not change wording.
        Upgrade path: switch to mistletoe Token tree if we need to support
        headings inside blockquotes or other nested structures.
        """
        titles: list[TitleInfo] = []
        for line_no, line in enumerate(content.splitlines(), start=1):
            stripped = line.strip()
            match = re.match(r"^(#{1,6})\s+(.+)$", stripped)
            if match:
                level = len(match.group(1))
                text = match.group(2).strip()
                titles.append(TitleInfo(level=level, text=text, line_no=line_no))
        return titles

    @staticmethod
    def _render_html(content: str) -> str:
        """Render markdown body to HTML using mistletoe."""
        return mistletoe.markdown(content)
