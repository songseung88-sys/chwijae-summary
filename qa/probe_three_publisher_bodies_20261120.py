"""Read-only current official article DOM probe for three affected publishers.

No login, access-control bypass, Firestore changes, or article text logging.
"""
import json, re
from urllib.parse import urlparse
from bs4 import BeautifulSoup
import requests
from collector import main as p

URLS = [
 ("kbmaeil-missing-20261117", "https://www.kbmaeil.com/article/20261117500786"),
 ("news2day-phrase-not-found-20261118", "https://www.news2day.co.kr/article/20261118500006"),
 ("jjan-confirmed-target-20260128", "https://www.jjan.kr/article/20260128500447"),
 ("jjan-amp-confirmed-20260705", "https://www.jjan.kr/articleAmp/20260705500138"),
 ("jjan-20260219", "https://www.jjan.kr/article/20260219500239"),
]
SELECTORS = [
 "#articleBody","#article_body","#article-view-content-div",
 "#articleView","#article-view","#article-view-content",
 "#article-body-content","#articleContent","#article-content",
 "#news_body","#news_content","#newsBody","#news-view-content",
 "#view_content","#view_cont","#viewContent",".article-body",
 ".articleBody",".article_body",".article-content",".article_view",
 ".article-view",".article_view_content",".news_content",
 ".news_view",".article_text",".article-txt",".article_txt",
 ".view-content",".view_content",".view_text",".news_body",
 "[itemprop=articleBody]","[class*=article-body]",
 "[class*=articleBody]","[class*=article-content]",
 "[class*=article_cont]","[id*=article]","main","article"
]
def title(soup):
    return (soup.title.get_text(" ",strip=True) if soup.title else "")[:100]

for label, url in URLS:
    record={"case":label,"requested_host":urlparse(url).hostname}
    try:
        parsed=p.parse_original(url)
        record["parser"]={
            "status":parsed.get("status_code"),"error":parsed.get("error"),
            "body_chars":len(parsed.get("body","")),
            "phrases":parsed.get("phrase_count"),
            "source":parsed.get("fetch_variant"),
            "final_url":parsed.get("final_url")
        }
        r=p.session.get(url,timeout=20,allow_redirects=True)
        record.update(http=r.status_code,final_url=r.url,raw_bytes=len(r.content))
        if r.status_code!=200:
            print("BODY_PROBE "+json.dumps(record,ensure_ascii=False),flush=True)
            continue
        if not r.encoding or r.encoding.lower()=="iso-8859-1":
            r.encoding=r.apparent_encoding or "utf-8"
        soup=BeautifulSoup(r.text,"html.parser")
        body=soup.body
        visible=body.get_text(" ",strip=True) if body else ""
        record.update(title=title(soup),visible_chars=len(visible),
                      visible_phrase=p.contains_target_phrase(visible),
                      source_phrase=p.contains_target_phrase(r.text),
                      og_url=(soup.select_one('meta[property="og:url"]') or {}).get("content",""),
                      canonical=(soup.select_one('link[rel="canonical"]') or {}).get("href",""),
                      article_jsonld=bool(p.news_jsonld(soup).get("articleBody")))
        candidates=[]
        for selector in SELECTORS:
            for node in soup.select(selector)[:2]:
                if not node or node.name not in ("div","section","article","main"):continue
                content=node.get_text(" ",strip=True)
                if len(content)>=75:
                    candidates.append({"css":selector,"tag":node.name,
                        "id":(node.get("id") or "")[:70],
                        "class":node.get("class",[])[:4],
                        "chars":len(content),
                        "phrase":p.contains_target_phrase(content),
                        "valid":p.valid_body_container(node)})
        record["candidates"]=candidates[:35]
        matches=soup.find_all(string=lambda v: isinstance(v,str) and p.contains_target_phrase(v))
        ancestors=[]
        for v in matches[:2]:
            if v.find_parent(["script","style","noscript","template"]):continue
            path=[]
            for parent in [v.parent,*list(v.parents)[:6]]:
                if parent and parent.name:
                    path.append({"tag":parent.name,"id":(parent.get("id") or "")[:55],
                        "class":parent.get("class",[])[:3],
                        "chars":len(parent.get_text(" ",strip=True))})
            ancestors.append(path)
        record["phrase_ancestry"]=ancestors
        record["body_markup_counts"]={
            "p":len(soup.select("p")),
            "article":len(soup.select("article")),
            "main":len(soup.select("main")),
            "jsonld":len(soup.select('script[type="application/ld+json"]'))
        }
    except Exception as exc:
        record["exception"]=type(exc).__name__+":"+str(exc)[:160]
    print("BODY_PROBE "+json.dumps(record,ensure_ascii=False),flush=True)
