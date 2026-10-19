#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
from collections import Counter, defaultdict
from datetime import datetime, timezone
from urllib.parse import urlparse

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from google.cloud import firestore

PROJECT_ID = os.getenv("GCP_PROJECT_ID", "").strip() or None
db = firestore.Client(project=PROJECT_ID)

app = FastAPI(
    title="취재를 종합하면 API",
    version="0.1.1",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["*"],
)


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


def recent_article_docs(limit=300):
    return list(
        db.collection("articles")
        .order_by("api_pubdate", direction=firestore.Query.DESCENDING)
        .limit(limit)
        .stream()
    )


@app.get("/")
def root():
    return {
        "service": "취재를 종합하면 API",
        "version": "0.1.1",
        "endpoints": ["/health", "/api/status", "/api/diagnostics", "/api/articles"],
    }


@app.get("/health")
def health():
    return {"ok": True}


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

        if state == "rejected":
            reason = original_error or "UNKNOWN_REJECTION"
            rejection_reasons[reason] += 1
            if len(rejected_samples) < 25:
                rejected_samples.append({
                    "title": data.get("api_title"),
                    "domain": domain,
                    "original_url": data.get("original_url"),
                    "naver_url": data.get("naver_url"),
                    "category_original": data.get("category_original"),
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
                    "reporters": data.get("reporters_original"),
                    "category_original": data.get("category_original"),
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
