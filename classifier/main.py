#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import hashlib
import json
import os
import re
import sys
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import requests
from google.cloud import firestore

KST = ZoneInfo("Asia/Seoul")
TAXONOMY_VERSION = "0.3"
PROMPT_VERSION = "0.3.3"
MODEL = os.getenv("OPENAI_MODEL", "gpt-6-luna")
OPENAI_URL = "https://api.openai.com/v1/responses"

PRIMARY = [
    "정치",
    "사회",
    "경제·산업",
    "국제",
    "문화·생활",
    "과학·IT",
    "스포츠",
    "기타",
]

SECONDARY = {
    "정치": [
        "청와대·국무총리실",
        "국회·정당",
        "선거",
        "국감",
        "국감",
        "지방자치",
        "외교",
        "국방",
        "정치 기타",
    ],
    "사회": [
        "사건·사고",
        "법조",
        "경찰",
        "복지·인구",
        "보건·의료",
        "교육",
        "환경·동물",
        "재난·안전",
        "시민사회·갈등",
        "여성·아동",
        "노동",
        "사회 기타",
    ],
    "경제·산업": [
        "기업·산업",
        "금융·증권",
        "부동산·건설",
        "거시경제·재정·세제",
        "소비·유통",
        "에너지·자원",
        "교통·물류",
        "전기·전자",
        "중화학",
        "자동차",
        "IT",
        "게임 산업",
        "중소기업·벤처",
        "바이오·헬스",
        "농축산업",
        "해양수산업",
        "경제산업 기타",
    ],
    "국제": [
        "국제정치·외교",
        "전쟁·안보",
        "국제경제",
        "국제사회·사건",
        "국제 기타",
    ],
    "문화·생활": [
        "문화예술·출판",
        "방송·연예",
        "관광·여행",
        "종교",
        "음식·여가",
        "문화생활 기타",
    ],
    "과학·IT": [
        "AI·소프트웨어",
        "플랫폼·통신",
        "반도체·전자기술",
        "과학·연구",
        "우주",
        "기술정책",
        "과학IT 기타",
    ],
    "스포츠": [
        "축구",
        "야구",
        "농구",
        "배구",
        "골프",
        "스포츠산업",
        "E스포츠",
        "스포츠 기타",
    ],
    "기타": [
        "복합",
        "분류 곤란",
    ],
}

TERTIARY_POLITICS_PARTY = ["여당", "야당", "없음"]
TERTIARY_LEGAL = [
    "법원·재판",
    "검찰",
    "중수청",
    "공소청",
    "특검",
    "공수처",
    "법무부",
    "법률·제도",
    "교정·형사정책",
    "법조 기타",
]
ALL_SECONDARY = [x for values in SECONDARY.values() for x in values]
ALL_TERTIARY = ["없음", "여당", "야당"] + TERTIARY_LEGAL

SYSTEM_PROMPT = """
너는 한국 뉴스 기사 주제 분류기다.
반드시 기사의 중심 사건과 뉴스가치에 따라 1차, 2차, 3차 분류를 하나씩 선택한다.
언론사 CMS 분류는 참고자료일 뿐 정답으로 취급하지 않는다.

핵심 규칙:
1) 1차는 정치, 사회, 경제·산업, 국제, 문화·생활, 과학·IT, 스포츠, 기타 중 하나다.
2) 2차는 반드시 선택한 1차에 속한 항목이어야 한다.
3) 3차는 '정치 > 국회·정당'과 '사회 > 법조'에서만 사용한다. 그 외에는 '없음'.
4) 국정감사 질의·답변·증언·자료공개·현장 공방이 중심이면 정치 > 국감으로 분류한다. 국감 관련 금융·교육·의료 등 주제는 태그로 남긴다. 국감에서 제기된 사안의 후속 수사·재판은 법조로 분류한다.
5) 공공기관의 조직·인사·기관 운영 자체는 정치 > 정치 기타로 분류한다. 공공기관의 서비스 자체가 중심이면 해당 실질 분야로 분류한다.
6) 정치 > 국회·정당의 3차는 여당, 야당, 없음 중 하나다. 선거는 2차 '선거', 국정감사는 2차 '국감'으로 분류한다.
5) 국정감사 질의·답변·증인 출석·감사 결과·국감에서 새로 드러난 문제가 기사 발생의 핵심이면 정치 > 국감을 우선한다. 제목이나 리드에서 국감·국정감사를 전면에 내세우고 감사장에서의 질의·답변·지적이 핵심이면 실질 쟁점이 금융·AI·공공기관 운영이어도 국감으로 분류한다. 국감이 과거 배경이나 단순 언급일 뿐이면 기사의 실질 주제로 분류한다. 이 국감 규칙은 아래 공공기관 운영 규칙보다 우선한다.
6) 중앙정부 부처·중앙 공공기관의 순수한 조직개편·임면·근태·내부 경영관리 자체가 중심일 때만 정치 > 정치 기타로 분류한다. 법조기관의 수사·감찰, 국방기관의 군사·방위 업무, 금융기관의 금융업무, 복지·의료기관의 서비스처럼 실질 분야가 분명하면 해당 분야를 우선한다. 지방자치단체 자체의 조직개편·인사 또는 지방 산하 기관의 임면·내부 인사 문제가 중심이면 정치 > 지방자치로 분류한다. 지방정부가 주체라는 이유만으로 축제·금융·교통·복지 등 실질 분야 기사를 지방자치로 보내지 않는다.
7) 사회 > 법조의 3차는 법원·재판, 검찰, 중수청, 공소청, 특검, 공수처, 법무부, 법률·제도, 교정·형사정책, 법조 기타 중 하나다.
8) 기업이 연구개발, 기술, 제품, 공정, 경쟁력, 투자, 사업화의 주체라면 과학·IT보다 경제·산업을 우선한다.
   예: 기업의 반도체 공정 개발은 경제·산업 > 전기·전자.
   대학·공공연구기관·연구자 중심의 연구성과 자체는 과학·IT을 우선한다.
9) 기업 기사라도 중심 사건이 노동, 수사·재판, 경찰 활동이면 그 사건 성격을 우선한다.
10) 구체 업종에 해당하면 경제·산업 > 기업·산업보다 구체 업종을 우선한다.
11) 대한민국 정부의 외교 행위는 정치 > 외교, 해외 국가 간 외교 이슈는 국제 > 국제정치·외교를 우선한다.
12) 태그는 1~6개, 구체적인 기관·기업·인물·산업·사건명을 짧게 적는다.
13) confidence는 0~1 사이 숫자다. 경계가 명확하지 않으면 낮춰라.
14) reason_short는 한국어 한 문장으로, 왜 그 중심 분류를 골랐는지만 간단히 적는다.
""".strip()

def taxonomy_text():
    lines = []
    for primary in PRIMARY:
        lines.append(f"{primary}: " + " / ".join(SECONDARY[primary]))
    return "\n".join(lines)

SCHEMA = {
    "type": "object",
    "properties": {
        "primary": {"type": "string", "enum": PRIMARY},
        "secondary": {"type": "string", "enum": ALL_SECONDARY},
        "tertiary": {"type": "string", "enum": ALL_TERTIARY},
        "topic_tags": {
            "type": "array",
            "items": {"type": "string"},
            "minItems": 1,
            "maxItems": 6,
        },
        "confidence": {
            "type": "number",
            "minimum": 0,
            "maximum": 1,
        },
        "reason_short": {"type": "string"},
    },
    "required": [
        "primary",
        "secondary",
        "tertiary",
        "topic_tags",
        "confidence",
        "reason_short",
    ],
    "additionalProperties": False,
}

def apply_special_rules(result, article):
    title = (
        article.get("title_resolved")
        or article.get("title_original")
        or article.get("title_naver")
        or article.get("api_title")
        or ""
    )

    # 제목이 국감/국정감사를 직접 표방하는 경우만 규칙으로 확정한다.
    # 본문에서 국감을 단순 언급한 기사는 AI가 실제 중심 사건을 판단하도록 둔다.
    explicit_audit_title = bool(re.search(r"(?:국정감사|국감)", title))

    if explicit_audit_title:
        result["primary"] = "정치"
        result["secondary"] = "국감"
        result["tertiary"] = "없음"
        result["reason_short"] = "제목에서 국정감사를 직접 기사 프레임으로 제시하고 있어 국감으로 분류했다."

    return result


def validate_result(result):
    primary = result.get("primary")
    secondary = result.get("secondary")
    tertiary = result.get("tertiary")

    if primary not in SECONDARY:
        return False, "invalid_primary"
    if secondary not in SECONDARY[primary]:
        return False, f"secondary_not_in_primary:{primary}>{secondary}"

    if primary == "정치" and secondary == "국회·정당":
        if tertiary not in TERTIARY_POLITICS_PARTY:
            return False, "invalid_party_tertiary"
    elif primary == "사회" and secondary == "법조":
        if tertiary not in TERTIARY_LEGAL:
            return False, "invalid_legal_tertiary"
    else:
        if tertiary != "없음":
            return False, "tertiary_should_be_none"

    return True, ""

def extract_output_text(response_json):
    for item in response_json.get("output", []):
        if item.get("type") != "message":
            continue
        for part in item.get("content", []):
            if part.get("type") == "output_text":
                return part.get("text", "")
    return ""

def call_openai(api_key, article, correction=None):
    title = article.get("title_resolved") or article.get("title_original") or article.get("title_naver") or article.get("api_title") or ""
    publisher = article.get("publisher_original") or ""
    category_original = article.get("category_original") or ""
    body = article.get("body_text_private") or ""
    contexts = article.get("phrase_contexts") or []
    phrase_context = "\n".join(
        str(x.get("text") or "") for x in contexts if isinstance(x, dict)
    )

    body_for_classification = body[:10000]
    prompt = f"""
아래 기사를 분류하라.

[분류표]
{taxonomy_text()}

[기사]
제목: {title}
언론사: {publisher}
언론사 원문 분류: {category_original}
'취재를 종합하면' 포함 문맥:
{phrase_context}

본문:
{body_for_classification}
""".strip()

    if correction:
        prompt += f"\n\n이전 출력의 검증 오류: {correction}\n분류표의 계층 규칙을 지켜 다시 분류하라."

    payload = {
        "model": MODEL,
        "store": False,
        "input": [
            {
                "role": "system",
                "content": [{"type": "input_text", "text": SYSTEM_PROMPT}],
            },
            {
                "role": "user",
                "content": [{"type": "input_text", "text": prompt}],
            },
        ],
        "text": {
            "format": {
                "type": "json_schema",
                "name": "article_classification",
                "description": "한국 뉴스 기사의 계층형 주제 분류",
                "schema": SCHEMA,
                "strict": True,
            }
        },
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    last_error = None
    for attempt in range(4):
        try:
            r = requests.post(
                OPENAI_URL,
                headers=headers,
                json=payload,
                timeout=90,
            )
            if r.status_code in (429, 500, 502, 503, 504):
                last_error = f"HTTP_{r.status_code}:{r.text[:200]}"
                time.sleep(2 ** attempt)
                continue
            r.raise_for_status()
            data = r.json()
            text = extract_output_text(data)
            if not text:
                raise RuntimeError("empty_output_text")
            result = json.loads(text)
            return result, data.get("id", ""), data.get("usage") or {}
        except Exception as exc:
            last_error = f"{type(exc).__name__}:{str(exc)[:300]}"
            if attempt < 3:
                time.sleep(2 ** attempt)
                continue
            raise RuntimeError(last_error)

    raise RuntimeError(last_error or "unknown_openai_error")

def article_input_hash(article):
    payload = {
        "title": article.get("title_resolved") or article.get("api_title") or "",
        "body": article.get("body_text_private") or "",
        "category_original": article.get("category_original") or "",
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()

def main():
    project_id = os.getenv("GCP_PROJECT_ID", "").strip() or None
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    limit = int(os.getenv("CLASSIFY_LIMIT", "100"))
    force = os.getenv("CLASSIFY_FORCE", "false").lower() == "true"

    if not api_key:
        print("Missing OPENAI_API_KEY", file=sys.stderr)
        sys.exit(2)

    db = firestore.Client(project=project_id)
    now = datetime.now(KST)
    run_ref = db.collection("classifier_runs").document(
        now.strftime("%Y%m%dT%H%M%S%z")
    )

    docs = list(
        db.collection("articles")
        .order_by("api_pubdate", direction=firestore.Query.DESCENDING)
        .limit(300)
        .stream()
    )

    targets = []
    for doc in docs:
        data = doc.to_dict() or {}
        if data.get("status") != "accepted":
            continue
        if not force and data.get("taxonomy_version") == TAXONOMY_VERSION:
            continue
        targets.append((doc, data))
        if len(targets) >= limit:
            break

    summary = {
        "started_at": now.isoformat(),
        "taxonomy_version": TAXONOMY_VERSION,
        "prompt_version": PROMPT_VERSION,
        "model": MODEL,
        "target_count": len(targets),
        "classified": 0,
        "failed": 0,
        "retried_for_validation": 0,
        "low_confidence_below_0_7": 0,
        "primary_counts": {},
        "secondary_counts": {},
        "errors": {},
    }

    for idx, (doc, article) in enumerate(targets, start=1):
        try:
            result, response_id, usage = call_openai(api_key, article)
            result = apply_special_rules(result, article)
            ok, err = validate_result(result)
            if not ok:
                summary["retried_for_validation"] += 1
                result, response_id, usage = call_openai(api_key, article, correction=err)
                result = apply_special_rules(result, article)
                ok, err = validate_result(result)
                if not ok:
                    raise RuntimeError(f"validation_failed_after_retry:{err}")

            update = {
                "category_primary": result["primary"],
                "category_secondary": result["secondary"],
                "category_tertiary": (
                    None if result["tertiary"] == "없음" else result["tertiary"]
                ),
                "topic_tags": result["topic_tags"],
                "classification_confidence": result["confidence"],
                "classification_reason_short": result["reason_short"],
                "classification_method": "AI",
                "taxonomy_version": TAXONOMY_VERSION,
                "classifier_model": MODEL,
                "classifier_prompt_version": PROMPT_VERSION,
                "classifier_response_id": response_id,
                "classification_input_hash": article_input_hash(article),
                "classification_usage": usage,
                "classified_at": firestore.SERVER_TIMESTAMP,
            }
            doc.reference.set(update, merge=True)

            summary["classified"] += 1
            if float(result["confidence"]) < 0.7:
                summary["low_confidence_below_0_7"] += 1

            p = result["primary"]
            s = result["secondary"]
            summary["primary_counts"][p] = summary["primary_counts"].get(p, 0) + 1
            summary["secondary_counts"][s] = summary["secondary_counts"].get(s, 0) + 1

            print(
                f"[{idx}/{len(targets)}] {p} > {s}"
                f" > {result['tertiary']} | {result['confidence']:.2f}"
                f" | {(article.get('title_resolved') or article.get('api_title') or '')[:60]}"
            )

        except Exception as exc:
            summary["failed"] += 1
            key = f"{type(exc).__name__}:{str(exc)[:180]}"
            summary["errors"][key] = summary["errors"].get(key, 0) + 1
            print(
                f"[{idx}/{len(targets)}] ERROR {key}",
                file=sys.stderr,
            )

    summary["finished_at"] = datetime.now(KST).isoformat()
    run_ref.set(summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
