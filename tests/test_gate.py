import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GATE = ROOT / "gate"
sys.path.insert(0, str(GATE))
from qvt_gate import cli, quotes, scrub  # noqa: E402
from qvt_gate.cites import check_entries  # noqa: E402


def gate(*args):
    return cli.main([str(a) for a in args])


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        shutil.copytree(GATE / "examples", self.tmp / "ex")
        self.reg_path = self.tmp / "ex" / "registry.json"
        self.reg = json.loads(self.reg_path.read_text())

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def save(self):
        self.reg_path.write_text(json.dumps(self.reg))


class Cites(Base):
    def test_example_passes(self):
        self.assertEqual(check_entries(self.reg, self.reg_path.parent), [])
        self.assertEqual(gate("cites", "--registry", self.reg_path), 0)

    def test_unknown_field_and_bad_grade_fail(self):
        self.reg["entries"]["book:garden-survey"]["extra"] = 1
        self.reg["entries"]["web:seed-notes"]["grade"] = "E"
        errs = " ".join(check_entries(self.reg, self.reg_path.parent))
        self.assertIn("unknown field", errs)
        self.assertIn("not A, B, C or D", errs)

    def test_grade_a_needs_existing_screenshot(self):
        self.reg["entries"]["book:garden-survey"]["screenshot"] = "missing.png"
        self.assertIn("does not exist", " ".join(check_entries(self.reg, self.reg_path.parent)))

    def test_grade_b_needs_via_and_others_forbid_it(self):
        self.reg["entries"]["web:seed-notes"]["via"] = None
        self.reg["entries"]["book:garden-survey"]["via"] = {"work": "w", "page": "1"}
        errs = " ".join(check_entries(self.reg, self.reg_path.parent))
        self.assertIn("grade B needs via", errs)
        self.assertIn("via must be null", errs)

    def test_undefined_and_grade_d_keys_in_a_build_fail(self):
        self.save()
        doc = self.tmp / "doc.md"
        doc.write_text("ok [[cite:book:garden-survey]] lead [[cite:report:soil-lead]] "
                       "gone [[cite:web:nope]]")
        self.assertEqual(gate("cites", "--registry", self.reg_path, "--used", doc), 1)
        doc.write_text("ok [[cite:book:garden-survey]]")
        self.assertEqual(gate("cites", "--registry", self.reg_path, "--used", doc), 0)


class Quotes(Base):
    def test_example_passes(self):
        self.assertEqual(gate("quotes", "--registry", self.reg_path), 0)

    def test_first_difference_reported(self):
        src = "The survey found that participants joined a cooperative."
        probs = quotes.check_quote("The survey found that participants joined a cooperatve.", src)
        self.assertEqual(len(probs), 1)
        self.assertIn("at char", probs[0])

    def test_hyphen_rejoin_and_wrap(self):
        self.assertEqual(quotes.check_quote("structured access", "struc-\ntured\naccess"), [])

    def test_case_and_punctuation_are_exact(self):
        self.assertTrue(quotes.check_quote("Structured access", "structured access"))
        self.assertTrue(quotes.check_quote("structured, access", "structured access"))

    def test_nfc_vs_nfkc(self):
        self.assertTrue(quotes.check_quote("first", "ﬁrst"))
        self.assertEqual(quotes.check_quote("first", "ﬁrst", "NFKC"), [])
        self.assertEqual(quotes.check_quote("café", "café"), [])

    def test_homoglyph_detected(self):
        probs = quotes.check_quote("cаt", "cаt")  # Cyrillic a inside a Latin word
        self.assertTrue(any("mixed-script" in p for p in probs))

    def test_missing_text_file_fails(self):
        self.reg["entries"]["book:garden-survey"]["text_file"] = "nope.txt"
        self.save()
        self.assertEqual(gate("quotes", "--registry", self.reg_path), 1)


class Manifest(Base):
    def test_freeze_verify_and_tamper(self):
        d = self.tmp / "ex" / "sources"
        self.assertEqual(gate("manifest", "freeze", d), 0)
        lines = (d / "MANIFEST.sha256").read_text().splitlines()
        self.assertEqual(len(lines), 2)
        self.assertRegex(lines[0], r"^[0-9a-f]{64}  \S")
        self.assertEqual(gate("manifest", "verify", d), 0)
        (d / "garden-survey.txt").write_text("changed")
        self.assertEqual(gate("manifest", "verify", d), 1)

    def test_extra_and_missing_files(self):
        d = self.tmp / "ex" / "sources"
        gate("manifest", "freeze", d)
        (d / "new.txt").write_text("x")
        self.assertEqual(gate("manifest", "verify", d), 1)
        self.assertEqual(gate("manifest", "verify", d, "--allow-extra"), 0)
        (d / "garden-survey.txt").unlink()
        self.assertEqual(gate("manifest", "verify", d, "--allow-extra"), 1)


class Scrub(Base):
    def test_grade_d_dropped_and_check_fails(self):
        self.assertEqual(gate("scrub", "--check", "--registry", self.reg_path), 1)
        out = self.tmp / "clean.json"
        self.assertEqual(gate("scrub", "--registry", self.reg_path, "--out", out), 0)
        clean = json.loads(out.read_text())
        self.assertNotIn("report:soil-lead", clean["entries"])
        self.assertEqual(gate("scrub", "--check", "--registry", out), 0)

    def test_word_cap_and_access_urls(self):
        e = self.reg["entries"]["book:garden-survey"]
        e["quote"] = " ".join(f"w{i}" for i in range(40))
        e["url"] = "https://login.library.proxy.example.org/login?url=https://example.org/x"
        out, changes = scrub.scrub_registry(self.reg, 25)
        got = out["entries"]["book:garden-survey"]
        self.assertTrue(got["quote"].endswith("w24 ..."))
        self.assertIsNone(got["url"])
        self.assertEqual(len(changes), 3)  # grade D, access url, long quote

    def test_plain_urls_survive(self):
        self.assertFalse(scrub.is_access_url("https://example.org/garden-survey"))
        self.assertTrue(scrub.is_access_url("https://x.example.org/?qurl=https://y.org"))

    def test_input_not_mutated(self):
        before = json.dumps(self.reg, sort_keys=True)
        scrub.scrub_registry(self.reg, 5)
        self.assertEqual(json.dumps(self.reg, sort_keys=True), before)


class CliProcess(unittest.TestCase):
    def test_wrapper_runs(self):
        r = subprocess.run([sys.executable, "-B", str(GATE / "qvt-gate"), "--version"],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0)


if __name__ == "__main__":
    unittest.main()
