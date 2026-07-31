"""
Proportional scroll mapping for multi-pane viewers.

The middle (source) and right (preview) panes have different widths because
the user can drag the splitter, so the same markdown wraps to different line
counts in each pane and produces different content heights.  Pixel-based
scroll sync would therefore drift; ratio-based mapping (value / maximum) is
the only shared frame that respects each pane's own range.

Pure Python by design (no PyQt5) so the mapping can be unit-tested headlessly.
"""

from __future__ import annotations


def proportional_scroll_target(value: int, source_max: int, target_max: int) -> int:
    """Map a scrollbar value proportionally onto another scrollbar's range.

    ``value`` is the current position of the source scrollbar whose maximum
    is ``source_max``; the result is the position the target scrollbar (max
    ``target_max``) should take so both panes show the same fraction of their
    content.

    Returns 0 when either range is empty (a pane with no scrollable content),
    and clamps the result defensively in case ``value`` arrives outside
    ``[0, source_max]`` — which happens transiently while Qt lays out a
    document and shrinks a scrollbar's range.
    """
    if source_max <= 0 or target_max <= 0:
        return 0
    ratio = value / source_max
    return max(0, min(target_max, round(ratio * target_max)))
