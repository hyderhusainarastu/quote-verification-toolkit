"""`qvt-gate cites`: no ungraded or unseen citation reaches a built document."""
import re
from pathlib import Path

from .common import (ENTRY_FIELDS, DEFAULT_SOURCES, GRADES, KEY_RE,
                     load_registry, report)

DEFAULT_PATTERN = r"\[\[cite:([^\]\s]+)\]\]"


def check_entries(reg, root):
    errs = []
    sources = reg.get("allowed_sources", DEFAULT_SOURCES)
    for key, c in reg["entries"].items():
        w = f"entry {key}"
        if not isinstance(c, dict):
            errs.append(f"{w}: must be an object")
            continue
        unknown = sorted(set(c) - ENTRY_FIELDS)
        if unknown:
            errs.append(f"{w}: unknown field(s) {', '.join(unknown)}")
        if c.get("key") != key:
            errs.append(f"{w}: 'key' field {c.get('key')!r} differs from its object key")
        if not KEY_RE.match(key):
            errs.append(f"{w}: key format must be <source>:<slug> (lowercase, digits, . -)")
        grade = c.get("grade")
        if grade not in GRADES:
            errs.append(f"{w}: grade {grade!r} is not A, B, C or D")
            continue
        if grade == "D":
            continue  # a lead: it never ships, so only its grade matters
        if c.get("source") not in sources:
            errs.append(f"{w}: source {c.get('source')!r} is not in allowed_sources")
        if not isinstance(c.get("label"), str) or not c["label"].strip():
            errs.append(f"{w}: label missing")
        shot = c.get("screenshot")
        page = (c.get("locator") or {}).get("page")
        if page not in (None, "") and not shot:
            errs.append(f"{w}: locator.page {page!r} set but no screenshot")
        if shot and not (root / shot).is_file():
            errs.append(f"{w}: screenshot {shot} does not exist on disk")
        if grade == "A" and not shot:
            errs.append(f"{w}: grade A without a screenshot")
        via = c.get("via")
        if grade == "B":
            if not isinstance(via, dict) or not via.get("work") or not via.get("page"):
                errs.append(f"{w}: grade B needs via {{work, page}}")
        elif via is not None:
            errs.append(f"{w}: via must be null outside grade B")
    return errs


def used_keys(paths, pattern):
    rx = re.compile(pattern)
    used = {}
    for p in paths:
        text = Path(p).read_text(encoding="utf-8", errors="replace")
        for m in rx.finditer(text):
            used.setdefault(m.group(1), str(p))
    return used


def run(args):
    reg = load_registry(args.registry)
    root = Path(args.root) if args.root else Path(args.registry).resolve().parent
    errs = check_entries(reg, root)
    paths = []
    for u in args.used or []:
        p = Path(u)
        paths += sorted(q for q in p.rglob("*") if q.is_file()) if p.is_dir() else [p]
    for key, where in used_keys(paths, args.pattern).items():
        entry = reg["entries"].get(key)
        if entry is None:
            errs.append(f"{where}: citation {key} is not defined in the registry")
        elif entry.get("grade") == "D":
            errs.append(f"{where}: citation {key} is grade D and may not be displayed")
    return report("cites", errs)
