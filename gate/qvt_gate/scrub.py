"""`qvt-gate scrub`: make a registry safe to publish.

Three rules: cap the words of any displayed quote, remove institutional access
(proxy / sign-in) URLs, and drop grade D entries entirely."""
import copy
import json
import re
from pathlib import Path
from urllib.parse import urlparse

from .common import load_registry, report

# Hosts and query parameters that mark a library or institutional access link.
ACCESS_HOST = re.compile(r"(^|\.)(proxy|libproxy|ezproxy|openathens|idm\.oclc)[.\-]|^proxy\d*\.", re.I)
ACCESS_QUERY = re.compile(r"[?&](qurl|url|target)=https?(%3A|:)", re.I)
ACCESS_PATH = re.compile(r"/(login|shibboleth|saml|sso)(/|\?|$)", re.I)


def is_access_url(url):
    if not isinstance(url, str) or not url:
        return False
    u = urlparse(url)
    return bool(ACCESS_HOST.search(u.hostname or "") or ACCESS_QUERY.search(url)
                or ACCESS_PATH.search(u.path))


def cap_words(text, cap):
    words = text.split()
    if len(words) <= cap:
        return text
    return " ".join(words[:cap]) + " ..."


def scrub_registry(reg, max_words):
    """Return (scrubbed copy, list of change descriptions)."""
    out = copy.deepcopy(reg)
    changes = []
    for key in list(out["entries"]):
        e = out["entries"][key]
        if e.get("grade") == "D":
            del out["entries"][key]
            changes.append(f"{key}: dropped (grade D)")
            continue
        if is_access_url(e.get("url")):
            e["url"] = None
            changes.append(f"{key}: removed access URL")
        q = e.get("quote")
        if isinstance(q, str) and len(q.split()) > max_words:
            e["quote"] = cap_words(q, max_words)
            changes.append(f"{key}: quote cut to {max_words} words")
    return out, changes


def run(args):
    reg = load_registry(args.registry)
    out, changes = scrub_registry(reg, args.max_words)
    if args.check:
        return report("scrub", changes)
    dest = Path(args.out) if args.out else Path(args.registry)
    dest.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    for c in changes:
        print(f"scrub: {c}")
    print(f"scrub: wrote {dest} ({len(out['entries'])} entries, {len(changes)} change(s))")
    return 0
