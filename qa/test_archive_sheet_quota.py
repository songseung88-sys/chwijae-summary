"""Quota-regression tests for archive Sheets batch writes (no Google credentials)."""
import ast
import copy
import unittest
from pathlib import Path

SOURCE=Path("archive/main.py").read_text(encoding="utf-8")
TREE=ast.parse(SOURCE)
SHEET_WRITER=next(copy.deepcopy(n) for n in TREE.body
                  if isinstance(n,ast.ClassDef) and n.name=="SheetWriter")


class FakeHttpError(Exception):
    def __init__(self,status):
        super().__init__(f"HTTP {status}")
        self.resp=type("Response",(),{"status":status})()


class FakeClock:
    def __init__(self):self.now=100.0;self.sleep_calls=[]
    def monotonic(self):return self.now
    def sleep(self,seconds):
        self.sleep_calls.append(seconds)
        self.now+=seconds


class FakeSheetsAPI:
    def __init__(self,statuses):self.statuses=list(statuses);self.calls=0;self.sends=[]
    def batchUpdate(self,spreadsheetId,body):
        self.calls+=1
        self.sends.append((spreadsheetId,body))
        return self
    def execute(self):
        status=self.statuses.pop(0) if self.statuses else 200
        if status!=200:raise FakeHttpError(status)
        return {}


class SheetsQuotaTests(unittest.TestCase):
    def env(self,statuses):
        fake=FakeSheetsAPI(statuses)
        clock=FakeClock()
        scope={
            "HttpError":FakeHttpError,"time":clock,
            "random":type("Random",(),{"uniform":staticmethod(lambda a,b:0.0)})(),
            "SHEETS_MIN_WRITE_INTERVAL_SECONDS":2.2,
            "SHEETS_MAX_RATE_LIMIT_RETRIES":8,
            "SHEET_HEADERS":{"기사 목록":205},
            "KEY_COL":{"기사 목록":1},
            "value":lambda v:{"userEnteredValue":{"stringValue":str(v)}}
        }
        exec(compile(ast.Module(body=[SHEET_WRITER],type_ignores=[]),"archive/main.py","exec"),scope)
        writer=scope["SheetWriter"].__new__(scope["SheetWriter"])
        writer.api=fake;writer.id="private-test";writer._last_write_attempt=None
        return writer,fake,clock

    def test_retry_429_with_backoff_and_identical_atomic_payload(self):
        writer,api,clock=self.env([429,429,200])
        payload=[{"updateCells":{"rows":[]}}]
        writer.write_batch_with_retry(payload,1,1)
        self.assertEqual(api.calls,3)
        self.assertEqual(api.sends,[
            ("private-test",{"requests":payload})]*3)
        self.assertEqual(clock.sleep_calls,[5,10])
        self.assertEqual(clock.now,115.0)

    def test_pacing_between_successful_batches(self):
        writer,api,clock=self.env([200,200])
        writer.write_batch_with_retry([{"test":1}],1,2)
        writer.write_batch_with_retry([{"test":2}],2,2)
        self.assertEqual(api.calls,2)
        self.assertEqual(clock.sleep_calls,[2.2])

    def test_permission_or_invalid_request_fails_without_replay(self):
        for status in (400,401,403,404,500,503):
            with self.subTest(status=status):
                writer,api,clock=self.env([status])
                with self.assertRaises(FakeHttpError):
                    writer.write_batch_with_retry([{"appendCells":{"rows":[]}}],1,1)
                self.assertEqual(api.calls,1)
                self.assertFalse(clock.sleep_calls)

    def test_bounded_rate_limit_retry_exhaustion(self):
        writer,api,clock=self.env([429]*10)
        with self.assertRaises(FakeHttpError) as err:
            writer.write_batch_with_retry([{"appendCells":{"rows":[]}}],1,1)
        self.assertEqual(err.exception.resp.status,429)
        self.assertEqual(api.calls,9)  # initial call + maximum 8 retries
        self.assertEqual(clock.sleep_calls,[5,10,20,40,80,120,120,120])

    def test_writer_uses_retry_for_each_full_batch(self):
        writer,api,clock=self.env([200,200,200])
        writer.grids={"기사 목록":1000}
        writer.keys=lambda names:{"기사 목록":{str(i):i for i in range(1,302)}}
        data={"기사 목록":[["제목",str(i)] for i in range(1,302)]}
        count=writer.write(data)
        self.assertEqual(count,301)
        self.assertEqual(api.calls,3)
        self.assertGreaterEqual(sum(clock.sleep_calls),4.4)
        # Only updateCells, so no redundant appends on recovery.
        self.assertTrue(all("updateCells" in x for _,b in api.sends for x in b["requests"]))

if __name__=="__main__":unittest.main()
