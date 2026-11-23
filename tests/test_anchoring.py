import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from anchoring import find_quote_offset, rebind_anchor  # noqa: E402


class FindOffset(unittest.TestCase):
    def test_exact_context(self):
        t = "alpha beta gamma. alpha beta delta."
        self.assertEqual(find_quote_offset(t, "beta", "alpha ", " delta"), 24)

    def test_single_occurrence_survives_changed_context(self):
        self.assertEqual(find_quote_offset("one two three", "two", "ZZ", "YY"), 4)

    def test_context_scores_between_repeats(self):
        t = "x cat y. a cat b."
        self.assertEqual(find_quote_offset(t, "cat", "a ", " b"), 11)
        self.assertEqual(find_quote_offset(t, "cat", "x ", " Q"), 2)

    def test_tie_keeps_earliest(self):
        self.assertEqual(find_quote_offset("cat cat", "cat", "?", "?"), 0)

    def test_missing_and_empty(self):
        self.assertIsNone(find_quote_offset("abc", "zzz", "", ""))
        self.assertIsNone(find_quote_offset("abc", "", "", ""))


class Rebind(unittest.TestCase):
    anchor = {"quote": "seasonal planting guides", "prefix": "access to ", "suffix": "."}

    def test_one_block_rebinds(self):
        blocks = [{"block_id": "b1", "text": "nothing here"},
                  {"block_id": "b2", "text": "gives access to seasonal planting guides."}]
        r = rebind_anchor(self.anchor, blocks)
        self.assertEqual(r, {"state": "rebound", "block_id": "b2", "offset": 16})

    def test_two_blocks_is_unanchored(self):
        t = "access to seasonal planting guides."
        blocks = [{"block_id": "b1", "text": t}, {"block_id": "b2", "text": t}]
        self.assertEqual(rebind_anchor(self.anchor, blocks), {"state": "unanchored"})

    def test_no_block_is_unanchored(self):
        self.assertEqual(rebind_anchor(self.anchor, [{"block_id": "b", "text": "x"}]),
                         {"state": "unanchored"})


if __name__ == "__main__":
    unittest.main()
