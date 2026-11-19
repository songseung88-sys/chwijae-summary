"""Uncapped 7-day publisher and reporter rankings: offline archive/API contracts.

The archive source is already accepted and canonical-deduplicated. No changes
to article/alias data and no external Firestore or web calls in these tests.
"""
import ast
import collections
import json
import re
import unittest
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import urlparse


def load(path, name, env):
    source = Path(path).read_text(encoding="utf-8")
    node = next(n for n in ast.parse(source).body
                if isinstance(n, ast.FunctionDef) and n.name == name)
    exec(compile(ast.Module(body=[node], type_ignores=[]), path, "exec"), env)
    return env[name]


class Snap:
    def __init__(self, key, payload=None):
        self.id = key
        self.exists = payload is not None
        self.payload = payload
    def to_dict(self):
        return self.payload


class Db:
    def __init__(self):
        self.summaries = {}
        self.writes = []
        self.commits = 0
    def collection(self, name):
        assert name == "daily_ranking_summaries", name
        return self
    def document(self, key):
        return key
    def batch(self):
        self.writes = []
        return self
    def set(self, key, value, merge=False):
        assert merge is False
        self.writes.append((key, value))
    def commit(self):
        self.commits += 1
        self.summaries.update(dict(self.writes))
    def get_all(self, refs):
        return [Snap(key, self.summaries.get(key)) for key in refs]


def article(day, pub, byline):
    return {"_date": str(day), "publisher_original": pub,
            "reporters_resolved": byline}


class UncappedWeeklyRankings(unittest.TestCase):
    def setUp(self):
        self.db = Db()
        self.archive_env = {"collections": collections, "re": re,
                            "urlparse": urlparse, "json": json}
        load("archive/main.py", "ranking_source_name", self.archive_env)
        self.publish = load("archive/main.py",
                            "publish_daily_ranking_summaries", self.archive_env)
        self.api_env = {
            "db": self.db, "date": date, "timedelta": timedelta,
            "Counter": collections.Counter,
            "publisher_display": lambda a, aliases:
                aliases.get(a.get("publisher_original"), a.get("publisher_original")),
        }
        self.api_env["split_reporters"] = load(
            "api/main.py", "split_reporters", {"re": re})
        self.query_days = []
        self.live_articles = {}
        def day_query(day):
            self.query_days.append(str(day))
            return self.live_articles.get(str(day), [])
        self.api_env["accepted_ranking_articles_for_day"] = day_query
        self.weekly = load("api/main.py",
                           "complete_weekly_rankings", self.api_env)

    def test_more_than_1200_articles_and_first_day_retained(self):
        begin = date(2026, 11, 13)
        days = [begin + timedelta(days=i) for i in range(7)]
        rows = ([article(begin, "언론A", "홍길동 기자")] * 601
                + [article(days[1], "언론A", "홍길동 기자")] * 500
                + [article(days[5], "언론B", "김철수, 박영희 기자")] * 315)
        self.publish(self.db, rows, days, "2026-11-19T23:00:00+09:00")
        pubs, journalists = self.weekly(begin, days[-1], {}, live_day=None)
        self.assertEqual(sum(pubs.values()), 1416)
        self.assertEqual(pubs["언론A"], 1101)
        self.assertEqual(pubs["언론B"], 315)
        self.assertEqual(journalists[("홍길동", "언론A")], 1101)
        self.assertEqual(journalists[("김철수", "언론B")], 315)
        self.assertEqual(journalists[("박영희", "언론B")], 315)
        self.assertEqual(self.query_days, [])
        self.assertEqual(self.db.commits, 1)
        self.assertEqual(len(self.db.summaries), 7)
        self.assertEqual(self.db.summaries[str(begin)]["article_count"], 601)
        self.assertEqual(self.db.summaries[str(days[2])]["article_count"], 0)
        self.assertTrue(all(v["version"] == "raw-publisher-byline-v1"
                            for v in self.db.summaries.values()))

    def test_alias_changes_and_same_reporter_name_other_publisher(self):
        begin = date(2026, 11, 13)
        self.publish(self.db, [
            article(begin, "www.kgnews.co.kr", "홍길동"),
            article(begin, "경기신문", "홍길동"),
            article(begin, "다른언론", "홍길동"),
        ], [begin], "time")
        aliases = {"www.kgnews.co.kr": "경기신문"}
        pubs, journalists = self.weekly(begin, begin, aliases)
        self.assertEqual(pubs, {"경기신문": 2, "다른언론": 1})
        self.assertEqual(journalists[("홍길동", "경기신문")], 2)
        self.assertEqual(journalists[("홍길동", "다른언론")], 1)
        # Alias edits apply without republishing older summary documents.
        changed = {"www.kgnews.co.kr": "경기도신문"}
        pubs2, journalists2 = self.weekly(begin, begin, changed)
        self.assertEqual(pubs2["경기도신문"], 1)
        self.assertEqual(journalists2[("홍길동", "경기도신문")], 1)

    def test_today_is_live_and_missing_day_queries_are_not_capped(self):
        begin = date(2026, 11, 13)
        end = begin + timedelta(days=6)
        missing = begin + timedelta(days=3)
        self.publish(self.db, [
            article(begin, "과거언론", "김기자"),
            article(end, "낡은오늘", "김기자"),
        ], [begin, end], "old sync")
        self.live_articles[str(missing)] = [
            {"publisher_original": "누락보정", "reporters_resolved": "박유나"}
            for _ in range(70)
        ]
        self.live_articles[str(end)] = [
            {"publisher_original": "실시간언론", "reporters_resolved": "박유나"}
            for _ in range(42)
        ]
        pubs, journalists = self.weekly(begin, end, {}, live_day=end)
        self.assertEqual(pubs, {"과거언론": 1, "누락보정": 70, "실시간언론": 42})
        self.assertEqual(journalists[("박유나", "실시간언론")], 42)
        self.assertNotIn("낡은오늘", pubs)
        self.assertIn(str(end), self.query_days)
        self.assertIn(str(missing), self.query_days)
        self.assertNotIn(str(begin), self.query_days)

    def test_invalid_summary_triggers_exact_daily_query_not_partial_count(self):
        begin = date(2026, 11, 13)
        self.db.summaries[str(begin)] = {
            "version": "raw-publisher-byline-v1", "article_count": 50,
            "publisher_counts": [
                {"publisher_original": "언론A", "count": 12}
            ], "byline_counts": []}
        self.live_articles[str(begin)] = [
            {"publisher_original": "정상데이터", "reporters_resolved": "홍길동"}
            for _ in range(50)
        ]
        pubs, _ = self.weekly(begin, begin, {})
        self.assertEqual(pubs["정상데이터"], 50)
        self.assertNotIn("언론A", pubs)
        self.assertEqual(self.query_days, [str(begin)])


if __name__ == "__main__":
    unittest.main()
