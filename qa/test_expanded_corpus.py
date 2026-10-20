"""Lexical corpus expansion and URL de-duplication checks."""
import ast
import unittest
from pathlib import Path

source=Path("collector/main.py").read_text(encoding="utf-8")
tree=ast.parse(source)
constants={"PHRASE":"취재를 종합하면",
           "ADDITIONAL_PHRASE":"본지 취재 결과",
           "TARGET_PHRASES":("취재를 종합하면","본지 취재 결과")}
nodes=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in
       ("target_phrase_counts","contains_target_phrase","phrase_contexts","collect_target_candidates")]
ns=dict(constants)
exec(compile(ast.Module(body=nodes,type_ignores=[]),"collector/main.py","exec"),ns)

class ExpandedCorpus(unittest.TestCase):
    def test_both_expressions_and_context(self):
        sample="당일 취재를 종합하면 사실이었다. 본지 취재 결과 처음 확인됐다. 본지 취재 결과 재확인."
        counts=ns["target_phrase_counts"](sample)
        self.assertEqual(counts,{"취재를 종합하면":1,"본지 취재 결과":2})
        self.assertEqual(ns["phrase_contexts"]([sample])[0]["count"],3)
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
        self.assertEqual(called,['"취재를 종합하면"','"본지 취재 결과"'])
        self.assertEqual(len(rows),2)
        self.assertEqual(rows[0]["original_url"],"https://b.example/2")
        self.assertEqual(len(queries),2)

if __name__=="__main__":
    unittest.main()
