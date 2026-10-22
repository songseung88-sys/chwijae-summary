"""Tests for site-specific public-body extraction with fake network responses."""
import unittest
from unittest.mock import patch
from bs4 import BeautifulSoup
from collector import main as c

URL="https://www.businesspost.co.kr/BP?command=article_view&num=448697"
MOBILE="https://m.businesspost.co.kr/BP?command=article_view&num=448697"
BP_TEXT="6일 업계 취재를 종합하면 해당 기업은 추가적인 데이터 분석을 진행했다. " * 4
VIVA_TEXT="20일 브릿지경제 취재를 종합하면 해당 기관은 새로운 지원 사업을 준비 중이다. " * 4
KBSM_TEXT="21일 취재를 종합하면 당국은 관련 사건을 조사하고 있는 것으로 알려졌다. " * 4

class FakeResponse:
    def __init__(self,status,url,body=""):
        self.status_code=status
        self.url=url
        self.text=body
        self.content=body.encode()
        self.encoding="utf-8"
        self.apparent_encoding="utf-8"

class PublisherSiteRecovery(unittest.TestCase):
    def test_mobile_url_exact_allowlist(self):
        self.assertEqual(c.official_businesspost_mobile_url(URL),MOBILE)
        for path in (
            "http://www.businesspost.co.kr/BP?command=article_view&num=448697",
            "https://m.businesspost.co.kr/BP?command=article_view&num=448697",
            "https://evil.businesspost.co.kr/BP?command=article_view&num=448697",
            "https://www.businesspost.co.kr/BP?command=article_view&num=bad",
            "https://www.businesspost.co.kr/news/articleView.html?num=448697",
        ):
            self.assertEqual(c.official_businesspost_mobile_url(path),"")

    def test_businesspost_public_mobile_recovery(self):
        html="<html><body><div id='article-body-content'><p>"+BP_TEXT+"</p></div></body></html>"
        with patch.object(c.session,"get",side_effect=[FakeResponse(403,URL),FakeResponse(200,MOBILE,html)]) as get:
            result=c.parse_original(URL)
        self.assertEqual(get.call_count,2)
        self.assertEqual(result["fetch_variant"],"OFFICIAL_MOBILE")
        self.assertEqual(result["final_url"],MOBILE)
        self.assertEqual(result["phrase_count"],4)
        self.assertIn("취재를 종합하면",result["body"])

    def test_wrong_article_or_homepage_is_rejected(self):
        html="<div id='article-body-content'><p>"+BP_TEXT+"</p></div>"
        wrong="https://m.businesspost.co.kr/BP?command=article_view&num=1234"
        with patch.object(c.session,"get",side_effect=[FakeResponse(403,URL),FakeResponse(200,wrong,html)]) as get:
            result=c.parse_original(URL)
        self.assertEqual(get.call_count,2)
        self.assertEqual(result["error"],"HTTP_403")
        self.assertEqual(result["phrase_count"],0)

    def test_businesspost_no_fallback_when_original_works(self):
        html="<div id='article-body-content'><p>"+BP_TEXT+"</p></div>"
        with patch.object(c.session,"get",return_value=FakeResponse(200,URL,html)) as get:
            result=c.parse_original(URL)
        self.assertEqual(get.call_count,1)
        self.assertEqual(result["fetch_variant"],"ORIGINAL")
        self.assertEqual(result["phrase_count"],4)

    def test_viva100_body_selector(self):
        html="<html><body><div class='news_content'><p>"+VIVA_TEXT+"</p></div></body></html>"
        soup=BeautifulSoup(html,"html.parser")
        node=c.choose_body_container(soup,"www.viva100.com")
        self.assertIsNotNone(node)
        self.assertEqual(node.get("class"),["news_content"])
        with patch.object(c.session,"get",return_value=FakeResponse(
            200,"https://www.viva100.com/article/20261020500664",html)):
            record=c.parse_original("https://www.viva100.com/article/20261020500664")
        self.assertEqual(record["phrase_count"],4)

    def test_kbsm_malformed_article_body_in_head(self):
        html=("<html><head><title>경북신문</title><div itemprop='articleBody'><p>"+
              KBSM_TEXT+"</p></div></head><body><div>메뉴</div></body></html>")
        soup=BeautifulSoup(html,"html.parser")
        node=soup.select_one('[itemprop="articleBody"]')
        self.assertIsNotNone(node.find_parent("head"))
        self.assertFalse(c.valid_body_container(node))
        self.assertIs(c.choose_body_container(soup,"www.kbsm.net"),node)
        self.assertIsNone(c.choose_body_container(soup,"www.unrelated.co.kr"))
        with patch.object(c.session,"get",return_value=FakeResponse(
            200,"https://www.kbsm.net/news/view.php?idx=538427",html)):
            record=c.parse_original("https://www.kbsm.net/news/view.php?idx=538427")
        self.assertEqual(record["phrase_count"],4)

    def test_script_and_meta_not_treated_as_body(self):
        html=("<html><head><script>"+KBSM_TEXT+"</script>"+
              "<meta itemprop='articleBody' content='"+KBSM_TEXT+"'></head><body></body></html>")
        self.assertIsNone(c.publisher_body_node(BeautifulSoup(html,"html.parser"),"www.kbsm.net"))

if __name__=="__main__":
    unittest.main()
