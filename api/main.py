#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
from datetime import datetime, timezone
from typing import Optional

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from google.cloud import firestore

PROJECT_ID = os.getenv("GCP_PROJECT_ID", "").strip() or None
db = firestore.Client(project=PROJECT_ID)

app = FastAPI(
    title="취재를 종합하면 API",
    version="0.1.0",
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


@app.get("/")
def root():
    return {
        "service": "취재를 종합하면 API",
        "version": "0.1.0",
        "endpoints": ["/health", "/api/status", "/api/articles"],
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

    article_docs = (
        db.collection("articles")
        .order_by("api_pubdate", direction=firestore.Query.DESCENDING)
        .limit(300)
        .stream()
    )

    total_seen = 0
    accepted = 0
    rejected = 0
    source_counts = {}
    category_available = 0
    exclusive = 0
    wire_reprint = 0

    for doc in article_docs:
        total_seen += 1
        data = doc.to_dict() or {}
        state = data.get("status")
        if state == "accepted":
            accepted += 1
        elif state == "rejected":
            rejected += 1

        source = data.get("final_source") or "UNKNOWN"
        source_counts[source] = source_counts.get(source, 0) + 1

        if data.get("category_original"):
            category_available += 1
        if data.get("is_exclusive_strict"):
            exclusive += 1
        if data.get("is_wire_reprint_suspected"):
            wire_reprint += 1

    return {
        "latest_run": run_list[0] if run_list else None,
        "recent_runs": run_list,
        "recent_article_snapshot": {
            "sample_size": total_seen,
            "accepted": accepted,
            "rejected": rejected,
            "source_counts": source_counts,
            "category_original_available": category_available,
            "exclusive_strict": exclusive,
            "wire_reprint_suspected": wire_reprint,
        },
    }


@app.get("/api/articles")
def articles(
    limit: int = Query(default=30, ge=1, le=100),
    accepted_only: bool = True,
):
    # 단일-field index만 사용하기 위해 최근 기사부터 넉넉히 읽고 애플리케이션에서 필터링한다.
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
