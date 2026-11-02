"""Stable article identity, without treating meaningful URL parameters as tracking.

The same module is copied to collector, public API and archive runtimes.
Do not normalize article content, stored original URLs, or other publisher IDs.
"""
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

NOCUT_HOSTS = frozenset(("nocutnews.co.kr", "www.nocutnews.co.kr"))
NOCUT_ARTICLE = re.compile(r"/news/(\d+)/?$", re.ASCII)


def canonical_article_url(value):
    url = str(value or "").strip()
    if not url:
        return ""
    try:
        parsed = urlsplit(url)
    except ValueError:
        return url
    host = (parsed.hostname or "").lower()
    if parsed.scheme.lower() not in ("https", "http") or not host:
        return url
    if host in NOCUT_HOSTS:
        match = NOCUT_ARTICLE.fullmatch(parsed.path)
        if match:
            # Never let an acquisition tracking code create a second article.
            return "https://www.nocutnews.co.kr/news/" + match.group(1)
    if not parsed.query and not parsed.fragment:
        return url
    pairs = parse_qsl(parsed.query, keep_blank_values=True)
    meaningful = [(k, v) for k, v in pairs if not k.lower().startswith("utm_")]
    if len(meaningful) == len(pairs) and not parsed.fragment:
        return url
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path,
                       urlencode(meaningful), ""))


def article_identity(article):
    return canonical_article_url(
        article.get("original_url") or article.get("naver_url") or ""
    ) or str(article.get("id") or "")


def completeness_score(article):
    """Prefer retained original text for research; equal scores keep first seen."""
    archived = (article.get("archive_body_status") == "수집 성공" and
                bool(article.get("archive_body_text")))
    return (
        int(archived),
        int(bool(article.get("body_text_private"))),
        int(bool(article.get("reporters_resolved"))),
        int(bool(article.get("taxonomy_version"))),
        len(str(article.get("archive_body_text") or "")),
        len(str(article.get("body_text_private") or "")),
    )


def unique_articles(articles):
    """View-only collapse for historical duplicate Firestore documents."""
    seen = {}
    for article in articles:
        key = article_identity(article)
        old = seen.get(key)
        if old is None or completeness_score(article) > completeness_score(old):
            seen[key] = article
    return list(seen.values())
