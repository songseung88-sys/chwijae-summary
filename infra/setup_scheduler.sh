#!/usr/bin/env bash
# One-time Cloud Shell setup for the chwijae-summary production schedulers.
# Run with a project administrator account. This provisions PAUSED jobs so
# GitHub Actions continues collecting until the migration is explicitly activated.
set -euo pipefail

PROJECT_ID="chwijae-summary"
REGION="asia-northeast3"
INVOKER_NAME="chwijae-scheduler-invoker"
INVOKER_SA="${INVOKER_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"

echo "Project: ${PROJECT_ID} | Region: ${REGION}"
gcloud projects describe "${PROJECT_ID}" --format="value(projectId)" >/dev/null
gcloud services enable cloudscheduler.googleapis.com run.googleapis.com --project="${PROJECT_ID}"

if ! gcloud iam service-accounts describe "${INVOKER_SA}" --project="${PROJECT_ID}" >/dev/null 2>&1; then
  gcloud iam service-accounts create "${INVOKER_NAME}" \
    --project="${PROJECT_ID}" \
    --display-name="Chwijae scheduled Cloud Run jobs invoker"
fi

# Cloud Scheduler uses the job's persisted environment; execution-time overrides
# from GitHub Actions do not persist. Do this before creating new schedules.
gcloud run jobs update chwijae-classifier-test \
  --project="${PROJECT_ID}" \
  --region="${REGION}" \
  --update-env-vars="CLASSIFY_FORCE=false,CLASSIFY_LIMIT=100" \
  --quiet

# IAM is eventually consistent: a new service account can take 60s or more
# to become usable in Cloud Run IAM bindings. Retry without recreating it.
grant_job_invoker() {
  local job="$1" attempt
  local error_file
  error_file="$(mktemp)"
  for attempt in 1 2 3 4 5 6 7 8 9 10; do
    if gcloud run jobs add-iam-policy-binding "${job}" \
      --project="${PROJECT_ID}" \
      --region="${REGION}" \
      --member="serviceAccount:${INVOKER_SA}" \
      --role="roles/run.invoker" \
      --quiet > /dev/null 2>"${error_file}"; then
      echo "Cloud Run Invoker granted on ${job}."
      rm -f "${error_file}"
      return 0
    fi
    if (( attempt == 10 )); then
      echo "Unable to grant Cloud Run Invoker on ${job} after 10 attempts." >&2
      cat "${error_file}" >&2
      rm -f "${error_file}"
      return 1
    fi
    echo "IAM binding not ready (attempt ${attempt}/10). Retrying in 15 seconds..."
    sleep 15
  done
}

for JOB in chwijae-collector chwijae-classifier-test; do
  echo "Granting limited Cloud Run invoker role on ${JOB}"
  grant_job_invoker "${JOB}"
done

upsert_schedule() {
  local name="$1" cron="$2" target="$3"
  local uri="https://run.googleapis.com/v2/projects/${PROJECT_ID}/locations/${REGION}/jobs/${target}:run"
  local common=(
    --project="${PROJECT_ID}"
    --location="${REGION}"
    --schedule="${cron}"
    --time-zone="Asia/Seoul"
    --uri="${uri}"
    --http-method="POST"
    --oauth-service-account-email="${INVOKER_SA}"
    --oauth-token-scope="https://www.googleapis.com/auth/cloud-platform"
    --attempt-deadline="120s"
    --max-retry-attempts=0
    --quiet
  )
  if gcloud scheduler jobs describe "${name}" --project="${PROJECT_ID}" --location="${REGION}" >/dev/null 2>&1; then
    gcloud scheduler jobs update http "${name}" "${common[@]}"
  else
    gcloud scheduler jobs create http "${name}" "${common[@]}"
  fi
  # Hold until GitHub recurring schedule is disabled, to avoid two schedulers.
  local state
  state="$(gcloud scheduler jobs describe "${name}" --project="${PROJECT_ID}" --location="${REGION}" --format="value(state)")"
  if [[ "${state}" != "PAUSED" ]]; then
    gcloud scheduler jobs pause "${name}" --project="${PROJECT_ID}" --location="${REGION}" --quiet
  fi
  gcloud scheduler jobs describe "${name}" \
    --project="${PROJECT_ID}" --location="${REGION}" \
    --format="table(name,schedule,timeZone,state)"
}

upsert_schedule "chwijae-collector-half-hourly" "7,37 * * * *" "chwijae-collector"
upsert_schedule "chwijae-classifier-hourly" "20 * * * *" "chwijae-classifier-test"

echo
echo "Cloud Scheduler setup completed. Both new schedules remain PAUSED."
echo "The existing GitHub Actions schedules are intentionally still active."
echo "Next: confirm new jobs exist, then switch schedulers in a separate step."
