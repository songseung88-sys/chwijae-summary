"""Validated BigKinds history and reorderable About page blocks.

All published annual totals derive from the ten publisher series.
"""
import json
from pathlib import Path

SOURCE_PATH = Path(__file__).resolve().parent / "static" / "bigkinds-annual-2016-2025.json"
SOURCE = json.loads(SOURCE_PATH.read_text(encoding="utf-8"))
YEARS = list(range(2016, 2026))
PUBLISHERS = tuple(SOURCE["publishers"].keys())
CHART_KEYS = ("annual", "publisher")


def validate_history(payload):
    if not isinstance(payload, dict):
        raise ValueError("빅카인즈 데이터가 올바르지 않습니다.")
    if payload.get("years") != YEARS:
        raise ValueError("연도는 2016~2025년으로 고정됩니다.")
    publishers = payload.get("publishers")
    if not isinstance(publishers, dict) or set(publishers) != set(PUBLISHERS):
        raise ValueError("기존 10개 언론사 모두의 수치를 입력해주세요.")
    cleaned = {}
    for name in PUBLISHERS:
        numbers = publishers[name]
        if not isinstance(numbers, list) or len(numbers) != len(YEARS):
            raise ValueError(name + "의 연도별 수치가 누락되었습니다.")
        if any(type(n) is not int or n < 0 or n > 1000000 for n in numbers):
            raise ValueError(name + "의 기사 수는 0 이상 100만 이하의 정수여야 합니다.")
        cleaned[name] = list(numbers)
    totals = [sum(cleaned[name][i] for name in PUBLISHERS) for i in range(len(YEARS))]
    if "totals" in payload and payload["totals"] != totals:
        raise ValueError("연간 합계는 언론사별 수치의 합과 같아야 합니다.")
    return {
        "source": SOURCE["source"],
        "query": SOURCE["query"],
        "source_note": SOURCE["source_note"],
        "years": YEARS.copy(),
        "totals": totals,
        "publishers": cleaned,
    }


def default_about_layout(intro=""):
    result = []
    if intro:
        result.append({"type": "text", "text": intro[:30000]})
    result.extend([{"type": "chart", "chart": key} for key in CHART_KEYS])
    return result


def validate_about_layout(value):
    if not isinstance(value, list) or not 2 <= len(value) <= 22:
        raise ValueError("소개글은 최대 20개까지 추가할 수 있습니다.")
    output = []
    seen = []
    total_chars = 0
    for block in value:
        if not isinstance(block, dict):
            raise ValueError("잘못된 페이지 배치 항목입니다.")
        if block.get("type") == "chart":
            key = block.get("chart")
            if key not in CHART_KEYS or key in seen:
                raise ValueError("두 개의 그래프는 각각 한 번씩 배치해야 합니다.")
            seen.append(key)
            output.append({"type": "chart", "chart": key})
        elif block.get("type") == "text":
            contents = block.get("text")
            if not isinstance(contents, str) or len(contents) > 30000:
                raise ValueError("소개글은 블록당 3만 자 이하여야 합니다.")
            total_chars += len(contents)
            output.append({"type": "text", "text": contents})
        else:
            raise ValueError("알 수 없는 페이지 배치 항목입니다.")
    if set(seen) != set(CHART_KEYS):
        raise ValueError("연간·언론사별 그래프를 모두 포함해야 합니다.")
    if total_chars > 60000:
        raise ValueError("전체 소개글은 6만 자 이하여야 합니다.")
    return output
