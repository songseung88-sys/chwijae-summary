"""Regression tests for editable BigKinds counts and flexible About blocks."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "api"))
from bigkinds_content import (SOURCE, PUBLISHERS, YEARS, default_about_layout,
                              validate_about_layout, validate_history)


class BigkindsEditorTest(unittest.TestCase):
    def test_source_totals_match_every_publisher(self):
        dataset = validate_history(SOURCE)
        self.assertEqual(dataset["totals"], [77, 93, 156, 498, 2684, 3716, 4015, 3916, 3463, 4391])
        self.assertEqual(len(PUBLISHERS), 10)
        self.assertEqual(dataset["years"], YEARS)

    def test_edit_publisher_auto_changes_annual_total(self):
        dataset = {"years": YEARS, "publishers": {k: list(v) for k, v in SOURCE["publishers"].items()}}
        dataset["publishers"]["경향신문"][9] += 8
        result = validate_history(dataset)
        self.assertEqual(result["totals"][9], 4399)
        self.assertEqual(result["publishers"]["경향신문"][9], 1310)
        self.assertEqual(result["totals"][:9], SOURCE["totals"][:9])

    def test_reject_inconsistent_totals(self):
        dataset = {"years": YEARS, "publishers": SOURCE["publishers"], "totals": [0] * 10}
        with self.assertRaisesRegex(ValueError, "합계"):
            validate_history(dataset)

    def test_reject_missing_or_malformed_values(self):
        for bad in (-1, 1.2, True, "10", None, 1000001):
            values = {k: list(v) for k,v in SOURCE["publishers"].items()}
            values["한국일보"][2] = bad
            with self.subTest(value=bad), self.assertRaises(ValueError):
                validate_history({"years": YEARS, "publishers": values})
        values = {k: list(v) for k,v in SOURCE["publishers"].items()}
        del values["한국일보"]
        with self.assertRaises(ValueError):
            validate_history({"years": YEARS, "publishers": values})

    def test_migrate_existing_single_introduction(self):
        self.assertEqual(default_about_layout("기존 소개글"), [
            {"type": "text", "text": "기존 소개글"},
            {"type": "chart", "chart": "annual"},
            {"type": "chart", "chart": "publisher"},
        ])

    def test_reorder_and_multiple_introduction_blocks(self):
        ordered = [
            {"type": "chart", "chart": "annual"},
            {"type": "text", "text": "그래프 중간에 들어갈 글"},
            {"type": "chart", "chart": "publisher"},
            {"type": "text", "text": "<img src=x onerror=alert(1)>"},
        ]
        self.assertEqual(validate_about_layout(ordered), ordered)

    def test_reject_removed_or_duplicate_charts(self):
        for bad in (
            [{"type": "chart", "chart": "annual"}, {"type": "text", "text": "설명"}],
            [{"type": "chart", "chart": "annual"}, {"type": "chart", "chart": "annual"}],
            [{"type": "chart", "chart": "annual"}, {"type": "chart", "chart": "publisher"},
             {"type": "text", "text": "a" * 30001}],
        ):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                validate_about_layout(bad)


if __name__ == "__main__":
    unittest.main()
