"""Read-only diagnostics of Etoday byline extraction, to run only during PR review."""
import json
import sys
from pathlib import Path
from urllib.parse import urlparse
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import requests
from bs4 import BeautifulSoup
from collector import main as c

urls=[
 "https://www.etoday.co.kr/news/view/2640213",
 "https://www.etoday.co.kr/news/view/2640275",
 "https://www.etoday.co.kr/news/view/2640195",
 "https://www.etoday.co.kr/news/view/2597191",
]
for url in urls:
    report={"url":url}
    try:
        response=c.session.get(url,timeout=14)
        report["status"]=response.status_code
        if response.status_code==200:
            response.encoding=response.apparent_encoding or "utf-8"
            soup=BeautifulSoup(response.text,"html.parser")
            data=c.news_jsonld(soup)
            raw=data.get("publisher")
            pub=raw.get("name","") if isinstance(raw,dict) else raw
            report["jsonld_author"]=str(data.get("author"))[:150]
            report["meta_author"]=c.meta(soup,"author","article:author","parsely-author")
            report["meta_publisher"]=c.meta(soup,"og:site_name","application-name","publisher")
            report["jsonld_publisher"]=pub
            report["publisher_resolved"]=c.normalize_publisher(pub or report["meta_publisher"],urlparse(response.url).hostname)
            report["parsed_reporter"]=c.parse_original(url).get("reporters")
            report["author_selectors"]={}
            for sel in [".reporter",".reporter_name",".journalist",".author",".byline",
                         "[class*='reporter']","[class*='journalist']","[class*='byline']",
                         ".media_end_head_journalist_name","[class*='writer']", "[class*='journalist_name']",
                         "a[href*='/reporter']",".news_view_writer",".writer","#reporter"]:
                el=soup.select(sel)
                if el: report["author_selectors"][sel]=[e.get_text(" ",strip=True)[:90] for e in el[:4]]
            report["html_author_fragments"]=[]
            for string in soup.find_all(string=lambda t: t and "김재학 기자" in t):
                report["html_author_fragments"].append({"tag":string.parent.name,"class":string.parent.get("class",[]),
                  "id":string.parent.get("id"),"parent_class":string.parent.parent.get("class",[]) if string.parent.parent else []})
                if len(report["html_author_fragments"])>=3:break
    except Exception as exc:report["exception"]=type(exc).__name__+":"+str(exc)[:180]
    print("ETODAY_PROBE "+json.dumps(report,ensure_ascii=False),flush=True)

try:
    r=requests.get("https://based-on-our-reporting.com/api/dashboard?date=2026-10-26",timeout=12)
    print("DASHBOARD_STATUS",r.status_code)
    if r.ok:
        data=r.json()
        rows=[{"url":a.get("original_url"),"naver":a.get("naver_url"),"reporters":a.get("reporters"),"publisher":a.get("publisher")}
              for a in data.get("articles",[]) if "etoday.co.kr" in (a.get("original_url") or "")]
        print("DASHBOARD_ETODAY "+json.dumps(rows[:15],ensure_ascii=False))
        for row in rows[:7]:
            if not row.get("naver"):continue
            detail={"original":row["url"],"naver":row["naver"],"stored":row["reporters"]}
            try:
                nav=c.session.get(row["naver"],timeout=13)
                detail["status"]=nav.status_code
                if nav.ok:
                    nav.encoding=nav.apparent_encoding or "utf-8"
                    soup=BeautifulSoup(nav.text,"html.parser")
                    data_ld=c.news_jsonld(soup)
                    detail["meta_author"]=c.meta(soup,"author","article:author","parsely-author")
                    detail["jsonld_author"]=str(data_ld.get("author"))[:100]
                    detail["parsed"]=c.parse_naver(row["naver"]).get("reporters")
                    detail["visible_byline_candidates"]={}
                    for sel in [".media_end_head_journalist_name",".byline_s",".reporter_area .name","[class*='journalist']",
                                ".media_end_head_journalist","[class*='reporter']","a[href*='journalist']"]:
                        es=soup.select(sel)
                        if es:detail["visible_byline_candidates"][sel]=[e.get_text(" ",strip=True)[:90] for e in es[:4]]
            except Exception as exc:detail["error"]=type(exc).__name__+":"+str(exc)[:100]
            print("ETODAY_NAVER "+json.dumps(detail,ensure_ascii=False),flush=True)

except Exception as exc: print("DASHBOARD_ERROR",type(exc).__name__,str(exc)[:200])
