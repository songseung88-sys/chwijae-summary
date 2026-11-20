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

    def test_kbmaeil_reported_missing_article_has_verifiable_body(self):
        main_url="https://www.kbmaeil.com/article/20261117500786"
        content="취재를 종합하면 농해수위 여야 의원들이 현장을 방문해 현황을 점검했다. " * 5
        html=("<div class='article_area'><div class='news_content'><p>"+
              content+"</p></div></div><article class='related_news'>"+
              "관련 기사 추천 영역입니다. " * 10+"</article>")
        with patch.object(c.session,"get",return_value=FakeResponse(200,main_url,html)):
            result=c.parse_original(main_url)
        self.assertGreater(len(result["body"]), 100)
        self.assertEqual(result["phrase_count"], 5)
        self.assertEqual(result["error"], "")
        self.assertIn("농해수위", result["body"])
        self.assertNotIn("관련 기사 추천", result["body"])

    def test_news2day_related_news_is_not_the_article(self):
        main_url="https://www.news2day.co.kr/article/20261118500006"
        content="취재에 따르면 증권사들이 모바일 자산관리 서비스 경쟁을 벌이고 있다. " * 6
        related="관련 기사 내용만 담긴 잘못된 영역. " * 9
        html=("<article class='related_news'>"+related+"</article>"+
              "<div class='view_con cf'><div class='view_con_wrap'><p>"+
              content+"</p></div></div>")
        with patch.object(c.session,"get",return_value=FakeResponse(200,main_url,html)):
            result=c.parse_original(main_url)
        self.assertGreater(len(result["body"]), 100)
        self.assertEqual(result["phrase_counts"]["취재에 따르면"], 6)
        self.assertNotIn("관련 기사 내용", result["body"])
        self.assertEqual(result["error"], "")

    def test_jjan_article_and_amp_article_body_only(self):
        content="전북일보 취재를 종합하면 현장 관계자들이 사업 타당성을 검토하고 있다. " * 5
        urls_and_html=[
            ("https://www.jjan.kr/article/20260128500447",
             "<div class='article_txt_container'><p>"+content+"</p></div>"),
            ("https://www.jjan.kr/articleAmp/20260705500138",
             "<div id='amp_article'><p>"+content+"</p></div>"),
        ]
        for url,html in urls_and_html:
            with self.subTest(url=url):
                with patch.object(c.session,"get",return_value=FakeResponse(200,url,html)):
                    result=c.parse_original(url)
                self.assertEqual(result["phrase_count"], 5)
                self.assertEqual(result["error"], "")
                self.assertGreater(len(result["body"]), 100)

    def test_missing_phrase_is_not_false_body_extraction_failure(self):
        # Readable official body without the source-expression lexicon must be
        # PHRASE_NOT_FOUND, never BODY_NOT_FOUND or silently accepted.
        for host,selector in [
            ("www.jjan.kr", "article_txt_container"),
            ("www.kbmaeil.com", "news_content"),
            ("www.news2day.co.kr", "view_con_wrap"),
        ]:
            url=f"https://{host}/article/20261120500011"
            html=("<div class='"+selector+"'><p>"+
                  ("이 기사는 실제로 읽을 수 있지만 연구 대상 검색표현은 포함하지 않는다. " * 7)+
                  "</p></div>")
            with self.subTest(host=host):
                with patch.object(c.session,"get",return_value=FakeResponse(200,url,html)):
                    result=c.parse_original(url)
                self.assertGreater(len(result["body"]), 100)
                self.assertEqual(result["phrase_count"], 0)
                self.assertEqual(result["error"], "PHRASE_NOT_FOUND")

    def test_site_selectors_do_not_match_other_publishers(self):
        article="취재에 따르면 새로운 기획이 발표됐다는 소식이다. " * 9
        soup=BeautifulSoup("<div class='view_con_wrap'>"+article+"</div>","html.parser")
        self.assertIsNone(c.publisher_body_node(soup,"evil.example.net"))

    def test_scripts_cannot_fake_news2day_body_phrase(self):
        good="대상 검색표현 없이도 본문은 실제로 게시돼 있어야 한다. " * 6
        spoof="취재에 따르면 광고 문구가 표시된다. " * 8
        url="https://www.news2day.co.kr/article/20261118500006"
        html="<div class='view_con_wrap'><script>"+spoof+"</script><p>"+good+"</p></div>"
        with patch.object(c.session,"get",return_value=FakeResponse(200,url,html)):
            result=c.parse_original(url)
        self.assertEqual(result["phrase_count"],0)
        self.assertEqual(result["error"],"PHRASE_NOT_FOUND")

    def test_script_and_meta_not_treated_as_body(self):
        html=("<html><head><script>"+KBSM_TEXT+"</script>"+
              "<meta itemprop='articleBody' content='"+KBSM_TEXT+"'></head><body></body></html>")
        self.assertIsNone(c.publisher_body_node(BeautifulSoup(html,"html.parser"),"www.kbsm.net"))

if __name__=="__main__":
    unittest.main()
