"""Exploratory subjectless candidates: lexical matching, context, and archives.

These matches are not adjudications of implicit/anonymous attribution.
The original paper-table3-v2 counts must remain separate.
"""
import ast
import collections
import copy
import json
import re
import types
import unittest
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parents[1]
SOURCE=(ROOT/"collector/main.py").read_text(encoding="utf-8")
ARCHIVE=(ROOT/"archive/main.py").read_text(encoding="utf-8")
TREE=ast.parse(SOURCE)
ARCHIVE_TREE=ast.parse(ARCHIVE)

def assignment(tree,name):
    return ast.literal_eval(next(n.value for n in tree.body if isinstance(n,ast.Assign)
        and any(isinstance(t,ast.Name) and t.id==name for t in n.targets)))

def functions(tree,names,ns):
    nodes=[]
    for n in tree.body:
        if isinstance(n,ast.FunctionDef) and n.name in names:
            node=copy.deepcopy(n)
            node.decorator_list=[]
            nodes.append(node)
    exec(compile(ast.Module(body=nodes,type_ignores=[]),"<source>","exec"),ns)

candidate_version=assignment(TREE,"SUBJECTLESS_CANDIDATE_VERSION")
rules=assignment(TREE,"SUBJECTLESS_CANDIDATE_RULES")
compiled=tuple((major,sub,label,re.compile(regex))
    for major,sub,label,regex in rules)
ns={"re":re,"SUBJECTLESS_CANDIDATE_COMPILED":compiled,
    "SUBJECTLESS_CANDIDATE_VERSION":candidate_version,
    "KST":ZoneInfo("Asia/Seoul"),"datetime":datetime}
functions(TREE,{"subjectless_candidate_fields","backfill_subjectless_candidates_batch"},ns)
extract=ns["subjectless_candidate_fields"]

class CandidateRules(unittest.TestCase):
    def test_six_preapproved_expressions_and_existing_types_only(self):
        labels=[r[2] for r in rules]
        self.assertEqual(labels,[
            "우려가 나온다","목소리가 나온다","의견이 나온다",
            "평가가 나온다","전망이 나온다","지적된다",
        ])
        self.assertEqual(len(set(labels)),6)
        self.assertEqual({(major,sub) for major,sub,*_ in rules},{
            ("출처소거형","자생발생형"),("출처소거형","피동형")
        })
        for forbidden in ["예상된다","전망된다","추정된다","비판이 나온다"]:
            self.assertNotIn(forbidden,labels)

    def test_all_six_candidates_normalize_variants(self):
        body=("취재를 종합하면 사실이 전해졌다.\n"
              "업계에서는 우려가 나온다. 우려도 나왔다. "
              "시민단체에서 목소리가 나왔다. 의견도 나온다. "
              "긍정적 평가가 나왔다. 전망이 나오고 있다. "
              "대책의 문제점이 지적된다. 한계도 지적됐다.")
        data=extract(body)
        self.assertEqual(data["subjectless_candidate_version"],candidate_version)
        self.assertEqual(data["subjectless_candidate_counts"],{
            "우려가 나온다":2,"목소리가 나온다":1,
            "의견이 나온다":1,"평가가 나온다":1,
            "전망이 나온다":1,"지적된다":2,
        })
        self.assertEqual(data["subjectless_candidate_type_counts"],{
            "출처소거형 / 자생발생형":6,"출처소거형 / 피동형":2
        })
        contexts=data["subjectless_candidate_contexts"]
        self.assertEqual(len(contexts),8)
        self.assertTrue(all(x["paragraph_no"]==2 for x in contexts))
        self.assertEqual(contexts[0]["previous_paragraph_end"],
                         "취재를 종합하면 사실이 전해졌다.")
        self.assertTrue(all(x["matched_text"] in x["context"] for x in contexts))

    def test_exclusions_and_source_visible_context_remain_candidates_only(self):
        body=("기상청은 정확한 전망을 밝혔다.\n"
              "해당 기관에서는 전망이 나왔다. "
              "예상된다, 전망된다, 추정된다. 비판이 나온다.")
        data=extract(body)
        self.assertEqual(data["subjectless_candidate_counts"],
                         {"전망이 나온다":1})
        self.assertIn("해당 기관",data["subjectless_candidate_contexts"][0]["context"])
        self.assertNotIn("source_missing",data)
        self.assertNotIn("is_subjectless",data)

    def test_false_positive_prefix_not_matched_and_examples_bounded(self):
        d=extract("취재를 종합하면 " + "우려가 나왔다. "*90)
        self.assertEqual(d["subjectless_candidate_counts"]["우려가 나온다"],90)
        self.assertEqual(len(d["subjectless_candidate_contexts"]),40)
        self.assertEqual(extract("취재를 종합하면 중립적이다.")["subjectless_candidate_counts"],{})

    def test_backfill_resume_is_bounded_and_idempotent(self):
        class Snap:
            def __init__(self,ref):
                self.reference=ref
                self.exists=ref.data is not None
            def to_dict(self):return self.reference.data
        class Ref:
            def __init__(self,path,data=None):
                self.path=path;self.data=data;self.writes=0
            def get(self):return Snap(self)
            def set(self,fields,merge=False):
                self.data={**(self.data or {}),**fields} if merge else fields
                self.writes+=1
        articles=[
            Ref("articles/a",{"status":"accepted","body_text_private":"우려가 나온다."}),
            Ref("articles/b",{"status":"accepted","body_text_private":"지적됐다."}),
            Ref("articles/c",{"status":"rejected","body_text_private":"우려가 나온다."}),
            Ref("articles/d",{"status":"accepted","body_text_private":""}),
        ]
        marker=Ref("maintenance_runs/"+candidate_version)
        class Query:
            def __init__(self,after=-1):self.after=after;self.limit_n=100
            def order_by(self,*args,**kwargs):return self
            def start_after(self,doc):
                self.after=next(i for i,r in enumerate(articles) if r.path==doc.reference.path)
                return self
            def limit(self,n):self.limit_n=n;return self
            def stream(self):
                return [r.get() for r in articles[self.after+1:self.after+1+self.limit_n]]
        class DB:
            def collection(self,name):
                return self if name=="maintenance_runs" else Query()
            def document(self,path):
                if path==candidate_version:return marker
                return next(r for r in articles if r.path==path)
        db=DB()
        c=ns["backfill_subjectless_candidates_batch"]
        c(db,2)
        self.assertEqual(marker.data["scanned_articles"],2)
        self.assertFalse(marker.data["done"])
        self.assertEqual(articles[0].data["subjectless_candidate_counts"],{"우려가 나온다":1})
        c(db,2)
        self.assertEqual(marker.data["scanned_articles"],4)
        c(db,2)
        self.assertTrue(marker.data["done"])
        self.assertEqual(marker.data["updated_articles"],2)
        self.assertEqual(marker.data["matched_articles"],2)
        self.assertEqual(marker.data["skipped_missing_body"],1)
        c(db,2)
        self.assertEqual(articles[0].writes,1)
        self.assertEqual(articles[1].writes,1)

    def test_research_archive_version_is_separate_from_paper(self):
        self.assertEqual(assignment(ARCHIVE_TREE,"CANDIDATE_VERSION"),candidate_version)
        mapping=assignment(ARCHIVE_TREE,"CANDIDATE_SUBTYPE")
        self.assertEqual(set(mapping),{r[2] for r in rules})
        self.assertEqual(mapping["지적된다"],"피동형")
        self.assertEqual(mapping["전망이 나온다"],"자생발생형")
        self.assertIn('day,CANDIDATE_VERSION,"출처소거형",sub,term',ARCHIVE)
        self.assertIn('day,"paper-table3-v2",major,sub,term',ARCHIVE)
        # Private exploratory counts are not read by the public API.
        api=(ROOT/"api/main.py").read_text(encoding="utf-8")
        self.assertNotIn("subjectless_candidate_counts",api)
        self.assertIn('"secondary_taxonomy_version") != "paper-table3-v2"',api)

if __name__=="__main__":unittest.main()
