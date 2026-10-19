#!/usr/bin/env bash
set -euo pipefail

PROJECT_ID="chwijae-summary"
REGION="asia-northeast3"
REPO="songseung88-sys/chwijae-summary"
GITHUB_OWNER="songseung88-sys"

POOL_ID="github"
PROVIDER_ID="chwijae-summary"
DEPLOY_SA_NAME="github-deployer"
RUNTIME_SA_NAME="collector-runtime"
ARTIFACT_REPO="chwijae"

DEPLOY_SA="${DEPLOY_SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"
RUNTIME_SA="${RUNTIME_SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"

echo "== Project =="
gcloud config set project "${PROJECT_ID}"
PROJECT_NUMBER="$(gcloud projects describe "${PROJECT_ID}" --format='value(projectNumber)')"
echo "Project: ${PROJECT_ID} (${PROJECT_NUMBER})"
echo "Region : ${REGION}"

echo "== Enable APIs =="
gcloud services enable   run.googleapis.com   artifactregistry.googleapis.com   firestore.googleapis.com   secretmanager.googleapis.com   cloudscheduler.googleapis.com   iamcredentials.googleapis.com   sts.googleapis.com

echo "== Firestore =="
if ! gcloud firestore databases describe --database='(default)' >/dev/null 2>&1; then
  gcloud firestore databases create     --database='(default)'     --location="${REGION}"     --edition=standard     --type=firestore-native
else
  echo "Firestore default database already exists."
fi

echo "== Artifact Registry =="
if ! gcloud artifacts repositories describe "${ARTIFACT_REPO}" --location="${REGION}" >/dev/null 2>&1; then
  gcloud artifacts repositories create "${ARTIFACT_REPO}"     --repository-format=docker     --location="${REGION}"     --description="chwijae-summary container images"
else
  echo "Artifact Registry repository already exists."
fi

echo "== Service accounts =="
if ! gcloud iam service-accounts describe "${DEPLOY_SA}" >/dev/null 2>&1; then
  gcloud iam service-accounts create "${DEPLOY_SA_NAME}"     --display-name="GitHub deployer for chwijae-summary"
fi

if ! gcloud iam service-accounts describe "${RUNTIME_SA}" >/dev/null 2>&1; then
  gcloud iam service-accounts create "${RUNTIME_SA_NAME}"     --display-name="Cloud Run collector runtime"
fi

echo "== Runtime IAM =="
gcloud projects add-iam-policy-binding "${PROJECT_ID}"   --member="serviceAccount:${RUNTIME_SA}"   --role="roles/datastore.user"   --condition=None >/dev/null

echo "== Deploy IAM =="
for ROLE in   roles/run.admin   roles/serviceusage.serviceUsageConsumer   roles/secretmanager.viewer
do
  gcloud projects add-iam-policy-binding "${PROJECT_ID}"     --member="serviceAccount:${DEPLOY_SA}"     --role="${ROLE}"     --condition=None >/dev/null
done

gcloud artifacts repositories add-iam-policy-binding "${ARTIFACT_REPO}"   --location="${REGION}"   --member="serviceAccount:${DEPLOY_SA}"   --role="roles/artifactregistry.writer" >/dev/null

gcloud iam service-accounts add-iam-policy-binding "${RUNTIME_SA}"   --member="serviceAccount:${DEPLOY_SA}"   --role="roles/iam.serviceAccountUser" >/dev/null

echo "== Secret resources (values are NOT created here) =="
for SECRET in naver-api-client-id naver-api-client-secret openai-api-key; do
  if ! gcloud secrets describe "${SECRET}" >/dev/null 2>&1; then
    gcloud secrets create "${SECRET}" --replication-policy=automatic
  fi
  gcloud secrets add-iam-policy-binding "${SECRET}"     --member="serviceAccount:${RUNTIME_SA}"     --role="roles/secretmanager.secretAccessor" >/dev/null
done

echo "== Workload Identity Federation =="
if ! gcloud iam workload-identity-pools describe "${POOL_ID}"   --location=global >/dev/null 2>&1; then
  gcloud iam workload-identity-pools create "${POOL_ID}"     --location=global     --display-name="GitHub Actions Pool"
fi

if ! gcloud iam workload-identity-pools providers describe "${PROVIDER_ID}"   --location=global   --workload-identity-pool="${POOL_ID}" >/dev/null 2>&1; then
  gcloud iam workload-identity-pools providers create-oidc "${PROVIDER_ID}"     --location=global     --workload-identity-pool="${POOL_ID}"     --display-name="chwijae-summary GitHub provider"     --attribute-mapping="google.subject=assertion.sub,attribute.actor=assertion.actor,attribute.repository=assertion.repository,attribute.repository_owner=assertion.repository_owner"     --attribute-condition="assertion.repository == '${REPO}'"     --issuer-uri="https://token.actions.githubusercontent.com"
fi

POOL_NAME="$(gcloud iam workload-identity-pools describe "${POOL_ID}"   --location=global --format='value(name)')"

gcloud iam service-accounts add-iam-policy-binding "${DEPLOY_SA}"   --role="roles/iam.workloadIdentityUser"   --member="principalSet://iam.googleapis.com/${POOL_NAME}/attribute.repository/${REPO}" >/dev/null

PROVIDER_NAME="$(gcloud iam workload-identity-pools providers describe "${PROVIDER_ID}"   --location=global   --workload-identity-pool="${POOL_ID}"   --format='value(name)')"

echo
echo "=============================================="
echo "Bootstrap complete."
echo "Workload Identity Provider:"
echo "  ${PROVIDER_NAME}"
echo "Deploy service account:"
echo "  ${DEPLOY_SA}"
echo "Runtime service account:"
echo "  ${RUNTIME_SA}"
echo
echo "NEXT:"
echo "1) Add NEW secret versions to:"
echo "   naver-api-client-id"
echo "   naver-api-client-secret"
echo "   openai-api-key (optional for now)"
echo "2) Do not paste the new values into GitHub or ChatGPT."
echo "3) Then run the GitHub Actions workflow: Deploy collector."
echo "=============================================="
