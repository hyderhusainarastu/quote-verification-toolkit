# Witness resolution: extended rationale and pitfalls

This is supporting material for SKILL.md step 4 ("Resolve the right witness
file before trusting any failure"). It goes into more depth on *why* each
part of that procedure exists, using a generalized, synthetic example. If
you just need the procedure, SKILL.md is self-sufficient; read this when
you're implementing witness resolution for your own project's identifier
scheme and want to see the failure modes that motivated each rule.

## The problem in one sentence

When a quotation is checked against the wrong file, the checker cannot
tell the difference between "the quotation is wrong" and "I read the
wrong file" -- both produce `NOT_FOUND`. Every rule below exists to keep
that ambiguity from reaching a report as a false citation-integrity
finding.

## Pitfall 1: the citation key and the storage key are not always the same string

A document is often cited by a short identifier (an author-year key, a
ticket number, a slug) that is *not necessarily* the same string used to
name its extracted-text file on disk, especially if the file naming
happened separately (an earlier intake pass, a different naming
convention, a rename). A resolver that looks for a witness file named
exactly after the citation key, and stops if none exists, will report
`NOT_FOUND` on quotations that verify perfectly once pointed at the
correctly-named file.

**Rule:** treat "which file backs this citation" as its own resolution
step, separate from "does the quotation match." Build a mapping (however
your project tracks it -- a manifest, an index file, a lookup table) from
citation key to storage key, and resolve through it before ever opening a
file.

## Pitfall 2: a resolving field can mean different things for different record types

Suppose your citation records carry a field that's supposed to name "the
document this excerpt lives in" -- call it a container field. For one
kind of record, that field genuinely names the held document (a chapter's
container field names the edited volume you have on file). For a
*different* kind of record using the same field name, it names something
you don't hold at all (a conference paper's container field names the
proceedings volume, not the paper itself, which is filed separately under
its own identifier). If your resolver tries the container field first
(correctly, since it's the more specific witness class), got no match for
a proceedings-type record, and treats that as the end of the search
instead of falling through to the next resolution step, every citation
of that record type resolves to nothing -- a batch of false failures with
one root cause. As an illustration of scale: a corpus with, say, a few
dozen conference-paper citations sharing this record type would misreport
every one of them as a failure from this single falling-through-not-
implemented bug, with zero real citation defects among them.

**Rule:** a resolution field failing to match is not itself a result. It
means "try the next step in the ladder," not "there is no witness." Only
exhausting every step is a real "no witness found."

## Pitfall 3: identifier collisions across near-duplicate records

Two distinct source documents can share every field your fallback
resolution step keys on. Concretely: two edited volumes from the same
publisher, same year, same five-person editor list, different titles.
An identifier scheme that falls back to "match on editor list + year" when
nothing more specific matches cannot tell these two records apart, and
will pick whichever one happens to sort first -- silently, with no error,
resolving citations of one volume to the extracted text of the other. As
an illustration: if two such volumes each contribute a handful of
cited chapters, a coarse resolver could silently misresolve citations
across all of them, every one reported `NOT_FOUND` (because none of
their words appear in the *other* volume) and every one verifying
correctly once properly resolved.

**Rule:** order your resolution ladder from most-specific to
least-specific, and only fall back to a coarse, collision-prone match
(like "same author list, same year") as an absolute last resort. Always
record which step in the ladder actually produced the resolution, in the
output, so a reviewer can see that a result rests on the risky last-resort
step and treat it with appropriate suspicion rather than as settled.

## Pitfall 4: a repair attempt can make things worse, not better

Not every re-extraction or repair pass on a source file is actually an
improvement. A rebuild that reorders words within a column incorrectly is
worse than the original it was meant to fix. If your candidate-ranking
step treats "has been through a repair pass" as inherently higher-quality
without a way to mark a specific repair as having failed review, a bad
repair can outrank a merely-imperfect original.

**Rule:** maintain an explicit exclusion mechanism (a naming convention,
a manifest flag) for known-bad repair attempts, and treat exclusion as
absolute -- a rejected file is never a fallback, no matter how few other
candidates remain. `scripts/quote_verify.py` implements this as
`--exclude-pattern`, applied before ranking, not after.

## Pitfall 5: a single normalization choice can be wrong in either direction

Some text-cleanup steps are double-edged. Joining line-final hyphens
("infor-\nmation" -> "information") fixes words that were broken by line
wrapping, but it also destroys words that are genuinely
hyphenated compounds ("re-cover" -> "recover"), and a quotation
that depends on the hyphenated spelling will fail to match a
hyphen-joined witness even though the source is fine. There is no single
correct choice -- it depends on the specific word.

**Rule:** where a normalization choice is genuinely double-edged, try both
directions before recording a failure, and let whichever one succeeds win.
Don't pick one normalization policy globally and treat every resulting
mismatch as a citation defect.

## Summary: the meta-rule

Every pitfall above produces the identical symptom -- a mechanical
`NOT_FOUND` -- for a cause that has nothing to do with the accuracy of the
quotation. The fix is never to make the substring check itself smarter;
it's to make sure the check runs against the *right file*, tried in the
*right order*, with known-bad candidates *excluded outright*, before a
failure is ever reported as a finding about the citation rather than a
finding about the file.
