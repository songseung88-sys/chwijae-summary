"""Six-target expansion stays aligned across collector and API; no Firestore calls."""
import ast
import re
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def load_targets(path,fn_names):
    tree=ast.parse((ROOT/path).read_text(encoding="utf-8"))
    names={"PHRASE","ADDITIONAL_PHRASE","TARGET_PHRASE_RULES",
           "TARGET_PHRASE_COMPILED","LEGACY_TARGET_PHRASES","TARGET_PHRASE_VERSION",
           "TARGET_SEARCH_QUERIES"}
    nodes=[n for n in tree.body if isinstance(n,ast.Assign) and
           any(isinstance(t,ast.Name) and t.id in names for t in n.targets)]
    nodes += [n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in fn_names]
    ns={"re":re}
    exec(compile(ast.Module(body=nodes,type_ignores=[]),path,"exec"),ns)
    return ns

class TargetPhraseExpansion(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.collector=load_targets("collector/main.py",{"target_phrase_counts","contains_target_phrase",
                                                        "phrase_contexts","subjectless_type_counts",
                                                        "collect_target_candidates"})
        cls.api=load_targets("api/main.py",{"target_counts_for_article"})

    def test_collector_api_rules_identical(self):
        self.assertEqual(self.collector["TARGET_PHRASE_RULES"],self.api["TARGET_PHRASE_RULES"])
        self.assertEqual(self.collector["TARGET_PHRASE_VERSION"],self.api["TARGET_PHRASE_VERSION"])
        self.assertEqual(len(self.collector["TARGET_PHRASE_RULES"]),6)
        self.assertEqual(self.collector["LEGACY_TARGET_PHRASES"],
                         ("취재를 종합하면","본지 취재 결과"))

    def test_whitespace_variants_count_as_one_canonical_category(self):
        sample=("취재를 종합하면 사실입니다. 본지 취재 결과 확인됐습니다. "
                "본지 취재결과도 확인됐습니다. 취재에 따르면 그렇습니다. "
                "취재한 결과 제도가 달랐습니다. 취재를 한 결과 사실이었습니다. "
                "본보 취재 결과 밝혀졌습니다. 본보 취재결과도 드러났습니다. "
                "본지 확인 결과 위반이었습니다. 본지 확인결과 역시 위반입니다.")
        expected={
            "취재를 종합하면":1,"본지 취재 결과":2,"취재에 따르면":1,
            "취재한 결과":2,"본보 취재 결과":2,"본지 확인 결과":2,
        }
        self.assertEqual(self.collector["target_phrase_counts"](sample),expected)
        self.assertEqual(self.api["target_counts_for_article"](
            {"body_text_private":sample}),expected)
        self.assertTrue(self.collector["contains_target_phrase"](sample))
        self.assertEqual(self.collector["phrase_contexts"]([sample])[0]["count"],10)

    def test_new_only_news_is_eligible_but_generic_news_is_not(self):
        for line in ("취재에 따르면 사건이 확인됐다.","취재한 결과 새로운 사실이 드러났다.",
                     "본보 취재 결과 사실이 밝혀졌다.","본지 확인 결과 부정이 있었다."):
            with self.subTest(line=line):
                self.assertTrue(self.collector["contains_target_phrase"](line))
        for line in ("관계자에 따르면 그랬다.","취재할 결과를 기다린다.","본지 확인 기자"):
            self.assertFalse(self.collector["contains_target_phrase"](line))

    def test_historical_without_body_uses_saved_counts_only(self):
        saved={"phrase_counts":{"취재를 종합하면":1,"본지 취재 결과":1}}
        counts=self.api["target_counts_for_article"](saved)
        self.assertEqual(sum(counts.values()),2)
        self.assertEqual(counts["취재에 따르면"],0)

    def test_group_overlaps_do_not_double_headline(self):
        docs=[
            {"id":"a","body_text_private":"취재를 종합하면 본지 취재 결과를 확인했다."},
            {"id":"b","body_text_private":"본보 취재 결과 새 사실이 나타났다."},
            {"id":"c","body_text_private":"취재한 결과 새로운 문제가 드러났다."}
        ]
        counts=[self.api["target_counts_for_article"](a) for a in docs]
        self.assertEqual(len(docs),3)
        self.assertEqual(sum(sum(c.values()) for c in counts),4)
        self.assertEqual(sum(any(c.get(k) for k in ("취재를 종합하면","본지 취재 결과")) for c in counts),1)

    def test_expanded_queries_have_priority_and_deduplicate_urls(self):
        q=self.collector["TARGET_SEARCH_QUERIES"]
        self.assertEqual(q[:3],('"취재를 종합하면"','"본지 취재 결과"','"본지 취재결과"'))
        self.assertEqual(len(q),10)
        calls=[]
        def fake(_id,_secret,_target,query):
            calls.append(query)
            rows=[{"original_url":"https://news.example/1","api_pubdate":"2026-10-28T10:00:00+09:00"}]
            if query=='"본지 확인 결과"':
                rows.append({"original_url":"https://news.example/2",
                             "api_pubdate":"2026-10-28T11:00:00+09:00"})
            return rows
        self.collector["fetch_candidates"]=fake
        entries,queries=self.collector["collect_target_candidates"]("id","sec","2026-10-28",100)
        self.assertEqual(len(calls),10)
        self.assertEqual(queries,list(q))
        self.assertEqual(len(entries),2)
        self.assertEqual(entries[0]["original_url"],"https://news.example/2")

    def test_legacy_subjectless_subtype_not_inflated(self):
        collector=self.collector
        collector["SUBJECTLESS_RULES"]=[]
        collector["SUBJECTLESS_OTHER_RULES"]=[]
        collector["secondary_counts"]=lambda body:{}
        a=collector["subjectless_type_counts"]("취재를 종합하면 본지 취재 결과",{})
        b=collector["subjectless_type_counts"]("취재를 종합하면 본지 취재 결과 취재한 결과",{})
        self.assertEqual(a["기자귀속형 / 종합형"],2)
        self.assertEqual(b["기자귀속형 / 종합형"],2)

    def test_dashboard_response_has_versioned_breakdown(self):
        src=(ROOT/"api/main.py").read_text(encoding="utf-8")
        for snippet in ('"legacy_today_count": legacy_today_count',
                        '"target_phrase_breakdown": target_breakdown',
                        '"target_phrase_counts": article_target_counts.get(',
                        '"target_phrase_expanded_since": "2026-10-28"'):
            self.assertIn(snippet,src)

if __name__=="__main__":unittest.main()
