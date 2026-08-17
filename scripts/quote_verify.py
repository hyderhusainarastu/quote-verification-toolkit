#!/usr/bin/env python3
"""
quote_verify.py -- Verify that quoted excerpts actually appear in source texts.

Standalone CLI, Python standard library only (csv, re, difflib, unicodedata,
argparse, pathlib, glob, datetime). No third-party dependencies.

WHY THIS EXISTS
----------------
A naive substring check ("is quote in text?") fails constantly on real
extracted text, for reasons that have nothing to do with whether the quote
is actually accurate:

  - PDF extraction wraps lines, so a quote that reads as one sentence in the
    manuscript is split across a line break (or, worse, interleaved with an
    adjacent column) in the extracted .txt file.
  - Ligatures ("fi", "fl") and precomposed accented letters come out of PDF
    extractors as single Unicode code points that a naive normalizer either
    mangles or leaves mismatched against plain-ASCII manuscript prose.
  - Authors legitimately elide mid-quote ("the volunteers ... logged
    nearly four hundred hours restoring the archive"), which is never a
    contiguous substring of any faithful extraction.
  - A source may have several extracted-text variants of differing quality
    (a raw first pass, a column-aware rebuild, a de-hyphenated version), and
    checking the wrong one produces a false failure that looks exactly like
    a real citation defect.

This script treats a failed match as a hypothesis, not a verdict: it
normalizes aggressively, tries every witness file it is given, and reports
which witness and which reasoning produced the result, so a human reviewer
can tell a genuine citation problem from a tooling artifact at a glance.

VERDICTS
--------
  VERIFIED        Exact match against a witness, after normalization.
  FUZZY           A near-match at or above --fuzzy-threshold (default 0.95)
                   but not exact. Treat as a citation-integrity candidate.
  NOT_FOUND        No match, exact or fuzzy, against the best available
                   witness. Treat as a citation-integrity candidate.
  NOT_VERIFIABLE   The quote could not be meaningfully checked -- no witness
                   file was found, the witness is flagged as defective, or
                   the quote is too short (after normalization) for a
                   substring test to mean anything. This is NEVER a
                   citation-integrity finding by itself; it is a statement
                   about the available text, not about the citation.

VERIFIED and FUZZY are deliberately disjoint in this implementation: a
similarity of exactly 1.0 is VERIFIED, anything in [threshold, 1.0) is
FUZZY, and anything below threshold is NOT_FOUND. That is a stricter
reading than "fuzzy at or above threshold counts as VERIFIED" -- pick
whichever policy your project needs and adjust the rank assignment in
verify_quote() accordingly (look for the `if result["fuzzy_count"] == 0`
check, which is what draws the VERIFIED/FUZZY line); the default keeps
the two labels meaning different things so a report can be sorted by
them unambiguously.

USAGE
-----
  Single quote, single witness:
    quote_verify.py --quote "the exact words" --source-file paper.txt

  Single quote, multiple witnesses tried in preference order (first is
  most preferred; the script still tries the rest if an earlier witness
  does not produce VERIFIED, and reports which witness actually resolved
  the quote):
    quote_verify.py --quote "..." \\
        --source-file paper.clean.txt --source-file paper.txt

  Batch mode over a CSV of quotes:
    quote_verify.py --quotes-csv quotes.csv --source-file paper.txt \\
        --output results.csv

  Batch mode where each row names its own source (e.g. a slug column) and
  candidate witness files are discovered from a directory:
    quote_verify.py --quotes-csv quotes.csv \\
        --source-column source_slug --source-dir extracted_text/ \\
        --source-pattern "{key}.*" \\
        --prefer-token clean --prefer-token v2 --prefer-token sweep \\
        --output results.csv

  LaTeX manuscripts (protects \\ldots/\\dots elision markers before macro
  stripping, restores accent macros to base letters, strips \\footnote{}
  bodies and remaining macros):
    quote_verify.py --quotes-csv quotes.csv --source-file paper.txt \\
        --strip-latex --output results.csv

Run with --help for the full flag list.
"""

from __future__ import annotations

import argparse
import csv
import datetime
import difflib
import glob
import re
import sys
import unicodedata
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

# --------------------------------------------------------------------------
# Tunables that are also documented as CLI flags below; kept as constants
# only where they are structural rather than per-run choices.
# --------------------------------------------------------------------------

# A code point that cannot occur in ordinary prose or TeX source and is not
# alphanumeric, so it survives every later stripping step until we
# deliberately split on it. Used to protect "..." / U+2026 / \ldots / \dots
# elision markers from being silently deleted by macro-stripping or
# alphanumeric-only filtering before the elision test gets to run.
ELLIPSIS_SENTINEL = "\u0000"

ELLIPSIS_RE = re.compile(r"\\ldots(?:\\\s)?|\\dots(?:\\\s)?|\.\.\.|\u2026")

# SGML/HTML numeric and named entities occasionally left in extracted text
# layers (e.g. "&dquo;", "&amp;"). Stripped, not decoded, since we only
# need them gone for matching purposes.
SGML_ENTITY_RE = re.compile(r"&[a-zA-Z#0-9]+;")

# TeX accent macros: \"o , \'{e} , \^a , \`i , \~n , \=e , \.o -> restore to
# the bare base letter *before* generic macro stripping runs, otherwise a
# brace-argument stripper deletes the base letter along with the macro.
ACCENT_MACRO_RE = re.compile(r"\\[\"'^`~=.]\{?([a-zA-Z])\}?")

# \footnote{...} bodies (non-nested only -- see README for the limitation).
FOOTNOTE_RE = re.compile(r"\\footnote\{[^{}]*\}")

# Any remaining \macro, \macro[opt]{arg}{arg}... (non-nested arguments).
LATEX_MACRO_RE = re.compile(r"\\[a-zA-Z]+(\[[^\]]*\])?(\{[^{}]*\})*")

DEFAULT_FUZZY_THRESHOLD = 0.95
DEFAULT_MIN_SEGMENT_CHARS = 15
DEFAULT_CONTEXT_CHARS = 150
DEFAULT_EXCLUDE_PATTERN = r"reject"

CSV_FIELDNAMES = [
    "quote_id",
    "exact_quote",
    "verdict",
    "reason",
    "witness_file",
    "similarity",
    "segments_matched",
    "context",
    "checked_by",
    "checked_date",
]


# --------------------------------------------------------------------------
# Normalization
# --------------------------------------------------------------------------

def restore_accent_macros(text: str) -> str:
    return ACCENT_MACRO_RE.sub(r"\1", text)


def strip_latex_markup(text: str) -> str:
    """Strip \\footnote{} bodies, restore accent macros, strip remaining
    macros. Caller is responsible for protecting elision sentinels first."""
    text = FOOTNOTE_RE.sub("", text)
    text = restore_accent_macros(text)
    text = LATEX_MACRO_RE.sub("", text)
    return text


def preprocess(raw_text: str, strip_latex: bool = False) -> str:
    """NFKD-decompose and strip SGML entities. Returns text that still has
    original spacing/punctuation/case -- used to build a readable context
    snippet and as the base for the alphanumeric index map below.

    NFKD decomposition is not optional: PDF extractors emit ligatures
    ("\ufb01" for "fi") and precomposed accented letters ("\u00e9" for "e"
    with acute) as single code points. Deleting non-alphanumeric characters
    without decomposing first turns "\ufb01rst three" into "rstthree" (the
    ligature vanishes as one opaque code point instead of becoming "fi")
    and turns "caf\u00e9" into "caf" while a plain-ASCII "cafe" stays
    "cafe" -- two different normalized strings for the same word, and a
    false NOT_FOUND that has nothing to do with the citation.
    """
    text = unicodedata.normalize("NFKD", raw_text)
    text = SGML_ENTITY_RE.sub("", text)
    if strip_latex:
        text = strip_latex_markup(text)
    return text


def alnum_index_map(intermediate_text: str) -> Tuple[str, List[int]]:
    """Reduce to lowercase [a-z0-9] only, remembering, for every kept
    character, its index in intermediate_text -- so a match found in the
    stripped string can be mapped back to a human-readable context snippet
    in something close to the original text."""
    norm_chars: List[str] = []
    index_map: List[int] = []
    for i, ch in enumerate(intermediate_text):
        lch = ch.lower()
        if ("a" <= lch <= "z") or ("0" <= lch <= "9"):
            norm_chars.append(lch)
            index_map.append(i)
    return "".join(norm_chars), index_map


def split_on_ellipsis(quote: str, strip_latex: bool = False) -> List[str]:
    """Split an elided quotation into ordered segments.

    Order of operations matters and is the entire point of this function:
    the ellipsis markers are protected with a sentinel BEFORE any macro
    stripping happens. A generic LaTeX macro stripper (needed to remove
    \\footnote{...}, accent macros, etc.) matches \\ldots and \\dots as
    ordinary macros and deletes them -- if that runs first, an elided
    quotation like "the volunteers\\ldots\\ logged nearly four hundred
    hours" collapses to "the volunteers logged nearly four hundred hours"
    as one contiguous string, the split
    step has nothing left to split on, and a genuinely elided-but-correct
    quotation reports NOT_FOUND (tested as a single un-splittable span
    against text that is not contiguous anywhere, by construction).
    """
    quote = SGML_ENTITY_RE.sub("", unicodedata.normalize("NFKD", quote))
    quote = ELLIPSIS_RE.sub(ELLIPSIS_SENTINEL, quote)
    if strip_latex:
        quote = strip_latex_markup(quote)
    segments = [s for s in quote.split(ELLIPSIS_SENTINEL) if s.strip()]
    return segments if segments else [quote]


# --------------------------------------------------------------------------
# Matching
# --------------------------------------------------------------------------

def fuzzy_search(
    norm_segment: str, norm_text: str, search_from: int = 0, slack: int = 30
) -> Tuple[float, Optional[Tuple[int, int]]]:
    """Best-effort fuzzy match of norm_segment inside norm_text[search_from:].

    Stdlib-only approach: use difflib to find the longest common substring
    between segment and text, use that as an anchor, then slide a
    same-length window around the anchor and score each with
    SequenceMatcher.ratio(), keeping the best. This is not guaranteed to
    find the global optimum on adversarial input, but it is effective in
    practice for the kind of near-miss (a handful of character
    substitutions from OCR noise or a stray hyphen) this tool targets, and
    it stays within the standard library.
    """
    seglen = len(norm_segment)
    if seglen == 0:
        return 0.0, None
    haystack = norm_text[search_from:]
    if not haystack:
        return 0.0, None

    matcher = difflib.SequenceMatcher(None, haystack, norm_segment, autojunk=False)
    match = matcher.find_longest_match(0, len(haystack), 0, seglen)
    if match.size == 0:
        return 0.0, None

    anchor = match.a - match.b  # estimated start of segment within haystack
    best_ratio = 0.0
    best_window: Optional[Tuple[int, int]] = None
    for offset in range(-slack, slack + 1):
        start = anchor + offset
        if start < 0:
            continue
        end = start + seglen
        if end > len(haystack):
            continue
        window = haystack[start:end]
        ratio = difflib.SequenceMatcher(None, norm_segment, window, autojunk=False).ratio()
        if ratio > best_ratio:
            best_ratio = ratio
            best_window = (search_from + start, search_from + end)
    return best_ratio, best_window


def match_segments(
    segments_raw: Sequence[str],
    norm_text: str,
    fuzzy_threshold: float,
    min_segment_chars: int,
    strip_latex: bool,
) -> dict:
    """Match an ordered list of quote segments against normalized witness
    text, each segment required to occur after the end of the previous
    one. Returns a result dict with keys: ok, exact_count, fuzzy_count,
    total, spans (list of (start, end) in norm_text), too_short.
    """
    norm_segments = []
    for seg in segments_raw:
        intermediate = preprocess(seg, strip_latex=strip_latex)
        norm, _ = alnum_index_map(intermediate)
        norm_segments.append(norm)

    testable = [s for s in norm_segments if len(s) >= min_segment_chars]
    if not testable:
        return {"ok": False, "too_short": True, "spans": [], "exact_count": 0,
                "fuzzy_count": 0, "total": len(norm_segments)}

    cursor = 0
    spans: List[Tuple[int, int]] = []
    exact_count = 0
    fuzzy_count = 0
    for norm_seg in norm_segments:
        if not norm_seg:
            continue
        idx = norm_text.find(norm_seg, cursor)
        if idx != -1:
            spans.append((idx, idx + len(norm_seg)))
            cursor = idx + len(norm_seg)
            exact_count += 1
            continue
        ratio, window = fuzzy_search(norm_seg, norm_text, search_from=cursor)
        if window is not None and ratio >= fuzzy_threshold:
            spans.append(window)
            cursor = window[1]
            fuzzy_count += 1
            continue
        return {"ok": False, "too_short": False, "spans": spans,
                "exact_count": exact_count, "fuzzy_count": fuzzy_count,
                "total": len(norm_segments)}

    return {"ok": True, "too_short": False, "spans": spans,
            "exact_count": exact_count, "fuzzy_count": fuzzy_count,
            "total": len(norm_segments)}


# --------------------------------------------------------------------------
# Witness (source file) handling
# --------------------------------------------------------------------------

class Witness:
    """One candidate source-text file, preprocessed once and cached."""

    def __init__(self, path: Path, strip_latex: bool = False):
        self.path = path
        raw_text = path.read_text(encoding="utf-8", errors="replace")
        self.intermediate = preprocess(raw_text, strip_latex=strip_latex)
        self.norm_text, self.index_map = alnum_index_map(self.intermediate)

    def context(self, span: Tuple[int, int], context_chars: int) -> str:
        start_norm, end_norm = span
        if not self.index_map:
            return ""
        start_norm = max(0, min(start_norm, len(self.index_map) - 1))
        end_norm = max(0, min(end_norm - 1, len(self.index_map) - 1))
        orig_start = self.index_map[start_norm]
        orig_end = self.index_map[end_norm] + 1
        lo = max(0, orig_start - context_chars)
        hi = min(len(self.intermediate), orig_end + context_chars)
        snippet = self.intermediate[lo:hi]
        return " ".join(snippet.split())


_witness_cache: dict = {}


def load_witness(path: Path, strip_latex: bool) -> Witness:
    key = (str(path.resolve()), strip_latex)
    if key not in _witness_cache:
        _witness_cache[key] = Witness(path, strip_latex=strip_latex)
    return _witness_cache[key]


def rank_candidates(
    paths: Sequence[Path], prefer_tokens: Sequence[str], exclude_re: re.Pattern
) -> List[Path]:
    """Order candidate witness files by preference.

    Files matching exclude_re (default: filenames containing "reject",
    case-insensitive -- a rejected repair is worse than the stored
    original and must never be read) are dropped entirely. Remaining
    files are ranked by the first --prefer-token substring found in their
    filename (earlier tokens = more preferred), then alphabetically.
    Files matching no token sort after all tokened files, in the order
    they were given.

    --prefer-token has no built-in default: name your own project's
    quality markers (e.g. "clean", "v2", "sweep", "readingorder") on the
    command line. The ranking mechanism is generic; the vocabulary is
    yours.
    """
    kept = [p for p in paths if not exclude_re.search(p.name)]

    def rank_key(p: Path):
        name_lower = p.name.lower()
        for i, tok in enumerate(prefer_tokens):
            if tok and tok.lower() in name_lower:
                return (i, p.name)
        return (len(prefer_tokens), p.name)

    return sorted(kept, key=rank_key)


def resolve_candidates(
    explicit_files: Sequence[str],
    source_dir: Optional[str],
    source_pattern: str,
    key: Optional[str],
    prefer_tokens: Sequence[str],
    exclude_re: re.Pattern,
) -> List[Path]:
    """Build the ordered witness candidate list for one quote.

    explicit_files (--source-file, repeatable) are used verbatim, in the
    order given, and are never excluded or re-ranked -- an explicit list
    is a direct instruction. If source_dir/source_pattern/key are also
    given, matching files discovered there are appended, ranked by
    rank_candidates(), for cases where you want per-row auto-discovery
    (e.g. a CSV column naming a per-quote source key and a directory of
    "{key}.*" extraction variants) instead of listing every file by hand.
    """
    candidates: List[Path] = [Path(f) for f in explicit_files]
    if source_dir and key:
        pattern = str(Path(source_dir) / source_pattern.format(key=key))
        discovered = [Path(p) for p in glob.glob(pattern)]
        candidates.extend(rank_candidates(discovered, prefer_tokens, exclude_re))
    return candidates


# --------------------------------------------------------------------------
# Verification of one quote against an ordered witness list
# --------------------------------------------------------------------------

def verify_quote(
    quote: str,
    candidates: Sequence[Path],
    fuzzy_threshold: float,
    min_segment_chars: int,
    context_chars: int,
    strip_latex: bool,
    override_reason: Optional[str] = None,
) -> dict:
    """Try each candidate witness in order; keep the best result seen.

    Ranking of outcomes, best to worst: VERIFIED > FUZZY > NOT_FOUND.
    Every candidate is tried (not just until the first VERIFIED short-
    circuits), because an earlier-preferred witness that fails may simply
    be a worse extraction of the same source -- a later, lower-ranked
    witness matching is real evidence, not a reason to keep searching for
    something better. The witness that actually produced the result is
    always recorded, so a reviewer can see (and distrust, if warranted)
    which file a verdict rests on.
    """
    existing = [c for c in candidates if c.exists()]
    if not existing:
        return {
            "verdict": "NOT_VERIFIABLE",
            "reason": override_reason or "NO_SOURCE_FILE",
            "witness_file": "",
            "similarity": "",
            "segments_matched": "",
            "context": "",
        }

    segments_raw = split_on_ellipsis(quote, strip_latex=strip_latex)

    # TOO_SHORT is a property of the quote, not of any particular witness:
    # if every segment is below the minimum length, a substring test can
    # never mean anything, so there is no point trying every file.
    all_too_short = True
    for seg in segments_raw:
        intermediate = preprocess(seg, strip_latex=strip_latex)
        norm, _ = alnum_index_map(intermediate)
        if len(norm) >= min_segment_chars:
            all_too_short = False
            break
    if all_too_short:
        return {
            "verdict": "NOT_VERIFIABLE",
            "reason": "TOO_SHORT",
            "witness_file": "",
            "similarity": "",
            "segments_matched": f"0/{len(segments_raw)}",
            "context": "",
        }

    best = None  # (rank, result_dict) ; rank: 2=VERIFIED 1=FUZZY 0=NOT_FOUND

    for path in existing:
        witness = load_witness(path, strip_latex=strip_latex)
        result = match_segments(
            segments_raw, witness.norm_text, fuzzy_threshold, min_segment_chars, strip_latex
        )
        if not result["ok"]:
            rank = 0
            similarity = ""
            context = ""
        else:
            exact = result["exact_count"]
            total = result["total"]
            if result["fuzzy_count"] == 0:
                rank = 2  # VERIFIED
                similarity = "1.0"
            else:
                rank = 1  # FUZZY
                similarity = f">= {fuzzy_threshold}"
            spans = result["spans"]
            if spans:
                lo = min(s[0] for s in spans)
                hi = max(s[1] for s in spans)
                context = witness.context((lo, hi), context_chars)
            else:
                context = ""

        candidate_result = {
            "verdict": {2: "VERIFIED", 1: "FUZZY", 0: "NOT_FOUND"}[rank],
            "reason": "" if rank else (override_reason or ""),
            "witness_file": str(path),
            "similarity": similarity,
            "segments_matched": f"{result.get('exact_count', 0) + result.get('fuzzy_count', 0)}/{result.get('total', len(segments_raw))}",
            "context": context,
        }

        if best is None or rank > best[0]:
            best = (rank, candidate_result)
        if rank == 2:
            break  # VERIFIED against this witness; no witness can beat it

    assert best is not None
    rank, result = best
    if rank == 0 and override_reason:
        result = dict(result)
        result["verdict"] = "NOT_VERIFIABLE"
        result["reason"] = override_reason
    return result


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="quote_verify.py",
        description=(
            "Verify that quoted excerpts appear in their source texts, "
            "tolerant of PDF line-wraps, whitespace collapse, Unicode "
            "ligatures/accents, SGML entities, and mid-quote elision "
            "('...' / U+2026 / \\ldots / \\dots)."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    quote_group = p.add_mutually_exclusive_group(required=True)
    quote_group.add_argument(
        "--quote", help="A single quotation to verify (verbatim text)."
    )
    quote_group.add_argument(
        "--quotes-csv",
        help="CSV file of quotations to verify in batch. Must have a "
        "column with the quote text (see --quote-column).",
    )

    p.add_argument(
        "--source-file",
        action="append",
        default=[],
        metavar="PATH",
        help="A candidate witness text file. Repeatable; order given is "
        "preference order (most preferred first). Every quote is tried "
        "against every --source-file given, applied globally in single-"
        "quote mode or as the default candidate list in batch mode when "
        "--source-column is not used.",
    )
    p.add_argument(
        "--source-column",
        metavar="NAME",
        help="Batch mode only: CSV column whose value identifies which "
        "source each row belongs to (e.g. a slug or filename stem). "
        "Combined with --source-dir/--source-pattern to auto-discover "
        "per-row candidate witness files.",
    )
    p.add_argument(
        "--source-dir",
        metavar="DIR",
        help="Directory to search for per-row witness files when "
        "--source-column is set.",
    )
    p.add_argument(
        "--source-pattern",
        default="{key}.*",
        metavar="GLOB",
        help='Glob pattern for discovering witness files under --source-dir, '
        'with "{key}" substituted for the --source-column value. '
        'Default: "%(default)s".',
    )
    p.add_argument(
        "--prefer-token",
        action="append",
        default=[],
        metavar="TOKEN",
        help="Substring to look for in discovered witness filenames, used "
        "to rank multiple candidates for the same source. Repeatable; "
        "earlier tokens are preferred. E.g. --prefer-token clean "
        "--prefer-token v2 --prefer-token raw ranks a "
        "'paper.clean.txt' above 'paper.v2.txt' above 'paper.raw.txt'. "
        "Has no default -- define your own project's quality markers.",
    )
    p.add_argument(
        "--exclude-pattern",
        default=DEFAULT_EXCLUDE_PATTERN,
        metavar="REGEX",
        help="Case-insensitive regex; discovered witness filenames "
        "matching it are dropped entirely (never read), e.g. a rejected "
        "repair that is worse than the stored original. Applies only to "
        "files discovered via --source-dir, not to explicit --source-file "
        "paths. Default: %(default)r.",
    )

    p.add_argument(
        "--quote-column", default="exact_quote", metavar="NAME",
        help="Batch mode: CSV column holding the quote text. Default: %(default)s.",
    )
    p.add_argument(
        "--id-column", default="quote_id", metavar="NAME",
        help="Batch mode: CSV column holding a quote identifier, carried "
        "through to the output. Default: %(default)s.",
    )
    p.add_argument(
        "--override-column", default="override_reason", metavar="NAME",
        help="Batch mode: optional CSV column. When a row's cell in this "
        "column is non-empty and the quote does not VERIFY or FUZZY-match, "
        "the verdict is forced to NOT_VERIFIABLE with that cell's text as "
        "the reason, instead of NOT_FOUND -- for sources known in advance "
        "to have no sound extraction (e.g. a damaged scan). Default: "
        "%(default)s. If the column is absent from the CSV this is a "
        "no-op.",
    )

    p.add_argument(
        "--fuzzy-threshold", type=float, default=DEFAULT_FUZZY_THRESHOLD,
        metavar="RATIO",
        help="Similarity ratio (0-1) at or above which a non-exact match "
        "counts as FUZZY rather than NOT_FOUND. Default: %(default)s.",
    )
    p.add_argument(
        "--min-segment-chars", type=int, default=DEFAULT_MIN_SEGMENT_CHARS,
        metavar="N",
        help="A quote (or, for an elided quote, every one of its segments) "
        "shorter than this many normalized characters cannot be "
        "meaningfully substring-tested and is reported NOT_VERIFIABLE / "
        "TOO_SHORT instead of NOT_FOUND. Default: %(default)s.",
    )
    p.add_argument(
        "--context-chars", type=int, default=DEFAULT_CONTEXT_CHARS,
        metavar="N",
        help="Characters of surrounding text to include on each side of a "
        "match in the reported context snippet. Default: %(default)s.",
    )
    p.add_argument(
        "--strip-latex", action="store_true",
        help="Treat quotes and witness text as possibly containing LaTeX "
        "markup: protect elision markers before macro stripping, restore "
        "accent macros (\\\"o -> o) to base letters, strip \\footnote{} "
        "bodies and remaining \\macros{}. Off by default (plain text).",
    )

    p.add_argument(
        "--output", metavar="PATH",
        help="Write results as CSV to this path. In single-quote mode, "
        "writes one row. If omitted, results print to stdout.",
    )
    p.add_argument(
        "--checked-by", default="", metavar="NAME",
        help="Recorded in the checked_by output column. Optional.",
    )
    p.add_argument(
        "--quiet", action="store_true",
        help="Suppress the per-quote human-readable summary lines in "
        "batch mode; still prints the final tally.",
    )

    return p


def read_quotes_csv(path: str, quote_col: str, id_col: str, override_col: str):
    with open(path, "r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    if rows and quote_col not in rows[0]:
        raise SystemExit(
            f"error: column {quote_col!r} not found in {path}; "
            f"available columns: {list(rows[0].keys())}"
        )
    for row in rows:
        row.setdefault(id_col, "")
        row.setdefault(override_col, "")
    return rows


def format_result_line(quote_id: str, result: dict) -> str:
    bits = [result["verdict"]]
    if result.get("reason"):
        bits.append(f"({result['reason']})")
    if result.get("witness_file"):
        bits.append(f"witness={result['witness_file']}")
    return f"  {quote_id}: {' '.join(bits)}"


def write_csv(rows: List[dict], path: str) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDNAMES)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in CSV_FIELDNAMES})


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_arg_parser().parse_args(argv)
    exclude_re = re.compile(args.exclude_pattern, re.IGNORECASE)
    today = datetime.date.today().isoformat()

    output_rows: List[dict] = []

    if args.quote is not None:
        candidates = resolve_candidates(
            args.source_file, None, args.source_pattern, None,
            args.prefer_token, exclude_re,
        )
        if not candidates:
            print("error: --quote requires at least one --source-file", file=sys.stderr)
            return 2
        result = verify_quote(
            args.quote, candidates, args.fuzzy_threshold,
            args.min_segment_chars, args.context_chars, args.strip_latex,
        )
        row = {
            "quote_id": "",
            "exact_quote": args.quote,
            "checked_by": args.checked_by,
            "checked_date": today,
            **result,
        }
        output_rows.append(row)
        print(format_result_line("quote", result))
        if result.get("context"):
            print(f"    context: {result['context']}")

    else:
        rows_in = read_quotes_csv(
            args.quotes_csv, args.quote_column, args.id_column, args.override_column
        )
        tally = {"VERIFIED": 0, "FUZZY": 0, "NOT_FOUND": 0, "NOT_VERIFIABLE": 0}
        for row in rows_in:
            quote = row.get(args.quote_column, "")
            quote_id = row.get(args.id_column, "")
            override_reason = row.get(args.override_column) or None
            key = row.get(args.source_column) if args.source_column else None

            candidates = resolve_candidates(
                args.source_file, args.source_dir, args.source_pattern, key,
                args.prefer_token, exclude_re,
            )
            result = verify_quote(
                quote, candidates, args.fuzzy_threshold, args.min_segment_chars,
                args.context_chars, args.strip_latex, override_reason=override_reason,
            )
            tally[result["verdict"]] = tally.get(result["verdict"], 0) + 1
            output_rows.append({
                "quote_id": quote_id,
                "exact_quote": quote,
                "checked_by": args.checked_by,
                "checked_date": today,
                **result,
            })
            if not args.quiet:
                print(format_result_line(quote_id or "(no id)", result))

        total = len(rows_in)
        print(
            f"\n{tally['VERIFIED']}/{total} VERIFIED, {tally['FUZZY']} FUZZY, "
            f"{tally['NOT_FOUND']} NOT_FOUND, {tally['NOT_VERIFIABLE']} NOT_VERIFIABLE"
        )

    if args.output:
        write_csv(output_rows, args.output)
        print(f"\nwrote {len(output_rows)} row(s) to {args.output}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
