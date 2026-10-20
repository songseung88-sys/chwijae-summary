"""Publisher aliases are display-only and require existing admin auth.

Runs without a GCP connection; exercises the exact production endpoint functions.
"""
import ast
import copy
import hmac
import re
import unittest
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse

source=Path("api/main.py").read_text(encoding="utf-8")
tree=ast.parse(source)
names={
    "domain_of", "normalize_publisher", "publisher_source_name",
    "get_publisher_aliases", "publisher_display",
    "require_admin", "list_publisher_names", "update_publisher_names",
}
nodes=[]
for node in tree.body:
    if isinstance(node,ast.FunctionDef) and node.name in names:
        node=copy.deepcopy(node)
        node.decorator_list=[]
        nodes.append(node)

class FakeHttpException(Exception):
    def __init__(self,status_code,detail):
        self.status_code=status_code
        self.detail=detail

class FakeSnapshot:
    def __init__(self, data):
        self.exists=data is not None
        self.data=data
    def to_dict(self):
        return self.data

class FakeRef:
    def __init__(self,store,key):
        self.store=store
        self.key=key
    def get(self):
        return FakeSnapshot(self.store.get(self.key))
    def set(self,payload,merge=False):
        if merge:
            self.store.setdefault(self.key,{}).update(payload)
        else:
            self.store[self.key]=payload

class FakeCollection:
    def __init__(self,store):
        self.store=store
    def document(self,key):
        return FakeRef(self.store,key)

class FakeDB:
    def __init__(self):
        self.store={}
    def collection(self,key):
        assert key=="site_config"
        return FakeCollection(self.store)

db=FakeDB()
articles=[
    {"publisher_original":"KBS 뉴스","original_url":"https://kbs.co.kr/1"},
    {"publisher_original":"KBS 뉴스","original_url":"https://kbs.co.kr/2"},
    {"publisher_original":"KBS","original_url":"https://kbs.co.kr/3"},
    {"publisher_original":"ETODAY","original_url":"https://etoday.co.kr/4"},
]
ns=dict(re=re,hmac=hmac,Counter=Counter,urlparse=urlparse,db=db,
        ADMIN_EDITOR_PASSWORD="secret",
        Header=lambda default=None:default,HTTPException=FakeHttpException,
        firestore=type("MockFirestore",(),{"SERVER_TIMESTAMP":"SERVER_TIME"})(),
        accepted_articles=lambda limit=1200:articles)
exec(compile(ast.Module(body=nodes,type_ignores=[]),"api/main.py","exec"),ns)

class PublisherDisplayAliases(unittest.TestCase):
    def setUp(self):
        db.store.clear()

    def test_editor_lists_actual_names_with_counts(self):
        result=ns["list_publisher_names"]("secret")
        rows={r["source"]:r for r in result["publishers"]}
        self.assertEqual(rows["KBS 뉴스"]["article_count"],2)
        self.assertEqual(rows["KBS 뉴스"]["display_name"],"KBS 뉴스")
        self.assertEqual(rows["ETODAY"]["default_name"],"이투데이")
        with self.assertRaises(FakeHttpException) as ctx:
            ns["list_publisher_names"]("wrong")
        self.assertEqual(ctx.exception.status_code,401)

    def test_alias_affects_rankings_but_not_raw_metadata(self):
        ns["update_publisher_names"]({
            "updates":[{"source":"KBS 뉴스","display_name":"KBS"}]
        },"secret")
        aliases=ns["get_publisher_aliases"]()
        self.assertEqual(aliases["KBS 뉴스"],"KBS")
        self.assertEqual(
            Counter(ns["publisher_display"](a,aliases) for a in articles)["KBS"],3
        )
        self.assertEqual(articles[0]["publisher_original"],"KBS 뉴스")
        self.assertEqual(ns["publisher_display"](articles[3],aliases),"이투데이")
        self.assertTrue(ns["list_publisher_names"]("secret")["publishers"][0]["is_custom"])

    def test_reset_and_reject_invalid_input(self):
        update=ns["update_publisher_names"]
        update({"updates":[{"source":"KBS 뉴스","display_name":"KBS"}]},"secret")
        update({"updates":[{"source":"KBS 뉴스","display_name":"KBS 뉴스"}]},"secret")
        self.assertNotIn("KBS 뉴스",ns["get_publisher_aliases"]())
        with self.assertRaises(FakeHttpException):
            update({"updates":[{"source":"KBS 뉴스","display_name":"허위"}]},"wrong")
        with self.assertRaises(FakeHttpException):
            update({"updates":[{"source":"KBS 뉴스","display_name":"a"*81}]},"secret")

if __name__=="__main__":
    unittest.main()
