"""Read-only production-parser smoke test against verified official articles.

No Firestore writes, login, bypass, whole-body output or network crawler.
Only five fixed, publicly accessible publisher URLs are fetched.
"""
import json
from collector import main as c

CASES = [
    ("kbmaeil-previously-body-missing",
     "https://www.kbmaeil.com/article/20261117500786", 500, True),
    ("news2day-previously-related-news",
     "https://www.news2day.co.kr/article/20261118500006", 500, True),
    ("jjan-confirmed-article",
     "https://www.jjan.kr/article/20260128500447", 350, True),
    ("jjan-confirmed-amp",
     "https://www.jjan.kr/articleAmp/20260705500138", 350, True),
    ("jjan-readable-without-target",
     "https://www.jjan.kr/article/20260219500239", 350, False),
]
failures=[]
for label,url,min_chars,expected_phrase in CASES:
    result=c.parse_original(url)
    chars=len(result["body"])
    phrases=result["phrase_count"]
    expected_error="" if expected_phrase else "PHRASE_NOT_FOUND"
    good=(result["status_code"]==200 and chars>=min_chars
          and bool(phrases)==expected_phrase and result["error"]==expected_error
          and not c.suspicious_body(result["body"]))
    output={"case":label,"status":result["status_code"],"body_chars":chars,
            "paragraphs":len(result["paragraphs"]),"phrases":phrases,
            "error":result["error"],"expected_error":expected_error,
            "valid":good}
    print("THREE_PUBLISHER_VERIFY "+json.dumps(output,ensure_ascii=False),flush=True)
    if not good:failures.append(output)
if failures:
    raise SystemExit("THREE_PUBLISHER_VERIFY_FAIL "+str(len(failures)))
print("THREE_PUBLISHER_VERIFY_PASS fixed article bodies and true no-phrase exclusions",flush=True)
