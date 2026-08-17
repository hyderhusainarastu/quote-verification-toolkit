---
name: quote-verification-toolkit
description: Verify that quoted excerpts actually appear in their source texts, tolerant of PDF line-wraps, whitespace collapse, Unicode ligatures/accents, SGML entities, and mid-quote elision. Invoke before treating any direct quotation as citation-safe -- e.g. before a manuscript goes to a reviewer, before a quote ledger is marked verified, or whenever a mechanical substring check reports a quote as missing from its source and that result needs to be trusted or distrusted.
---

# Quote Verification Toolkit

## What this skill is for

A direct quotation in a manuscript, report, or ledger is a specific factual
claim: "these words, in this order, appear in that source." That claim is
checkable, and it should be checked mechanically before anyone treats it as
true -- but a naive `quote in source_text` substring check is wrong far more
often than the citation is. This skill runs a verification pass that is
aggressive enough to survive the ways real extracted text differs from the
quotation's surface form, and that clearly separates two very different
kinds of bad news:

- **The quotation is wrong** (the cited source doesn't say that) -- a real
  citation-integrity problem.
- **The extraction is wrong** (the file being checked against is a bad scan,
  a column-interleaved PDF dump, or missing a repaired variant) -- a tooling
  problem that produces a false failure indistinguishable, on the surface,
  from the first case.

Conflating these two is the single most damaging mistake this skill exists
to prevent. A `NOT_FOUND` result is evidence about *the file you checked*,
not about the citation, until it has been re-run against the best available
extraction of that source. Treating every `NOT_FOUND` as a confirmed defect
manufactures false findings; treating every `NOT_FOUND` as "probably just
the extractor" hides real ones. The point of the four-verdict output
contract below is to force that distinction to be made explicitly, every
time.

## When to run this

- Before any quotation is marked verified in a ledger, bibliography, or
  citation-integrity report.
- Before a manuscript, article, or report containing direct quotes is
  submitted, published, or handed to a reviewer.
- Whenever a prior verification pass reported a quote as `NOT_FOUND` and you
  need to know whether that is a real problem or a stale/low-quality
  extraction file.
- As a mechanical sweep step inside a larger review process (e.g. one check
  in a pre-publication checklist), run over every direct quotation in the
  document being reviewed.

Do not run it as a substitute for reading the source. A `VERIFIED` verdict
means the exact words appear in the file checked; it says nothing about
whether the quotation is used in a way that misrepresents the source's
meaning, or whether it exceeds a project's own quote-length policy. Length
and fair-use/quote-budget policy are the caller's responsibility, not this
tool's.

## The algorithm

### 1. Normalize aggressively, on both sides, the same way

Whitespace, line breaks, and column layout are not part of a quotation's
identity. A PDF-to-text extractor wraps lines at a column width that has
nothing to do with sentence boundaries, and a two-column page read
linearly can interleave column 1 and column 2 line by line. The
normalization below makes all of that irrelevant by discarding whitespace
entirely rather than trying to reconcile it:

1. **NFKD-decompose** the text. This is not optional. PDF extractors emit
   ligatures ("fi", "fl") as single code points and Latin letters with
   diacritics as single precomposed code points. A normalizer that strips
   non-alphanumeric characters *without* decomposing first turns "ﬁrst
   three" into "rstthree" (the ligature disappears as one opaque symbol
   instead of separating into "f" + "i") and turns "café" into "caf"
   while a plain-ASCII rendering of the same word ("cafe") normalizes to
   something else entirely. Two spellings of the same word landing on two
   different normalized strings is a false mismatch that has nothing to do
   with whether the quotation is accurate.
2. **Strip SGML/HTML entities** (`&amp;`, `&dquo;`, numeric entities) --
   text layers extracted from some publishing pipelines carry these
   literally.
3. **Lowercase**, then **delete every character that is not `[a-z0-9]`**.
   This one step absorbs whitespace collapse, line-wrap differences,
   hyphenation, punctuation-spacing differences, and column interleaving
   all at once, because none of the removed characters can affect whether
   the remaining letters and digits line up. Do not implement a lighter
   "collapse whitespace, don't touch punctuation" normalizer instead --
   it survives fewer real extraction defects for no accuracy benefit, and
   this skill supersedes that approach.

Apply the identical procedure to the quotation and to the witness text
before comparing them. Comparing normalized-to-normalized is the whole
point; comparing normalized-quote-to-raw-witness (or vice versa) reproduces
the false-mismatch problem this step exists to remove.

### 2. Elided quotations are a sequence of spans, not one substring

A quotation containing an ellipsis (`"the volunteers ... logged nearly
four hundred hours restoring the archive"`) is a genuine, common, and
legitimate way to quote --
and it is never a contiguous substring of a faithful extraction, by
construction. Verifying it correctly requires:

1. **Split the quote on every elision marker**: a literal `...`, the
   Unicode ellipsis `…` (U+2026), and, if the source is LaTeX, `\ldots`
   and `\dots` (consuming a following escaped space, `\ `, so it doesn't
   survive as stray text).
2. **Require each resulting segment to occur in the witness text after the
   end of the match for the previous segment** -- in order, not anywhere.
3. **At least one segment must clear the minimum meaningful length**
   (default 15 normalized characters) for the result to count as a real
   test. A quotation where every segment is shorter than that is not
   verifiable by substring matching at all (see `TOO_SHORT` below) --
   report it as such rather than either passing or failing it.

**Order of operations is the entire bug, if you get it wrong.** If the
source text may contain LaTeX (or any other markup with its own escape
syntax), the elision markers must be protected with a sentinel value
**before** any markup-stripping runs, not after. A generic macro/markup
stripper that removes `\footnote{...}`, accent commands, and other
control sequences will match `\ldots` and `\dots` as ordinary macros and
delete them right along with everything else -- and once that happens,
`"the volunteers\ldots\ logged nearly four hundred hours"` has silently
become `"the volunteers logged nearly four hundred hours"`, a single
contiguous string with
nothing left to split on. The elision test then runs against the whole
span as one substring, finds no contiguous match (because the real text
isn't contiguous), and reports `NOT_FOUND` on a quotation that is
verbatim correct. This is not a hypothetical: it is the exact failure
mode that motivated documenting this order explicitly, and it produces a
false, high-confidence-looking citation-integrity finding out of a
tooling bug. The required order is:

1. Replace every elision marker with a sentinel that cannot appear in
   ordinary prose or markup and is not alphanumeric.
2. Strip footnote/comment bodies, if applicable.
3. Restore markup-specific accent/escape sequences to their base letters
   (e.g. LaTeX `\"o` -> `o`) -- do this *before* generic macro stripping,
   because a macro stripper that deletes a macro's braced argument would
   otherwise delete the base letter along with the accent command.
4. Strip remaining markup.
5. Split on the sentinel and run the ordered-segment test from above.

### 3. Exact match first, fuzzy match as a bounded fallback

For each segment (a whole unelided quote is the one-segment case):

1. Try an **exact substring match** in the normalized witness text, at or
   after the position where the previous segment's match ended.
2. If that fails, try a **similarity-ratio match** against text starting
   from the same position: locate the best-aligned same-length window of
   witness text and score it against the segment. If the ratio is at or
   above the fuzzy threshold (default **0.95**), accept it as a match but
   record that this segment matched fuzzily, not exactly.
3. If neither succeeds, the segment is unmatched and the whole quotation
   fails against this witness.

A quotation where every segment matched exactly is `VERIFIED`. A
quotation where every segment matched, but at least one matched only
fuzzily, is `FUZZY` -- report it as a citation-integrity candidate, not
as a pass, because a near-miss can mean a real transcription slip in the
quotation just as easily as it can mean OCR noise in the extraction.

### 4. Resolve the right witness file before trusting any failure

A source may have more than one extracted-text file on disk: a raw first
extraction pass, a column-aware or hyphenation-aware rebuild, an OCR
re-run, or a previously-attempted repair that turned out to be wrong.
**Which file you check against changes the answer**, and checking only
the first (or only the original, or only the alphabetically-first) file
found is exactly how a tooling artifact gets misreported as a citation
defect. Before trusting any `NOT_FOUND`, apply this procedure:

1. **Build the candidate list.** Enumerate every extracted-text variant
   that exists for the cited source.
2. **Exclude known-bad candidates unconditionally.** A file explicitly
   marked as a rejected or superseded repair attempt is worse than the
   original and must never be read as a witness, no matter what else is
   available.
3. **Rank what remains by your own project's quality markers**, most
   trustworthy first (for example: a corpus-wide re-extraction pass over a
   raw first pass; a column-aware rebuild over a linear dump of a
   multi-column page; a de-hyphenation-aware pass tried in *both*
   directions -- hyphen removed and hyphen retained -- since de-hyphenation
   itself can destroy a genuine hyphenated compound the quotation depends
   on). There is no universal ranking; define the markers that describe
   your own extraction pipeline's outputs.
4. **Try every candidate, not just the first.** A higher-ranked witness
   failing does not mean the quotation is wrong -- it may just be a worse
   extraction of the same source for this particular span. Keep the best
   result seen across all candidates (`VERIFIED` beats `FUZZY` beats
   `NOT_FOUND`), and stop only once a witness produces `VERIFIED` (nothing
   can beat it). Always record *which* witness file actually produced the
   reported verdict, so a reviewer can see -- and distrust, if warranted --
   a result that rests on a low-ranked witness.
5. **If a source is known in advance to have no sound extraction at all**
   (a damaged scan, a capture with a clipped margin, corrupted OCR with no
   corrected file on disk), a failure to match is a fact about the file,
   not the citation. Mark it `NOT_VERIFIABLE` with the reason stated, not
   `NOT_FOUND` -- and if a match *does* succeed despite the known defect,
   that is still real evidence and should be reported `VERIFIED`. The
   override exists to suppress false defects, not true passes.

This witness-resolution step is the difference between a verification pass
that finds real citation problems and one that spends a reviewer's time
chasing extraction bugs it manufactured itself. A sweep that reads only
the stored original extraction for every source will, in practice, report
a batch of `NOT_FOUND` failures whose only common cause is "wrong file
read" -- not any actual defect in the quotations themselves. Applying the
five-step procedure above before trusting a `NOT_FOUND` result is what
keeps that batch of false failures from ever reaching a citation-integrity
report as if it were real evidence. `references/witness-resolution-notes.md`
walks through the specific failure modes (identifier-key mismatches,
resolving-field collisions, near-duplicate-record collisions, bad repair
attempts, double-edged normalization choices) in more depth, using
illustrative (not real-world) scenarios, if you're implementing this step
for your own project's identifier scheme.

## Output contract -- four verdicts, not interchangeable

| Verdict | Meaning | Is it a citation-integrity finding? |
|---|---|---|
| `VERIFIED` | Exact match against the best available witness. | No -- this is a pass. |
| `FUZZY` | Matched at or above the similarity threshold, but not exactly. | **Yes.** Investigate: real near-miss, or OCR/extraction noise? |
| `NOT_FOUND` | No match, exact or fuzzy, against the best available witness. | **Yes.** This is the result that needs a human to read the actual source. |
| `NOT_VERIFIABLE` | Could not be meaningfully checked: no witness file exists, the witness is known-defective, or the quote (every elided segment of it) is below the minimum testable length. | **No, never by itself.** State the reason every time this label is used. |

Never merge `FUZZY`/`NOT_FOUND` and `NOT_VERIFIABLE` into one "failed"
bucket in a report. The first pair says something about the *quotation*.
The second says something about the *file*. A verification report that
collapses them will eventually generate a severe-looking finding against
a citation that was correct all along, purely because the checker had
nothing sound to check it against.

A quotation shorter than the minimum testable length (default: 15
normalized characters -- roughly, a single common word) is not a pass and
not a failure. It is present in the running text far too often for a
substring test to mean anything at that length. Report it as
`NOT_VERIFIABLE` with reason `TOO_SHORT` and, if the quotation matters,
check it by reading the source directly instead of mechanically.

## How to run it

The bundled script (`scripts/quote_verify.py`, standard library only, no
dependencies) implements the full algorithm above. Two modes:

**Single quote:**

```
python3 scripts/quote_verify.py \
  --quote "the exact words to check" \
  --source-file path/to/extracted_text.txt
```

**Batch, from a CSV of quotations** (columns configurable; default
`quote_id`, `exact_quote`):

```
python3 scripts/quote_verify.py \
  --quotes-csv quotes.csv \
  --source-file path/to/extracted_text.txt \
  --output results.csv
```

**Batch with per-row witness resolution**, when different rows cite
different sources and you have a directory of extracted-text variants
named by a per-source key (e.g. a slug column in the CSV):

```
python3 scripts/quote_verify.py \
  --quotes-csv quotes.csv \
  --source-column source_slug \
  --source-dir extracted_text/ \
  --source-pattern "{key}.*" \
  --prefer-token clean --prefer-token v2 --prefer-token raw \
  --exclude-pattern "reject" \
  --output results.csv
```

`--prefer-token` (repeatable, most-preferred first) and `--exclude-pattern`
implement the witness-ranking procedure from step 4 above; they have no
built-in vocabulary because that vocabulary is specific to whatever
extraction pipeline produced your files -- supply your own project's
markers.

An optional CSV column (default name `override_reason`; see
`--override-column`) implements the source-known-to-have-no-sound-
extraction override from step 4.5: when a row's cell in that column is
non-empty and the quote fails to match, the verdict is forced to
`NOT_VERIFIABLE` with that text as the reason, instead of `NOT_FOUND`.

Pass `--strip-latex` when quotations or witness text may contain LaTeX
markup (accent macros, `\footnote{}`, other control sequences); it applies
the order-of-operations procedure from step 2 automatically. Leave it off
for plain text.

Every quote is checked against every witness that resolves for it, in
preference order, and the best result across all of them is reported --
never just the first witness tried. Full flag reference: run the script
with `--help`.

## Reading the results

For each quote, the output records: the verdict; a reason (populated for
`NOT_VERIFIABLE`); which witness file produced the result; a similarity
indicator; how many of the quote's segments matched; and a context
snippet from the witness text around the match, for a human to eyeball.

Treat the results this way:

- **`VERIFIED`**: no action needed.
- **`FUZZY` or `NOT_FOUND`**: read the reported context snippet and the
  actual source. If the witness resolution in step 4 was followed and the
  quote still doesn't match, this is very likely a real citation problem
  -- fix the quotation or find where the words actually appear. Do not
  silently use a quotation with either verdict.
- **`NOT_VERIFIABLE`**: read the reason. If it's `TOO_SHORT`, decide by
  eye whether the (very short) quotation is accurate. If it's a witness
  problem (no source file, known-defective source), the quotation is
  neither confirmed nor refuted -- flag it for a follow-up extraction
  pass or manual check, and do not report it as a citation defect in the
  meantime.

## Worked example

See `examples/synthetic_source.txt`, `examples/synthetic_quotes.csv`, and
`examples/synthetic_results_expected.csv` -- a small fabricated source
text and quote set (clearly synthetic, not real research) exercising every
verdict, including a line-wrapped exact match, an elided quote, a
ligature/accent normalization case, a below-threshold OCR-style typo
(`FUZZY`), a genuinely absent phrase (`NOT_FOUND`), a single-word quote
(`TOO_SHORT`), and a forced source-defect override
(`NOT_VERIFIABLE`). Running the batch command above against those two
files reproduces the same `verdict` (and, where applicable, `reason`) for
every row as documented in `examples/synthetic_results_expected.csv`. The
two files aren't byte-identical: the real `results.csv` carries several
additional columns the summary file doesn't (`witness_file`, `similarity`,
`segments_matched`, `context`, `checked_by`, `checked_date` -- the last of
which is always today's date and so can never match a static file byte for
byte). Compare `quote_id`/`verdict`/`reason` between the two rather than
diffing the files directly.
