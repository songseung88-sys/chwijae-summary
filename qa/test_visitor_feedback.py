"""Non-network safety and integration tests for visitor opinions."""
import ast
import copy
import re
import sys
import types
import unittest
import uuid
from pathlib import Path


SOURCE=Path("api/feedback_store.py").read_text()
TREE=ast.parse(SOURCE)
NAMES={"clean_feedback","sheet_row","save_feedback_to_sheet"}
NODES=[copy.deepcopy(n) for n in TREE.body if isinstance(n,ast.FunctionDef) and n.name in NAMES]


class DummyValues:
    def __init__(self,existing=None):
        self.existing=existing or []
        self.calls=[]
        self.method=None

    def get(self,**kwargs):
        self.method="get";self.calls.append(("get",kwargs));return self

    def append(self,**kwargs):
        self.method="append";self.calls.append(("append",kwargs));return self

    def execute(self):
        if self.method=="get":
            return {"values":[[v] for v in self.existing]}
        return {"updates":{"updatedRows":1}}


class FeedbackTests(unittest.TestCase):
    def ctx(self,existing=None):
        vals=DummyValues(existing)
        api=types.SimpleNamespace(values=lambda:vals)
        g=types.SimpleNamespace(auth=types.SimpleNamespace(
            default=lambda **kwargs:("credentials",None)))
        ns={
            "uuid":uuid, "MAX_MESSAGE":3000,
            "SHEET_ID":"test-sheet-id","SHEET_NAME":"의견 보내기",
            "google":g,"build":lambda *args,**kwargs:types.SimpleNamespace(spreadsheets=lambda:api)
        }
        exec(compile(ast.Module(body=NODES,type_ignores=[]),"<feedback>","exec"),ns)
        return ns,vals

    def test_validate_text_and_uuid(self):
        ns,_=self.ctx()
        ident=str(uuid.uuid4())
        self.assertEqual(ns["clean_feedback"]({"submission_id":ident,"message":"  제안 드립니다.  "}),
                         (ident,"제안 드립니다.",False))
        self.assertEqual(ns["clean_feedback"]({"submission_id":ident,"message":"하나 더",
                         "website":"spam.example"})[-1],True)
        for invalid in ("", " ", "a", "x"*3001, "\x00test"):
            with self.subTest(invalid=invalid[:15]),self.assertRaises(ValueError):
                ns["clean_feedback"]({"submission_id":ident,"message":invalid})
        with self.assertRaises(ValueError):
            ns["clean_feedback"]({"submission_id":"not-a-uuid","message":"정상적인 제안"})

    def test_sheet_append_is_raw_and_idempotent(self):
        ident=str(uuid.uuid4())
        ns,vals=self.ctx()
        msg="=IMPORTXML(\"http://bad.example\", \"//a\")"
        self.assertTrue(ns["save_feedback_to_sheet"](ident,"2026-10-21 05:00:00",msg))
        self.assertEqual(vals.calls[1][0],"append")
        kwargs=vals.calls[1][1]
        self.assertEqual(kwargs["valueInputOption"],"RAW")
        self.assertEqual(kwargs["body"]["values"][0],[
            ident,"2026-10-21 05:00:00",msg,"",""
        ])
        ns2,vals2=self.ctx(existing=[ident])
        self.assertFalse(ns2["save_feedback_to_sheet"](ident,"2026-10-21 05:00:00",msg))
        self.assertEqual(len(vals2.calls),1)

    def test_html_and_backend_reconciliation(self):
        html=Path("api/static/about.html").read_text()
        self.assertNotIn("‘취재를 종합하면’ 10년의 기록",html)
        self.assertNotIn("빅카인즈에서 조사한 10개 언론사의 연도별 기사 수입니다.",html)
        for token in ("feedbackDisclosure","feedbackForm","feedbackMessage",
                      "feedbackSubmit","feedbackStatus",">의견 보내기","전송하기","feedback.js"):
            self.assertIn(token,html)
        self.assertIn("<details",html)
        self.assertNotIn("<details open",html)
        self.assertLess(html.index('id="bigkindsPublisherSection"'),
                        html.index('id="feedbackDisclosure"'))
        main=Path("api/main.py").read_text()
        self.assertIn('@app.post("/api/feedback")',main)
        self.assertIn("save_feedback_to_sheet",main)
        archive=Path("archive/main.py").read_text()
        self.assertIn('"의견 보내기":209',archive)
        self.assertIn('if name == "의견 보내기":',archive)
        self.assertIn("include_pending_feedback",archive)
        self.assertIn("mark_feedback_delivered",archive)
        self.assertIn("timeBased().everyMinutes(5)",Path("infra/feedback-alerts.gs").read_text())


if __name__=="__main__":
    unittest.main()
