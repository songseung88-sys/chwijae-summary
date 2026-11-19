"""Regression for 2026-11-14 rejected-candidate crash and invisible failed runs.

Offline tests execute the actual collector function bodies with fake Firestore,
no live network / credentials / article body modification.
"""
import ast
import json
import os
import unittest
from datetime import datetime, timezone, timedelta
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import urlparse
from pathlib import Path

KST = timezone(timedelta(hours=9))


def function(path, name, context):
    source = Path(path).read_text(encoding="utf-8")
    node = next(x for x in ast.parse(source).body
                if isinstance(x, ast.FunctionDef) and x.name == name)
    exec(compile(ast.Module(body=[node], type_ignores=[]), path, "exec"), context)
    return context[name]


class Document:
    def __init__(self, initial=None):
        self.id = "doc1"
        self.data = dict(initial) if initial is not None else None
        self.writes = []
    @property
    def exists(self):
        return self.data is not None
    def get(self):
        return self
    def to_dict(self):
        return self.data
    def set(self, data, merge=False):
        self.writes.append(dict(data))
        self.data = {**(self.data or {}), **data} if merge else dict(data)


class FakeDB:
    def __init__(self, existing=None):
        self.docs = {"doc1": Document(existing)}
        self.run_ref = Document()
    def collection(self, name):
        self.current_collection = name
        return self
    def document(self, name):
        if self.current_collection == "collector_runs":
            return self.run_ref
        assert self.current_collection == "articles"
        return self.docs.setdefault(name, Document())


class CollectorRunLoggingTests(unittest.TestCase):
    def env(self, existing=None, successful=False):
        db = FakeDB(existing)
        item = {
            "original_url": "https://example.net/news/article?id=4",
            "naver_url": "",
            "api_title": "대상 기사",
            "api_description": "본문 요약",
            "api_pubdate": "2026-11-19T07:07:00+09:00",
        }
        original = {
            "ok": successful, "body": ("취재를 종합하면 테스트 본문" if successful else ""),
            "phrase_count": (1 if successful else 0),
            "phrase_contexts": [],
            "secondary": {},
            "title": "", "reporters": "",
            "publisher": "테스트신문", "error": ("" if successful else "PHRASE_NOT_FOUND"),
        }
        context = {
            "datetime": datetime, "KST": KST, "urlparse": urlparse, "json": json,
            "firestore": SimpleNamespace(SERVER_TIMESTAMP="SERVER_TIME"),
            "backfill_subjectless_once": lambda db: None,
            "backfill_subjectless_candidates_batch": lambda db: None,
            "repair_etoday_reporters_once": lambda db: None,
            "collect_target_candidates": lambda *args: ([item], ["검색어"]),
            "doc_id": lambda url: "doc1",
            "parse_original": lambda url: original,
            "parse_naver": lambda url: {"phrase_count": 0},
            "suspicious_body": lambda x: False,
            "suspicious_context": lambda x: False,
            "similarity": lambda a, b: 1.0,
            "detect_wire_reprint": lambda *a: ("", False),
            "strict_exclusive": lambda x: False,
            "subjectless_candidate_fields": lambda x: {},
            "subjectless_type_counts": lambda *a: {},
            "target_phrase_counts": lambda x: {"취재를 종합하면": 1} if successful else {},
            "secondary_counts": lambda x: {},
            "classify_candidate_outcome": function("collector/main.py",
                                                  "classify_candidate_outcome", {}),
            "COLLECTOR_VERSION": "test-v1",
            "TARGET_PHRASE_VERSION": "target-v1",
            "SECONDARY_TAXONOMY_VERSION": "table3-v2",
            "PHRASE": "취재를 종합하면",
        }
        return db, function("collector/main.py", "collect_job", context)

    def test_new_rejected_article_is_logged_without_unboundlocalerror(self):
        db, collect = self.env()
        collect(db, db.run_ref, datetime(2026,11,19,7,7,tzinfo=KST),
                "id", "secret", False, 160)
        run = db.run_ref.data
        self.assertEqual(run["state"], "completed")
        self.assertEqual(run["rejected"], 1)
        self.assertEqual(run["first_excluded"], 1)
        self.assertEqual(run["rejected_examples"][0]["outcome"], "first_excluded")
        self.assertEqual(db.docs["doc1"].data["status"], "rejected")
        self.assertTrue(run.get("finished_at"))

    def test_repeated_rejected_article_is_classified_without_crash(self):
        db, collect = self.env({"status": "rejected", "first_seen_at": "earlier"})
        collect(db, db.run_ref, datetime(2026,11,19,7,37,tzinfo=KST),
                "id", "secret", False, 160)
        run = db.run_ref.data
        self.assertEqual(run["repeat_excluded"], 1)
        self.assertEqual(run["rejected_examples"][0]["outcome"], "repeat_excluded")
        self.assertEqual(db.docs["doc1"].data["first_seen_at"], "earlier")

    def test_previous_rejection_can_recover(self):
        db, collect = self.env({"status": "rejected"}, successful=True)
        collect(db, db.run_ref, datetime(2026,11,19,8,7,tzinfo=KST),
                "id", "secret", False, 160)
        self.assertEqual(db.run_ref.data["recovered"], 1)
        self.assertEqual(db.run_ref.data["new_accepted"], 1)
        self.assertEqual(db.docs["doc1"].data["status"], "accepted")

    def test_failed_run_is_persisted_before_exception_and_rethrown(self):
        db = FakeDB()
        class FailJob:
            def __call__(self, *args):
                self.initial = db.run_ref.data.copy()
                raise RuntimeError("synthetic failure")
        job = FailJob()
        context = {
            "os": os, "sys": __import__("sys"),
            "datetime": datetime, "KST": KST,
            "firestore": SimpleNamespace(Client=lambda project=None: db),
            "TARGET_PHRASE_VERSION": "target-v1",
            "collect_job": job,
        }
        main = function("collector/main.py", "main", context)
        with patch.dict(os.environ, {
            "NAVER_API_HUB_CLIENT_ID": "mock-only",
            "NAVER_API_HUB_CLIENT_SECRET": "mock-only",
            "GCP_PROJECT_ID": "fake",
        }):
            with self.assertRaisesRegex(RuntimeError, "synthetic failure"):
                main()
        self.assertEqual(job.initial["state"], "running")
        self.assertIn("started_at", job.initial)
        self.assertEqual(db.run_ref.data["state"], "failed")
        self.assertEqual(db.run_ref.data["failure_type"], "RuntimeError")
        self.assertNotIn("finished_at", db.run_ref.data)
        self.assertEqual(db.run_ref.data["errors"], {"COLLECTOR_FATAL_RuntimeError": 1})

    def test_failed_collector_has_distinct_sheet_status(self):
        collect_rows=function("archive/main.py","collect_run_rows",{})
        run={"id":"20261114T103702+0900","state":"failed",
             "started_at":"2026-11-14T10:37:02+09:00",
             "target_date":"2026-11-14","failed_at":"2026-11-14T10:37:16+09:00",
             "errors":{"COLLECTOR_FATAL_UnboundLocalError":1}}
        result=collect_rows([run],"sync")
        row=result["30분 수집 로그"][0]
        self.assertEqual(row[0],run["id"])
        self.assertEqual(row[14],"실패")
        self.assertEqual(row[12],run["errors"])
        self.assertEqual(row[16],run["id"])
        complete=collect_rows([{**run,"finished_at":"now","state":"completed"}],"sync")
        self.assertEqual(complete["30분 수집 로그"][0][14],"완료")


if __name__ == "__main__":
    unittest.main()
