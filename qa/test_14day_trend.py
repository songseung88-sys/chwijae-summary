"""14-day chart must use complete archived daily counts, never preview cap.

No Firestore credentials: all tests exercise exact production helper ASTs.
"""
import ast
import collections
import unittest
from datetime import date, timedelta
from pathlib import Path


def function(path, name, namespace):
    source = Path(path).read_text(encoding="utf-8")
    node = next(x for x in ast.parse(source).body
                if isinstance(x, ast.FunctionDef) and x.name == name)
    exec(compile(ast.Module(body=[node], type_ignores=[]), path, "exec"), namespace)
    return namespace[name]


class FakeSnap:
    def __init__(self, name, value=None, version="unique-accepted-v1"):
        self.id = name
        self.exists = value is not None
        self._data = {"count": value, "version": version}
    def to_dict(self):
        return self._data


class FakeDb:
    def __init__(self, counts=None):
        self.counts = counts or {}
        self.written = []
        self.commits = 0
    def collection(self, name):
        self.collection_name = name
        return self
    def document(self, name):
        assert self.collection_name == "daily_article_counts"
        return name
    def get_all(self, refs):
        for day in refs:
            yield self.counts.get(day, FakeSnap(day))
    def batch(self):
        self.written = []
        return self
    def set(self, ref, payload, merge=False):
        assert merge
        self.written.append((ref, payload))
    def commit(self):
        self.commits += 1


class DailyTrendRegression(unittest.TestCase):
    def test_publish_counts_all_14_days_not_a_capped_preview(self):
        fake = FakeDb()
        publish = function("archive/main.py", "publish_daily_article_counts",
                           {"collections": collections})
        days = {date(2026, 11, 6) + timedelta(days=i) for i in range(14)}
        corpus = [
            *({"_date": "2026-11-06"} for _ in range(101)),
            *({"_date": "2026-11-07"} for _ in range(28)),
            *({"_date": "2026-11-12"} for _ in range(190)),
            *({"_date": "2026-11-18"} for _ in range(232)),
        ]
        publish(fake, corpus, days, "2026-11-19T18:00:00+09:00")
        rows = dict(fake.written)
        self.assertEqual(fake.commits, 1)
        self.assertEqual(len(rows), 14)
        self.assertEqual(rows["2026-11-06"]["count"], 101)
        self.assertEqual(rows["2026-11-07"]["count"], 28)
        self.assertEqual(rows["2026-11-12"]["count"], 190)
        self.assertEqual(rows["2026-11-18"]["count"], 232)
        self.assertEqual(rows["2026-11-08"]["count"], 0)
        self.assertTrue(all(v["version"] == "unique-accepted-v1"
                            for v in rows.values()))

    def test_api_reads_verified_counts_and_preserves_missing_distinction(self):
        data = {
            "2026-11-06": FakeSnap("2026-11-06", 101),
            "2026-11-12": FakeSnap("2026-11-12", 190),
            "2026-11-13": FakeSnap("2026-11-13", 163),
            "2026-11-14": FakeSnap("2026-11-14", -1),
            "2026-11-15": FakeSnap("2026-11-15", 80, version="old"),
        }
        fake = FakeDb(data)
        read = function("api/main.py", "archived_daily_counts",
                        {"db": fake, "timedelta": timedelta})
        output = read(date(2026, 11, 6), date(2026, 11, 19))
        self.assertEqual(output, {
            "2026-11-06": 101,
            "2026-11-12": 190,
            "2026-11-13": 163,
        })
        self.assertNotIn("2026-11-07", output)
        self.assertNotIn("2026-11-14", output)
        self.assertNotIn("2026-11-15", output)


if __name__ == "__main__":
    unittest.main()
