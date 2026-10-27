"""Publisher-name reporters must never enter rankings; existing Etoday mistakes are repaired."""
import ast
import re
import unittest
from pathlib import Path
from bs4 import BeautifulSoup
from collector import main as c

ROOT=Path(__file__).resolve().parents[1]


class EtodayAttribution(unittest.TestCase):
    def test_etoday_normalizes_as_publisher(self):
        self.assertEqual(c.normalize_publisher("ETODAY","www.etoday.co.kr"),"이투데이")
        self.assertEqual(c.normalize_publisher("이투데이","m.etoday.co.kr"),"이투데이")

    def test_masthead_is_not_person_even_when_publisher_metadata_differs(self):
        for raw in ("이투데이","이투데이 기자","ETODAY","E-TODAY","이투데이  기자"):
            with self.subTest(raw=raw):
                self.assertEqual(c.normalize_reporter_text(raw,"ETODAY","www.etoday.co.kr"),"")
        self.assertEqual(c.normalize_reporter_text("김재학","이투데이","www.etoday.co.kr"),"김재학")
        self.assertEqual(c.normalize_reporter_text(
            "경기인천취재본부 김재학 기자","이투데이","www.etoday.co.kr"),"김재학")
        self.assertEqual(c.normalize_reporter_text("이세령 기자","이투데이","www.etoday.co.kr"),"이세령")

    def test_visible_byline_overrides_generic_site_author(self):
        soup=BeautifulSoup('''<html><head>
        <meta name="author" content="이투데이">
        <meta property="og:site_name" content="ETODAY">
        </head><body><h1>취재 기사</h1>
        <div class="writer"><a href="/reporter?eid=Jo801005">경기인천취재본부 김재학 기자</a></div>
        <div class="article_body"><p>내용은 별도 문단에 있습니다.</p></div></body></html>''',"html.parser")
        self.assertEqual(c.infer_reporters(soup,{"author":{"name":"이투데이"}},"이투데이","www.etoday.co.kr"),"김재학")

    def test_generic_author_without_named_person_is_unknown(self):
        soup=BeautifulSoup('<html><head><meta name="author" content="이투데이"></head>'+
                           '<body><div class="reporter">이투데이</div></body></html>',"html.parser")
        self.assertEqual(c.infer_reporters(soup,{"author":{"name":"ETODAY"}},"이투데이","www.etoday.co.kr"),"")

    def test_historical_correction_only_for_exact_verified_url(self):
        def item(url,name="이투데이",naver=""):
            return {"original_url":url,"publisher_original":"ETODAY",
                    "reporters_original":name,"reporters_resolved":name,"reporters_naver":naver}
        for id in ("2640275","2640213","2640198","2640195"):
            with self.subTest(id=id):
                x=c.etoday_reporter_correction(item("https://www.etoday.co.kr/news/view/"+id))
                self.assertEqual(x["reporters_resolved"],"김재학")
                self.assertEqual(x["reporter_repair_status"],"VERIFIED")
                self.assertEqual(x["reporter_source"],"VERIFIED_BYLINE")
        unverified=c.etoday_reporter_correction(item("https://www.etoday.co.kr/news/view/2640173"))
        self.assertEqual(unverified["reporters_resolved"],"")
        self.assertEqual(unverified["reporter_repair_status"],"UNKNOWN_NOT_GUESSED")
        self.assertEqual(unverified["reporter_invalid_previous"],"이투데이")
        self.assertEqual(
            c.etoday_reporter_correction(item("https://www.etoday.co.kr/news/view/2640187",naver="김재학")),
            None if False else {
                "reporters_resolved":"김재학",
                "reporters_original":"",
                "reporter_source":"NAVER",
                "reporter_invalid_previous":"이투데이",
                "reporter_repair_status":"NAVER",
                "reporter_repaired_at":c.firestore.SERVER_TIMESTAMP,
            })
        self.assertIsNone(c.etoday_reporter_correction(item("https://www.hani.co.kr/news/view/2640275")))
        self.assertIsNone(c.etoday_reporter_correction(item("https://www.etoday.co.kr/news/view/2640275",name="김재학")))

    def test_api_and_archive_never_rank_publication_as_writer(self):
        for path,func in [("api/main.py","split_reporters"),("archive/main.py","reporters")]:
            root=ast.parse((ROOT/path).read_text(encoding="utf-8"))
            node=next(n for n in root.body if isinstance(n,ast.FunctionDef) and n.name==func)
            ns={"re":re,"display_name":lambda article,aliases:"이투데이"}
            exec(compile(ast.Module(body=[node],type_ignores=[]),path,"exec"),ns)
            if func=="split_reporters":
                self.assertEqual(ns[func]("이투데이",publisher="이투데이"),[])
                self.assertEqual(ns[func]("김재학",people_only=True,publisher="이투데이"),["김재학"])
            else:
                self.assertEqual(ns[func]({"reporters_resolved":"이투데이"}),[])
                self.assertEqual(ns[func]({"reporters_resolved":"김재학"}),["김재학"])

    def test_collector_calls_one_time_repair_before_new_collection(self):
        src=(ROOT/"collector/main.py").read_text(encoding="utf-8")
        self.assertIn("repair_etoday_reporters_once(db)",src)
        self.assertIn('ETODAY_REPORTER_REPAIR_ID = "etoday-publisher-as-byline-20261027-v1"',src)


if __name__=="__main__":unittest.main()
