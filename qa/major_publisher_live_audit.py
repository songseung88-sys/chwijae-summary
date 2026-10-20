"""Read-only live audit of publisher extraction for ordinary and rejected articles.
It never accesses Firestore and never writes to the article corpus.
Run through the major-publisher-extraction GitHub Actions workflow.
"""
import json
import re
from bs4 import BeautifulSoup
from collector import main as parser

CASES = [
    ("한겨레 일반기사(대조군)", "https://www.hani.co.kr/arti/economy/economy_general/1283128.html"),
    ("한겨레 이전 제외기사", "https://www.hani.co.kr/arti/society/society_general/1282992.html"),
    ("한겨레 실제 대상표현 포함기사", "https://www.hani.co.kr/arti/society/society_general/1282797.html"),
    ("조선비즈 실제 대상표현 포함기사", "https://biz.chosun.com/policy/policy_sub/2026/07/06/AJELXLVC45FUBN3AQLFI3BOL54/"),
    ("조선일보 대상표현 포함기사", "https://www.chosun.com/national/court_law/2026/10/19/QBU7C6OQXJCPLKSFGWB2FVOOMI/"),
    ("조선일보 이전 제외기사", "https://www.chosun.com/politics/politics_general/2026/10/19/T6OV5ZEJJZEETISIIXKBMMCSU4/"),
    ("조선일보 네이버 전송본(대상 표현 포함)", "https://n.news.naver.com/mnews/article/023/0004004566?sid=102"),
    ("조선일보 네이버 전송본(이전 제외)", "https://n.news.naver.com/mnews/article/023/0004004619?sid=100"),
    ("뉴시스 이전 제외기사", "https://www.newsis.com/view/NISX20261019_0003831566"),
    ("조선비즈 이전 제외기사", "https://biz.chosun.com/industry/business-venture/2026/10/19/GTVLXA5DL5GNPGAH6G7A4EURKY/"),
    ("이투데이 이전 제외기사", "https://www.etoday.co.kr/news/view/2637259"),
]
EXTRA_SELECTORS = [
    "article", "main", ".article-text", ".article-body", ".article_view",
    "#article-view-content-div", "#newsct_article", "#dic_area",
    "#articleBody", "#article_body", "#articleView", ".newsct_body",
    ".article_detail", ".news_content", "#news_body_id", ".article_txt",
    ".article-content", "#article-text", "[itemprop=articleBody]",
    ".article-content-body", ".article_cont", ".article_view_content",
    ".article_viewer", "#view_content", ".article-body-wrap", ".news_view",
]

def examine(name,url):
    record={"case":name,"host":url.split("/")[2],"url":url}
    try:
        response=parser.session.get(url,timeout=18,allow_redirects=True)
        record["http_status"]=response.status_code
        record["download_bytes"]=len(response.content)
        record["final_host"]=response.url.split("/")[2]
        if response.status_code!=200:
            print("AUDIT_CASE "+json.dumps(record,ensure_ascii=False))
            return
        if not response.encoding or response.encoding.lower()=="iso-8859-1":
            response.encoding=response.apparent_encoding or "utf-8"
        soup=BeautifulSoup(response.text,"html.parser")
        record["page_title"]=(parser.meta(soup,"og:title") or (soup.title.get_text(" ",strip=True) if soup.title else ""))[:95]
        record["raw_page_text_len"]=len(soup.get_text(" ",strip=True))
        record["raw_page_phrase_counts"]=parser.target_phrase_counts(soup.get_text(" ",strip=True))
        record["page_metadata"]={
            "json_ld_count":len(list(parser.iter_jsonld(soup))),
            "json_ld_article_body_length":len(parser.news_jsonld(soup).get("articleBody") or ""),
            "html_articleBody_occurrences":response.text.count("articleBody"),
            "html_article_content_occurrences":response.text.lower().count("articlecontent"),
            "next_data_script":bool(soup.select_one("#__NEXT_DATA__")),
            "json_ld_types":[str(x.get("@type"))[:65] for raw in parser.iter_jsonld(soup)
                             for x in parser.flatten_jsonld(raw)][:8],
        }
        candidate_rows=[]
        for selector in EXTRA_SELECTORS:
            for element in soup.select(selector)[:2]:
                txt=element.get_text(" ",strip=True)
                if len(txt)>90:
                    candidate_rows.append({"selector":selector,"length":len(txt),
                                           "phrase_counts":parser.target_phrase_counts(txt),
                                           "text_sample":txt[:65]})
        record["candidate_nodes"]=sorted(candidate_rows,key=lambda x:-x["length"])[:11]
        # Entirely independent of phrase filtering: inspect general article readability.
        choice=parser.choose_body_container(soup)
        record["chosen_tag"]=choice.name if choice else None
        record["chosen_classes"]=choice.get("class",[]) if choice else []
        record["chosen_id"]=choice.get("id") if choice else None
        if choice:
            paragraphs=parser.extract_paragraphs(choice)
            body="\n".join(paragraphs)
            record["extracted_length"]=len(body)
            record["paragraph_count"]=len(paragraphs)
            record["phrase_counts"]=parser.target_phrase_counts(body)
            record["first_paragraph"]=paragraphs[0][:110] if paragraphs else ""
        else:
            record["extracted_length"]=0
        # The actual production parser treats a missing target expression differently.
        result=parser.parse_naver(url) if "n.news.naver.com" in url else parser.parse_original(url)
        record["production_error"]=result.get("error")
        record["production_body_length"]=len(result.get("body") or "")
        record["production_phrase_counts"]=result.get("phrase_counts") or {}
    except Exception as exc:
        record["exception"]=type(exc).__name__+": "+str(exc)[:180]
    print("AUDIT_CASE "+json.dumps(record,ensure_ascii=False))

if __name__=="__main__":
    for name,url in CASES:
        examine(name,url)
