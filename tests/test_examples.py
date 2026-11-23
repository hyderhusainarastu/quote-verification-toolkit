"""The example run must reproduce the verdicts documented in synthetic_results_expected.csv."""
import csv
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def read(path):
    with open(path, newline="", encoding="utf-8") as f:
        return {r["quote_id"]: (r["verdict"], r["reason"]) for r in csv.DictReader(f)}


class ExampleOutput(unittest.TestCase):
    def test_matches_expected_csv(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "results.csv"
            subprocess.run(
                [sys.executable, "-B", str(ROOT / "scripts" / "quote_verify.py"),
                 "--quotes-csv", str(ROOT / "examples" / "synthetic_quotes.csv"),
                 "--source-file", str(ROOT / "examples" / "synthetic_source.txt"),
                 "--output", str(out)],
                check=True, capture_output=True, cwd=ROOT)
            got = read(out)
        want = read(ROOT / "examples" / "synthetic_results_expected.csv")
        self.assertEqual(set(got), set(want))
        for qid, expected in want.items():
            self.assertEqual(got[qid], expected, qid)


if __name__ == "__main__":
    unittest.main()
