"""`qvt-gate manifest freeze|verify`: SHA-256 manifest, one `<hex>  <path>` line per file."""
import hashlib
from pathlib import Path

from .common import report

DEFAULT_NAME = "MANIFEST.sha256"


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def list_files(root, skip):
    return sorted(p.relative_to(root).as_posix() for p in root.rglob("*")
                  if p.is_file() and p.name != skip and ".git" not in p.parts)


def freeze(root, manifest):
    lines = [f"{sha256(root / rel)}  {rel}" for rel in list_files(root, manifest.name)]
    manifest.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    print(f"manifest: froze {len(lines)} file(s) into {manifest}")
    return 0


def read_manifest(manifest):
    out = {}
    for n, line in enumerate(manifest.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        digest, sep, rel = line.partition("  ")
        if not sep or len(digest) != 64:
            raise SystemExit(f"error: {manifest}:{n}: expected '<64 hex>  <path>'")
        out[rel] = digest
    return out


def verify(root, manifest, allow_extra=False):
    want = read_manifest(manifest)
    errs = []
    for rel, digest in want.items():
        p = root / rel
        if not p.is_file():
            errs.append(f"{rel}: listed in the manifest but missing")
        elif sha256(p) != digest:
            errs.append(f"{rel}: content changed since the manifest was frozen")
    if not allow_extra:
        for rel in sorted(set(list_files(root, manifest.name)) - set(want)):
            errs.append(f"{rel}: present but not in the manifest")
    return report("manifest", errs)


def run(args):
    root = Path(args.dir)
    if not root.is_dir():
        raise SystemExit(f"error: {root} is not a directory")
    manifest = Path(args.manifest) if args.manifest else root / DEFAULT_NAME
    if args.action == "freeze":
        return freeze(root, manifest)
    if not manifest.is_file():
        raise SystemExit(f"error: manifest {manifest} not found")
    return verify(root, manifest, args.allow_extra)
