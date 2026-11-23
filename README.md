# Quote Verification Toolkit

Check that a quoted excerpt actually appears in the source text it's
attributed to -- reliably, even when the source text is a PDF extraction
full of line wraps, ligatures, accented letters, or a mid-quote ellipsis.

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

## Works with

| Surface | How | Status |
|---|---|---|
| Command line (any tool that can run Python 3.10+) | `scripts/quote_verify.py`, `gate/qvt-gate`; standard library only | tested 2026-11-23, Python 3.14 |
| Claude Code | native skill (`SKILL.md`) via `install.sh --claude` | not tested |
| Codex | native skill via `.agents/skills` (`install.sh --agents`) | not tested |
| Gemini CLI | native skill via `.agents/skills`, pointer in `GEMINI.md` | not tested |
| Cursor | native skill via `.agents/skills`; reads `AGENTS.md` | not tested |
| Copilot | pointer to `AGENTS.md` | not tested |
| ChatGPT / Claude.ai / Gemini (chat) | prompt: paste `PROMPT.md` (or `PROMPT.short.md`) | not tested |

## What it does

A plain `if quote in source_text` check fails constantly on real extracted
text, for reasons that have nothing to do with whether the quotation is
accurate: PDF text extractors wrap lines wherever the column ends, not at
sentence boundaries; "fi"/"fl" ligatures and accented letters come out of
some extractors as single Unicode characters that don't match their
plain-ASCII spelling; and a legitimately elided quotation ("the volunteers ...
logged nearly four hundred hours") is never one contiguous span in a
faithful extraction to begin with.

This toolkit normalizes both the quotation and the source text the same
aggressive way (Unicode-decompose, strip everything but letters and
digits, compare), handles elided quotations as an ordered sequence of
spans rather than one substring, supports checking a quotation against
several candidate source-text files at once (useful when a source has more
than one extracted-text variant of differing quality) and reports which
file actually produced the result, and falls back to a similarity-ratio
match at a configurable threshold when an exact match fails.

It reports one of four outcomes for every quotation:

- **VERIFIED** -- exact match found.
- **FUZZY** -- a near-match at or above the similarity threshold, not
  exact. Worth a human look.
- **NOT_FOUND** -- no match, exact or fuzzy. Worth a human look.
- **NOT_VERIFIABLE** -- couldn't be meaningfully checked (no source file
  supplied, source flagged as unreliable, or the quotation is too short to
  test at all). This is never treated as a citation-integrity finding by
  itself, and the reason is always stated.

Keeping `NOT_VERIFIABLE` separate from `FUZZY`/`NOT_FOUND` matters: the
first pair says something about the *quotation*, the second says something
about the *file you checked it against*. A tool that conflates them turns
missing or low-quality source text into false accusations against
perfectly accurate quotations.

## Quick start

```sh
git clone https://github.com/hyderhusainarastu/quote-verification-toolkit
cd quote-verification-toolkit
python3 scripts/quote_verify.py --help        # use it as a plain CLI, no install
./install.sh --claude                         # ~/.claude/skills/quote-verification-toolkit
./install.sh --agents --project .             # .agents/skills (Codex, Cursor, Gemini CLI)
./install.sh --gemini --cursor --copilot --project .   # pointer blocks only
./install.sh --uninstall --claude --agents    # removes only what it installed
```

With no flag, `install.sh` prints help and changes nothing. It symlinks by
default (`--copy` to copy), never overwrites a path it does not own, and has
`--dry-run`. For a chat tool with no file access, paste `PROMPT.md`.

## Use from an AI coding agent

`AGENTS.md` is the single instruction file; `CLAUDE.md`, `GEMINI.md` and
`.github/copilot-instructions.md` only point at it. An agent should run
`scripts/quote_verify.py` before calling a quotation verified, and treat FUZZY,
NOT_FOUND and NOT_VERIFIABLE as needing a human look.

## Worked example (synthetic data)

`examples/` contains a small, clearly-fabricated source text and a CSV of
quotations exercising every verdict. Nothing in it is real research --
it's example data for this README.

```
python3 scripts/quote_verify.py \
  --quotes-csv examples/synthetic_quotes.csv \
  --source-file examples/synthetic_source.txt \
  --output results.csv
```

Output:

```
  q1_linewrap: VERIFIED witness=examples/synthetic_source.txt
  q2_elision: VERIFIED witness=examples/synthetic_source.txt
  q3_ligature_accent: VERIFIED witness=examples/synthetic_source.txt
  q4_too_short: NOT_VERIFIABLE (TOO_SHORT)
  q5_fuzzy: FUZZY witness=examples/synthetic_source.txt
  q6_not_found: NOT_FOUND witness=examples/synthetic_source.txt
  q7_source_defect: NOT_VERIFIABLE (damaged scan; no corrected file on disk) witness=examples/synthetic_source.txt

3/7 VERIFIED, 1 FUZZY, 1 NOT_FOUND, 2 NOT_VERIFIABLE
```

(The `witness=` suffix appears on every row that had a candidate witness
file to report, including `q7_source_defect` -- the override forces the
verdict to `NOT_VERIFIABLE`, but the witness file that produced the
overridden result is still recorded.)

`examples/synthetic_results_expected.csv` documents the intended verdict
and reason for each row and why it comes out that way. The full
`results.csv` from a real run carries several additional columns
(`witness_file`, `similarity`, `segments_matched`, `context`, and a
`checked_date` timestamp that changes every day) that this summary file
doesn't reproduce, so it's not meant to be diffed byte-for-byte against a
fresh run. Comparing the `verdict`/`reason` for each `quote_id` between
the two is a quick way to confirm the script is working correctly after
any local edits.

## Standalone CLI usage

The script has no dependencies beyond the Python 3 standard library.

**Check one quote against one source file:**

```
python3 scripts/quote_verify.py \
  --quote "the exact words to check" \
  --source-file your-project/paper/extracted_text.txt
```

**Check a batch of quotes from a CSV** (default columns `quote_id`,
`exact_quote`; override with `--id-column` / `--quote-column`):

```
python3 scripts/quote_verify.py \
  --quotes-csv your-project/quotes.csv \
  --source-file your-project/paper/extracted_text.txt \
  --output results.csv
```

**Multiple candidate source files for the same quote** (e.g. a cleaned
extraction and a raw fallback -- tried in the order given, and every one
is tried, not just the first that exists, because a higher-priority file
might simply be a worse extraction of a particular passage):

```
python3 scripts/quote_verify.py \
  --quote "..." \
  --source-file your-project/paper/extracted_text.clean.txt \
  --source-file your-project/paper/extracted_text.txt
```

**Per-row source discovery**, when different CSV rows cite different
sources and you keep extracted-text variants in one directory named by a
per-source key:

```
python3 scripts/quote_verify.py \
  --quotes-csv your-project/quotes.csv \
  --source-column source_slug \
  --source-dir your-project/extracted_text/ \
  --source-pattern "{key}.*" \
  --prefer-token clean --prefer-token v2 --prefer-token raw \
  --exclude-pattern "reject" \
  --output results.csv
```

**LaTeX sources** (protects `\ldots`/`\dots` elision markers before macro
stripping, restores `\"o`-style accent macros, strips `\footnote{}`):

```
python3 scripts/quote_verify.py \
  --quotes-csv your-project/quotes.csv \
  --source-file your-project/paper/manuscript_text.txt \
  --strip-latex
```

Run `python3 scripts/quote_verify.py --help` for the complete flag
reference, including `--fuzzy-threshold`, `--min-segment-chars`,
`--context-chars`, and the CSV column-name overrides.

## How the algorithm works

See `SKILL.md` for the full explanation -- normalization order, why
NFKD-decomposition matters, how elided quotations are matched as ordered
spans, why elision markers must be protected before any markup stripping
runs, and the witness-file resolution procedure for sources that have more
than one extracted-text variant.

## Build gate

`gate/` is a CI gate for a registry of quotes and citations (Python standard
library). `qvt-gate cites` checks evidence grades (A seen page image, B seen
public full text, C snippet only, D not seen, never displayed) and fails on
unknown or grade D keys. `qvt-gate quotes` does a byte-exact check after NFC
or NFKC and hyphen rejoin, reports the first difference and flags Latin/Greek
or Cyrillic look-alike letters. `qvt-gate manifest freeze|verify` keeps a
SHA-256 manifest of source files. `qvt-gate scrub --check` enforces a quote word
cap, strips access-gated URLs and drops grade D. See `gate/README.md`.

```
$ gate/qvt-gate quotes --registry gate/examples/registry.json
quotes: checked 2 quote(s) with NFC
quotes: ok
```

## Anchoring

`scripts/anchoring.py` finds a quote again after the source is re-extracted,
using the quote plus a little text before and after it (`find_quote_offset`,
`rebind_anchor`). A match in more than one block is reported as unanchored, not
guessed.

## Tests

```
python3 -m unittest discover -s tests -t .
```

Offline. Includes a test that diffs the example run against
`examples/synthetic_results_expected.csv`.

## How it differs

It is not a plagiarism or similarity detector, and it does not look sources up.
Related tools check different things: `hallucinated-citation-checker` checks
whether cited references exist, and `scholarly-citation-resolver` resolves them
to records. This toolkit checks the words inside the quotation against text you
already have.

## Limits

- It tests presence of words in a file, not whether the quote is used fairly.
- Fuzzy matching is a similarity ratio and can pass a near-miss; read FUZZY rows.
- Only text you supply is checked; scanned pages need OCR first.
- Only the command-line path is tested; platform rows marked "not tested" are
  untested.
- The `scrub` URL rules are patterns; review the result before publishing.

## Related

- [hallucinated-citation-checker](https://github.com/hyderhusainarastu/hallucinated-citation-checker): does the cited reference exist at all
- [scholarly-citation-resolver](https://github.com/hyderhusainarastu/scholarly-citation-resolver): resolve citations to records

## Keywords

quote verification, citation checking, fact-checking, PDF text extraction, fuzzy
match, research integrity, CI build gate, SHA-256 manifest, agent skill

## License

MIT. See `LICENSE`.

---
Part of palimnote-skills - more at https://github.com/hyderhusainarastu
