"""Regression for separate daily headline winners and week-to-date ranking lists.

Executes the production dashboard function with in-memory article records;
no network, credentials or Firestore writes.
"""
import ast
import copy
import json
import unittest
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = (ROOT / "api/main.py").read_text(encoding="utf-8")
TREE = ast.parse(MAIN)
KST = timezone(timedelta(hours=9))
DEFAULTS = ast.literal_eval(next(n.value for n in TREE.body
    if isinstance(n, ast.Assign)
    and any(isinstance(t, ast.Name) and t.id == "DEFAULT_SITE_CONFIG" for t in n.targets)))
UI_DEFAULTS = {x["key"]: x["default"]
    for x in json.loads((ROOT / "api/static/ui-copy-fields.json").read_text(encoding="utf-8"))}

def load_function(name, ns):
    node = copy.deepcopy(next(n for n in TREE.body
        if isinstance(n, ast.FunctionDef) and n.name == name))
    node.decorator_list = []
    exec(compile(ast.Module(body=[node], type_ignores=[]),
                 "api/main.py", "exec"), ns)
    return ns[name]

def article(ident, day, publisher, reporter):
    stamp = datetime.fromisoformat(day + "T12:00:00+09:00")
    return {
        "id": ident, "_dt": stamp,
        "api_pubdate": stamp.isoformat(),
        "publisher_original": publisher,
        "reporters_resolved": reporter,
        "title_resolved": "제목 " + ident,
    }

class FakeSnap:
    exists = True
    def to_dict(self):
        return {"ui_copy": {
            "card_reporter_label": "이번 주 가장 많이 '취재를 종합'한 기자",
            "section_publisher_title": "오늘 가장 많이 '취재를 종합'한 언론사",
            "card_publisher_label": "오늘 가장 많이 '취재를 종합'한 언론사",
        }}

class FakeDB:
    def collection(self, name):
        assert name == "site_config"
        return self
    def document(self, name):
        assert name == "public"
        return self
    def get(self):
        return FakeSnap()

class WeeklyDailyRankings(unittest.TestCase):
    def test_dashboard_uses_distinct_daily_winners_and_weekly_leaderboards(self):
        rows = [
            article("t1", "2026-10-28", "언론A", "오늘기자"),
            article("t2", "2026-10-28", "언론A", "오늘기자"),
            article("t3", "2026-10-28", "언론B", "다른기자"),
            article("w1", "2026-10-27", "언론B", "주간기자"),
            article("w2", "2026-10-27", "언론B", "주간기자"),
            article("w3", "2026-10-26", "언론B", "주간기자"),
            article("w4", "2026-10-26", "언론C", "기자C"),
            article("old", "2026-10-25", "언론D", "이전주기자"),
        ]
        ns = {
            "date": date, "datetime": datetime, "timedelta": timedelta,
            "Counter": Counter, "KST": KST,
            "Query": lambda default=None, **_kwargs: default,
            "accepted_articles": lambda limit: rows,
            "publisher_display": lambda a, aliases: aliases.get(a["publisher_original"], a["publisher_original"]),
            "get_publisher_aliases": lambda: {},
            "split_reporters": lambda value, **_kw: [value] if value else [],
            "get_site_config": lambda: {},
            "latest_successful_collection": lambda: None,
            "target_counts_for_article": lambda a: {"취재를 종합하면": 1},
            "TARGET_PHRASE_COMPILED": [("취재를 종합하면", None)],
            "TARGET_PHRASE_VERSION": "test-v1",
            "ADDITIONAL_PHRASE": "본지 취재 결과",
            "LEGACY_TARGET_PHRASES": ("취재를 종합하면", "본지 취재 결과"),
            "PAPER_SUBJECTLESS_LABELS": set(),
            "context_sentence": lambda s: s,
        }
        result = load_function("dashboard", ns)("2026-10-28")
        self.assertEqual(result["week_start"], "2026-10-26")
        self.assertEqual(result["today_count"], 3)
        self.assertEqual(result["top_publisher"], {"name": "언론A", "count": 2})
        self.assertEqual(result["top_reporter_today"], {
            "name": "오늘기자", "publisher": "언론A", "count": 2})
        self.assertEqual(result["top_reporter_week"], {
            "name": "주간기자", "publisher": "언론B", "count": 3})
        self.assertEqual(result["publisher_ranking_week"], [
            {"name": "언론B", "count": 4},
            {"name": "언론A", "count": 2},
            {"name": "언론C", "count": 1},
        ])
        self.assertEqual(result["publisher_ranking"], [
            {"name": "언론A", "count": 2}, {"name": "언론B", "count": 1}
        ])
        self.assertEqual(result["reporter_ranking_week"][0]["name"], "주간기자")
        self.assertNotIn("이전주기자", [r["name"] for r in result["reporter_ranking_week"]])
        self.assertEqual(len(result["articles"]), 3)

    def test_existing_admin_copy_changes_only_period_prefix(self):
        ns = {
            "db": FakeDB(),
            "DEFAULT_SITE_CONFIG": DEFAULTS,
            "DEFAULT_UI_COPY": UI_DEFAULTS,
            "LEGACY_UI_COPY_KEYS": set(DEFAULTS).intersection(UI_DEFAULTS),
            "validate_about_layout": lambda value: [],
            "default_about_layout": lambda value: [],
        }
        cfg = load_function("get_site_config", ns)()
        self.assertEqual(cfg["card_reporter_label"], "오늘 가장 많이 '취재를 종합'한 기자")
        self.assertEqual(cfg["section_publisher_title"], "이번 주 가장 많이 '취재를 종합'한 언론사")
        self.assertEqual(cfg["card_publisher_label"], "오늘 가장 많이 '취재를 종합'한 언론사")
        self.assertEqual(cfg["ui_copy"]["section_publisher_title"], cfg["section_publisher_title"])
        self.assertEqual(cfg["ui_copy"]["card_reporter_label"], cfg["card_reporter_label"])
        self.assertEqual(UI_DEFAULTS["card_reporter_asof"], "오늘 기준")
        self.assertNotIn("card_reporter_since", UI_DEFAULTS)

if __name__ == "__main__":
    unittest.main()
