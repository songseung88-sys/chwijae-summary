"""One-off read-only reachability and HTML selectors diagnosis for failing publishers.
Does not attempt authentication, circumvention, or collection from protected pages.
"""
import json
from urllib.parse import urlparse
import requests
from bs4 import BeautifulSoup

PAGES = [
    ("businesspost-main", "https://www.businesspost.co.kr/BP?command=article_view&num=448697"),
    ("businesspost-mobile", "https://m.businesspost.co.kr/BP?command=article_view&num=449697"),
    ("businesspost-news", "https://m.businesspost.co.kr/news/articleView.html?num=448192"),
    ("businesspost-admin", "https://admin.businesspost.co.kr/BP?command=article_view&num=448697"),
    ("viva-main", "https://www.viva100.com/article/20261020500664"),
    ("viva-mobile", "https://m.viva100.com/article/20261020500664"),
    ("kbsm-main", "https://www.kbsm.net/news/view.php?idx=538427"),
    ("kbsm-mobile", "https://m.kbsm.net/view.php?idx=534514"),
    ("ksmnews-main", "https://www.ksmnews.co.kr/"),
]
SELECTORS=[
    "article","main","[itemprop=articleBody]","#articleBody","#article_body",
    "#article-view-content-div",".article_view",".article-view",
    ".article_txt",".article_cont",".article-content",".article_view_content",
    ".article-body",".articleBody",".article_text","#article-view-content",
    "#articleContent","#articleView","#view_content","#articleViewContent",
    "#news_body",".news_content",".news_view",".view_cont","#news_body_id",
    ".news_con","#news_con",".view_text","#view_text",".read_cnt","#article_content",
    ".article_con","#articleText",".bodytext",".text_box","#newsViewContent",
    "#news_content",".news-view","#article_contents",
]
UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/155.0.0.0 Safari/537.36"
for name,url in PAGES:
    record={"case":name,"host":urlparse(url).netloc}
    try:
        result=requests.get(url,timeout=12,headers={"User-Agent":UA,"Accept-Language":"ko-KR,ko;q=0.9"},allow_redirects=True)
        record.update(status=result.status_code,final_host=urlparse(result.url).netloc,bytes=len(result.content))
        if result.status_code==200:
            if result.encoding in (None,"ISO-8859-1"):result.encoding=result.apparent_encoding or "utf-8"
            soup=BeautifulSoup(result.text,"html.parser")
            full=soup.get_text(" ",strip=True)
            record["page_phrase"]=full.count("취재를 종합하면")
            record["body_candidates"]=[]
            for selector in SELECTORS:
                node=soup.select_one(selector)
                if not node:continue
                body=node.get_text(" ",strip=True)
                if len(body)>90:
                    record["body_candidates"].append({"selector":selector,"chars":len(body),"phrase":body.count("취재를 종합하면"),"start":body[:45]})
            record["body_candidates"]=record["body_candidates"][:20]
            record["article_json_ld"]=any('NewsArticle' in str(x) for x in soup.select('script[type="application/ld+json"]'))
            record["title"]=(soup.title.get_text(" ",strip=True) if soup.title else "")[:90]
    except Exception as exc:record["exception"]=type(exc).__name__+":"+str(exc)[:155]
    print("PUBLISHER_PROBE "+json.dumps(record,ensure_ascii=False),flush=True)
