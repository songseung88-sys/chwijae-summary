"""Non-network regression tests for future-only Naver-first archive preference."""
import ast
import copy
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

SOURCE = Path("archive/main.py").read_text(encoding="utf-8")
TREE = ast.parse(SOURCE)
NAMES = {"archive_body", "body_quality"}
NODES = [copy.deepcopy(n) for n in TREE.body
         if isinstance(n, ast.FunctionDef) and n.name in NAMES]
VERSION = ast.literal_eval(next(n.value for n in TREE.body
    if isinstance(n, ast.Assign)
    and any(isinstance(t, ast.Name) and t.id == "ARCHIVE_VERSION"
            for t in n.targets)))


class FakeRef:
    def __init__(self):
        self.writes = []
    def set(self, obj, merge=False):
        self.writes.append((obj, merge))


class FakeDB:
    def __init__(self):
        self.ref = FakeRef()
        self.collections = []
    def collection(self, name):
        self.collections.append(name)
        return self
    def document(self, name):
        self.document_id = name
        return self.ref


class ArchiveNaverFirst(unittest.TestCase):
    def build(self, responses):
        calls = []
        def extractor(source):
            def run(url):
                calls.append((source, url))
                return responses[source]
            return run
        parser = SimpleNamespace(
            parse_naver=extractor("네이버뉴스"),
            parse_original=extractor("원문"),
            contains_target_phrase=lambda text: "취재를 종합하면" in text,
            suspicious_body=lambda text: False,
        )
        ns = dict(parser=parser, datetime=datetime, KST=ZoneInfo("Asia/Seoul"),
                  ARCHIVE_VERSION=VERSION, BODY_LIMIT=47500, MAX_BODY_PARTS=3)
        exec(compile(ast.Module(body=NODES, type_ignores=[]),
                     "archive/main.py", "exec"), ns)
        return ns["archive_body"], calls

    @staticmethod
    def good(source):
        return {"body": "취재를 종합하면 " + source + "의 검증된 기사 본문. " * 17}

    @staticmethod
    def article(**updates):
        return dict({"id":"a123", "original_url":"https://publisher.example/news/1",
                     "naver_url":"https://n.news.naver.com/mnews/article/123/12345"},
                    **updates)

    def test_both_available_naver_wins_without_original_request(self):
        archive, calls = self.build({
            "네이버뉴스":self.good("네이버"),
            "원문":self.good("언론사"),
        })
        db = FakeDB()
        body, source, status, err, checked = archive(self.article(), db)
        self.assertEqual(source, "네이버뉴스")
        self.assertEqual(body, self.good("네이버")["body"].strip())
        self.assertEqual(status, "수집 성공")
        self.assertEqual(err, "")
        self.assertTrue(checked)
        self.assertEqual(calls, [("네이버뉴스",self.article()["naver_url"])])
        self.assertEqual(len(db.ref.writes),1)
        self.assertEqual(db.ref.writes[0][0]["archive_body_source"],"네이버뉴스")
        self.assertEqual(db.ref.writes[0][0]["archive_body_text"],body)
        self.assertEqual(db.ref.writes[0][0]["archive_version"],VERSION)
        self.assertTrue(db.ref.writes[0][1])

    def test_absent_naver_link_uses_publisher_directly(self):
        archive, calls = self.build({"원문":self.good("언론사")})
        db = FakeDB()
        body, source, status, err, _ = archive(self.article(naver_url=""), db)
        self.assertEqual(source,"원문")
        self.assertEqual(status,"수집 성공")
        self.assertEqual(calls,[("원문",self.article()["original_url"])])
        self.assertIn("언론사",body)

    def test_invalid_naver_body_falls_back_to_publisher(self):
        archive, calls = self.build({
            "네이버뉴스":{"body":"짧거나 검색 표현이 없는 글"},
            "원문":self.good("언론사"),
        })
        db = FakeDB()
        body, source, status, err, _ = archive(self.article(), db)
        self.assertEqual([source for source, _url in calls],["네이버뉴스","원문"])
        self.assertEqual(source,"원문")
        self.assertEqual(status,"수집 성공")
        self.assertEqual(err,"")
        self.assertIn("언론사",body)
        self.assertEqual(db.ref.writes[0][0]["archive_body_source"],"원문")

    def test_both_invalid_logs_attempts_in_naver_first_order(self):
        archive, calls = self.build({
            "네이버뉴스":{"body":"bad","error":"NAVER_PARSE_FAILED"},
            "원문":{"body":"bad","error":"PUBLISHER_PARSE_FAILED"},
        })
        db = FakeDB()
        body, source, status, error, _ = archive(self.article(), db)
        self.assertEqual([source for source, _url in calls],["네이버뉴스","원문"])
        self.assertEqual(body,"수집 실패")
        self.assertEqual(source,"")
        self.assertEqual(status,"수집 실패")
        self.assertEqual(error,"네이버뉴스:NAVER_PARSE_FAILED; 원문:PUBLISHER_PARSE_FAILED")
        self.assertEqual(db.ref.writes[0][0]["archive_body_status"],"수집 실패")

    def test_preexisting_successful_publisher_archive_is_unchanged(self):
        archive, calls = self.build({"네이버뉴스":self.good("네이버")})
        db = FakeDB()
        old = self.article(archive_body_text="기존에 원문으로 저장한 본문",
                           archive_body_source="원문",
                           archive_body_status="수집 성공",
                           archive_body_checked_at="2026-10-20T09:00:00+09:00",
                           archive_version="previous")
        output = archive(old, db)
        self.assertEqual(output,("기존에 원문으로 저장한 본문","원문","수집 성공","",
                                 "2026-10-20T09:00:00+09:00"))
        self.assertEqual(calls,[])
        self.assertEqual(db.ref.writes,[])
        self.assertEqual(old["archive_version"],"previous")

    def test_preexisting_successful_naver_archive_is_unchanged(self):
        archive, calls = self.build({})
        db = FakeDB()
        old = self.article(archive_body_text="기존 네이버 본문",
                           archive_body_source="네이버뉴스",
                           archive_body_status="수집 성공")
        self.assertEqual(archive(old, db)[0],"기존 네이버 본문")
        self.assertFalse(calls)
        self.assertFalse(db.ref.writes)

    def test_previous_failure_is_eligible_for_new_naver_preference(self):
        archive, calls = self.build({"네이버뉴스":self.good("네이버")})
        db = FakeDB()
        old = self.article(archive_body_text="과거에 불완전하게 저장한 본문",
                           archive_body_source="원문",
                           archive_body_status="수집 실패")
        body, source, status, _error, _checked = archive(old, db)
        self.assertEqual(source,"네이버뉴스")
        self.assertEqual(status,"수집 성공")
        self.assertIn("네이버",body)
        self.assertEqual(len(calls),1)


if __name__ == "__main__":
    unittest.main()
