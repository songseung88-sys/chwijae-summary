"""Lexical corpus expansion and URL de-duplication checks."""
import ast
import re
import unittest
from pathlib import Path

source=Path("collector/main.py").read_text(encoding="utf-8")
tree=ast.parse(source)
constants={"PHRASE":"취재를 종합하면",
           "ADDITIONAL_PHRASE":"본지 취재 결과",
           "TARGET_PHRASES":("취재를 종합하면","본지 취재 결과")}
nodes=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in
       ("target_phrase_counts","contains_target_phrase","phrase_contexts","collect_target_candidates")]
pattern_assign=next(n for n in tree.body if isinstance(n,ast.Assign)
    and any(isinstance(t,ast.Name) and t.id=="ADDITIONAL_PHRASE_PATTERN" for t in n.targets))
ns=dict(constants,re=re)
exec(compile(ast.Module(body=[pattern_assign]+nodes,type_ignores=[]),"collector/main.py","exec"),ns)

class ExpandedCorpus(unittest.TestCase):
    def test_both_expressions_and_context(self):
        sample="당일 취재를 종합하면 사실이었다. 본지 취재 결과 처음 확인됐다. 본지 취재 결과 재확인."
        counts=ns["target_phrase_counts"](sample)
        self.assertEqual(counts,{"취재를 종합하면":1,"본지 취재 결과":2})
        self.assertEqual(ns["phrase_contexts"]([sample])[0]["count"],3)
        # Real-world variant in a rejected Kado.net source must be canonicalized.
        self.assertEqual(ns["target_phrase_counts"]("19일 본지 취재결과 춘천시는 시비를 투입했다.")["본지 취재 결과"],1)
        self.assertTrue(ns["contains_target_phrase"]("19일 본지 취재결과 춘천시는 시비를 투입했다."))
        self.assertTrue(ns["contains_target_phrase"]("본지 취재 결과 결과가 나왔다"))
        self.assertFalse(ns["contains_target_phrase"]("기자에 따르면"))

    def test_independent_queries_deduplicate_urls(self):
        called=[]
        def fetch(_id,_secret,_day,query):
            called.append(query)
            common={"original_url":"https://a.example/1","api_pubdate":"2026-10-20T10:00:00+09:00"}
            new={"original_url":"https://b.example/2","api_pubdate":"2026-10-20T10:20:00+09:00"}
            return [common] if "취재를 종합하면" in query else [common,new]
        ns["fetch_candidates"]=fetch
        rows,queries=ns["collect_target_candidates"]("id","secret","2026-10-20",100)
        self.assertEqual(called,['"취재를 종합하면"','"본지 취재 결과"','"본지 취재결과"'])
        self.assertEqual(len(rows),2)
        self.assertEqual(rows[0]["original_url"],"https://b.example/2")
        self.assertEqual(len(queries),3)

if __name__=="__main__":
    unittest.main()
