#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import ast
import os
import re
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from google.cloud import firestore

PROJECT_ID = os.getenv("GCP_PROJECT_ID", "").strip() or None
KST = ZoneInfo("Asia/Seoul")
PHRASE = "취재를 종합하면"
db = firestore.Client(project=PROJECT_ID)

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


def split_reporters(value):
    value = str(value or "").strip()
    if not value:
        return []
    if value.startswith("http://") or value.startswith("https://"):
        return []
    out = []
    for part in re.split(r"[,/·|]", value):
        part = re.sub(r"\s*(기자|특파원|논설위원|에디터|PD)$", "", part).strip()
        if re.fullmatch(r"[가-힣]{2,4}", part) or re.fullmatch(r"[가-힣A-Za-z0-9]{2,10}팀", part):
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
        for reporter in split_reporters(article.get("reporters_original")):
            reporter_counts[reporter] += 1

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
            "reporters": split_reporters(a.get("reporters_original")),
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
            {"name": top_reporter[0][0], "count": top_reporter[0][1]}
            if top_reporter else None
        ),
        "publisher_ranking": [
            {"name": name, "count": count}
            for name, count in publisher_counts.most_common(10)
        ],
        "reporter_ranking_week": [
            {"name": name, "count": count}
            for name, count in reporter_counts.most_common(10)
        ],
        "category_ranking_original": [
            {"name": name, "count": count}
            for name, count in category_counts.most_common(10)
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
    accepted_samples = []
    rejected_samples = []

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
            reporters = split_reporters(data.get("reporters_original"))
            if reporters:
                metadata_quality["reporter_available"] += 1
            else:
                metadata_quality["reporter_missing"] += 1
            if data.get("publisher_original"):
                metadata_quality["publisher_available"] += 1
            if data.get("category_original"):
                metadata_quality["category_available"] += 1

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
                    "reporters": split_reporters(data.get("reporters_original")),
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

    return {
        "article_count_scanned": len(docs),
        "rejection_reasons": dict(rejection_reasons),
        "accepted_original_errors": dict(accepted_original_errors),
        "metadata_quality": dict(metadata_quality),
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
