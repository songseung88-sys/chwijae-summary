"""Approved six-expression public display, without changing paper-based counts."""
import ast
import copy
import re
import unittest
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
API_TREE=ast.parse((ROOT/"api/main.py").read_text(encoding="utf-8"))
COL_TREE=ast.parse((ROOT/"collector/main.py").read_text(encoding="utf-8"))
KST=timezone(timedelta(hours=9))

def assignment(tree,name):
    return ast.literal_eval(next(n.value for n in tree.body
        if isinstance(n,ast.Assign) and any(
            isinstance(t,ast.Name) and t.id==name for t in n.targets)))

VERSION=assignment(API_TREE,"SUBJECTLESS_CANDIDATE_VERSION")
RULES=assignment(API_TREE,"SUBJECTLESS_CANDIDATE_RULES")
LABELS={r[2] for r in RULES}
COMPILED=tuple((label,re.compile(pattern)) for _,_,label,pattern in RULES)

def load_function(tree,name,ns):
    node=copy.deepcopy(next(n for n in tree.body
        if isinstance(n,ast.FunctionDef) and n.name==name))
    node.decorator_list=[]
    exec(compile(ast.Module(body=[node],type_ignores=[]),"<test>","exec"),ns)
    return ns[name]

def fixture(ident,day,body,**kwargs):
    a={"id":ident, "_dt":datetime.fromisoformat(day+"T12:00:00+09:00"),
       "api_pubdate":day+"T12:00:00+09:00",
       "publisher_original":"신문사", "reporters_resolved":"검증기자",
       "body_text_private":body,"title_resolved":"기사 "+ident}
    a.update(kwargs)
    return a

class PublicSubjectlessExpansion(unittest.TestCase):
    def setUp(self):
        self.ns={"Counter":Counter,"re":re,"SUBJECTLESS_CANDIDATE_VERSION":VERSION,
                 "SUBJECTLESS_CANDIDATE_COMPILED":COMPILED,
                 "SUBJECTLESS_CANDIDATE_LABELS":LABELS}
        self.read=load_function(API_TREE,"public_subjectless_candidate_counts",self.ns)

    def test_collector_api_rules_stay_identical(self):
        self.assertEqual(VERSION,assignment(COL_TREE,"SUBJECTLESS_CANDIDATE_VERSION"))
        self.assertEqual(RULES,assignment(COL_TREE,"SUBJECTLESS_CANDIDATE_RULES"))
        self.assertEqual(LABELS,{"우려가 나온다","목소리가 나온다","의견이 나온다",
                                 "평가가 나온다","전망이 나온다","지적된다"})
        self.assertTrue(LABELS.isdisjoint({"예상된다","전망된다","추정된다","비판이 나온다"}))
        self.assertEqual({(major,sub) for major,sub,*_ in RULES},
                         {("출처소거형","자생발생형"),("출처소거형","피동형")})

    def test_stored_version_and_fallback_match_with_generic_source(self):
        body="업계에서는 우려가 나온다. 목소리가 나왔다. 지적됐다. 전망이 나왔다."
        source=fixture("new","2026-10-28",body)
        self.assertEqual(self.read(source),{
            "우려가 나온다":1,"목소리가 나온다":1,
            "지적된다":1,"전망이 나온다":1})
        stored=fixture("old","2026-10-28",body,
            subjectless_candidate_version=VERSION,
            subjectless_candidate_counts={"우려가 나온다":3,
                                           "목소리가 나온다":2})
        self.assertEqual(self.read(stored).get("우려가 나온다"),3)
        self.assertEqual(self.read(stored).get("목소리가 나온다"),2)
        stale=fixture("stale","2026-10-28",body,
            subjectless_candidate_version="old",
            subjectless_candidate_counts={"우려가 나온다":99})
        self.assertEqual(self.read(stale)["우려가 나온다"],1)
        self.assertEqual(self.read(fixture("none","2026-10-28",
            "예상된다 전망된다 추정된다 비판이 나온다.")),{})

    def test_dashboard_joins_public_rankings_but_keeps_separate_audit_counts(self):
        rows=[
            fixture("stored","2026-10-28","과거 본문",
                    secondary_taxonomy_version="paper-table3-v2",
                    secondary_expressions={"알려졌다":2,"표밖":7},
                    subjectless_candidate_version=VERSION,
                    subjectless_candidate_counts={"우려가 나온다":3,"전망이 나온다":1}),
            fixture("fallback","2026-10-28",
                "업계에서는 우려가 나온다. 목소리가 나왔다. 지적됐다. "
                "의견이 나왔다. 긍정적 평가가 나왔다.",
                    secondary_taxonomy_version="paper-table3-v2",
                    secondary_expressions={"알려졌다":1}),
            fixture("excluded","2026-10-28","예상된다 전망된다 추정된다 비판이 나온다."),
            fixture("other-day","2026-10-27","",
                    subjectless_candidate_version=VERSION,
                    subjectless_candidate_counts={"우려가 나온다":99}),
        ]
        ns={
            **self.ns,"date":date,"datetime":datetime,"timedelta":timedelta,"KST":KST,
            "Query":lambda default=None,**kwargs:default,
            "accepted_articles":lambda limit:rows,
            "publisher_display":lambda a,aliases:a["publisher_original"],
            "get_publisher_aliases":lambda:{},
            "split_reporters":lambda s,**kwargs:[s] if s else [],
            "get_site_config":lambda:{},
            "latest_successful_collection":lambda:None,
            "target_counts_for_article":lambda a:{"취재를 종합하면":1},
            "TARGET_PHRASE_COMPILED":[("취재를 종합하면",None)],
            "TARGET_PHRASE_VERSION":"test",
            "ADDITIONAL_PHRASE":"본지 취재 결과",
            "LEGACY_TARGET_PHRASES":("취재를 종합하면","본지 취재 결과"),
            "PAPER_SUBJECTLESS_LABELS":{"알려졌다"},
            "context_sentence":lambda s:s,
            "public_subjectless_candidate_counts":self.read,
            "summarize_core_phrase_positions":lambda rows: {"eligible_articles":0,"analyzed_articles":0},
        }
        result=load_function(API_TREE,"dashboard",ns)("2026-10-28")
        combined={r["name"]:r["count"] for r in result["secondary_expressions"]}
        original={r["name"]:r["count"] for r in result["secondary_expressions_paper"]}
        extension={r["name"]:r["count"] for r in result["secondary_expressions_extension"]}
        self.assertEqual(original,{"알려졌다":3})
        self.assertEqual(extension,{
            "우려가 나온다":4,"전망이 나온다":1,"목소리가 나온다":1,
            "지적된다":1,"의견이 나온다":1,"평가가 나온다":1
        })
        self.assertEqual(combined,dict(original,**extension))
        self.assertEqual(result["secondary_expressions"][0],
                         {"name":"우려가 나온다","count":4})
        self.assertEqual(result["secondary_methodology"]["extension_version"],VERSION)
        self.assertEqual(result["today_count"],3)
        for forbidden in ("예상된다","전망된다","추정된다","비판이 나온다","표밖"):
            self.assertNotIn(forbidden,combined)

if __name__=="__main__":unittest.main()
