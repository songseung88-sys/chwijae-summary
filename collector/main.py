#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import hashlib
import html
import json
import os
import re
import sys
import time
from datetime import datetime
from difflib import SequenceMatcher
from email.utils import parsedate_to_datetime
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup
from google.cloud import firestore

KST = ZoneInfo("Asia/Seoul")
PHRASE = "취재를 종합하면"
NAVER_API_URL = "https://naverapihub.apigw.ntruss.com/search/v1/news"
SECONDARY_EXPRESSIONS = [
    "알려졌다",
    "전해졌다",
    "해석된다",
    "지적이 나온다",
    "법조계에 따르면",
    "한 셈이다",
]
WIRE_NAMES = ["연합뉴스", "뉴스1", "뉴시스"]
COLLECTOR_VERSION = "0.3.2-reporter-fallback"

PUBLISHER_BY_HOST = {
    "khan.co.kr": "경향신문",
    "chosun.com": "조선일보",
    "biz.chosun.com": "조선비즈",
    "joongang.co.kr": "중앙일보",
    "hani.co.kr": "한겨레",
    "hankookilbo.com": "한국일보",
    "yna.co.kr": "연합뉴스",
    "news1.kr": "뉴스1",
    "newsis.com": "뉴시스",
    "mk.co.kr": "매일경제",
    "edaily.co.kr": "이데일리",
    "sedaily.com": "서울경제",
    "segye.com": "세계일보",
    "view.asiae.co.kr": "아시아경제",
    "nocutnews.co.kr": "노컷뉴스",
}

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/155.0.0.0 Safari/537.36"
)

COMMON_BODY_SELECTORS = [
    "#dic_area",
    "#newsct_article",
    "article",
    "#articleBody",
    "#article_body",
    "#article-view-content-div",
    ".article-body",
    ".article_body",
    ".articleBody",
    ".article_view",
    ".article-view",
    ".news_body",
    ".news-body",
    ".view_cont",
    ".view-content",
    ".article_txt",
    ".article-text",
]

session = requests.Session()
session.headers.update({
    "User-Agent": UA,
    "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.7",
})


def clean_text(value):
    if value is None:
        return ""
    value = html.unescape(str(value))
    value = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def normalize_compare(text):
    text = clean_text(text)
    text = re.sub(r"\s+", "", text)
    return text[:30000]


def similarity(a, b):
    a = normalize_compare(a)
    b = normalize_compare(b)
    if not a or not b:
        return None
    return round(SequenceMatcher(None, a, b).ratio(), 4)


def is_naver_news_url(url):
    host = (urlparse(url).hostname or "").lower()
    return "naver.com" in host and ("news" in host or "n.news" in host)


def parse_pubdate(value):
    try:
        dt = parsedate_to_datetime(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=KST)
        return dt.astimezone(KST)
    except Exception:
        return None


def meta(soup, *keys):
    for key in keys:
        for attr in ("property", "name", "itemprop"):
            tag = soup.find("meta", attrs={attr: key})
            if tag and tag.get("content"):
                return clean_text(tag["content"])
    return ""


def iter_jsonld(soup):
    for tag in soup.find_all("script", attrs={"type": re.compile(r"ld\+json", re.I)}):
        raw = tag.string or tag.get_text(" ", strip=True)
        if not raw:
            continue
        try:
            obj = json.loads(raw)
        except Exception:
            continue
        yield obj


def flatten_jsonld(obj):
    if isinstance(obj, list):
        for item in obj:
            yield from flatten_jsonld(item)
    elif isinstance(obj, dict):
        yield obj
        if "@graph" in obj:
            yield from flatten_jsonld(obj["@graph"])


def news_jsonld(soup):
    for raw in iter_jsonld(soup):
        for obj in flatten_jsonld(raw):
            typ = obj.get("@type")
            types = typ if isinstance(typ, list) else [typ]
            if any(t in ("NewsArticle", "Article", "ReportageNewsArticle") for t in types):
                return obj
    return {}


def author_name(value):
    if not value:
        return ""
    items = value if isinstance(value, list) else [value]
    names = []
    for item in items:
        name = item.get("name") if isinstance(item, dict) else item
        name = clean_text(name)
        if name:
            names.append(name)
    return ", ".join(dict.fromkeys(names))


def normalize_publisher(name, host):
    host = (host or "").lower().removeprefix("www.")
    for domain, label in PUBLISHER_BY_HOST.items():
        if host == domain or host.endswith("." + domain):
            return label
    name = clean_text(name)
    if name.lower() == "the kyunghyang shinmun":
        return "경향신문"
    return name


def normalize_reporter_text(raw, publisher=""):
    raw = clean_text(raw)
    if not raw:
        return ""
    if raw.startswith("http://") or raw.startswith("https://"):
        return ""
    if publisher and raw == publisher:
        return ""

    names = re.findall(r"([가-힣]{2,4})\s*기자", raw)
    if names:
        return ", ".join(dict.fromkeys(names))

    parts = [clean_text(x) for x in re.split(r"[,/·|]", raw)]
    good = []
    for part in parts:
        part = re.sub(r"\s*(기자|특파원|논설위원|에디터|PD)$", "", part).strip()
        if re.fullmatch(r"[가-힣]{2,4}", part):
            good.append(part)
        elif re.fullmatch(r"[가-힣A-Za-z0-9]{2,10}팀", part):
            good.append(part)
    return ", ".join(dict.fromkeys(good))


def infer_reporters(soup, data, publisher, host):
    candidates = [
        author_name(data.get("author")),
        meta(soup, "author", "article:author", "parsely-author"),
    ]
    for selector in [
        ".reporter", ".reporter_name", ".journalist", ".author", ".byline",
        "[class*='reporter']", "[class*='journalist']", "[class*='byline']",
    ]:
        for node in soup.select(selector)[:5]:
            candidates.append(node.get_text(" ", strip=True))

    for raw in candidates:
        cleaned = normalize_reporter_text(raw, publisher)
        if cleaned:
            return cleaned

    host = (host or "").lower().removeprefix("www.")
    if host.endswith("ksilbo.co.kr") or host.endswith("labortoday.co.kr"):
        page_text = clean_text(soup.get_text(" ", strip=True))
        m = re.search(r"기자명\s*([가-힣]{2,4})\s*기자", page_text)
        if m:
            return m.group(1)
        m = re.search(r"([가-힣]{2,4})\s*기자\s+[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+", page_text)
        if m:
            return m.group(1)

    return ""


def breadcrumb_category(soup):
    for raw in iter_jsonld(soup):
        for obj in flatten_jsonld(raw):
            if obj.get("@type") != "BreadcrumbList":
                continue
            names = []
            for item in obj.get("itemListElement", []):
                if not isinstance(item, dict):
                    continue
                name = item.get("name")
                if not name and isinstance(item.get("item"), dict):
                    name = item["item"].get("name")
                name = clean_text(name)
                if name:
                    names.append(name)
            if len(names) >= 2:
                return " > ".join(names[-3:])
    return ""


def choose_body_container(soup):
    candidates = []
    for selector in COMMON_BODY_SELECTORS:
        for node in soup.select(selector):
            text = clean_text(node.get_text("\n", strip=True))
            if PHRASE in text and len(text) >= 120:
                candidates.append((len(text), node))
    if candidates:
        return max(candidates, key=lambda x: x[0])[1]

    phrase_nodes = soup.find_all(string=lambda s: isinstance(s, str) and PHRASE in s)
    for text_node in phrase_nodes:
        node = text_node.parent
        for _ in range(8):
            if node is None:
                break
            text = clean_text(node.get_text("\n", strip=True))
            if PHRASE in text and len(text) >= 300:
                return node
            node = node.parent
    return soup.select_one("article") or soup.select_one("main")


def extract_paragraphs(container):
    if not container:
        return []
    paras = []
    for p in container.find_all("p"):
        text = clean_text(p.get_text(" ", strip=True))
        if len(text) >= 20 and text not in paras:
            paras.append(text)
    if any(PHRASE in p for p in paras):
        return paras

    raw = container.get_text("\n", strip=True)
    lines = [clean_text(x) for x in re.split(r"\n+", raw)]
    return [x for x in lines if len(x) >= 20]


def phrase_contexts(paragraphs):
    out = []
    for idx, paragraph in enumerate(paragraphs, start=1):
        count = paragraph.count(PHRASE)
        if count:
            out.append({
                "paragraph_no": idx,
                "count": count,
                "text": paragraph,
            })
    return out


def secondary_counts(body):
    return {
        exp: body.count(exp)
        for exp in SECONDARY_EXPRESSIONS
        if body.count(exp) > 0
    }


def strict_exclusive(title):
    return bool(re.match(r"^\s*\[단독\]", clean_text(title)))


def detect_wire_reprint(body, publisher, host):
    prefix = body[:1500]
    detected = ""
    for wire in WIRE_NAMES:
        if re.search(rf"\b{re.escape(wire)}\s+취재를 종합하면", prefix):
            detected = wire
            break
    if not detected:
        return "", False

    publisher = publisher or ""
    self_wire = (
        (detected == "연합뉴스" and ("연합뉴스" in publisher or "yna.co.kr" in host))
        or (detected == "뉴시스" and ("뉴시스" in publisher or "newsis.com" in host))
        or (detected == "뉴스1" and ("뉴스1" in publisher or "news1.kr" in host))
    )
    return detected, not self_wire


def parse_original(url):
    result = {
        "ok": False,
        "status_code": None,
        "final_url": url,
        "title": "",
        "publisher": "",
        "reporters": "",
        "published_at": "",
        "modified_at": "",
        "category_original": "",
        "body": "",
        "paragraphs": [],
        "phrase_contexts": [],
        "phrase_count": 0,
        "secondary": {},
        "error": "",
    }
    if not url:
        result["error"] = "NO_ORIGINAL_URL"
        return result

    try:
        r = session.get(url, timeout=20, allow_redirects=True)
        result["status_code"] = r.status_code
        result["final_url"] = r.url
        if r.status_code != 200:
            result["error"] = f"HTTP_{r.status_code}"
            return result

        if not r.encoding or r.encoding.lower() == "iso-8859-1":
            r.encoding = r.apparent_encoding or "utf-8"
        soup = BeautifulSoup(r.text, "html.parser")
        data = news_jsonld(soup)

        result["title"] = clean_text(
            data.get("headline")
            or meta(soup, "og:title", "twitter:title")
            or (soup.find("h1").get_text(" ", strip=True) if soup.find("h1") else "")
        )

        publisher = data.get("publisher")
        if isinstance(publisher, dict):
            publisher = publisher.get("name")
        host = (urlparse(r.url).hostname or "").lower()
        publisher_raw = clean_text(publisher) or meta(
            soup, "og:site_name", "application-name", "publisher"
        )
        result["publisher"] = normalize_publisher(publisher_raw, host)
        result["reporters"] = infer_reporters(soup, data, result["publisher"], host)
        result["published_at"] = clean_text(
            data.get("datePublished")
            or meta(soup, "article:published_time", "datePublished", "pubdate", "date")
        )
        result["modified_at"] = clean_text(
            data.get("dateModified")
            or meta(soup, "article:modified_time", "dateModified")
        )
        result["category_original"] = clean_text(data.get("articleSection")) or meta(
            soup, "article:section", "section", "parsely-section"
        ) or breadcrumb_category(soup)
        if result["category_original"] == result["publisher"]:
            result["category_original"] = ""

        container = choose_body_container(soup)
        paragraphs = extract_paragraphs(container)

        if not any(PHRASE in p for p in paragraphs):
            article_body = clean_text(data.get("articleBody"))
            if PHRASE in article_body:
                paragraphs = [article_body]

        body = "\n".join(paragraphs)
        result["body"] = body
        result["paragraphs"] = paragraphs
        result["phrase_count"] = body.count(PHRASE)
        result["phrase_contexts"] = phrase_contexts(paragraphs)
        result["secondary"] = secondary_counts(body)
        result["ok"] = bool(body)
        if not body:
            result["error"] = "BODY_NOT_FOUND"
        elif result["phrase_count"] == 0:
            result["error"] = "PHRASE_NOT_FOUND"
        return result
    except requests.RequestException as e:
        result["error"] = f"REQUEST_ERROR:{type(e).__name__}"
        return result
    except Exception as e:
        result["error"] = f"PARSE_ERROR:{type(e).__name__}:{str(e)[:120]}"
        return result


def suspicious_body(text):
    text = str(text or "")
    markers = [
        '{"props":',
        '"pageProps":',
        "Fusion.spa",
        "var messageText =",
        "__NEXT_DATA__",
        '"contentArrange":',
    ]
    if any(marker in text for marker in markers):
        return True
    if len(text) > 80000:
        return True
    return False


def parse_naver(url):
    result = {
        "ok": False,
        "reporters": "",
        "body": "",
        "paragraphs": [],
        "phrase_contexts": [],
        "phrase_count": 0,
        "secondary": {},
        "error": "",
    }
    if not url:
        result["error"] = "NO_NAVER_PAGE"
        return result

    try:
        r = session.get(url, timeout=20, allow_redirects=True)
        if r.status_code != 200:
            result["error"] = f"HTTP_{r.status_code}"
            return result
        r.encoding = r.apparent_encoding or "utf-8"
        soup = BeautifulSoup(r.text, "html.parser")
        reporter_candidates = []
        for selector in [
            ".media_end_head_journalist_name",
            ".byline_s",
            ".reporter_area .name",
            "[class*='journalist']",
        ]:
            for reporter_node in soup.select(selector)[:10]:
                reporter_candidates.append(reporter_node.get_text(" ", strip=True))
        for raw_reporter in reporter_candidates:
            cleaned_reporter = normalize_reporter_text(raw_reporter)
            if cleaned_reporter:
                result["reporters"] = cleaned_reporter
                break

        node = soup.select_one("#dic_area") or soup.select_one("#newsct_article")
        if not node:
            result["error"] = "BODY_NOT_FOUND"
            return result
        raw = node.get_text("\n", strip=True)
        paragraphs = [clean_text(x) for x in re.split(r"\n+", raw)]
        paragraphs = [x for x in paragraphs if len(x) >= 20]
        body = "\n".join(paragraphs)
        result["body"] = body
        result["paragraphs"] = paragraphs
        result["phrase_count"] = body.count(PHRASE)
        result["phrase_contexts"] = phrase_contexts(paragraphs)
        result["secondary"] = secondary_counts(body)
        result["ok"] = bool(body)
        if result["phrase_count"] == 0:
            result["error"] = "PHRASE_NOT_FOUND"
        return result
    except requests.RequestException as e:
        result["error"] = f"REQUEST_ERROR:{type(e).__name__}"
        return result
    except Exception as e:
        result["error"] = f"PARSE_ERROR:{type(e).__name__}:{str(e)[:120]}"
        return result


def fetch_candidates(client_id, client_secret, target_date, query, max_pages=10):
    headers = {
        "X-NCP-APIGW-API-KEY-ID": client_id,
        "X-NCP-APIGW-API-KEY": client_secret,
    }
    candidates = []
    seen = set()

    for start in range(1, min(max_pages, 10) * 100 + 1, 100):
        params = {
            "query": query,
            "display": 100,
            "start": start,
            "sort": "date",
            "format": "json",
        }
        r = session.get(NAVER_API_URL, headers=headers, params=params, timeout=20)
        r.raise_for_status()
        items = r.json().get("items", [])
        if not items:
            break

        dates = []
        for item in items:
            dt = parse_pubdate(item.get("pubDate", ""))
            if not dt:
                continue
            dates.append(dt.date())
            if dt.date() != target_date:
                continue

            original_url = item.get("originallink") or item.get("link") or ""
            key = original_url or item.get("link", "")
            if key and key not in seen:
                seen.add(key)
                candidates.append({
                    "api_title": clean_text(item.get("title", "")),
                    "api_description": clean_text(item.get("description", "")),
                    "api_pubdate": dt.isoformat(),
                    "original_url": original_url,
                    "naver_url": item.get("link", "") if is_naver_news_url(item.get("link", "")) else "",
                })

        if dates and min(dates) < target_date:
            break
        time.sleep(0.15)

    return candidates


def doc_id(url):
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:32]


def main():
    project_id = os.getenv("GCP_PROJECT_ID", "").strip() or None
    client_id = os.environ.get("NAVER_API_HUB_CLIENT_ID", "").strip()
    client_secret = os.environ.get("NAVER_API_HUB_CLIENT_SECRET", "").strip()
    compare_naver = os.getenv("COMPARE_NAVER", "true").lower() == "true"
    max_articles = int(os.getenv("MAX_ARTICLES_PER_RUN", "100"))

    if not client_id or not client_secret:
        print("Missing NAVER API credentials.", file=sys.stderr)
        sys.exit(2)

    db = firestore.Client(project=project_id)
    now = datetime.now(KST)
    target_date = now.date()
    run_ref = db.collection("collector_runs").document(now.strftime("%Y%m%dT%H%M%S%z"))

    quoted_query = f'"{PHRASE}"'
    candidates = fetch_candidates(
        client_id, client_secret, target_date, query=quoted_query
    )[:max_articles]

    summary = {
        "target_date": str(target_date),
        "started_at": now.isoformat(),
        "search_query_used": quoted_query,
        "candidates": len(candidates),
        "accepted": 0,
        "existing_accepted": 0,
        "new_accepted": 0,
        "original_success": 0,
        "naver_fallback": 0,
        "rejected": 0,
        "exclusive": 0,
        "wire_reprint_suspected": 0,
        "errors": {},
    }

    for idx, item in enumerate(candidates, start=1):
        original_url = item["original_url"]
        article_ref = db.collection("articles").document(doc_id(original_url))

        existing = article_ref.get()
        existing_data = existing.to_dict() if existing.exists else {}
        if (
            existing.exists
            and existing_data.get("status") == "accepted"
            and existing_data.get("collector_version") == COLLECTOR_VERSION
        ):
            summary["accepted"] += 1
            summary["existing_accepted"] += 1
            summary["exclusive"] += int(bool(existing_data.get("is_exclusive_strict")))
            summary["wire_reprint_suspected"] += int(
                bool(existing_data.get("is_wire_reprint_suspected"))
            )
            article_ref.set({
                "last_seen_at": firestore.SERVER_TIMESTAMP,
                "last_seen_api_pubdate": item["api_pubdate"],
            }, merge=True)
            print(f"[{idx}/{len(candidates)}] SKIP existing {item['api_title'][:60]}")
            continue

        original = parse_original(original_url)
        naver = parse_naver(item["naver_url"]) if compare_naver and item["naver_url"] else {
            "ok": False, "reporters": "", "body": "", "phrase_count": 0, "phrase_contexts": [],
            "secondary": {}, "error": "NO_NAVER_PAGE"
        }

        if original["phrase_count"] > 0 and not suspicious_body(original.get("body", "")):
            final = original
            source = "ORIGINAL"
            summary["original_success"] += 1
        elif naver["phrase_count"] > 0:
            final = naver
            source = "NAVER_FALLBACK"
            summary["naver_fallback"] += 1
        elif original["phrase_count"] > 0:
            final = original
            source = "ORIGINAL_LOW_QUALITY"
            summary["original_success"] += 1
        else:
            final = original
            source = "REJECTED"
            summary["rejected"] += 1

        host = (urlparse(original_url).hostname or "").lower()
        wire_source, wire_reprint = detect_wire_reprint(
            original.get("body", "") or naver.get("body", ""),
            original.get("publisher", ""),
            host,
        )

        is_exclusive = strict_exclusive(item["api_title"])
        if source != "REJECTED":
            summary["accepted"] += 1
            summary["new_accepted"] += 1
            summary["exclusive"] += int(is_exclusive)
            summary["wire_reprint_suspected"] += int(wire_reprint)

        for err in (original.get("error"), naver.get("error")):
            if err and err not in ("NO_NAVER_PAGE", "PHRASE_NOT_FOUND"):
                summary["errors"][err] = summary["errors"].get(err, 0) + 1

        reporters_original = original.get("reporters", "")
        reporters_naver = naver.get("reporters", "")
        reporters_resolved = reporters_original or reporters_naver
        reporter_source = "ORIGINAL" if reporters_original else ("NAVER" if reporters_naver else "NONE")

        article = {
            "status": "accepted" if source != "REJECTED" else "rejected",
            "final_source": source,
            "api_title": item["api_title"],
            "api_description": item["api_description"],
            "api_pubdate": item["api_pubdate"],
            "original_url": original_url,
            "naver_url": item["naver_url"],
            "publisher_original": original.get("publisher", ""),
            "reporters_original": reporters_original,
            "reporters_naver": reporters_naver,
            "reporters_resolved": reporters_resolved,
            "reporter_source": reporter_source,
            "published_at_original": original.get("published_at", ""),
            "modified_at_original": original.get("modified_at", ""),
            "category_original": original.get("category_original", ""),
            "is_exclusive_strict": is_exclusive,
            "phrase": PHRASE,
            "phrase_count": final.get("phrase_count", 0),
            "phrase_contexts": final.get("phrase_contexts", []),
            "secondary_expressions": final.get("secondary", {}),
            "body_text_private": final.get("body", ""),
            "original_parse_error": original.get("error", ""),
            "naver_parse_error": naver.get("error", ""),
            "body_similarity_original_vs_naver": similarity(
                original.get("body", ""), naver.get("body", "")
            ) if item["naver_url"] else None,
            "phrase_context_similarity": similarity(
                " ".join(x["text"] for x in original.get("phrase_contexts", [])),
                " ".join(x["text"] for x in naver.get("phrase_contexts", [])),
            ) if original.get("phrase_count") and naver.get("phrase_count") else None,
            "wire_source_detected": wire_source,
            "is_wire_reprint_suspected": wire_reprint,
            "first_seen_at": firestore.SERVER_TIMESTAMP,
            "last_seen_at": firestore.SERVER_TIMESTAMP,
            "collector_version": COLLECTOR_VERSION,
        }
        article_ref.set(article, merge=True)
        print(f"[{idx}/{len(candidates)}] {source} {item['api_title'][:70]}")

    summary["finished_at"] = datetime.now(KST).isoformat()
    run_ref.set(summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
