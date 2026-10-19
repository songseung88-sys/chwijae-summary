#!/usr/bin/env bash
set -euo pipefail

PROJECT_ID="chwijae-summary"
REGION="asia-northeast3"
SERVICE_NAME="chwijae-api"
RUNTIME_SA="collector-runtime@chwijae-summary.iam.gserviceaccount.com"
SECRET_NAME="admin-editor-password"

gcloud config set project "${PROJECT_ID}" >/dev/null

read -s -p "관리자 편집 비밀번호를 입력하세요: " ADMIN_PASSWORD
echo
read -s -p "한 번 더 입력하세요: " ADMIN_PASSWORD_CONFIRM
echo

if [[ -z "${ADMIN_PASSWORD}" ]]; then
  echo "비밀번호가 비어 있습니다."
  exit 1
fi

if [[ "${ADMIN_PASSWORD}" != "${ADMIN_PASSWORD_CONFIRM}" ]]; then
  echo "두 비밀번호가 일치하지 않습니다."
  exit 1
fi

if gcloud secrets describe "${SECRET_NAME}" --project="${PROJECT_ID}" >/dev/null 2>&1; then
  printf '%s' "${ADMIN_PASSWORD}" | gcloud secrets versions add "${SECRET_NAME}" \
    --project="${PROJECT_ID}" --data-file=-
else
  printf '%s' "${ADMIN_PASSWORD}" | gcloud secrets create "${SECRET_NAME}" \
    --project="${PROJECT_ID}" --replication-policy=automatic --data-file=-
fi

gcloud secrets add-iam-policy-binding "${SECRET_NAME}" \
  --project="${PROJECT_ID}" \
  --member="serviceAccount:${RUNTIME_SA}" \
  --role="roles/secretmanager.secretAccessor" >/dev/null

gcloud run services update "${SERVICE_NAME}" \
  --project="${PROJECT_ID}" \
  --region="${REGION}" \
  --set-secrets="ADMIN_EDITOR_PASSWORD=${SECRET_NAME}:latest" \
  --quiet

unset ADMIN_PASSWORD ADMIN_PASSWORD_CONFIRM

URL="$(gcloud run services describe "${SERVICE_NAME}" \
  --project="${PROJECT_ID}" --region="${REGION}" --format='value(status.url)')"

echo
echo "관리자 문구 편집 기능이 활성화되었습니다."
echo "관리자 화면: ${URL}/admin"
