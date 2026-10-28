"""Descriptive location of the FIRST core phrase in archived news bodies.

This module is deliberately independent of Firestore, the collector, and
paper-specific subjectless taxonomy. It only measures the literal phrase
'취재를 종합하면' in a normalized paragraph stream.
"""
from collections import Counter
from statistics import median
import re

CORE_PHRASE = "취재를 종합하면"
# A sentence break is counted only when followed by a space. Abbreviations
# and unusual punctuation may still complicate sentence segmentation.
SENTENCE_END = re.compile(r"""[.!?。][”’"'\)\]]*\s+""")


def first_core_phrase_location(body):
    """Return one location per body, never one observation per occurrence.

    Character offset is zero-based and includes spaces and ONE newline
    between normalized nonempty paragraphs. Paragraph order starts at 1.
    """
    if not isinstance(body, str) or not body.strip():
        return None
    paragraphs = [re.sub(r"[ \t\r\f\v]+", " ", line).strip()
                  for line in body.splitlines() if line.strip()]
    offset = 0
    for number, paragraph in enumerate(paragraphs, 1):
        index = paragraph.find(CORE_PHRASE)
        if index >= 0:
            prefix = paragraph[:index]
            sentence_number = len(list(SENTENCE_END.finditer(prefix))) + 1
            if not prefix.strip():
                structure = "문단 첫머리"
            elif sentence_number == 1:
                structure = "첫 문장 중간"
            else:
                structure = "후속 문장"
            before_start = max(0, index - 65)
            after_end = min(len(paragraph), index + len(CORE_PHRASE) + 105)
            excerpt = ("…" if before_start else "") + paragraph[before_start:after_end]
            if after_end < len(paragraph):
                excerpt += "…"
            return {
                "character_offset": offset + index,
                "paragraph": number,
                "sentence": sentence_number,
                "structure": structure,
                "excerpt": excerpt,
            }
        offset += len(paragraph) + 1
    return None


def summarize_core_phrase_positions(articles):
    """Summarize one observation per accepted article containing the phrase.

    An existing successfully archived body takes priority. When it does not
    contain the phrase, fall back to the collector's saved body without any
    network request or database write. The caller selects the date's articles.
    """
    records = []
    eligible = 0
    missing_body = 0
    source_counts = Counter()
    for article in articles:
        archive = article.get("archive_body_text") or ""
        collector = article.get("body_text_private") or ""
        has_phrase = CORE_PHRASE in archive or CORE_PHRASE in collector or bool(
            (article.get("phrase_counts") or {}).get(CORE_PHRASE))
        if not has_phrase:
            continue
        eligible += 1
        if article.get("archive_body_status") == "수집 성공" and CORE_PHRASE in archive:
            body = archive
            source = article.get("archive_body_source") or "보관 본문"
        elif CORE_PHRASE in collector:
            body = collector
            source = "수집 저장 본문"
        else:
            body = ""
            source = ""
        location = first_core_phrase_location(body)
        if location is None:
            missing_body += 1
            continue
        source_counts[source] += 1
        records.append((location, article))
    count = len(records)
    paragraphs = Counter(loc["paragraph"] for loc, _ in records)
    structures = Counter(loc["structure"] for loc, _ in records)
    buckets = [
        {"label": label, "count": sum(freq for number, freq in paragraphs.items()
                                    if (number == start if start < 5 else number >= 5))}
        for label, start in [("1문단", 1), ("2문단", 2),
                             ("3문단", 3), ("4문단", 4), ("5문단 이상", 5)]
    ]
    positions = [loc["character_offset"] for loc, _ in records]
    # Show a small, diverse set of checkable sentences, not full private bodies.
    samples = []
    for bucket_number in (2, 1, 3, 4, 5):
        candidates = [(loc, article) for loc, article in records
                      if min(loc["paragraph"], 5) == bucket_number]
        if not candidates:
            continue
        loc, article = sorted(candidates,
                              key=lambda pair: (pair[0]["character_offset"],
                                                str(pair[1].get("id") or "")))[0]
        samples.append({
            "paragraph": loc["paragraph"],
            "character_offset": loc["character_offset"],
            "structure": loc["structure"],
            "excerpt": loc["excerpt"],
            "publisher": article.get("publisher_original") or "",
            "url": article.get("original_url") or article.get("naver_url") or "",
        })
    return {
        "expression": CORE_PHRASE,
        "eligible_articles": eligible,
        "analyzed_articles": count,
        "unavailable_articles": missing_body,
        "mean_characters": round(sum(positions) / count, 1) if count else None,
        "median_characters": median(positions) if count else None,
        "within_500_articles": sum(pos <= 500 for pos in positions),
        "paragraph_distribution": buckets,
        "modal_paragraph": min(paragraphs, key=lambda n: (-paragraphs[n], n))
                           if paragraphs else None,
        "structure": [
            {"label": name, "count": structures[name]}
            for name in ("문단 첫머리", "첫 문장 중간", "후속 문장")
        ],
        "source_counts": dict(source_counts),
        "examples": samples,
        "methodology": "정규화된 본문 기준 공백 포함 글자 수·문단 사이 줄바꿈 1자; 첫 출현만 집계",
    }
