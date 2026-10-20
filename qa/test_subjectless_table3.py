"""Fast, dependency-free regression tests for Table 3 subjectless expression patterns."""
import ast
import re
import unittest
from pathlib import Path

src = Path("collector/main.py").read_text(encoding="utf-8")
tree = ast.parse(src)

def get_assignment(name):
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == name for t in node.targets
        ):
            return ast.literal_eval(node.value)
    raise ValueError(name)

ns = {
    "re": re,
    "PHRASE": get_assignment("PHRASE"),
    "SUBJECTLESS_RULES": get_assignment("SUBJECTLESS_RULES"),
}
fn_nodes = [
    node for node in tree.body
    if isinstance(node, ast.FunctionDef)
    and node.name in {"secondary_counts", "subjectless_type_counts"}
]
exec(compile(ast.Module(body=fn_nodes, type_ignores=[]), "collector/main.py", "exec"), ns)
counts = ns["secondary_counts"]
group_counts = ns["subjectless_type_counts"]


class SubjectlessTable3(unittest.TestCase):
    def test_all_six_subtypes(self):
        body = ("중앙일보 취재를 종합하면 이러한 사실이 알려졌다. "
                "검증 결과가 전해졌다. 그가 퇴직했다고 한다. "
                "지적이 나온다. 우려가 제기된다. "
                "다른 의미로 풀이된다. 시간이 부족해 보인다. "
                "소극적인 태도로 해석된다. 검토가 거론된다. "
                "모두 동의한 셈이다. 주목할 대목이다. 이변이라는 관측이다.")
        data = counts(body)
        groups = group_counts(body, data)
        self.assertEqual(data.get("알려졌다"), 1)
        self.assertEqual(data.get("했다고 한다"), 1)
        self.assertEqual(data.get("지적이 나온다"), 1)
        self.assertEqual(data.get("풀이된다"), 1)
        self.assertEqual(data.get("셈이다"), 1)
        self.assertEqual(groups.get("출처소거형 / 피동형"), 2)
        self.assertEqual(groups.get("출처소거형 / 전언형"), 1)
        self.assertEqual(groups.get("출처소거형 / 자생발생형"), 2)
        self.assertEqual(groups.get("기자귀속형 / 해석형"), 4)
        self.assertEqual(groups.get("기자귀속형 / 명사형"), 3)
        self.assertEqual(groups.get("기자귀속형 / 종합형"), 1)
        self.assertNotIn("취재를 종합하면", data)

    def test_paper_variant_normalization(self):
        data = counts("지적도 나온다. 지적이 나왔다. 우려도 제기됐다. 해석이 나온다. 분석도 나왔다.")
        self.assertEqual(data.get("지적이 나온다"), 2)
        self.assertEqual(data.get("우려가 제기된다"), 1)
        self.assertEqual(data.get("해석이 나온다"), 1)
        self.assertEqual(data.get("분석이 나온다"), 1)

    def test_legacy_or_direct_quote_not_mixed(self):
        data = counts("법조계에 따르면 기자는 말했다. 당국은 이를 전했다. 취재를 종합하면 사실이다.")
        self.assertEqual(data, {})
        self.assertEqual(group_counts("취재를 종합하면").get("기자귀속형 / 종합형"), 1)

    def test_six_subtypes_present(self):
        kinds = {(major, subtype) for major, subtype, _label, _pat in ns["SUBJECTLESS_RULES"]}
        self.assertEqual(kinds, {
            ("출처소거형", "피동형"), ("출처소거형", "전언형"),
            ("출처소거형", "자생발생형"), ("기자귀속형", "해석형"),
            ("기자귀속형", "명사형"),
        })


if __name__ == "__main__":
    unittest.main()
