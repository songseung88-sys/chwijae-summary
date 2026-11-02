"""No Nocut duplicate article may be counted twice because of tracking codes."""
import ast
import hashlib
import importlib.util
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def load_identity(path):
    spec=importlib.util.spec_from_file_location("article_identity",path)
    obj=importlib.util.module_from_spec(spec);spec.loader.exec_module(obj)
    return obj

collector=load_identity(ROOT/"collector/article_identity.py")
api=load_identity(ROOT/"api/article_identity.py")

class CanonicalArticleIdentity(unittest.TestCase):
    def test_identical_functions_in_all_runtimes(self):
        self.assertEqual((ROOT/"collector/article_identity.py").read_bytes(),
                         (ROOT/"api/article_identity.py").read_bytes())
        for url in (
            "https://www.nocutnews.co.kr/news/6597419?utm_source=naver&utm_campaign=one",
            "https://www.nocutnews.co.kr/news/6597419?utm_source=naver&utm_campaign=two",
            "https://www.etoday.co.kr/news/view/123456?utm_campaign=a",
            "https://example.co.kr/post?idxno=123&utm_campaign=b",
        ):
            self.assertEqual(collector.canonical_article_url(url),api.canonical_article_url(url))

    def test_real_three_way_duplicate(self):
        inputs=[
            "https://www.nocutnews.co.kr/news/6597419?utm_source=naver&utm_medium=article&utm_campaign=20261027063019",
            "https://www.nocutnews.co.kr/news/6597419?utm_source=naver&utm_medium=article&utm_campaign=20261027070719",
            "https://www.nocutnews.co.kr/news/6597419?utm_source=naver&utm_medium=article&utm_campaign=20261027032823",
        ]
        self.assertEqual({collector.canonical_article_url(u) for u in inputs},
                         {"https://www.nocutnews.co.kr/news/6597419"})
        self.assertEqual(len({hashlib.sha256(collector.canonical_article_url(u).encode()).hexdigest()[:32] for u in inputs}),1)
        self.assertEqual(len({hashlib.sha256(u.encode()).hexdigest()[:32] for u in inputs}),3)

    def test_identifiable_query_is_preserved(self):
        self.assertEqual(collector.canonical_article_url("https://publisher.example/BP?command=article_view&num=123&utm_campaign=abc"),
                         "https://publisher.example/BP?command=article_view&num=123")
        a="https://publisher.example/BP?command=article_view&num=123"
        b="https://publisher.example/BP?command=article_view&num=124"
        self.assertNotEqual(collector.canonical_article_url(a),collector.canonical_article_url(b))
        self.assertNotEqual(collector.canonical_article_url("https://www.nocutnews.co.kr/news/6597419"),
                            collector.canonical_article_url("https://www.nocutnews.co.kr/news/6597418"))
        self.assertEqual(collector.canonical_article_url("https://www.nocutnews.co.kr/news/6597419/?utm_campaign=third"),
                         "https://www.nocutnews.co.kr/news/6597419")

    def test_other_domain_semantic_params_and_no_queries(self):
        self.assertEqual(collector.canonical_article_url("https://media.example.com/story?id=33&utm_source=n"),
                         "https://media.example.com/story?id=33")
        self.assertEqual(collector.canonical_article_url("https://media.example.com/story?id=34"),
                         "https://media.example.com/story?id=34")
        self.assertEqual(collector.canonical_article_url("https://media.example.com/story?id=33"),
                         "https://media.example.com/story?id=33")
        self.assertEqual(collector.canonical_article_url(""),"")

    def test_old_accepted_documents_preserve_complete_record(self):
        base="https://www.nocutnews.co.kr/news/6597419"
        rows=[
            {"id":"old1","original_url":base+"?utm_campaign=a","status":"accepted",
             "body_text_private":"본문","archive_body_status":"수집 성공",
             "archive_body_text":"보관된 전체 본문","reporters_resolved":"홍길동"},
            {"id":"old2","original_url":base+"?utm_campaign=b","status":"accepted",
             "body_text_private":"본문"},
            {"id":"old3","original_url":base+"?utm_campaign=c","status":"accepted",
             "body_text_private":"본문","reporters_resolved":"홍길동"},
            {"id":"independent","original_url":base.replace("6597419","6597418"),
             "status":"accepted"},
        ]
        winner=collector.unique_articles(rows)
        self.assertEqual(len(winner),2)
        self.assertEqual(winner[0]["id"],"old1")
        self.assertEqual(winner[1]["id"],"independent")
        self.assertEqual(collector.unique_articles(winner),winner)

    def test_collector_dedups_before_fetch_and_ids(self):
        src=(ROOT/"collector/main.py").read_text()
        self.assertIn('key = canonical_article_url(original_url or item.get("link", ""))',src)
        self.assertIn('key = canonical_article_url(item.get("original_url") or item.get("naver_url"))',src)
        self.assertIn('hashlib.sha256(canonical_article_url(url).encode("utf-8"))',src)

    def test_dashboard_and_archive_dedup_before_totals(self):
        api_src=(ROOT/"api/main.py").read_text()
        archive_src=(ROOT/"archive/main.py").read_text()
        self.assertIn('return unique_articles(out)',api_src)
        self.assertIn('return unique_articles(rows)',archive_src)
        self.assertIn('self.article_url_keys.get(canonical)',archive_src)
        self.assertIn('canonical_article_url(row[18])',archive_src)
        self.assertIn('COPY collector/article_identity.py ./article_identity.py',
                      (ROOT/"archive/Dockerfile").read_text())

if __name__=="__main__":unittest.main()
