#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import ast
import hmac
import os
import re
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from google.cloud import firestore

PROJECT_ID = os.getenv("GCP_PROJECT_ID", "").strip() or None
KST = ZoneInfo("Asia/Seoul")
PHRASE = "취재를 종합하면"
ADMIN_EDITOR_PASSWORD = os.getenv("ADMIN_EDITOR_PASSWORD", "")
db = firestore.Client(project=PROJECT_ID)

DEFAULT_SITE_CONFIG = {
    "hero_description": "한국 언론의 기사에서 “취재를 종합하면”이 어떻게 쓰이는지 기록합니다.",
    "card_today_label": "오늘의 '취재 종합'",
    "card_publisher_label": "오늘의 최다 '취재 종합' 언론사",
    "card_reporter_label": "이번 주 가장 많이 '취재 종합'한 기자",
    "card_exclusive_label": "[단독] 동반 비율",
    "section_publisher_title": "오늘의 최다 '취재 종합' 언론사",
    "section_reporter_title": "이번 주 가장 많이 '취재 종합'한 기자",
    "section_category_title": "원문 기사 분류",
    "section_secondary_title": "함께 쓰인 무주체형 표현",
    "section_history_title": "최근 14일",
    "section_articles_title": "오늘의 '취재 종합' 문장들",
    "ranking_view_all_text": "전체 보기",
    "ranking_collapse_text": "접기",
    "paragraph_toggle_text": "문단 보기",
    "original_link_text": "원문 보기",
    "naver_link_text": "네이버 뉴스에서 보기",
    "articles_more_text": "더 보기",
}

app = FastAPI(
    title="취재를 종합하면 API",
    version="0.2.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["*"],
)

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


def serialize_value(value):
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    if isinstance(value, dict):
        return {k: serialize_value(v) for k, v in value.items()}
    if isinstance(value, list):
        return [serialize_value(v) for v in value]
    return value


def doc_to_dict(doc):
    data = doc.to_dict() or {}
    data["id"] = doc.id
    return serialize_value(data)


def domain_of(url):
    return (urlparse(url or "").hostname or "").lower().removeprefix("www.")


def recent_article_docs(limit=1200):
    return list(
        db.collection("articles")
        .order_by("api_pubdate", direction=firestore.Query.DESCENDING)
        .limit(limit)
        .stream()
    )


def parse_kst(value):
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=KST)
        return dt.astimezone(KST)
    except Exception:
        return None


def clean_category(value):
    text = str(value or "").strip()
    if not text:
        return ""
    if text.startswith("[") and text.endswith("]"):
        try:
            values = ast.literal_eval(text)
            if isinstance(values, list):
                return " · ".join(str(x).strip() for x in values if str(x).strip())
        except Exception:
            pass
    return text


def split_reporters(value, people_only=False):
    value = str(value or "").strip()
    if not value:
        return []
    if value.startswith("http://") or value.startswith("https://"):
        return []
    out = []
    for part in re.split(r"[,/·|]", value):
        part = re.sub(r"\s*(기자|특파원|논설위원|에디터|PD)$", "", part).strip()
        if re.fullmatch(r"[가-힣]{2,4}", part):
            out.append(part)
        elif not people_only and re.fullmatch(r"[가-힣A-Za-z0-9]{2,10}팀", part):
            out.append(part)
    return list(dict.fromkeys(out))


def context_sentence(paragraph):
    paragraph = re.sub(r"\s+", " ", str(paragraph or "")).strip()
    if not paragraph:
        return ""
    sentences = re.split(r"(?<=[.!?。])\s+|(?<=다\.)\s+", paragraph)
    for sentence in sentences:
        if PHRASE in sentence:
            return sentence.strip()
    pos = paragraph.find(PHRASE)
    if pos < 0:
        return paragraph[:180]
    start = max(0, pos - 90)
    end = min(len(paragraph), pos + len(PHRASE) + 110)
    excerpt = paragraph[start:end]
    if start:
        excerpt = "…" + excerpt
    if end < len(paragraph):
        excerpt += "…"
    return excerpt


def accepted_articles(limit=1200):
    out = []
    for doc in recent_article_docs(limit):
        data = doc.to_dict() or {}
        if data.get("status") != "accepted":
            continue
        data["id"] = doc.id
        data["_dt"] = parse_kst(data.get("api_pubdate"))
        data["category_original"] = clean_category(data.get("category_original"))
        out.append(data)
    return out


def get_site_config():
    config = dict(DEFAULT_SITE_CONFIG)
    snap = db.collection("site_config").document("public").get()
    if snap.exists:
        stored = snap.to_dict() or {}
        for key in DEFAULT_SITE_CONFIG:
            value = stored.get(key)
            if isinstance(value, str) and value.strip():
                config[key] = value.strip()
    return config


def require_admin(password):
    if not ADMIN_EDITOR_PASSWORD:
        raise HTTPException(status_code=503, detail="관리자 비밀번호가 아직 설정되지 않았습니다.")
    if not password or not hmac.compare_digest(password, ADMIN_EDITOR_PASSWORD):
        raise HTTPException(status_code=401, detail="관리자 비밀번호가 올바르지 않습니다.")


@app.get("/admin")
def admin_page():
    return FileResponse(os.path.join(STATIC_DIR, "admin.html"))


@app.get("/api/config")
def public_config():
    return get_site_config()


@app.put("/api/admin/config")
def update_site_config(payload: dict, x_admin_password: str | None = Header(default=None)):
    require_admin(x_admin_password)
    updates = {}
    for key in DEFAULT_SITE_CONFIG:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            updates[key] = value.strip()
    if not updates:
        raise HTTPException(status_code=400, detail="저장할 문구가 없습니다.")
    updates["updated_at"] = firestore.SERVER_TIMESTAMP
    db.collection("site_config").document("public").set(updates, merge=True)
    return {"ok": True, "config": get_site_config()}


@app.get("/")
def dashboard_page():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


@app.get("/api")
def api_root():
    return {
        "service": "취재를 종합하면 API",
        "version": "0.2.0",
        "endpoints": [
            "/health",
            "/api/dashboard",
            "/api/status",
            "/api/diagnostics",
            "/api/articles",
        ],
    }


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/api/dashboard")
def dashboard(target_date: str | None = Query(default=None, alias="date")):
    if target_date:
        try:
            selected = date.fromisoformat(target_date)
        except ValueError:
            selected = datetime.now(KST).date()
    else:
        selected = datetime.now(KST).date()

    week_start = selected - timedelta(days=selected.weekday())
    all_articles = accepted_articles(1200)

    today_articles = [
        a for a in all_articles
        if a.get("_dt") and a["_dt"].date() == selected
    ]
    week_articles = [
        a for a in all_articles
        if a.get("_dt") and week_start <= a["_dt"].date() <= selected
    ]

    publisher_counts = Counter(
        (a.get("publisher_original") or domain_of(a.get("original_url")) or "미확인")
        for a in today_articles
    )

    reporter_counts = Counter()
    for article in week_articles:
        publisher = article.get("publisher_original") or domain_of(article.get("original_url")) or "미확인"
        for reporter in split_reporters(
            article.get("reporters_resolved") or article.get("reporters_original"),
            people_only=True,
        ):
            reporter_counts[(reporter, publisher)] += 1

    category_counts = Counter(
        a.get("category_original") or "미분류"
        for a in today_articles
    )

    secondary_counts = Counter()
    for article in today_articles:
        for exp, count in (article.get("secondary_expressions") or {}).items():
            secondary_counts[exp] += int(count or 0)

    exclusive_count = sum(bool(a.get("is_exclusive_strict")) for a in today_articles)

    daily_counts = Counter()
    for article in all_articles:
        dt = article.get("_dt")
        if not dt:
            continue
        if selected - timedelta(days=13) <= dt.date() <= selected:
            daily_counts[str(dt.date())] += 1

    top_publisher = publisher_counts.most_common(1)
    top_reporter = reporter_counts.most_common(1)
    config = get_site_config()

    article_rows = []
    for a in sorted(
        today_articles,
        key=lambda x: x.get("_dt") or datetime.min.replace(tzinfo=KST),
        reverse=True,
    ):
        contexts = a.get("phrase_contexts") or []
        first_context = contexts[0].get("text", "") if contexts else ""
        article_rows.append({
            "id": a.get("id"),
            "title": a.get("api_title"),
            "publisher": a.get("publisher_original") or domain_of(a.get("original_url")) or "미확인",
            "reporters": split_reporters(a.get("reporters_resolved") or a.get("reporters_original")),
            "published_at": a.get("api_pubdate"),
            "category_original": a.get("category_original") or "미분류",
            "is_exclusive": bool(a.get("is_exclusive_strict")),
            "phrase_count": int(a.get("phrase_count") or 0),
            "context_sentence": context_sentence(first_context),
            "context_paragraph": first_context,
            "secondary_expressions": a.get("secondary_expressions") or {},
            "original_url": a.get("original_url"),
            "naver_url": a.get("naver_url"),
        })

    return {
        "date": str(selected),
        "week_start": str(week_start),
        "today_count": len(today_articles),
        "exclusive_count": exclusive_count,
        "exclusive_ratio": round(exclusive_count / len(today_articles), 4) if today_articles else 0,
        "top_publisher": (
            {"name": top_publisher[0][0], "count": top_publisher[0][1]}
            if top_publisher else None
        ),
        "top_reporter_week": (
            {
                "name": top_reporter[0][0][0],
                "publisher": top_reporter[0][0][1],
                "count": top_reporter[0][1],
            }
            if top_reporter else None
        ),
        "publisher_ranking": [
            {"name": name, "count": count}
            for name, count in publisher_counts.most_common()
        ],
        "reporter_ranking_week": [
            {"name": key[0], "publisher": key[1], "count": count}
            for key, count in reporter_counts.most_common()
        ],
        "category_ranking_original": [
            {"name": name, "count": count}
            for name, count in category_counts.most_common()
        ],
        "secondary_expressions": [
            {"name": name, "count": count}
            for name, count in secondary_counts.most_common()
        ],
        "daily_counts_14d": [
            {
                "date": str(selected - timedelta(days=offset)),
                "count": daily_counts.get(str(selected - timedelta(days=offset)), 0),
            }
            for offset in range(13, -1, -1)
        ],
        "articles": article_rows,
        "site_config": config,
        "methodology": {
            "query": f'"{PHRASE}"',
            "source_priority": "언론사 원문 우선, NAVER 전송본 비교",
            "refresh": "30분 간격",
            "category_note": "현재 주제는 언론사 원문 카테고리를 참고값으로 표시합니다.",
        },
    }


@app.get("/api/status")
def status():
    runs = (
        db.collection("collector_runs")
        .order_by("started_at", direction=firestore.Query.DESCENDING)
        .limit(10)
        .stream()
    )
    run_list = [doc_to_dict(doc) for doc in runs]

    article_docs = recent_article_docs(300)

    total_seen = 0
    accepted = 0
    rejected = 0
    source_counts = Counter()
    category_available = 0
    accepted_category_available = 0
    exclusive = 0
    accepted_exclusive = 0
    wire_reprint = 0
    accepted_wire_reprint = 0

    for doc in article_docs:
        total_seen += 1
        data = doc.to_dict() or {}
        state = data.get("status")
        if state == "accepted":
            accepted += 1
        elif state == "rejected":
            rejected += 1

        source_counts[data.get("final_source") or "UNKNOWN"] += 1

        if data.get("category_original"):
            category_available += 1
            if state == "accepted":
                accepted_category_available += 1
        if data.get("is_exclusive_strict"):
            exclusive += 1
            if state == "accepted":
                accepted_exclusive += 1
        if data.get("is_wire_reprint_suspected"):
            wire_reprint += 1
            if state == "accepted":
                accepted_wire_reprint += 1

    return {
        "latest_run": run_list[0] if run_list else None,
        "recent_runs": run_list,
        "recent_article_snapshot": {
            "sample_size": total_seen,
            "accepted": accepted,
            "rejected": rejected,
            "source_counts": dict(source_counts),
            "category_original_available": category_available,
            "accepted_category_original_available": accepted_category_available,
            "exclusive_strict_all_candidates": exclusive,
            "exclusive_strict_accepted": accepted_exclusive,
            "exclusive_ratio_among_accepted": (
                round(accepted_exclusive / accepted, 4) if accepted else None
            ),
            "wire_reprint_suspected": wire_reprint,
            "accepted_wire_reprint_suspected": accepted_wire_reprint,
        },
    }


@app.get("/api/diagnostics")
def diagnostics():
    docs = recent_article_docs(300)

    by_domain = defaultdict(lambda: {
        "total": 0,
        "accepted": 0,
        "rejected": 0,
        "category_available": 0,
        "has_naver_url": 0,
        "naver_verified": 0,
    })
    rejection_reasons = Counter()
    accepted_original_errors = Counter()
    metadata_quality = Counter()
    paragraph_quality = Counter()

    reporter_missing_samples = []
    category_missing_samples = []
    publisher_missing_samples = []
    suspicious_reporter_samples = []
    reporter_fallback_samples = []
    paragraph_issue_samples = []
    accepted_samples = []
    rejected_samples = []

    suspicious_context_markers = [
        '"description":',
        '{"description"',
        '"pageProps":',
        '{"props":',
        "__NEXT_DATA__",
        "Fusion.spa",
        '"contentArrange":',
        "var messageText =",
    ]

    for doc in docs:
        data = doc.to_dict() or {}
        state = data.get("status") or "unknown"
        domain = domain_of(data.get("original_url")) or "(unknown)"
        stats = by_domain[domain]
        stats["total"] += 1
        stats[state] = stats.get(state, 0) + 1

        if data.get("category_original"):
            stats["category_available"] += 1
        if data.get("naver_url"):
            stats["has_naver_url"] += 1
        if data.get("naver_url") and not data.get("naver_parse_error"):
            stats["naver_verified"] += 1

        original_error = data.get("original_parse_error") or ""
        naver_error = data.get("naver_parse_error") or ""

        if state == "accepted":
            resolved_reporter = data.get("reporters_resolved") or data.get("reporters_original")
            reporters = split_reporters(resolved_reporter)
            raw_reporter = str(data.get("reporters_original") or "")
            publisher = data.get("publisher_original") or ""
            category = clean_category(data.get("category_original"))

            reporter_source = data.get("reporter_source") or ("ORIGINAL" if raw_reporter else "NONE")
            metadata_quality[f"reporter_source_{reporter_source.lower()}"] += 1

            if reporters:
                metadata_quality["reporter_available"] += 1
                if reporter_source == "NAVER":
                    reporter_fallback_samples.append({
                        "title": data.get("api_title"),
                        "domain": domain,
                        "publisher": publisher,
                        "reporters": reporters,
                        "reporters_original": raw_reporter,
                        "reporters_naver": data.get("reporters_naver") or "",
                        "original_url": data.get("original_url"),
                        "naver_url": data.get("naver_url"),
                    })
                if any(
                    reporter in {"시민", "무산", "비상", "사회", "정치", "경제", "뉴스"}
                    for reporter in reporters
                ):
                    suspicious_reporter_samples.append({
                        "title": data.get("api_title"),
                        "domain": domain,
                        "publisher": publisher,
                        "reporters": reporters,
                        "raw_reporter": raw_reporter,
                        "reporters_naver": data.get("reporters_naver") or "",
                        "reporter_source": reporter_source,
                        "original_url": data.get("original_url"),
                    })
            else:
                metadata_quality["reporter_missing"] += 1
                reporter_missing_samples.append({
                    "title": data.get("api_title"),
                    "domain": domain,
                    "publisher": publisher,
                    "raw_reporter": raw_reporter,
                    "reporters_naver": data.get("reporters_naver") or "",
                    "reporter_source": reporter_source,
                    "original_url": data.get("original_url"),
                    "naver_url": data.get("naver_url"),
                })

            if publisher:
                metadata_quality["publisher_available"] += 1
            else:
                metadata_quality["publisher_missing"] += 1
                publisher_missing_samples.append({
                    "title": data.get("api_title"),
                    "domain": domain,
                    "original_url": data.get("original_url"),
                })

            if category:
                metadata_quality["category_available"] += 1
            else:
                metadata_quality["category_missing"] += 1
                category_missing_samples.append({
                    "title": data.get("api_title"),
                    "domain": domain,
                    "publisher": publisher,
                    "reporters": reporters,
                    "original_url": data.get("original_url"),
                    "naver_url": data.get("naver_url"),
                })

            contexts = data.get("phrase_contexts") or []
            context_texts = [
                str(item.get("text") or "")
                for item in contexts
                if isinstance(item, dict)
            ]
            max_context = max(context_texts, key=len, default="")
            max_context_length = len(max_context)
            body_text = str(data.get("body_text_private") or "")
            body_length = len(body_text)
            context_body_ratio = (
                round(max_context_length / body_length, 4)
                if body_length else None
            )

            issues = []
            markers_found = [
                marker for marker in suspicious_context_markers
                if marker in max_context
            ]
            if markers_found:
                issues.append("SCRIPT_OR_JSON_MARKER")
                paragraph_quality["script_or_json_marker"] += 1
            if max_context_length >= 1200:
                issues.append("VERY_LONG_CONTEXT")
                paragraph_quality["very_long_context"] += 1
            if (
                context_body_ratio is not None
                and body_length >= 1000
                and context_body_ratio >= 0.75
            ):
                issues.append("CONTEXT_LOOKS_LIKE_WHOLE_BODY")
                paragraph_quality["context_looks_like_whole_body"] += 1

            context_similarity = data.get("phrase_context_similarity")
            if (
                isinstance(context_similarity, (int, float))
                and context_similarity < 0.75
            ):
                issues.append("LOW_ORIGINAL_NAVER_CONTEXT_SIMILARITY")
                paragraph_quality["low_original_naver_context_similarity"] += 1

            if data.get("final_source") == "ORIGINAL_LOW_QUALITY":
                issues.append("ORIGINAL_LOW_QUALITY_SOURCE")
                paragraph_quality["original_low_quality_source"] += 1

            if not context_texts:
                issues.append("NO_CONTEXT")
                paragraph_quality["no_context"] += 1

            if issues:
                paragraph_issue_samples.append({
                    "title": data.get("api_title"),
                    "domain": domain,
                    "publisher": publisher,
                    "final_source": data.get("final_source"),
                    "issues": issues,
                    "context_length": max_context_length,
                    "body_length": body_length,
                    "context_body_ratio": context_body_ratio,
                    "phrase_context_similarity": context_similarity,
                    "markers_found": markers_found,
                    "context_preview": max_context[:240],
                    "original_url": data.get("original_url"),
                    "naver_url": data.get("naver_url"),
                })

        if state == "rejected":
            reason = original_error or "UNKNOWN_REJECTION"
            rejection_reasons[reason] += 1
            if len(rejected_samples) < 25:
                rejected_samples.append({
                    "title": data.get("api_title"),
                    "domain": domain,
                    "original_url": data.get("original_url"),
                    "naver_url": data.get("naver_url"),
                    "category_original": clean_category(data.get("category_original")),
                    "original_parse_error": original_error,
                    "naver_parse_error": naver_error,
                })
        elif state == "accepted":
            if original_error:
                accepted_original_errors[original_error] += 1
            if len(accepted_samples) < 20:
                accepted_samples.append({
                    "title": data.get("api_title"),
                    "domain": domain,
                    "publisher": data.get("publisher_original"),
                    "reporters": split_reporters(
                        data.get("reporters_resolved") or data.get("reporters_original")
                    ),
                    "category_original": clean_category(data.get("category_original")),
                    "is_exclusive_strict": data.get("is_exclusive_strict"),
                    "phrase_count": data.get("phrase_count"),
                    "final_source": data.get("final_source"),
                    "body_similarity_original_vs_naver": data.get("body_similarity_original_vs_naver"),
                    "phrase_context_similarity": data.get("phrase_context_similarity"),
                    "original_url": data.get("original_url"),
                    "naver_url": data.get("naver_url"),
                })

    domain_rows = []
    for domain, stats in by_domain.items():
        row = {"domain": domain, **stats}
        row["success_rate"] = round(
            stats["accepted"] / stats["total"], 4
        ) if stats["total"] else None
        domain_rows.append(row)

    domain_rows.sort(key=lambda x: (-x["total"], x["domain"]))
    paragraph_issue_samples.sort(
        key=lambda x: (
            -len(x["issues"]),
            -(x["context_length"] or 0),
        )
    )

    return {
        "article_count_scanned": len(docs),
        "rejection_reasons": dict(rejection_reasons),
        "accepted_original_errors": dict(accepted_original_errors),
        "metadata_quality": dict(metadata_quality),
        "metadata_issues": {
            "reporter_missing": reporter_missing_samples,
            "category_missing": category_missing_samples,
            "publisher_missing": publisher_missing_samples,
            "suspicious_reporter": suspicious_reporter_samples,
            "reporter_fallback": reporter_fallback_samples,
        },
        "paragraph_quality": dict(paragraph_quality),
        "paragraph_issues": paragraph_issue_samples[:50],
        "domains": domain_rows,
        "accepted_samples": accepted_samples,
        "rejected_samples": rejected_samples,
    }


@app.get("/api/articles")
def articles(
    limit: int = Query(default=30, ge=1, le=100),
    accepted_only: bool = True,
):
    scan_limit = min(max(limit * 4, 100), 400)
    docs = (
        db.collection("articles")
        .order_by("api_pubdate", direction=firestore.Query.DESCENDING)
        .limit(scan_limit)
        .stream()
    )

    safe_fields = {
        "status",
        "final_source",
        "api_title",
        "api_description",
        "api_pubdate",
        "original_url",
        "naver_url",
        "publisher_original",
        "reporters_original",
        "reporters_naver",
        "reporters_resolved",
        "reporter_source",
        "published_at_original",
        "modified_at_original",
        "category_original",
        "is_exclusive_strict",
        "phrase",
        "phrase_count",
        "phrase_contexts",
        "secondary_expressions",
        "original_parse_error",
        "naver_parse_error",
        "body_similarity_original_vs_naver",
        "phrase_context_similarity",
        "wire_source_detected",
        "is_wire_reprint_suspected",
        "collector_version",
    }

    out = []
    for doc in docs:
        data = doc.to_dict() or {}
        if accepted_only and data.get("status") != "accepted":
            continue

        item = {"id": doc.id}
        for key in safe_fields:
            if key in data:
                item[key] = serialize_value(data[key])
        out.append(item)

        if len(out) >= limit:
            break

    return {
        "count": len(out),
        "articles": out,
    }
