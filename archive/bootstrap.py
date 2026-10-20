"""Cloud Run startup guard: record initialization and any fatal exception."""
import os
import runpy
import sys
import traceback
from datetime import datetime
from zoneinfo import ZoneInfo

def report(status, message):
    try:
        from google.cloud import firestore
        db=firestore.Client(project=os.getenv("GCP_PROJECT_ID") or None)
        args=sys.argv[1:]
        mode="logs" if "logs" in args else "full"
        db.collection("archive_status").document(mode).set({
            "mode":mode,"status":status,
            "detail":str(message)[:1400],
            "updated_at":datetime.now(ZoneInfo("Asia/Seoul")).isoformat(),
        },merge=True)
        print("ARCHIVE_BOOTSTRAP_STATUS",mode,status,flush=True)
    except Exception as ex:
        print("ARCHIVE_BOOTSTRAP_STATUS_WRITE_FAILED",
              type(ex).__name__,str(ex)[:450],file=sys.stderr,flush=True)

if __name__=="__main__":
    report("started","Cloud Run entrypoint reached; starting Python archive module")
    arguments=sys.argv[1:]
    try:
        sys.argv=["/app/main.py"]+arguments
        runpy.run_path("/app/main.py",run_name="__main__")
    except BaseException:
        detail=traceback.format_exc()
        print(detail,file=sys.stderr,flush=True)
        report("failure",detail)
        raise
