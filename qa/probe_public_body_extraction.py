"""Public, read-only diagnostic of article DOMs; no auth, crawling, or Firestore writes.

Only requests already-public official publisher URLs. Failures produce evidence,
not exceptions. No article full text is copied to logs.
"""
import json
from urllib.parse import urlparse
import requests
from bs4 import BeautifulSoup
from collector import main as parser

URLS = [
    ("jjan-public", "https://www.jjan.kr/article/20260219500239"),
    ("ksm-public", "https://www.ksmnews.co.kr/news/view.php?idx=617133"),
    ("thebell-front", "https://www.thebell.co.kr/front/newsview.asp?code=0104&key=202611031125563160103086"),
    ("thebell-official-free", "https://m.thebell.co.kr/m/newsview.asp?newskey=202611031125563160103086&svccode=03"),
]
SELECTORS = [
    "#articleBody", "#article_body", "#article-view-content-div",
    "#articleView", "#article-view", "#article-content",
    "#article-text", "#news_body", "#news_content",
    "#view_content", "#view_cont", ".article_view", ".article_view_content",
    ".article-body", ".article_body", ".news_view", ".news_content",
    ".detail_view", ".view_content", ".article-content",
    "article", "main", "[itemprop=articleBody]",
]
for label, url in URLS:
    host = (urlparse(url).hostname or "")
    record = {"case": label, "host": host}
    try:
        parsed = parser.parse_original(url)
        record.update(parser_error=parsed.get("error") or "",
                      parser_status=parsed.get("status_code"),
                      parser_chars=len(parsed.get("body") or ""),
                      parser_phrases=parsed.get("phrase_count") or 0,
                      parser_variant=parsed.get("fetch_variant") or "",
                      parser_final_host=(urlparse(parsed.get("final_url") or "").hostname or ""))
        if parsed.get("body") and parsed.get("phrase_count"):
            print("PUBLIC_BODY_PROBE " + json.dumps(record, ensure_ascii=False), flush=True)
            continue
        r = requests.get(url, timeout=12, headers={"User-Agent": parser.UA}, allow_redirects=True)
        record.update(http_status=r.status_code, response_chars=len(r.content),
                      resolved_host=(urlparse(r.url).hostname or ""))
        if r.status_code == 200:
            r.encoding = r.apparent_encoding or "utf-8"
            soup = BeautifulSoup(r.text, "html.parser")
            selected = parser.choose_body_container(soup, host)
            record["selected_tag"] = selected.name if selected else ""
            record["selected_id"] = selected.get("id", "") if selected else ""
            record["selected_classes"] = selected.get("class", [])[:5] if selected else []
            record["visible_target_rough"] = parser.contains_target_phrase(
                soup.get_text(" ", strip=True))
            candidates=[]
            for css in SELECTORS:
                for node in soup.select(css)[:2]:
                    content = node.get_text(" ", strip=True)
                    if len(content) > 100:
                        candidates.append({"css": css, "chars": len(content),
                            "phrase": parser.contains_target_phrase(content)})
            record["candidates"] = candidates[:15]
            record["page_title"] = (soup.title.get_text(" ", strip=True) if soup.title else "")[:110]
            visible=soup.get_text(" ", strip=True)
            record["visible_chars"] = len(visible)
            record["visible_head"] = visible[:190]
            record["raw_html_has_phrase"] = parser.contains_target_phrase(r.text)
            record["json_ld"] = [
                {"type": str(node.get("type") or ""), "chars": len(node.string or ""),
                 "has_phrase": parser.contains_target_phrase(node.string or "")}
                for node in soup.select('script[type="application/ld+json"]')[:3]
            ]
            record["meta_og_title"] = (soup.select_one('meta[property="og:title"]') or {}).get("content", "")[:110]
            record["iframes"] = [
                urlparse(tag.get("src") or "").hostname or ""
                for tag in soup.select("iframe[src]")[:3]
            ]
            record["script_count"] = len(soup.select("script"))
            record["article_body_token_in_source"] = "articleBody" in r.text
            record["dom_selected_source"] = [
                {"selector": "#__NEXT_DATA__", "present": bool(soup.select_one("#__NEXT_DATA__"))},
                {"selector": "nuxt", "present": "__NUXT__" in r.text},
            ]
    except Exception as exc:
        record["exception"] = type(exc).__name__ + ": " + str(exc)[:130]
    print("PUBLIC_BODY_PROBE " + json.dumps(record, ensure_ascii=False), flush=True)
