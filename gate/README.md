# qvt-gate

A build gate for documents that quote sources. It is a Python standard-library
CLI with no network access. Run it in CI so a build fails when a quotation or
citation cannot be backed.

All examples use invented data. Run from the repository root.

```sh
gate/qvt-gate cites  --registry gate/examples/registry.json --used docs/
gate/qvt-gate quotes --registry gate/examples/registry.json
gate/qvt-gate manifest freeze gate/examples/sources
gate/qvt-gate manifest verify gate/examples/sources
gate/qvt-gate scrub  --registry registry.json --check
```

Exit codes: 0 pass, 1 findings, 2 usage error.

## Registry

One JSON file, `{"entries": {"<source>:<slug>": {...}}}`, described by
`registry.schema.json`. Evidence grades:

| Grade | Meaning | May be displayed |
|---|---|---|
| A | seen on a page image (needs `screenshot` that exists) | yes |
| B | seen in a public full text (needs `via` with `work` and `page`) | yes |
| C | snippet only | yes |
| D | not seen: a lead | never |

## Commands

- `cites`: validates every entry (grade, required fields, existing screenshots,
  key format) and fails on unknown fields. With `--used FILE_OR_DIR`, it scans for
  `[[cite:KEY]]` (change with `--pattern`) and fails on keys that are undefined or
  grade D.
- `quotes`: checks each entry's `quote` against its `text_file`. Both sides are put
  in NFC (or NFKC with `--nfkc`), words hyphenated across a line break are
  rejoined, and whitespace is collapsed. Case and punctuation are not touched, so
  the match is exact. A failure reports the first point of difference. Words that
  mix Latin letters with Greek or Cyrillic look-alikes are flagged.
- `manifest freeze|verify DIR`: writes or checks `MANIFEST.sha256`, one
  `<sha256>  <relative path>` line per file. Verify fails on changed, missing or
  extra files (`--allow-extra` ignores extras).
- `scrub`: caps displayed quotes (`--max-words`, default 25), removes access-gated
  URLs (library-proxy hosts, sign-in paths, redirect parameters) and drops grade D
  entries. `--check` changes nothing and exits 1 if a scrub would change something.

## Limits

It checks that a quote is present, not that it is correctly attributed or fairly
used. The URL rules are patterns, so review the output of `scrub` before publishing.
