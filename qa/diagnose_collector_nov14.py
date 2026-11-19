"""Read-only November 14 2026 (KST) collector audit.

Queries existing Cloud Scheduler logs, Cloud Run job execution metadata and
error logs with the repository's existing read-only GitHub deployment identity.
No Cloud Scheduler / Firestore / IAM modification.
"""
import datetime as dt
import json
import subprocess
from collections import Counter, defaultdict
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Asia/Seoul")
DAY = dt.date(2026, 11, 14)
START = "2026-11-13T15:00:00Z"
END = "2026-11-14T15:00:00Z"
PROJECT = "chwijae-summary"
REGION = "asia-northeast3"
SCHEDULE = "chwijae-collector-half-hourly"


def run(label, argv):
    try:
        p = subprocess.run(argv, capture_output=True, text=True, timeout=100)
    except Exception as exc:
        print("SOURCE_UNAVAILABLE", label, type(exc).__name__, str(exc)[:180], flush=True)
        return None
    if p.returncode:
        print("SOURCE_UNAVAILABLE", label, "code", p.returncode,
              (p.stderr or p.stdout)[-450:].strip(), flush=True)
        return None
    try:
        return json.loads(p.stdout)
    except ValueError:
        print("SOURCE_BAD_JSON", label, p.stdout[:180], flush=True)
        return None


def local_stamp(value):
    if not value:
        return None
    try:
        value = value.replace("Z", "+00:00")
        return dt.datetime.fromisoformat(value).astimezone(TZ)
    except (ValueError, AttributeError):
        return None


def slot(stamp):
    parsed = local_stamp(stamp)
    if parsed is None or parsed.date() != DAY:
        return None
    minute = 7 if parsed.minute < 22 else 37 if parsed.minute < 52 else 7
    hour = parsed.hour if parsed.minute < 52 else (parsed.hour + 1) % 24
    # Round to the nearest scheduled :07 / :37 slot. Discard >10-minute drift.
    nominal = dt.datetime.combine(DAY, dt.time(hour=hour, minute=minute), TZ)
    if abs((parsed - nominal).total_seconds()) > 10*60:
        return None
    return nominal.strftime("%H:%M")


def main():
    base = ["--project", PROJECT]
    sched = run("scheduler-description", [
        "gcloud", "scheduler", "jobs", "describe", SCHEDULE,
        "--location", REGION, "--project", PROJECT, "--format=json"])
    if isinstance(sched, dict):
        print("SCHEDULE_CONFIG", json.dumps({
            k:sched.get(k) for k in ("name","schedule","timeZone","state",
                 "attemptDeadline","lastAttemptTime","scheduleTime")
        }, ensure_ascii=False), flush=True)

    executions = run("cloud-run-executions", [
        "gcloud", "run", "jobs", "executions", "list",
        "--job=chwijae-collector", "--region="+REGION,
        "--project="+PROJECT, "--limit=1000", "--format=json"])
    ex_by_slot = defaultdict(list)
    ex_unassigned = []
    if isinstance(executions, list):
        for x in executions:
            started = x.get("startTime") or x.get("createTime") or x.get("metadata",{}).get("creationTimestamp")
            parsed = local_stamp(started)
            if not parsed or parsed.date()!=DAY:
                continue
            key = slot(started)
            conditions = x.get("status",{}).get("conditions",[])
            completed = next((c.get("status") for c in conditions if c.get("type")=="Completed"),None)
            record = {
                "started":parsed.strftime("%H:%M:%S"),
                "name":str(x.get("name") or x.get("metadata",{}).get("name") or "").rsplit("/",1)[-1],
                "completion":x.get("completionTime") or x.get("status",{}).get("completionTime"),
                "succeeded": x.get("succeededCount") or x.get("status",{}).get("succeededCount"),
                "failed":x.get("failedCount") or x.get("status",{}).get("failedCount"),
                "completed_condition":completed,
            }
            if key: ex_by_slot[key].append(record)
            else: ex_unassigned.append(record)
        print("RUN_EXECUTIONS_TOTAL", sum(map(len,ex_by_slot.values()))+len(ex_unassigned),
              "unassigned",len(ex_unassigned), "day_slots", len(ex_by_slot), flush=True)
    else:
        print("RUN_EXECUTIONS_UNAVAILABLE",flush=True)

    query = (
        'resource.type="cloud_scheduler_job" '
        f'AND timestamp>="{START}" AND timestamp<"{END}"'
    )
    sched_logs = run("scheduler-logs",[
        "gcloud","logging","read",query,"--project="+PROJECT,
        "--limit=2000","--format=json"])
    scheduler_by_slot = defaultdict(list)
    other_sched=0
    if isinstance(sched_logs,list):
        for item in sched_logs:
            r=item.get("resource",{}).get("labels",{})
            full=str(r.get("job_id") or r.get("job_name") or "")
            if SCHEDULE not in full: 
                other_sched +=1
                continue
            ts=item.get("timestamp")
            key=slot(ts)
            if not key: continue
            payload=item.get("jsonPayload") or {}
            http=item.get("httpRequest") or {}
            status=payload.get("status") or item.get("protoPayload",{}).get("status") or {}
            scheduler_by_slot[key].append({
                "time":local_stamp(ts).strftime("%H:%M:%S"),
                "http_status":http.get("status") or payload.get("httpRequest",{}).get("status"),
                "status_code":status.get("code") if isinstance(status,dict) else str(status)[:60],
                "severity":item.get("severity"),
                "type":str(payload.get("@type") or "").split(".")[-1],
            })
        print("SCHEDULER_LOGS_TOTAL",sum(map(len,scheduler_by_slot.values())),
              "other_jobs",other_sched,"day_slots",len(scheduler_by_slot),flush=True)
    else: print("SCHEDULER_LOGS_UNAVAILABLE",flush=True)

    error_query = (
       'resource.type="cloud_run_job" AND resource.labels.job_name="chwijae-collector" '
       f'AND timestamp>="{START}" AND timestamp<"{END}" '
       'AND severity>=ERROR'
    )
    errors=run("cloud-run-error-logs",[
       "gcloud","logging","read",error_query,"--project="+PROJECT,
       "--limit=500","--format=json"])
    errors_by_slot=Counter()
    if isinstance(errors,list):
        for e in errors:
            key=slot(e.get("timestamp"))
            if key:errors_by_slot[key]+=1
        print("CLOUD_RUN_ERROR_ENTRIES",len(errors),"error_slots",dict(sorted(errors_by_slot.items())),flush=True)
    else: print("CLOUD_RUN_ERRORS_UNAVAILABLE",flush=True)

    allslots=[f"{hour:02d}:{minute:02d}" for hour in range(24) for minute in (7,37)]
    for key in allslots:
        sc=scheduler_by_slot.get(key,[])
        ex=ex_by_slot.get(key,[])
        print("COLLECTOR_SLOT",json.dumps({
            "slot_kst":key,"scheduler_log_count":len(sc),
            "scheduler":sc,"executions":ex,
            "error_entries":errors_by_slot[key],
        },ensure_ascii=False),flush=True)

if __name__ == "__main__":
    main()
