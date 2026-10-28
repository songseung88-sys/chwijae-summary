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
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup
from google.cloud import firestore

KST = ZoneInfo("Asia/Seoul")
PHRASE = "취재를 종합하면"
ADDITIONAL_PHRASE = "본지 취재 결과"
TARGET_PHRASE_VERSION = "evidence-v2-20261028"
# The two historical seed expressions are kept separate from the newly
# collected evidence-attribution phrases for transparent longitudinal analysis.
TARGET_PHRASE_RULES = (
    (PHRASE, r"취재를 종합하면"),
    (ADDITIONAL_PHRASE, r"본지\s*취재\s*결과"),
    ("취재에 따르면", r"취재에\s*따르면"),
    ("취재한 결과", r"취재(?:를\s*)?한\s*결과"),
    ("본보 취재 결과", r"본보\s*취재\s*결과"),
    ("본지 확인 결과", r"본지\s*확인\s*결과"),
)
TARGET_PHRASES = tuple(label for label, _ in TARGET_PHRASE_RULES)
TARGET_PHRASE_COMPILED = tuple(
    (label, re.compile(pattern)) for label, pattern in TARGET_PHRASE_RULES
)
# Quoted exact-match searches; variants appear as individual queries where
# the collector's lexicon accepts spacing and grammatical variations.
TARGET_SEARCH_QUERIES = (
    f'"{PHRASE}"', f'"{ADDITIONAL_PHRASE}"', '"본지 취재결과"',
    '"취재에 따르면"', '"취재한 결과"', '"취재를 한 결과"',
    '"본보 취재 결과"', '"본보 취재결과"',
    '"본지 확인 결과"', '"본지 확인결과"',
)
LEGACY_TARGET_PHRASES = (PHRASE, ADDITIONAL_PHRASE)

def target_phrase_counts(body):
    body = str(body or "")
    return {label: len(pattern.findall(body))
            for label, pattern in TARGET_PHRASE_COMPILED}

def contains_target_phrase(text):
    return any(target_phrase_counts(text).values())
NAVER_API_URL = "https://naverapihub.apigw.ntruss.com/search/v1/news"
# Song & Ihm (2026), Table 3: two broad types and six subtypes.
# These are lexical candidate matches, not contextual judgments about whether
# a sentence actually suppresses its source. Keep precise versioned metadata.
SECONDARY_TAXONOMY_VERSION = "paper-table3-v2"
SUBJECTLESS_RULES = [
    # (major type, subtype, displayed canonical expression, lexical pattern)
    ("출처소거형", "피동형", "알려졌다", r"알려졌(?:다|고|으며|지만|는데)"),
    ("출처소거형", "피동형", "전해졌다", r"전해졌(?:다|고|으며|지만|는데)"),
    ("출처소거형", "전언형", "했다고 한다", r"(?:했|하였)다고\s+한다"),
    # User-approved extension beyond the paper's Table 3:
    ("출처소거형", "전언형", "법조계에 따르면", r"법조계에\s+따르면"),
    ("출처소거형", "자생발생형", "지적이 나온다", r"지적(?:이|도)\s+나(?:온다|왔다|오고|오면서)"),
    ("출처소거형", "자생발생형", "해석이 나온다", r"해석(?:이|도)\s+나(?:온다|왔다|오고|오면서)"),
    ("출처소거형", "자생발생형", "분석이 나온다", r"분석(?:이|도)\s+나(?:온다|왔다|오고|오면서)"),
    ("출처소거형", "자생발생형", "우려가 제기된다", r"우려(?:가|도)\s+제기(?:된다|됐다|되고|되면서)"),
    ("기자귀속형", "해석형", "풀이된다", r"풀이(?:된다|됐다|되고|되면서)"),
    ("기자귀속형", "해석형", "해석된다", r"해석(?:된다|됐다|되고|되면서)"),
    ("기자귀속형", "해석형", "보인다", r"보인다(?![가-힣])"),
    ("기자귀속형", "해석형", "거론된다", r"거론(?:된다|됐다|되고|되면서)"),
    ("기자귀속형", "명사형", "셈이다", r"셈이다(?![가-힣])"),
    ("기자귀속형", "명사형", "대목이다", r"대목이다(?![가-힣])"),
    ("기자귀속형", "명사형", "관측이다", r"관측이다(?![가-힣])"),
]
# Exploratory non-paper expressions. Keep them separate from paper type totals.
SUBJECTLESS_OTHER_RULES = [
    ("기타", "기타", "파악됐다", r"파악됐(?:다|고|으며|지만|는데)"),
    ("기타", "기타", "확인됐다", r"확인됐(?:다|고|으며|지만|는데)"),
]
WIRE_NAMES = ["연합뉴스", "뉴스1", "뉴시스"]
COLLECTOR_VERSION = "0.5.8-target-evidence-v2"

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
    "etoday.co.kr": "이투데이",
}

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/155.0.0.0 Safari/537.36"
)

COMMON_BODY_SELECTORS = [
    "#dic_area",
    "#newsct_article",
    '[itemprop="articleBody"]',
    "#articleBody",
    "#article_body",
    "#article-view-content-div",
    ".article-text",
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
    "article",
    "main",
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


def publisher_as_reporter(raw, publisher="", host=""):
    """A newsroom/site label must never be classified as an individual byline."""
    raw = clean_text(raw).strip()
    raw = re.sub(r"\\s*(?:기자|특파원|논설위원|에디터|PD)$", "", raw).strip()
    if not raw:
        return False
    normalized = raw.casefold().replace(" ", "").replace("-", "")
    if publisher and normalized == clean_text(publisher).casefold().replace(" ", "").replace("-", ""):
        return True
    expected = normalize_publisher("", host)
    if expected and normalized == expected.casefold().replace(" ", "").replace("-", ""):
        return True
    if (host or "").lower().endswith("etoday.co.kr"):
        return normalized in ("이투데이", "etoday")
    return False


def normalize_reporter_text(raw, publisher="", host=""):
    raw = clean_text(raw)
    if not raw:
        return ""
    if raw.startswith("http://") or raw.startswith("https://"):
        return ""
    if publisher_as_reporter(raw, publisher, host):
        return ""

    names = re.findall(r"([가-힣]{2,4})\s*기자", raw)
    if names:
        names = [n for n in names if not publisher_as_reporter(n, publisher, host)]
    if names:
        return ", ".join(dict.fromkeys(names))

    parts = [clean_text(x) for x in re.split(r"[,/·|]", raw)]
    good = []
    for part in parts:
        part = re.sub(r"\s*(기자|특파원|논설위원|에디터|PD)$", "", part).strip()
        if publisher_as_reporter(part, publisher, host):
            continue
        if re.fullmatch(r"[가-힣]{2,4}", part):
            good.append(part)
        elif re.fullmatch(r"[가-힣A-Za-z0-9]{2,10}팀", part):
            good.append(part)
    return ", ".join(dict.fromkeys(good))


def infer_reporters(soup, data, publisher, host):
    candidates = []
    if (host or "").lower().endswith("etoday.co.kr"):
        # Visible author links take precedence over generic '이투데이' author
        # metadata. Do not use related-news text as an inferred reporter.
        for node in soup.select('a[href*="/reporter?eid="]')[:5]:
            candidates.append(node.get_text(" ", strip=True))
    candidates.extend([
        author_name(data.get("author")),
        meta(soup, "author", "article:author", "parsely-author"),
    ])
    for selector in [
        ".reporter", ".reporter_name", ".journalist", ".author", ".byline",
        "[class*='reporter']", "[class*='journalist']", "[class*='byline']",
    ]:
        for node in soup.select(selector)[:5]:
            candidates.append(node.get_text(" ", strip=True))

    host = (host or "").lower().removeprefix("www.")
    page_text = clean_text(soup.get_text(" ", strip=True))

    for raw in candidates:
        cleaned = normalize_reporter_text(raw, publisher, host)
        if cleaned:
            # 팀 바이라인이 대표값으로 노출되는 CMS는 같은 페이지의
            # '○○팀 개인명 기자' 표기에서 실제 작성자를 우선한다.
            if cleaned.endswith("팀"):
                m = re.search(
                    rf"{re.escape(cleaned)}\s*([가-힣]{{2,4}})\s*기자",
                    page_text,
                )
                if m:
                    return m.group(1)
                # 경향신문 플랫처럼 상단에는 팀 바이라인, 기사 하단에는
                # 실제 작성자 이름+이메일을 노출하는 경우를 처리한다.
                if host.endswith("khan.co.kr"):
                    matches = re.findall(
                        r"([가-힣]{2,4})\s*기자\s+[A-Za-z0-9._%+-]+@(?:khan\.kr|kyunghyang\.com)",
                        page_text,
                    )
                    if matches:
                        return matches[-1]
            return cleaned

    # '기자명'은 뉴스 CMS의 명시적 메타데이터 라벨이므로 매체 공통 fallback으로 사용한다.
    m = re.search(r"기자명\s*([가-힣]{2,4})(?:\s*기자)?", page_text)
    if m and not publisher_as_reporter(m.group(1), publisher, host):
        return m.group(1)

    # 이메일 앞 이름은 현재 확인된 CMS에서만 제한적으로 사용한다.
    if host.endswith("ksilbo.co.kr") or host.endswith("labortoday.co.kr"):
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


def valid_body_container(node):
    """Exclude hidden search overlays and metadata/script markup from article bodies."""
    if node is None or node.name in ("script", "style", "noscript", "template", "nav", "head"):
        return False
    if node.find_parent(["script", "style", "noscript", "template", "nav", "head"]):
        return False
    if re.search(r"(^|[\s_-])(search_layer|search-layer|popup|modal)([\s_-]|$)",
                 " ".join(node.get("class", [])) + " " + (node.get("id") or ""),
                 flags=re.I):
        return False
    return True


# Site-specific public article containers. They are checked only on their
# matching publisher host, not against untrusted search-page text.
PUBLISHER_BODY_SELECTORS = {
    "businesspost.co.kr": ("#article-body-content",),
    "viva100.com": (".news_content",),
    "kbsm.net": ('[itemprop="articleBody"]',),
}


def publisher_body_node(soup, host):
    host = (host or "").lower()
    for domain, selectors in PUBLISHER_BODY_SELECTORS.items():
        if host != domain and not host.endswith("." + domain):
            continue
        for selector in selectors:
            node = soup.select_one(selector)
            if node is None or node.name not in ("div", "section", "article", "main"):
                continue
            text = clean_text(node.get_text("\n", strip=True))
            if not (100 <= len(text) <= 80000) or not contains_target_phrase(text):
                continue
            # Some kbsm pages have malformed head markup containing the
            # articleBody <div>. The browser moves it into body, but html.parser
            # leaves it under head; explicitly accept only this exact known
            # articleBody element on that host, never scripts or metadata.
            if domain == "kbsm.net" and node.get("itemprop") == "articleBody":
                return node
            if valid_body_container(node):
                return node
    return None


def official_businesspost_mobile_url(url):
    """One public mobile alternative for a www/root article blocked by HTTP 403."""
    parsed = urlparse(url or "")
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or host not in ("www.businesspost.co.kr", "businesspost.co.kr"):
        return ""
    if parsed.path != "/BP":
        return ""
    params = parse_qs(parsed.query)
    num = (params.get("num") or [""])[0]
    command = (params.get("command") or [""])[0]
    if not re.fullmatch(r"[0-9]{2,12}", num) or command not in ("article_view", "mobile_view"):
        return ""
    return f"https://m.businesspost.co.kr/BP?command=article_view&num={num}"


def choose_body_container(soup, host=""):
    site_node = publisher_body_node(soup, host) if host else None
    if site_node is not None:
        return site_node
    # Specific article-body containers beat generic article/page elements,
    # even when the article has none of our target phrases (QA / ordinary news).
    fallback = None
    for selector in COMMON_BODY_SELECTORS:
        for node in soup.select(selector):
            if not valid_body_container(node):
                continue
            text = clean_text(node.get_text("\n", strip=True))
            if not (100 <= len(text) <= 80000):
                continue
            if fallback is None:
                fallback = node
            if contains_target_phrase(text):
                return node

    # A rare layout might not use any of the common body wrappers.
    # NEVER search a script or its descendants for a phrase: Chosun's
    # fusion-metadata contains a serialized article, not visible body text.
    phrase_nodes = soup.find_all(string=lambda x: isinstance(x, str) and contains_target_phrase(x))
    for text_node in phrase_nodes:
        if text_node.find_parent(["script", "style", "noscript", "template", "nav", "head"]):
            continue
        node = text_node.parent
        for _ in range(6):
            if not valid_body_container(node) or node.name in ("html", "body"):
                break
            text = clean_text(node.get_text("\n", strip=True))
            if 150 <= len(text) <= 30000 and contains_target_phrase(text):
                return node
            node = node.parent
    return fallback


def clean_structured_fragment(value):
    text = clean_text(value)
    if not text:
        return ""

    # 일부 SPA/CMS가 본문 주변에 JSON의 description 필드를 텍스트처럼 노출한다.
    # JSON string의 실제 값만 안전하게 복원해 표시용 문맥에 키/이스케이프가 섞이지 않게 한다.
    m = re.match(
        r'^\{?\s*"description"\s*:\s*"((?:\\\\.|[^"\\\\])*)"',
        text,
    )
    if m:
        try:
            decoded = json.loads('"' + m.group(1) + '"')
            return clean_text(decoded)
        except Exception:
            return clean_text(m.group(1))

    return text


def extract_paragraphs(container):
    if not container:
        return []

    # 기사 영역 안의 구조화 데이터/광고 스크립트가 본문 텍스트로 섞이지 않게 제거한다.
    for bad in container.find_all(["script", "style", "noscript", "template"]):
        bad.decompose()

    paras = []
    for p in container.find_all("p"):
        raw = p.get_text("\n", strip=True)
        segments = [clean_structured_fragment(x) for x in re.split(r"\n+", raw)]
        for text in segments:
            if len(text) >= 20 and text not in paras:
                paras.append(text)
    if any(contains_target_phrase(p) for p in paras):
        return paras

    raw = container.get_text("\n", strip=True)
    lines = [clean_structured_fragment(x) for x in re.split(r"\n+", raw)]
    return [x for x in lines if len(x) >= 20]


def phrase_contexts(paragraphs):
    out = []
    for idx, paragraph in enumerate(paragraphs, start=1):
        counts = target_phrase_counts(paragraph)
        count = sum(counts.values())
        if count:
            out.append({
                "paragraph_no": idx,
                "count": count,
                "phrase_counts": {k: v for k, v in counts.items() if v},
                "text": paragraph,
            })
    return out


def secondary_counts(body):
    """Paper Table 3 expressions, excluding the mandatory seed phrase itself."""
    result = {}
    for _major, _subtype, label, pattern in (*SUBJECTLESS_RULES, *SUBJECTLESS_OTHER_RULES):
        count = len(re.findall(pattern, body))
        if count:
            result[label] = count
    return result


def subjectless_type_counts(body, expressions=None):
    """Versioned grouping; 종합형 is tracked through PHRASE separately."""
    expressions = expressions if expressions is not None else secondary_counts(body)
    groups = {}
    for major, subtype, label, _pattern in (*SUBJECTLESS_RULES, *SUBJECTLESS_OTHER_RULES):
        count = expressions.get(label, 0)
        if count:
            key = f"{major} / {subtype}"
            groups[key] = groups.get(key, 0) + count
    legacy_counts = target_phrase_counts(body)
    seed = sum(legacy_counts.get(p, 0) for p in LEGACY_TARGET_PHRASES)
    if seed:
        groups["기자귀속형 / 종합형"] = seed
    return groups


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
        "fetch_variant": "ORIGINAL",
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
        # Businesspost blocks the public desktop host in our collector runtime,
        # but publishes the same numbered article at its official mobile host.
        # No login/cookies/anti-bot bypass; only try that public equivalent once.
        if r.status_code == 403:
            mobile_url = official_businesspost_mobile_url(url)
            if mobile_url:
                alt = session.get(mobile_url, timeout=20, allow_redirects=True)
                mobile_num = parse_qs(urlparse(alt.url).query).get("num", [""])[0]
                requested_num = parse_qs(urlparse(url).query).get("num", [""])[0]
                if (alt.status_code == 200
                    and (urlparse(alt.url).hostname or "").lower() == "m.businesspost.co.kr"
                    and mobile_num == requested_num):
                    r = alt
                    result["status_code"] = 200
                    result["final_url"] = r.url
                    result["fetch_variant"] = "OFFICIAL_MOBILE"
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

        container = choose_body_container(soup, host)
        paragraphs = extract_paragraphs(container)

        if not any(contains_target_phrase(p) for p in paragraphs):
            article_body = clean_text(data.get("articleBody"))
            if contains_target_phrase(article_body):
                paragraphs = [article_body]

        body = "\n".join(paragraphs)
        result["body"] = body
        result["paragraphs"] = paragraphs
        result["phrase_count"] = sum(target_phrase_counts(body).values())
        result["phrase_counts"] = target_phrase_counts(body)
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


def suspicious_context(result):
    contexts = result.get("phrase_contexts") or []
    texts = [
        str(item.get("text") or "")
        for item in contexts
        if isinstance(item, dict)
    ]
    if not texts:
        return True
    markers = [
        '"description":',
        '{"description"',
        '"pageProps":',
        '{"props":',
        "__NEXT_DATA__",
        "Fusion.spa",
        '"contentArrange":',
        "var messageText =",
    ]
    for text in texts:
        if len(text) >= 1200:
            return True
        if any(marker in text for marker in markers):
            return True
    return False


def parse_naver(url):
    result = {
        "ok": False,
        "title": "",
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
        result["title"] = clean_text(
            meta(soup, "og:title", "twitter:title")
            or (soup.find("h2", id="title_area").get_text(" ", strip=True)
                if soup.find("h2", id="title_area") else "")
        )
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
        result["phrase_count"] = sum(target_phrase_counts(body).values())
        result["phrase_counts"] = target_phrase_counts(body)
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


def collect_target_candidates(client_id, client_secret, target_date, max_articles):
    # Query all authorized variants, then deduplicate on the original article URL.
    # Existing core phrases go first so a broad query cannot starve them.
    queries = list(TARGET_SEARCH_QUERIES)
    by_url = {}
    for query in queries:
        for item in fetch_candidates(client_id, client_secret, target_date, query=query):
            # Same published URL may appear in both search responses.
            key = item.get("original_url") or item.get("naver_url")
            if key:
                by_url.setdefault(key, item)
    candidates = sorted(
        by_url.values(), key=lambda row: row["api_pubdate"], reverse=True
    )
    return candidates[:max_articles], queries


def doc_id(url):
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:32]


# Historical correction is explicitly limited to named articles whose
# published bylines were independently verified on the Etoday article pages.
# All other erroneous publisher-name bylines become 'unknown', never invented.
ETODAY_VERIFIED_BYLINES_20261026 = {
    "2640275": "김재학",
    "2640213": "김재학",
    "2640198": "김재학",
    "2640195": "김재학",
}
ETODAY_REPORTER_REPAIR_ID = "etoday-publisher-as-byline-20261027-v1"


def etoday_reporter_correction(article):
    """Return audited correction, or None for articles with no fake byline."""
    original_url = article.get("original_url") or ""
    host = (urlparse(original_url).hostname or "").lower()
    if host not in ("www.etoday.co.kr", "m.etoday.co.kr", "etoday.co.kr"):
        return None
    raw = str(article.get("reporters_resolved") or article.get("reporters_original") or "")
    if not publisher_as_reporter(raw, article.get("publisher_original") or "", host):
        return None
    # Permit a correctly attributed Naver journalist if there is one.
    naver_reporter = normalize_reporter_text(
        article.get("reporters_naver") or "", "이투데이", host
    )
    news_id_match = re.fullmatch(r"/news/view/(\d+)", urlparse(original_url).path)
    key = news_id_match.group(1) if news_id_match else ""
    verified = ETODAY_VERIFIED_BYLINES_20261026.get(key, "")
    replacement = verified or naver_reporter
    return {
        "reporters_resolved": replacement,
        "reporters_original": "",
        "reporter_source": "VERIFIED_BYLINE" if verified else ("NAVER" if naver_reporter else "NONE"),
        "reporter_invalid_previous": raw,
        "reporter_repair_status": "VERIFIED" if verified else (
            "NAVER" if naver_reporter else "UNKNOWN_NOT_GUESSED"
        ),
        "reporter_repaired_at": firestore.SERVER_TIMESTAMP,
    }


def repair_etoday_reporters_once(db):
    """Correct bogus Etoday reporter names in existing accepted Firestore rows."""
    marker_ref = db.collection("maintenance_runs").document(ETODAY_REPORTER_REPAIR_ID)
    if marker_ref.get().exists:
        return
    checked = changed = verified = unknown = 0
    for doc in (
        db.collection("articles")
        .order_by("api_pubdate", direction=firestore.Query.DESCENDING)
        .limit(2000)
        .stream()
    ):
        article = doc.to_dict() or {}
        if article.get("status") != "accepted":
            continue
        checked += 1
        patch = etoday_reporter_correction(article)
        if patch is None:
            continue
        doc.reference.set(patch, merge=True)
        changed += 1
        verified += int(patch["reporter_repair_status"] in ("VERIFIED", "NAVER"))
        unknown += int(patch["reporter_repair_status"] == "UNKNOWN_NOT_GUESSED")
    marker_ref.set({
        "finished_at": datetime.now(KST).isoformat(),
        "scanned": checked,
        "corrected": changed,
        "confirmed": verified,
        "unknown": unknown,
    })
    print(f"[ETODAY BYLINE REPAIR] corrected={changed} confirmed={verified} unknown={unknown}")


def backfill_subjectless_once(db):
    """Recalculate the previously stored corpus from private body text, without
    re-fetching articles or invoking an AI model. Repeated runs are idempotent."""
    marker_ref = db.collection("maintenance_runs").document(SECONDARY_TAXONOMY_VERSION)
    if marker_ref.get().exists:
        return

    changed = 0
    missing_body = 0
    docs = (
        db.collection("articles")
        .order_by("api_pubdate", direction=firestore.Query.DESCENDING)
        .limit(2000)
        .stream()
    )
    for doc in docs:
        data = doc.to_dict() or {}
        if data.get("status") != "accepted" or data.get("secondary_taxonomy_version") == SECONDARY_TAXONOMY_VERSION:
            continue
        body = data.get("body_text_private") or ""
        if not body:
            missing_body += 1
            continue
        expressions = secondary_counts(body)
        counts = target_phrase_counts(body)
        doc.reference.set({
            "secondary_expressions": expressions,
            "subjectless_type_counts": subjectless_type_counts(body, expressions),
            "secondary_taxonomy_version": SECONDARY_TAXONOMY_VERSION,
            "phrase_counts": counts,
            "phrase_count": sum(counts.values()),
            "phrase_contexts": phrase_contexts(body.split("\n")),
        }, merge=True)
        changed += 1

    marker_ref.set({
        "finished_at": datetime.now(KST).isoformat(),
        "version": SECONDARY_TAXONOMY_VERSION,
        "updated_articles": changed,
        "skipped_without_body": missing_body,
        "limit": 2000,
    })
    print(f"[SUBJECTLESS BACKFILL] updated={changed}, missing_body={missing_body}")


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
    backfill_subjectless_once(db)
    repair_etoday_reporters_once(db)
    now = datetime.now(KST)
    target_date = now.date()
    run_ref = db.collection("collector_runs").document(now.strftime("%Y%m%dT%H%M%S%z"))

    candidates, queries = collect_target_candidates(
        client_id, client_secret, target_date, max_articles
    )

    summary = {
        "target_date": str(target_date),
        "started_at": now.isoformat(),
        "search_query_used": " ; ".join(queries),
        "search_queries_used": queries,
        "target_phrase_version": TARGET_PHRASE_VERSION,
        "candidates": len(candidates),
        "accepted": 0,
        "existing_accepted": 0,
        "new_accepted": 0,
        "original_success": 0,
        "naver_fallback": 0,
        "naver_preferred_diff": 0,
        "rejected": 0,
        "exclusive": 0,
        "wire_reprint_suspected": 0,
        "errors": {},
        "rejected_examples": [],
        "domain_diagnostics": {},
    }

    for idx, item in enumerate(candidates, start=1):
        original_url = item["original_url"]
        host = (urlparse(original_url).hostname or "미확인").lower()
        domain_stats = summary["domain_diagnostics"].setdefault(host, {
            "seen": 0, "accepted": 0, "rejected": 0,
            "original_errors": 0, "naver_errors": 0,
            "errors": {}, "examples": [],
        })
        domain_stats["seen"] += 1
        article_ref = db.collection("articles").document(doc_id(original_url))

        existing = article_ref.get()
        existing_data = existing.to_dict() if existing.exists else {}
        # On a rules-only upgrade, do not fetch all previously accepted articles.
        # The stored body already contains the text needed for an idempotent update.
        if (existing.exists and existing_data.get("status") == "accepted"
                and existing_data.get("collector_version") != COLLECTOR_VERSION
                and existing_data.get("body_text_private")
                and not suspicious_body(existing_data["body_text_private"])
                and not suspicious_context({
                    "phrase_contexts": existing_data.get("phrase_contexts") or [],
                })):

            body = existing_data["body_text_private"]
            counts = target_phrase_counts(body)
            if sum(counts.values()):
                expressions = secondary_counts(body)
                article_ref.set({
                    "collector_version": COLLECTOR_VERSION,
                    "secondary_expressions": expressions,
                    "secondary_taxonomy_version": SECONDARY_TAXONOMY_VERSION,
                    "subjectless_type_counts": subjectless_type_counts(body, expressions),
                    "phrase_counts": counts,
                    "phrase_count": sum(counts.values()),
                    "target_phrase_version": TARGET_PHRASE_VERSION,
                    "phrase_contexts": phrase_contexts(body.split("\n")),
                    "last_seen_at": firestore.SERVER_TIMESTAMP,
                }, merge=True)
                summary["accepted"] += 1
                summary["existing_accepted"] += 1
                domain_stats["accepted"] += 1
                summary["exclusive"] += int(bool(existing_data.get("is_exclusive_strict")))
                continue
        if (
            existing.exists
            and existing_data.get("status") == "accepted"
            and existing_data.get("collector_version") == COLLECTOR_VERSION
        ):
            summary["accepted"] += 1
            summary["existing_accepted"] += 1
            domain_stats["accepted"] += 1
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
            "ok": False, "title": "", "reporters": "", "body": "", "phrase_count": 0, "phrase_contexts": [],
            "secondary": {}, "error": "NO_NAVER_PAGE"
        }

        original_clean = (
            original["phrase_count"] > 0
            and not suspicious_body(original.get("body", ""))
            and not suspicious_context(original)
        )
        original_has_phrase = original["phrase_count"] > 0
        naver_has_phrase = naver["phrase_count"] > 0
        body_sim = (
            similarity(original.get("body", ""), naver.get("body", ""))
            if original_has_phrase and naver_has_phrase
            else None
        )

        # 표시·집계용 본문은 NAVER 전송본이 존재하고 원문과 다르면 NAVER를 기준으로 한다.
        # 원문은 언론사/기자/원문 카테고리 등 provenance용 메타데이터 기준으로 유지한다.
        if naver_has_phrase and original_has_phrase and body_sim is not None and body_sim < 1.0:
            final = naver
            source = "NAVER_PREFERRED_DIFF"
            summary["naver_preferred_diff"] += 1
        elif original_clean:
            final = original
            source = "ORIGINAL"
            summary["original_success"] += 1
        elif naver_has_phrase:
            final = naver
            source = "NAVER_FALLBACK"
            summary["naver_fallback"] += 1
        elif original_has_phrase:
            final = original
            source = "ORIGINAL_LOW_QUALITY"
            summary["original_success"] += 1
        else:
            final = original
            source = "REJECTED"
            summary["rejected"] += 1
            if len(summary["rejected_examples"]) < 20:
                summary["rejected_examples"].append({
                    "title": item["api_title"][:130],
                    "domain": (urlparse(original_url).hostname or "").lower(),
                    "original_error": original.get("error") or "",
                    "naver_error": naver.get("error") or "",
                    "has_naver_copy": bool(item["naver_url"]),
                })

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

        # Per-source diagnostics are complete for this run, unlike the capped
        # rejected_examples list. Absent phrases are recorded separately and
        # must not automatically be interpreted as an extraction bug.
        if source == "REJECTED":
            domain_stats["rejected"] += 1
            if len(domain_stats["examples"]) < 3:
                domain_stats["examples"].append(item["api_title"][:100])
        else:
            domain_stats["accepted"] += 1
        for result, kind in ((original, "original"), (naver, "naver")):
            err = result.get("error") or ""
            if not err or err == "NO_NAVER_PAGE":
                continue
            domain_stats[kind + "_errors"] += 1
            tag = kind + ":" + err
            domain_stats["errors"][tag] = domain_stats["errors"].get(tag, 0) + 1

        reporters_original = original.get("reporters", "")
        reporters_naver = naver.get("reporters", "")
        reporters_resolved = reporters_original or reporters_naver
        reporter_source = "ORIGINAL" if reporters_original else ("NAVER" if reporters_naver else "NONE")

        content_basis = "NAVER" if source in ("NAVER_PREFERRED_DIFF", "NAVER_FALLBACK") else "ORIGINAL"
        content_basis_reason = {
            "NAVER_PREFERRED_DIFF": "ORIGINAL_NAVER_DIFFER",
            "NAVER_FALLBACK": "ORIGINAL_UNAVAILABLE_OR_LOW_QUALITY",
            "ORIGINAL": "ORIGINAL_AND_NAVER_EQUIVALENT_OR_NAVER_UNAVAILABLE",
            "ORIGINAL_LOW_QUALITY": "NAVER_UNAVAILABLE",
            "REJECTED": "PHRASE_NOT_CONFIRMED",
        }.get(source, source)

        title_original = original.get("title", "")
        title_naver = naver.get("title", "")
        title_resolved = title_original or title_naver or item["api_title"]

        article = {
            "status": "accepted" if source != "REJECTED" else "rejected",
            "final_source": source,
            "content_basis": content_basis,
            "content_basis_reason": content_basis_reason,
            "api_title": item["api_title"],
            "title_original": title_original,
            "title_naver": title_naver,
            "title_resolved": title_resolved,
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
            "phrase_counts": final.get("phrase_counts", target_phrase_counts(final.get("body", ""))),
            "target_phrase_version": TARGET_PHRASE_VERSION,
            "phrase_count": final.get("phrase_count", 0),
            "phrase_contexts": final.get("phrase_contexts", []),
            "secondary_expressions": final.get("secondary", {}),
            "secondary_taxonomy_version": SECONDARY_TAXONOMY_VERSION,
            "subjectless_type_counts": subjectless_type_counts(
                final.get("body", ""), final.get("secondary", {})
            ),
            "body_text_private": final.get("body", ""),
            "original_parse_error": original.get("error", ""),
            "original_fetch_variant": original.get("fetch_variant", "ORIGINAL"),
            "original_fetch_final_url": original.get("final_url", original_url),
            "naver_parse_error": naver.get("error", ""),
            "body_similarity_original_vs_naver": body_sim if item["naver_url"] else None,
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
        if source == "REJECTED":
            print(
                f"[{idx}/{len(candidates)}] REJECTED"
                f" original={original.get('error') or '-'}"
                f" naver={naver.get('error') or '-'}"
                f" {item['api_title'][:70]}"
            )
        else:
            print(f"[{idx}/{len(candidates)}] {source} {item['api_title'][:70]}")

    summary["finished_at"] = datetime.now(KST).isoformat()
    run_ref.set(summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
