"""Regression tests for real-world article-body selection with both phrase variants."""
import ast
import html
import json
import re
import unittest
from pathlib import Path
from bs4 import BeautifulSoup

source = Path("collector/main.py").read_text(encoding="utf-8")
tree = ast.parse(source)
def literal_assignment(key):
    node = next(n for n in tree.body if isinstance(n, ast.Assign) and
                any(isinstance(t, ast.Name) and t.id == key for t in n.targets))
    return ast.literal_eval(node.value)
names={"clean_text", "target_phrase_counts", "contains_target_phrase",
       "valid_body_container", "choose_body_container", "extract_paragraphs", "clean_structured_fragment"}
funcs=[n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names]
rule_nodes=[n for n in tree.body if isinstance(n,ast.Assign)
    and any(isinstance(t,ast.Name) and t.id in
            {"TARGET_PHRASE_RULES","TARGET_PHRASE_COMPILED","LEGACY_TARGET_PHRASES"}
            for t in n.targets)]
ns={
    "re": re, "html": html, "json": json,
    "PHRASE": "취재를 종합하면",
    "ADDITIONAL_PHRASE": "본지 취재 결과",
    "TARGET_PHRASES": ("취재를 종합하면", "본지 취재 결과", "취재에 따르면", "취재한 결과", "본보 취재 결과", "본지 확인 결과"),
    "COMMON_BODY_SELECTORS": literal_assignment("COMMON_BODY_SELECTORS"),
}
exec(compile(ast.Module(body=rule_nodes+funcs,type_ignores=[]),"collector/main.py","exec"),ns)


class SiteBodySelection(unittest.TestCase):
    def test_published_spaced_phrase_in_article_div(self):
        body="20일 본지 취재 결과 연구자료 보안 점검이 실시됐으며 절차 보완이 필요하다는 사실이 확인됐다."
        html_doc="<html><body><div class='article-body'><p>"+body+"</p><p>"+("추가 현장 취재로 정보를 확인했습니다. "*5)+"</p></div></body></html>"
        soup=BeautifulSoup(html_doc,"html.parser")
        container=ns["choose_body_container"](soup)
        self.assertIsNotNone(container)
        extracted=ns["extract_paragraphs"](container)
        self.assertTrue(any("본지 취재 결과" in x for x in extracted))

    def test_hankyoreh_general_article_without_target_phrase(self):
        sample="이 대통령이 경제정책에 대한 입장을 설명하고 금융시장 안정 방안을 발표했다. "
        html_doc="<html><article><div class='article-text'><p>"+sample*5+"</p></div></article></html>"
        soup=BeautifulSoup(html_doc,"html.parser")
        element=ns["choose_body_container"](soup)
        self.assertIn("article-text",element.get("class",[]))
        extracted=ns["extract_paragraphs"](element)
        self.assertGreater(len(" ".join(extracted)),100)
        self.assertFalse(ns["contains_target_phrase"](" ".join(extracted)))

    def test_etoday_article_body_not_hidden_search_overlay(self):
        content="영천 폐기물 문제와 관련해 추가 확인을 거쳐 관계기관들이 조치를 결정했다. "*6
        html_doc="<html><article class='search_layer'><div itemprop='articleBody'>"+content+"</div></article></html>"
        soup=BeautifulSoup(html_doc,"html.parser")
        element=ns["choose_body_container"](soup)
        self.assertIsNotNone(element)
        self.assertEqual(element.get("itemprop"),"articleBody")
        self.assertFalse(ns["valid_body_container"](soup.select_one("article.search_layer")))
        extracted=ns["extract_paragraphs"](element)
        self.assertGreater(len(" ".join(extracted)),150)

    def test_chosun_script_metadata_must_never_be_article_text(self):
        script='{"data":{"body":"'+'본지 취재를 종합하면 허위 본문입니다. '*15+'"}}'
        soup=BeautifulSoup('<html><head><script id="fusion-metadata" type="application/json">'+script+
                           '</script></head><body><div id="app"></div></body></html>',"html.parser")
        self.assertIsNone(ns["choose_body_container"](soup))
        self.assertFalse(ns["valid_body_container"](soup.select_one("#fusion-metadata")))

    def test_kado_spaceless_variant_in_article(self):
        body="19일 본지 취재결과 춘천시의 행정절차에 변경이 있었으며 추후 관리체계 개편이 논의됐다."
        html_doc="<html><article><p>"+body+"</p><p>"+("사업 관련 기관이 추가 설명을 내놓았다. "*5)+"</p></article></html>"
        soup=BeautifulSoup(html_doc,"html.parser")
        container=ns["choose_body_container"](soup)
        extracted=ns["extract_paragraphs"](container)
        self.assertEqual(ns["target_phrase_counts"]("\n".join(extracted))["본지 취재 결과"],1)
        self.assertTrue(ns["contains_target_phrase"]("\n".join(extracted)))


if __name__=="__main__":
    unittest.main()
