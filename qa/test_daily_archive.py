"""Non-network regressions for Google Sheets export and full-text quality."""
import ast
import copy
import unittest
from pathlib import Path

source=Path("archive/main.py").read_text(encoding="utf-8")
tree=ast.parse(source)
names={"body_parts","body_quality","phrase_counts","norm_time","basename","display_name"}
nodes=[copy.deepcopy(x) for x in tree.body if isinstance(x,ast.FunctionDef) and x.name in names]
from datetime import datetime
from zoneinfo import ZoneInfo
from urllib.parse import urlparse
import re
ns={
    "BODY_LIMIT":47500,"MAX_BODY_PARTS":3,
    "parser":type("Parser",(),{"suspicious_body":staticmethod(lambda x:"__NEXT_DATA__" in x),
        "contains_target_phrase":staticmethod(lambda x:"취재를 종합하면" in x or "본지 취재 결과" in x)})(),
    "datetime":datetime,"KST":ZoneInfo("Asia/Seoul"),"re":re,"urlparse":urlparse,
}
exec(compile(ast.Module(body=nodes,type_ignores=[]),"archive/main.py","exec"),ns)

class TestArchive(unittest.TestCase):
    def test_body_overflow_no_silent_truncation(self):
        body="가"*(47500*2+4)
        parts=ns["body_parts"](body)
        self.assertEqual("".join(parts),body)
        self.assertEqual(len(parts),3)
        self.assertIsNone(ns["body_parts"]("나"*(47500*3+1)))
    def test_article_validation_rejects_metadata_and_wrong_body(self):
        quality=ns["body_quality"]
        ok,reason=quality({"body":"일반 기사 본문입니다. "*20})
        self.assertFalse(ok);self.assertEqual(reason,"TARGET_PHRASE_NOT_CONFIRMED")
        ok,reason=quality({"body":"__NEXT_DATA__ 취재를 종합하면 "+"뉴스 내용. "*30})
        self.assertFalse(ok);self.assertEqual(reason,"SCRIPT_OR_STRUCTURED_DATA")
        ok,reason=quality({"body":"취재를 종합하면 "+"기사 본문 내용. "*30})
        self.assertTrue(ok);self.assertEqual(reason,"")
    def test_publisher_aliases_do_not_mutate_stored_source(self):
        article={"publisher_original":"KBS 뉴스"}
        self.assertEqual(ns["display_name"](article,{"KBS 뉴스":"KBS"}),"KBS")
        self.assertEqual(article["publisher_original"],"KBS 뉴스")
        self.assertEqual(ns["display_name"]({"publisher_original":"ETODAY"},{}),"이투데이")
    def test_count_both_phrases_independently(self):
        article={"phrase_counts":{"취재를 종합하면":2,"본지 취재 결과":1}}
        self.assertEqual(ns["phrase_counts"](article),(2,1))
    def test_headers_match_sheet_columns(self):
        import re
        allfile=Path("archive/main.py").read_text()
        self.assertIn('"기사 목록":26',allfile)
        self.assertIn('"30분 수집 로그":16',allfile)
        self.assertIn('"언론사 수집 진단":12',allfile)
        self.assertIn('"수집 실패"',allfile)
        self.assertIn('collector_runs',allfile)
        self.assertIn('archive_body_text',allfile)
        self.assertIn('appendCells',allfile)

if __name__=="__main__":
    unittest.main()
