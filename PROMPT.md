# Quote verification: paste-in prompt

Use this in ChatGPT, Claude.ai, Gemini or a local model when you cannot run code. If you can run Python, use `scripts/quote_verify.py` instead; it is exact where a chat model is not.

## Task

I will give you (1) one or more quotations and (2) the source text they are attributed to. For each quotation, decide whether the words really appear in the source. Do not use outside knowledge. Judge only against the text I paste.

## How to compare

Ignore these differences, because they come from text extraction and not from the quotation:

- line breaks, repeated spaces and words split by a hyphen at a line end
- ligatures (fi, fl) and accented letters stored in a different form
- an ellipsis ("..." or the one-character form) inside the quotation: treat the pieces before and after it as separate spans that must appear in the same order

Do not ignore: a changed, added or missing word, a different number, different word order, or a different spelling that changes the word.

## Verdicts

Give exactly one per quotation:

- VERIFIED: the words appear in the source (allowing only the differences above).
- FUZZY: nearly matches but differs by a character or word. Show the difference.
- NOT_FOUND: no passage matches. Say so; do not guess a close passage.
- NOT_VERIFIABLE: the source text is missing, damaged or marked unreliable, or the quotation is only one or two common words. Say why. This is not a finding against the quotation.

## Output

A table with columns: id, verdict, evidence. For VERIFIED and FUZZY, put the matching source words in the evidence column, quoted exactly. For NOT_FOUND and NOT_VERIFIABLE, give the reason in one sentence.

End with one line of counts, for example: 3 VERIFIED, 1 FUZZY, 1 NOT_FOUND, 0 NOT_VERIFIABLE.

## Rules

- Quote evidence word for word from my text. Never fill in or repair a passage.
- If the source I pasted is long and you could not read all of it, say which part you did not see and use NOT_VERIFIABLE.
- Never call a quotation accurate on a FUZZY or NOT_VERIFIABLE result.

## My input

Quotations:

[paste numbered quotations here]

Source text:

[paste the source text here]
