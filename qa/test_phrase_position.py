"""Position analytics are per-article, first occurrence only, with transparent coverage."""
import importlib.util
import unittest
from pathlib import Path

PATH=Path("api/phrase_position.py")
spec=importlib.util.spec_from_file_location("phrase_position",PATH)
mod=importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

def article(ident,body,**kw):
    return {
        "id":ident,
        "body_text_private":body,
        "publisher_original":"검증언론",
        "original_url":"https://example.org/"+ident,
        **kw,
    }

class FirstPhrasePositionTest(unittest.TestCase):
    def test_first_paragraph_opening_and_repetitions(self):
        value=mod.first_core_phrase_location(
            "취재를 종합하면 첫 사례다. 취재를 종합하면 반복했다.\n둘째 문단")
        self.assertEqual(value["character_offset"],0)
        self.assertEqual(value["paragraph"],1)
        self.assertEqual(value["sentence"],1)
        self.assertEqual(value["structure"],"문단 첫머리")

    def test_second_paragraph_and_character_offset_including_space(self):
        first="첫 문단은 사건의 배경을 소개합니다."
        second="28일 뉴스룸 취재를 종합하면 사실이 확인된다."
        location=mod.first_core_phrase_location(first+"\n\n"+second)
        self.assertEqual(location["paragraph"],2)
        self.assertEqual(location["structure"],"첫 문장 중간")
        self.assertEqual(location["character_offset"],
                         len(first)+1+len("28일 뉴스룸 "))
        self.assertIn("28일 뉴스룸",location["excerpt"])

    def test_later_sentence_is_distinct_from_sentence_middle(self):
        loc=mod.first_core_phrase_location(
            "뉴스는 시작됐다. 이후에도 논란은 커졌다. 취재를 종합하면 후속 상황이다.")
        self.assertEqual(loc["paragraph"],1)
        self.assertEqual(loc["sentence"],3)
        self.assertEqual(loc["structure"],"후속 문장")

    def test_normalize_whitespace_and_skip_empty_lines(self):
        loc=mod.first_core_phrase_location(
            " 앞 문단.  \n  \n  취재를 종합하면  본문이다.\n")
        self.assertEqual(loc["paragraph"],2)
        self.assertEqual(loc["character_offset"],len("앞 문단.")+1)
        self.assertIsNone(mod.first_core_phrase_location(""))
        self.assertIsNone(mod.first_core_phrase_location("전망된다."))
        self.assertEqual(mod.first_core_phrase_location("취재를 종합하면")["character_offset"],0)

    def test_prefer_successful_archived_body_without_refetching_history(self):
        old=article("old","취재를 종합하면 수집 본문",
            archive_body_status="수집 성공",archive_body_source="네이버뉴스",
            archive_body_text="첫 문단\n취재를 종합하면 아카이브 본문")
        metrics=mod.summarize_core_phrase_positions([old])
        self.assertEqual(metrics["analyzed_articles"],1)
        self.assertEqual(metrics["source_counts"],{"네이버뉴스":1})
        self.assertEqual(metrics["modal_paragraph"],2)
        self.assertEqual(metrics["mean_characters"],len("첫 문단")+1)
        self.assertEqual(metrics["median_characters"],len("첫 문단")+1)

    def test_mixed_days_filtered_by_caller_and_eligible_missing_source(self):
        rows=[
            article("a","취재를 종합하면 A"),
            article("b","사건 시작.\n28일 취재를 종합하면 B"),
            article("c","배경. 첫 문장이 끝났다. 취재를 종합하면 C."),
            article("d","보통 기사. 취재를 종합하면 D."),
            article("e","",phrase_counts={"취재를 종합하면":1}),
            article("f","취재를 종합하면 반복. 취재를 종합하면 재반복."),
            article("g","없는 기사."),
        ]
        metrics=mod.summarize_core_phrase_positions(rows)
        self.assertEqual(metrics["eligible_articles"],6)
        self.assertEqual(metrics["analyzed_articles"],5)
        self.assertEqual(metrics["unavailable_articles"],1)
        self.assertEqual(sum(p["count"] for p in metrics["paragraph_distribution"]),5)
        self.assertEqual(sum(x["count"] for x in metrics["structure"]),5)
        self.assertEqual(metrics["paragraph_distribution"][0]["count"],4)
        self.assertEqual(metrics["paragraph_distribution"][1]["count"],1)
        self.assertEqual(metrics["modal_paragraph"],1)
        self.assertTrue(all("취재를 종합하면" in row["excerpt"]
                            for row in metrics["examples"]))
        self.assertGreaterEqual(metrics["within_500_articles"],4)
        self.assertEqual(metrics["source_counts"],{"수집 저장 본문":5})
        self.assertTrue(metrics["mean_characters"]>=0)

    def test_more_than_five_paragraph_bucket_and_exact_500_threshold(self):
        normal="가"*500+"취재를 종합하면"
        loc=mod.first_core_phrase_location(normal)
        self.assertEqual(loc["character_offset"],500)
        rows=[article("boundary",normal),
              article("late","첫\n둘\n셋\n넷\n다섯\n마지막 취재를 종합하면")]
        m=mod.summarize_core_phrase_positions(rows)
        self.assertEqual(m["within_500_articles"],2)
        self.assertEqual(m["paragraph_distribution"][-1]["count"],1)
        self.assertEqual(m["modal_paragraph"],1)

    def test_empty_denominator_is_not_reported_as_zero_characters(self):
        m=mod.summarize_core_phrase_positions([])
        self.assertIsNone(m["mean_characters"])
        self.assertIsNone(m["median_characters"])
        self.assertIsNone(m["modal_paragraph"])
        self.assertEqual(m["analyzed_articles"],0)
        self.assertEqual(m["eligible_articles"],0)

if __name__=="__main__":
    unittest.main()
