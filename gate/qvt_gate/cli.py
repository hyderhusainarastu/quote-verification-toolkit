import argparse
import sys

from . import __version__, cites, manifest, quotes, scrub
from .cites import DEFAULT_PATTERN


def build_parser():
    p = argparse.ArgumentParser(
        prog="qvt-gate",
        description="CI build gate for quotations and citations. Exit 0 = pass, 1 = findings, 2 = usage error.")
    p.add_argument("--version", action="version", version=__version__)
    sub = p.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("cites", help="check registry entries and the keys a build uses")
    c.add_argument("--registry", required=True)
    c.add_argument("--root", help="base for relative paths (default: the registry's folder)")
    c.add_argument("--used", nargs="*", help="files or folders to scan for citation keys")
    c.add_argument("--pattern", default=DEFAULT_PATTERN,
                   help="regex with one group that captures the key (default: [[cite:KEY]])")
    c.set_defaults(fn=cites.run)

    q = sub.add_parser("quotes", help="check each entry's quote appears byte-exact in its text_file")
    q.add_argument("--registry", required=True)
    q.add_argument("--root")
    q.add_argument("--nfkc", action="store_true", help="NFKC instead of NFC (folds ligatures)")
    q.set_defaults(fn=quotes.run)

    m = sub.add_parser("manifest", help="freeze or verify a SHA-256 source manifest")
    m.add_argument("action", choices=["freeze", "verify"])
    m.add_argument("dir")
    m.add_argument("--manifest", help=f"manifest path (default: DIR/{manifest.DEFAULT_NAME})")
    m.add_argument("--allow-extra", action="store_true", help="verify: ignore files not in the manifest")
    m.set_defaults(fn=manifest.run)

    s = sub.add_parser("scrub", help="cap quote length, strip access URLs, drop grade D")
    s.add_argument("--registry", required=True)
    s.add_argument("--max-words", type=int, default=25)
    s.add_argument("--check", action="store_true", help="change nothing; exit 1 if a scrub would change anything")
    s.add_argument("--out", help="write the scrubbed registry here (default: overwrite the input)")
    s.set_defaults(fn=scrub.run)
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
