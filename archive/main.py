"""Incremental, idempotent Firestore -> Google Sheets archive.

Cloud Run runtime identity must be granted edit access to the spreadsheet.
No publisher is excluded. Full-body copies remain in a private spreadsheet
and Firestore; link to the publisher for publication, not republishing.
"""
import argparse
import collections
import json
import os
import re
import time
from datetime import datetime, timedelta, date
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

import google.auth
from googleapiclient.discovery import build
from google.cloud import firestore
import collector_parser as parser

KST=ZoneInfo("Asia/Seoul")
SHEET_ID=os.environ["ARCHIVE_SPREADSHEET_ID"]
PROJECT_ID=os.environ.get("GCP_PROJECT_ID") or None
ARCHIVE_VERSION="sheets-v1-20261020"
BODY_LIMIT=47500
MAX_BODY_PARTS=3
MAX_ARTICLE_FETCH=int(os.environ.get("MAX_ARCHIVE_BODY_FETCH","100"))
SHEET_HEADERS={
    "일별 통계":750549775,"언론사별":201,"기자별":202,
    "주제별":203,"무주체형 표현":204,"기사 목록":205,
    "동기화 기록":206,"30분 수집 로그":207,"언론사 수집 진단":208,
    "의견 보내기":209,
}
KEY_COL={
    "일별 통계":14,"언론사별":10,"기자별":6,"주제별":7,
    "무주체형 표현":8,"기사 목록":26,"동기화 기록":7,
    "30분 수집 로그":16,"언론사 수집 진단":12,"의견 보내기":0,
}
# Google Sheets stores strings with a per-cell 50K limit.
# Keep the logical body in column V, overflow in AB/AC without silent truncation.
def body_parts(text):
    text=str(text or "")
    if len(text)>BODY_LIMIT*MAX_BODY_PARTS:
        return None
    return [text[i*BODY_LIMIT:(i+1)*BODY_LIMIT] for i in range(MAX_BODY_PARTS)]

def norm_time(value):
    if isinstance(value,datetime):
        return value.astimezone(KST) if value.tzinfo else value.replace(tzinfo=KST)
    if not value: return None
    try:
        result=datetime.fromisoformat(str(value).replace("Z","+00:00"))
        return result.astimezone(KST) if result.tzinfo else result.replace(tzinfo=KST)
    except (TypeError,ValueError):return None

def safe(v):
    if v is None:return ""
    if isinstance(v,bool):return v
    if isinstance(v,(int,float)):return v
    if isinstance(v,(dict,list)):v=json.dumps(v,ensure_ascii=False,separators=(",",":"))
    v=str(v)
    # Values are passed as raw stringValue CellData, never USER_ENTERED formulas.
    return v[:49000]

def value(v):
    v=safe(v)
    if isinstance(v,bool):return {"userEnteredValue":{"boolValue":v}}
    if isinstance(v,(int,float)):return {"userEnteredValue":{"numberValue":v}}
    return {"userEnteredValue":{"stringValue":v}}

def basename(article):
    return re.sub(r"\s+"," ",str(article.get("publisher_original") or urlparse(article.get("original_url") or "").hostname or "미확인")).strip()

def display_name(article,aliases):
    name=basename(article)
    if name in aliases:return aliases[name]
    if name.lower() in ("etoday","e-today"):return "이투데이"
    if re.match(r"^중부일보\s*[-–—]\s*.+",name):return "중부일보"
    return name

def reporters(article):
    text=str(article.get("reporters_resolved") or article.get("reporters_original") or "")
    result=[]
    for part in re.split(r"[,/·|]",text):
        part=re.sub(r"\s*(기자|특파원|논설위원|에디터|PD)$","",part).strip()
        if re.fullmatch(r"[가-힣]{2,4}",part) and part not in result:result.append(part)
    return result

def phrase_counts(article):
    v=article.get("phrase_counts") or {}
    return int(v.get("취재를 종합하면") or 0),int(v.get("본지 취재 결과") or 0)

def body_quality(result):
    text=str(result.get("body") or "").strip()
    if len(text)<140:return False,"BODY_TOO_SHORT"
    if not parser.contains_target_phrase(text):return False,"TARGET_PHRASE_NOT_CONFIRMED"
    if parser.suspicious_body(text):return False,"SCRIPT_OR_STRUCTURED_DATA"
    if text.count("\n")<1 and len(text)>40000:return False,"LONG_UNSTRUCTURED_TEXT"
    if text.count("{")>40 and text.count('":')>20:return False,"SERIALIZED_METADATA"
    if len(text)>BODY_LIMIT*MAX_BODY_PARTS:return False,"SHEETS_LENGTH_LIMIT"
    return True,""

def archive_body(article,db):
    """Original HTML first, then Naver; failed rows are retained and retried daily."""
    cached_text=article.get("archive_body_text")
    cached_source=article.get("archive_body_source")
    if cached_text and article.get("archive_body_status")=="수집 성공" and cached_source in ("원문","네이버뉴스"):
        return cached_text,cached_source,"수집 성공","",article.get("archive_body_checked_at") or ""
    checks=[]
    for label,url,extract in [
        ("원문",article.get("original_url"),parser.parse_original),
        ("네이버뉴스",article.get("naver_url"),parser.parse_naver),
    ]:
        if not url:
            checks.append(label+":URL 없음")
            continue
        result=extract(url)
        good,reason=body_quality(result)
        if good:
            text=result["body"].strip()
            checked=datetime.now(KST).isoformat()
            db.collection("articles").document(article["id"]).set({
                "archive_body_text":text,
                "archive_body_source":label,
                "archive_body_status":"수집 성공",
                "archive_body_error":"",
                "archive_body_checked_at":checked,
                "archive_version":ARCHIVE_VERSION,
            },merge=True)
            return text,label,"수집 성공","",checked
        checks.append(label+":"+(result.get("error") or reason or "품질 검사 실패"))
    checked=datetime.now(KST).isoformat()
    reason="; ".join(checks)[:1000]
    db.collection("articles").document(article["id"]).set({
        "archive_body_source":"",
        "archive_body_status":"수집 실패",
        "archive_body_error":reason,
        "archive_body_checked_at":checked,
        "archive_version":ARCHIVE_VERSION,
    },merge=True)
    return "수집 실패","","수집 실패",reason,checked

def scan_articles(db,dates):
    start=min(dates)
    stream=db.collection("articles").order_by("api_pubdate",direction=firestore.Query.DESCENDING).stream()
    rows=[]
    for snap in stream:
        doc=snap.to_dict() or {}
        d=norm_time(doc.get("api_pubdate"))
        if d is not None and d.date()<start:break
        if not d or d.date() not in dates or doc.get("status")!="accepted":continue
        doc["id"]=snap.id
        doc["_date"]=str(d.date())
        rows.append(doc)
    return rows

def scan_runs(db,mode,dates):
    cap=120 if mode=="logs" else 2000
    start=min(dates)
    rows=[]
    stream=db.collection("collector_runs").order_by("started_at",direction=firestore.Query.DESCENDING).limit(cap).stream()
    for snap in stream:
        obj=snap.to_dict() or {}
        stamp=norm_time(obj.get("started_at"))
        if stamp and stamp.date()<start:break
        if stamp and stamp.date() in dates:
            obj["id"]=snap.id
            rows.append(obj)
    return rows

def collect_rows(articles,aliases,now,max_fetch):
    out={name:[] for name in SHEET_HEADERS}
    bydate=collections.defaultdict(list)
    for a in articles:bydate[a["_date"]].append(a)
    new_fetches=0
    for day,group in sorted(bydate.items()):
        publ=collections.defaultdict(list)
        pub_reporter=collections.Counter()
        topics=collections.Counter()
        secondary=collections.Counter()
        secondary_docs=collections.Counter()
        n_exclusive=0
        n_primary=0
        n_additional=0
        phrase1=0
        phrase2=0
        all_reporters=set()
        ai_done=0
        for a in group:
            src=basename(a);label=display_name(a,aliases)
            publ[(src,label)].append(a)
            names=reporters(a)
            all_reporters.update((label,r) for r in names)
            for reporter in names:pub_reporter[(src,label,reporter)]+=1
            c1,c2=phrase_counts(a)
            n_primary+=c1>0
            n_additional+=c2>0
            phrase1+=c1;phrase2+=c2
            exclusive=bool(a.get("is_exclusive_strict"))
            n_exclusive+=exclusive
            if a.get("taxonomy_version")=="0.3" and a.get("category_secondary"):
                ai_done+=1
                topics[(a.get("category_primary") or "기타",a.get("category_secondary") or "",a.get("category_tertiary") or "")]+=1
            if a.get("secondary_taxonomy_version")=="paper-table3-v2":
                for term,count in (a.get("secondary_expressions") or {}).items():
                    term="셈이다" if term=="한 셈이다" else term
                    n=int(count or 0)
                    if n>0:secondary[term]+=n;secondary_docs[term]+=1
            body=a.get("archive_body_text") if a.get("archive_body_status")=="수집 성공" else None
            if body:
                body=body.strip()
                source=a.get("archive_body_source") or ""
                status="수집 성공";error="";checked=a.get("archive_body_checked_at") or ""
            elif new_fetches<max_fetch:
                body,source,status,error,checked=archive_body(a,DB)
                new_fetches+=1
            else:
                body="수집 대기";source="";status="수집 대기";error="이번 실행 본문 확인 한도";checked=""
            chunks=body_parts(body)
            if chunks is None:
                chunks=["수집 실패","",""]
                source=""
                status="수집 실패";error="SHEETS_LENGTH_LIMIT"
            p1,p2,p3=chunks
            excerpt=(a.get("phrase_contexts") or [{}])[0]
            if not isinstance(excerpt,dict):excerpt={}
            original=a.get("title_resolved") or a.get("title_original") or a.get("api_title") or ""
            row=[
                a["id"],day,a.get("api_pubdate") or "",src,label,", ".join(names),
                original,c1,c2,c1+c2,exclusive,a.get("category_primary") or "",
                a.get("category_secondary") or "",a.get("category_tertiary") or "",
                a.get("taxonomy_version") or "",a.get("secondary_taxonomy_version") or "",
                a.get("content_basis") or a.get("final_source") or "",excerpt.get("text") or "",
                a.get("original_url") or "",a.get("naver_url") or "",now,
                p1,source,status,error,checked,a["id"],p2,p3,
            ]
            out["기사 목록"].append(row)
        out["일별 통계"].append([
            day,len(group),len(set(k[1] for k in publ)),len(all_reporters),
            n_exclusive,round(n_exclusive/len(group),5),n_primary,n_additional,
            phrase1,phrase2,ai_done,len(group)-ai_done,sum(secondary.values()),now,day,
        ])
        for (src,label),a_list in sorted(publ.items()):
            c=[phrase_counts(a) for a in a_list]
            out["언론사별"].append([
                day,src,label,len(a_list),sum(bool(a.get("is_exclusive_strict")) for a in a_list),
                sum(x>0 for x,_ in c),sum(y>0 for _,y in c),
                sum(x for x,_ in c),sum(y for _,y in c),now,day+"|"+src,
            ])
        for (src,label,reporter),n in sorted(pub_reporter.items()):
            out["기자별"].append([day,src,label,reporter,n,now,day+"|"+src+"|"+reporter])
        for (first,second,third),n in sorted(topics.items()):
            key="|".join((day,"0.3",first,second,third))
            out["주제별"].append([day,"0.3",first,second,third,n,now,key])
        rules={term:(major,sub) for major,sub,term,*_ in parser.SUBJECTLESS_RULES+parser.SUBJECTLESS_OTHER_RULES}
        for term,n in sorted(secondary.items()):
            major,sub=rules.get(term,("기타","기타"))
            key="|".join((day,"paper-table3-v2",term))
            out["무주체형 표현"].append([day,"paper-table3-v2",major,sub,term,n,secondary_docs[term],now,key])
    return out,new_fetches

def collect_run_rows(runs,now):
    out={"30분 수집 로그":[],"언론사 수집 진단":[]}
    for run in runs:
        rid=run["id"]
        errors=run.get("errors") or {}
        entries=run.get("rejected_examples") or []
        out["30분 수집 로그"].append([
            rid,run.get("target_date") or "",run.get("started_at") or "",
            run.get("finished_at") or "",run.get("candidates") or 0,run.get("accepted") or 0,
            run.get("new_accepted") or 0,run.get("existing_accepted") or 0,
            run.get("rejected") or 0,run.get("original_success") or 0,
            run.get("naver_fallback") or 0,run.get("naver_preferred_diff") or 0,
            errors,len(entries),"완료" if run.get("finished_at") else "미완료",
            now,rid,
        ])
        diagnostics=run.get("domain_diagnostics") or {}
        if not diagnostics:
            for example in entries:
                host=example.get("domain") or "미확인"
                row=diagnostics.setdefault(host,{"seen":0,"accepted":0,"rejected":0,"original_errors":0,"naver_errors":0,"errors":{},"examples":[]})
                row["rejected"]+=1
                row["seen"]+=1
                row["examples"].append(str(example.get("title") or "")[:70])
                for kind,key in [("original_error","original_errors"),("naver_error","naver_errors")]:
                    e=example.get(kind)
                    if e:
                        row[key]+=1
                        row["errors"][kind+":"+str(e)]=row["errors"].get(kind+":"+str(e),0)+1
            basis="과거 로그 예시(전체 실패 기사 아님)"
        else:
            basis="전체 후보 도메인 진단"
        for host,v in sorted(diagnostics.items()):
            key=rid+"|"+host
            out["언론사 수집 진단"].append([
                rid,run.get("started_at") or "",host,v.get("seen") or 0,
                v.get("accepted") or 0,v.get("rejected") or 0,
                v.get("original_errors") or 0,v.get("naver_errors") or 0,
                v.get("errors") or {}, "; ".join((v.get("examples") or [])[:3])[:1200],
                basis,now,key,
            ])
    return out

def include_pending_feedback(db, rows):
    """Retry submissions which the public API could not confirm in Sheets."""
    refs = []
    incoming = []
    for snap in db.collection("visitor_feedback").where("status", "==", "pending").limit(100).stream():
        record = snap.to_dict() or {}
        message = record.get("message")
        if not isinstance(message, str) or not message.strip() or len(message) > 3000:
            continue
        incoming.append([snap.id, record.get("submitted_at", ""), message, "", ""])
        refs.append(snap.reference)
    rows["의견 보내기"] = incoming
    return refs


def mark_feedback_delivered(refs):
    for ref in refs:
        ref.update({"status": "saved", "reconciled_at": datetime.now(KST).isoformat()})


class SheetWriter:
    def __init__(self,sheet_id):
        creds,_=google.auth.default(scopes=["https://www.googleapis.com/auth/spreadsheets"])
        self.api=build("sheets","v4",credentials=creds,cache_discovery=False).spreadsheets()
        self.id=sheet_id
        meta=self.api.get(spreadsheetId=self.id,fields="sheets(properties(sheetId,title,gridProperties(rowCount)))").execute()
        self.grids={s["properties"]["title"]:s["properties"]["gridProperties"]["rowCount"] for s in meta["sheets"]}

    def keys(self,names):
        letters=lambda i:"" if i<0 else self.col_name(i)
        ranges=["'"+name.replace("'","''")+"'!"+letters(KEY_COL[name])+"2:"+letters(KEY_COL[name])
                for name in names]
        values=self.api.values().batchGet(spreadsheetId=self.id,ranges=ranges,valueRenderOption="UNFORMATTED_VALUE").execute()
        existing={}
        for name,v in zip(names,values.get("valueRanges") or []):
            mapping={}
            for row_index,row in enumerate(v.get("values") or [],start=1):
                if row and str(row[0]).strip():mapping[str(row[0])]=row_index
            existing[name]=mapping
        return existing

    @staticmethod
    def col_name(index):
        s="";index+=1
        while index:
            index,rem=divmod(index-1,26)
            s=chr(65+rem)+s
        return s

    def write(self,out):
        names=[name for name,rows in out.items() if rows]
        if not names:return 0
        existing=self.keys(names)
        requests=[];n=0
        for name in names:
            rows=out[name];sid=SHEET_HEADERS[name];index=existing[name]
            maxrow=max(index.values(),default=0)+1  # sheet coordinates: data starts at rowIndex=1
            appended=[];updated=[]
            for row in rows:
                key=str(row[KEY_COL[name]])
                if key in index:
                    if name == "의견 보내기":
                        # Never overwrite mail alert timestamps or private notes.
                        continue
                    updated.append((index[key],row))
                else:
                    appended.append(row)
            required=maxrow+len(appended)
            capacity=self.grids.get(name,1000)
            if required>capacity:
                growth=max(required-capacity,1000)
                requests.append({"appendDimension":{"sheetId":sid,"dimension":"ROWS","length":growth}})
                self.grids[name]=capacity+growth
            for idx,row in updated:
                requests.append({"updateCells":{"start":{"sheetId":sid,"rowIndex":idx,"columnIndex":0},
                  "rows":[{"values":[value(v) for v in row]}],"fields":"userEnteredValue"}})
                n+=1
            if appended:
                requests.append({"appendCells":{"sheetId":sid,
                  "rows":[{"values":[value(v) for v in row]} for row in appended],
                  "fields":"userEnteredValue"}})
                n+=len(appended)
        # API limit 1000 req; split to keep response sizes stable.
        for start in range(0,len(requests),150):
            batch=requests[start:start+150]
            self.api.batchUpdate(spreadsheetId=self.id,body={"requests":batch}).execute()
        return n

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--mode",choices=["full","logs"],default="full")
    ap.add_argument("--days",type=int,default=7)
    args=ap.parse_args()
    now=datetime.now(KST)
    dates={now.date()-timedelta(days=i) for i in range(max(1,min(args.days,90)))}
    global DB
    DB=firestore.Client(project=PROJECT_ID)
    now_iso=now.isoformat()
    writer=SheetWriter(SHEET_ID)
    run_rows=collect_run_rows(scan_runs(DB,args.mode,dates),now_iso)
    pending_refs=include_pending_feedback(DB,run_rows)
    if args.mode=="logs":
        written=writer.write(run_rows)
        mark_feedback_delivered(pending_refs)
        print(json.dumps({"mode":"logs","rows_written":written,"runs":len(run_rows["30분 수집 로그"])}))
        return
    raw=scan_articles(DB,dates)
    aliases_doc=DB.collection("site_config").document("publisher_aliases").get()
    aliases=(aliases_doc.to_dict() or {}).get("aliases",{}) if aliases_doc.exists else {}
    out,count=collect_rows(raw,aliases,now_iso,MAX_ARTICLE_FETCH)
    out.update(run_rows)
    try:
        written=writer.write(out)
        mark_feedback_delivered(pending_refs)
        status="성공"
        detail="정상 완료"
    except Exception as exc:
        written=0;status="실패";detail=str(exc)[:350]
        raise
    finally:
        if status=="성공":
            writer.write({"동기화 기록":[[
                str(now.date()),now_iso,len(raw),written,status,detail,ARCHIVE_VERSION,
                now_iso,
            ]]})
    print(json.dumps({"mode":"full","articles":len(raw),"body_attempts":count,"rows_written":written,
        "runs":len(run_rows["30분 수집 로그"]),"status":status},ensure_ascii=False))

def record_run_status(mode,status,detail):
    """Operational status in private Firestore, independent of log-viewer IAM."""
    db=firestore.Client(project=PROJECT_ID)
    db.collection("archive_status").document(mode).set({
        "mode":mode,"status":status,
        "detail":str(detail)[:300],
        "updated_at":datetime.now(KST).isoformat(),
        "archive_version":ARCHIVE_VERSION,
    },merge=True)


if __name__=="__main__":
    import sys
    mode="logs" if (
        "--mode" in sys.argv
        and sys.argv.index("--mode")+1<len(sys.argv)
        and sys.argv[sys.argv.index("--mode")+1]=="logs"
    ) else "full"
    try:
        main()
        record_run_status(mode,"success","Completed")
    except Exception as exc:
        try:
            record_run_status(mode,"failure",type(exc).__name__+": "+str(exc))
        except Exception:
            pass
        raise
