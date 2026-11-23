"""Shared helpers: registry loading and the rules every subcommand uses."""
import json
import re
import sys
from pathlib import Path

GRADES = ("A", "B", "C", "D")
GRADE_MEANING = {
    "A": "seen on a page image",
    "B": "seen in a public full text",
    "C": "snippet only",
    "D": "not seen (a lead; never displayed)",
}
ENTRY_FIELDS = {
    "key", "grade", "source", "label", "locator", "screenshot", "via",
    "quote", "text_file", "url", "note",
}
KEY_RE = re.compile(r"^[a-z]+:[a-z0-9.-]+$")
DEFAULT_SOURCES = ["Book", "Journal", "Archive", "Web", "Report", "Other"]


def load_registry(path):
    p = Path(path)
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise SystemExit(f"error: cannot read registry {path}: {e}")
    if not isinstance(data, dict) or not isinstance(data.get("entries"), dict):
        raise SystemExit("error: registry must be an object with an 'entries' object")
    return data


def report(name, errs, warns=()):
    """Print findings, return the exit code (0 pass, 1 findings)."""
    for w in warns:
        print(f"{name}: warn: {w}")
    for e in errs:
        print(f"{name}: FAIL: {e}")
    if errs:
        print(f"{name}: {len(errs)} problem(s)")
        return 1
    print(f"{name}: ok")
    return 0


def err_exit(msg):
    print(f"error: {msg}", file=sys.stderr)
    return 2
