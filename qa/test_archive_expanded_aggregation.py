"""End-to-end, no-cloud regression of expanded Sheets archive aggregation."""
import ast
import collections
import re
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path

source = Path("archive/main.py").read_text(encoding="utf-8")
tree = ast.parse(source)
functions = {"phrase_counts", "only_new_target_phrases", "collect_rows",
             "archive_body", "archive_body_needs_network",
             "collector_body_candidate", "save_archive_body", "body_quality"}
constants = {"TARGET_PHRASE_RULES", "TARGET_PHRASE_COMPILED",
             "TARGET_PHRASE_LABELS", "NEW_TARGET_PHRASE_LABELS"}
nodes = [n for n in tree.body
         if (isinstance(n, ast.FunctionDef) and n.name in functions)
         or (isinstance(n, ast.Assign) and any(
             isinstance(t, ast.Name) and t.id in constants for t in n.targets))]
ns = {
    "re": re, "collections": collections,
    "datetime": datetime, "KST": timezone(timedelta(hours=9)),
    "BODY_LIMIT": 47500, "MAX_BODY_PARTS": 3,
    "ARCHIVE_VERSION": "test-collector-cache",
    "SHEET_HEADERS": {name: 0 for name in
        ("일별 통계", "언론사별", "기자별", "주제별", "무주체형 표현",
         "기사 목록", "동기화 기록", "30분 수집 로그",
         "언론사 수집 진단", "의견 보내기")},
    "CANDIDATE_VERSION": "subjectless-candidate-v1-20261028",
    "CANDIDATE_SUBTYPE": {"우려가 나온다": "자생발생형"},
    "basename": lambda a: a.get("publisher_original") or "",
    "display_name": lambda a, aliases: a.get("publisher_original") or "",
    "reporters": lambda a: [a.get("reporters_resolved") or ""] if a.get("reporters_resolved") else [],
    "body_parts": lambda text: [text, "", ""],
    "parser": type("P", (), {"SUBJECTLESS_RULES": [
        ("출처소거형", "피동형", "알려졌다", "알려졌다")],
        "SUBJECTLESS_OTHER_RULES": [],
        "contains_target_phrase": staticmethod(lambda s: "취재에 따르면" in s),
        "suspicious_body": staticmethod(lambda s: False),
        "parse_naver": staticmethod(lambda url: (_ for _ in ()).throw(
            AssertionError("Unexpected HTTP NAVER request"))),
        "parse_original": staticmethod(lambda url: (_ for _ in ()).throw(
            AssertionError("Unexpected HTTP publisher request"))),
        })(),
}
exec(compile(ast.Module(body=nodes, type_ignores=[]),
             "archive/main.py", "exec"), ns)


class ArchiveExpandedAggregation(unittest.TestCase):
    def test_260_cached_bodies_recover_even_with_zero_network_budget(self):
        class FakeDB:
            def __init__(self):
                self.writes = {}
            def collection(self, name):
                self.collection_name = name
                return self
            def document(self, name):
                self.document_id = name
                return self
            def set(self, record, merge=False):
                assert merge and self.collection_name == "articles"
                self.writes[self.document_id] = record

        fake = FakeDB()
        ns["DB"] = fake
        text = "취재에 따르면, 이 기사는 실제로 수집된 본문이다. " * 10
        articles = [{
            "id": "cached-" + str(i),
            "_date": "2026-11-07",
            "api_pubdate": "2026-11-07T09:00:00+09:00",
            "publisher_original": "시험신문",
            "body_text_private": text,
            "content_basis": "ORIGINAL",
            "original_url": "https://example.org/article/" + str(i),
            "naver_url": "",
            "phrase_counts": {"취재에 따르면": 10},
        } for i in range(260)]
        output, http_attempts = ns["collect_rows"](
            articles, {}, "test-2026-11-09", max_fetch=0)
        self.assertEqual(http_attempts, 0)
        self.assertEqual(len(fake.writes), 260)
        self.assertEqual(len(output["기사 목록"]), 260)
        self.assertEqual(
            {row[23] for row in output["기사 목록"]}, {"수집 성공"})
        self.assertEqual(
            {row[22] for row in output["기사 목록"]}, {"원문"})
        self.assertTrue(all(row[21] == text.strip() for row in output["기사 목록"]))
        self.assertEqual(output["일별 통계"][0][1], 260)

    def test_new_only_article_and_subjectless_scopes(self):
        date = "2026-10-29"
        base = {"_date": date, "publisher_original": "시험신문",
                "reporters_resolved": "홍길동", "api_pubdate": date,
                "archive_body_status": "수집 성공",
                "archive_body_source": "네이버뉴스",
                "secondary_taxonomy_version": "paper-table3-v2",
                "subjectless_candidate_version": "subjectless-candidate-v1-20261028",
                "taxonomy_version": ""}
        new = dict(base, id="new",
            body_text_private="취재에 따르면 A. 취재에 따르면 B.",
            archive_body_text="취재에 따르면 A. 취재에 따르면 B.",
            secondary_expressions={"알려졌다": 1},
            subjectless_candidate_counts={"우려가 나온다": 2})
        old = dict(base, id="old",
            body_text_private="취재를 종합하면 C.",
            archive_body_text="취재를 종합하면 C.",
            secondary_expressions={}, subjectless_candidate_counts={})
        out, body_fetches = ns["collect_rows"]([new, old], {}, "timestamp", 0)
        self.assertEqual(body_fetches, 0)
        rows = {row[0]: row for row in out["기사 목록"]}
        # H/I remain historical counts, J is all six, AD:AG are new counts.
        self.assertEqual(rows["new"][4], "시험신문")
        self.assertEqual(rows["old"][4], "시험신문")
        self.assertEqual(rows["new"][7:10], [0, 0, 2])
        self.assertEqual(rows["new"][29:33], [2, 0, 0, 0])
        self.assertEqual(rows["old"][7:10], [1, 0, 1])
        daily = out["일별 통계"][0]
        self.assertEqual(daily[1], 2)
        self.assertEqual(daily[12], 1)  # paper Table 3 only
        self.assertEqual(daily[15:19], [1, 0, 0, 0])
        self.assertEqual(daily[19:23], [2, 0, 0, 0])
        self.assertEqual(daily[23:27], [3, 1, 2, 3])  # all, new-only, candidate, combined
        publisher = out["언론사별"][0]
        self.assertEqual(publisher[11:15], [1, 0, 0, 0])
        self.assertEqual(publisher[15:19], [2, 0, 0, 0])
        self.assertEqual(publisher[19:21], [3, 1])
        by_version = {(row[1], row[4]): row[5]
                      for row in out["무주체형 표현"]}
        self.assertEqual(by_version[("paper-table3-v2", "알려졌다")], 1)
        self.assertEqual(by_version[("subjectless-candidate-v1-20261028",
                                    "우려가 나온다")], 2)


if __name__ == "__main__":
    unittest.main()
