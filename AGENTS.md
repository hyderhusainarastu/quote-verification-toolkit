# quote-verification-toolkit

Skill and Python CLI that check whether quoted text appears in its source text, plus a CI gate for quote registries.

## Using this in your project

- Use it before treating any direct quotation as verified, or when a plain substring check says a quote is missing.
- Read `SKILL.md` for the procedure and the meaning of each verdict.
- Check quotes: `python3 scripts/quote_verify.py --quotes-csv quotes.csv --source-file text.txt --output results.csv` (single quote: `--quote "..."`).
- Verdicts: VERIFIED, FUZZY and NOT_FOUND need a human look when not VERIFIED; NOT_VERIFIABLE says the source could not be tested, never that the quote is wrong.
- Build gate: `gate/qvt-gate cites|quotes|manifest|scrub`. Exit 0 pass, 1 findings, 2 usage error. See `gate/README.md`.
- Relocate a quote after re-extraction: `scripts/anchoring.py` (`find_quote_offset`, `rebind_anchor`).
- Write results only to the file given with `--output` or `--out`. Never edit source text files or a frozen manifest to make a check pass.
- Never report a quote as accurate on a FUZZY or NOT_VERIFIABLE result.

## Working on this repo

- Setup: none. Python 3.10+, standard library only.
- Test: `python3 -m unittest discover -s tests -t .` (offline). Also `bash test_install.sh`.
- Keep example data invented. Do not add real texts, institution URLs or personal data.
- `install.sh` and `test_install.sh` are shared copies; change them only to match the shared template.
