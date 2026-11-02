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

# Domain-based fallback mappings must remain identical across all three
# components: collector, public API and private Sheets exporter.
class DomainPublisherFallback(unittest.TestCase):
    def test_domain_mapping_codes_and_publisher_label_no_shadowing(self):
        import ast
        from pathlib import Path
        expected = {
            "kgnews.co.kr": "경기신문",
            "tvchosun.com": "TV조선",
            "ilyosisa.co.kr": "일요시사",
            "hankookilbo.com": "한국일보",
            "weeklytrade.co.kr": "한국무역신문",
            "geconomy.co.kr": "지이코노미",
            "wowtv.co.kr": "한국경제TV",
            "osen.co.kr": "OSEN",
            "m-economynews.com": "M이코노미뉴스",
        }
        for filename, symbol in [
            ("collector/main.py", "PUBLISHER_BY_HOST"),
            ("api/main.py", "PUBLISHER_DISPLAY_BY_DOMAIN"),
            ("archive/main.py", "PUBLISHER_DISPLAY_BY_DOMAIN"),
        ]:
            source = Path(filename).read_text(encoding="utf-8")
            tree = ast.parse(source)
            dictionaries = [node for node in tree.body if isinstance(node, ast.Assign)
                 and any(isinstance(k, ast.Name) and k.id == symbol for k in node.targets)]
            self.assertEqual(len(dictionaries), 1, filename)
            mapping = ast.literal_eval(dictionaries[0].value)
            for host, label in expected.items():
                self.assertEqual(mapping.get(host), label, (filename,host))
        archive = Path("archive/main.py").read_text(encoding="utf-8")
        self.assertIn("for phrase_label in NEW_TARGET_PHRASE_LABELS:", archive)
