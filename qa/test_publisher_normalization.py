"""API publisher-display regression tests (no Firestore connection required)."""
import ast
import re
import unittest
from pathlib import Path

source = Path("api/main.py").read_text(encoding="utf-8")
module = ast.parse(source)
fn = next(
    node for node in module.body
    if isinstance(node, ast.FunctionDef) and node.name == "normalize_publisher"
)
ns = {"re": re}
exec(compile(ast.Module(body=[fn], type_ignores=[]), "api/main.py", "exec"), ns)
normalize = ns["normalize_publisher"]


class TestPublisherNormalization(unittest.TestCase):
    def test_etoday_aliases(self):
        for raw in ("ETODAY", "etoday", "Etoday", "E-TODAY"):
            with self.subTest(raw=raw):
                self.assertEqual(normalize(raw), "이투데이")

    def test_jungbu_website_slogan(self):
        self.assertEqual(
            normalize("중부일보 - 경기·인천의 든든한 친구"), "중부일보"
        )
        self.assertEqual(normalize("중부일보 – 경기 인천"), "중부일보")
        self.assertEqual(normalize("중부일보"), "중부일보")

    def test_dont_strip_other_hyphenated_publishers(self):
        self.assertEqual(normalize("A-B 뉴스"), "A-B 뉴스")
        self.assertEqual(normalize("중부일보리뷰 - 매거진"), "중부일보리뷰 - 매거진")

    def test_unknown_or_empty(self):
        self.assertEqual(normalize("  "), "미확인")
        self.assertEqual(normalize(None), "미확인")


if __name__ == "__main__":
    unittest.main()
