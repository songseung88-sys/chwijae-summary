# Cloud Scheduler migration — 취재를 종합하면

## Scope
- Collector: `chwijae-collector`, Asia/Seoul 07 and 37 minutes each hour.
- Classifier: `chwijae-classifier-test`, Asia/Seoul minute 20 hourly.
- Both use authenticated Cloud Run Jobs v2 `:run` endpoints, not the public dashboard API.
- A dedicated service account `chwijae-scheduler-invoker@chwijae-summary.iam.gserviceaccount.com`
  receives only Cloud Run Invoker on the two jobs.
- The classifier's existing environment remains `CLASSIFY_FORCE=false`; no forced
  reclassification is requested by Cloud Scheduler.

## One-time administrator step
The GitHub Workload Identity deployer deliberately has no Cloud Scheduler Admin or IAM Admin
role. Project owners should open Google Cloud Shell and run:

```bash
git clone https://github.com/songseung88-sys/chwijae-summary.git
cd chwijae-summary
bash infra/setup_scheduler.sh
```

The idempotent script enables the API, creates the restricted invoker identity,
grants the necessary job-level invoker role, creates or updates both schedules and
**PAUSES both Cloud Scheduler jobs**. Existing GitHub Actions schedules stay enabled.

If you have already cloned the repo, run `git pull --ff-only` in it instead of cloning again.

## Verify the setup
In Google Cloud Console > Cloud Scheduler, confirm both rows:
- `chwijae-collector-half-hourly` (schedule `7,37 * * * *`, Asia/Seoul)
- `chwijae-classifier-hourly` (schedule `20 * * * *`, Asia/Seoul)

Both must say **PAUSED**, and both target
`https://run.googleapis.com/v2/projects/chwijae-summary/locations/asia-northeast3/jobs/<job>:run`
using OAuth from the scheduler invoker.

## Safe cutover (after confirmation)
1. Remove the `schedule:` events from `.github/workflows/run-collector.yml`
   and `.github/workflows/run-classifier.yml`, **but retain `workflow_dispatch:`**
   so manual recovery remains possible.
2. Merge that change into main and verify no recurring GitHub schedules remain.
3. Resume both prepared Cloud Scheduler jobs:

```bash
gcloud scheduler jobs resume chwijae-collector-half-hourly --project=chwijae-summary --location=asia-northeast3
gcloud scheduler jobs resume chwijae-classifier-hourly --project=chwijae-summary --location=asia-northeast3
```

4. Check Cloud Scheduler execution status and `/api/status` on the next 30-minute
   boundary; check `/api/classification-test` after the next hourly classification.
5. If the new scheduler fails, pause its jobs and re-enable GitHub cron via a revert.

Until step 4, DO NOT declare migration complete. Cloud Scheduler success means a
trigger was delivered, not automatically that every source article was collected.
Continue reviewing collector `new_accepted`, `candidates`, and `errors`.

No key or credential value is stored in this repository.
