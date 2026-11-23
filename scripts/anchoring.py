#!/usr/bin/env python3
"""Relocate a quotation inside changed text using {quote, prefix, suffix}.

An anchor stores the quote plus a little text on each side. After the source is
re-extracted or re-flowed, the offset moves but the surrounding words usually do
not, so the anchor can be found again without storing character positions.

Standard library only.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Sequence


def find_quote_offset(full_text: str, quote: str, prefix: str = "", suffix: str = "") -> Optional[int]:
    """Start offset of `quote` in `full_text`, or None.

    1. If prefix+quote+suffix occurs, return the quote's offset inside it.
    2. Otherwise take every occurrence of `quote` alone and score it by how many
       of prefix / suffix sit right next to it (0, 1 or 2). The highest score
       wins; ties go to the earliest occurrence.
    """
    if not quote:
        return None
    exact = full_text.find(prefix + quote + suffix)
    if exact != -1:
        return exact + len(prefix)

    occurrences: List[int] = []
    start = 0
    while True:
        at = full_text.find(quote, start)
        if at == -1:
            break
        occurrences.append(at)
        start = at + 1
    if not occurrences:
        return None
    if len(occurrences) == 1:
        return occurrences[0]

    best, best_score = occurrences[0], -1
    for occ in occurrences:
        before = full_text[max(0, occ - len(prefix)):occ]
        after = full_text[occ + len(quote):occ + len(quote) + len(suffix)]
        score = (before == prefix) + (after == suffix)
        if score > best_score:
            best, best_score = occ, score
    return best


def rebind_anchor(anchor: Dict[str, str], candidates: Sequence[Dict[str, str]]) -> Dict[str, object]:
    """Find an anchor across candidate blocks ({"block_id", "text"}).

    Exactly one block matching is a relocation. No match, or a match in several
    blocks, is reported as unanchored: the function never guesses between blocks.
    """
    hits = []
    for block in candidates:
        off = find_quote_offset(block["text"], anchor["quote"],
                                anchor.get("prefix", ""), anchor.get("suffix", ""))
        if off is not None:
            hits.append((block["block_id"], off))
    if len(hits) != 1:
        return {"state": "unanchored"}
    return {"state": "rebound", "block_id": hits[0][0], "offset": hits[0][1]}
