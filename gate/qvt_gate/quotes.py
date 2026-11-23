"""`qvt-gate quotes`: byte-exact quote check after a fixed, documented normalisation."""
import re
import unicodedata
from pathlib import Path

from .common import load_registry, report

_HYPHEN_BREAK = re.compile(r"(\w)[-­]\s*\n\s*(\w)")
_WS = re.compile(r"\s+")
_SCRIPTS = ("LATIN", "GREEK", "CYRILLIC")


def normalize(text, form="NFC"):
    """Unicode form, rejoin words hyphenated across a line break, collapse whitespace.

    Case, punctuation and letters are left alone: the comparison stays exact."""
    text = unicodedata.normalize(form, text)
    text = _HYPHEN_BREAK.sub(r"\1\2", text)
    return _WS.sub(" ", text).strip()


def script_of(ch):
    if not ch.isalpha():
        return None
    name = unicodedata.name(ch, "")
    for s in _SCRIPTS:
        if name.startswith(s):
            return s
    return "OTHER"


def homoglyph_words(text):
    """Words that mix Latin with Greek or Cyrillic letters (look-alike substitution)."""
    bad = []
    for word in re.findall(r"\w+", text):
        scripts = {script_of(c) for c in word} - {None}
        if len(scripts) > 1 and "LATIN" in scripts:
            bad.append(word)
    return bad


def first_difference(quote, source):
    """Describe where the quote stops matching: its longest prefix present in the source."""
    lo, hi = 0, len(quote)
    while lo < hi:  # longest prefix that occurs in source
        mid = (lo + hi + 1) // 2
        if quote[:mid] in source:
            lo = mid
        else:
            hi = mid - 1
    at = source.find(quote[:lo]) if lo else -1
    ours = quote[max(0, lo - 12):lo + 18]
    theirs = source[at + max(0, lo - 12):at + lo + 18] if at >= 0 else ""
    return f"at char {lo} of the quote: ours {ours!r} vs source {theirs!r}"


def check_quote(quote, source, form="NFC"):
    """Return a list of problem strings (empty = exact match)."""
    q, s = normalize(quote, form), normalize(source, form)
    probs = []
    h = homoglyph_words(q)
    if h:
        probs.append(f"mixed-script word(s) in quote: {', '.join(sorted(set(h)))}")
    if q not in s:
        probs.append("not found: " + first_difference(q, s))
    return probs


def run(args):
    reg = load_registry(args.registry)
    root = Path(args.root) if args.root else Path(args.registry).resolve().parent
    form = "NFKC" if args.nfkc else "NFC"
    errs, checked = [], 0
    for key, c in reg["entries"].items():
        if c.get("grade") == "D" or not c.get("quote"):
            continue
        tf = c.get("text_file")
        if not tf:
            errs.append(f"entry {key}: has a quote but no text_file to check it against")
            continue
        path = root / tf
        if not path.is_file():
            errs.append(f"entry {key}: text_file {tf} does not exist")
            continue
        checked += 1
        for p in check_quote(c["quote"], path.read_text(encoding="utf-8"), form):
            errs.append(f"entry {key}: {p}")
    print(f"quotes: checked {checked} quote(s) with {form}")
    return report("quotes", errs)
