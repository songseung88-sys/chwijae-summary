# Google Cloud 최초 설정

이 프로젝트는 로컬 PC 없이 다음 구조로 운영합니다.

- GitHub: 코드 원본
- GitHub Actions: Cloud Run Job 배포
- Google Cloud Run Job: 기사 수집
- Firestore: 기사/수집 로그 저장
- Secret Manager: API 키 저장
- Cloud Scheduler: 수집 자동 실행(첫 수집 검증 후 추가)

## 0. 보안: 먼저 기존 키를 폐기

채팅에 노출된 기존 NAVER Client Secret과 OpenAI API secret key는 재사용하지 않습니다.

새로 발급한 값은 **이 저장소나 채팅에 붙여넣지 말고** Google Secret Manager에 직접 입력합니다.

## 1. Cloud Shell에서 bootstrap 실행

Google Cloud Console에서 프로젝트 `chwijae-summary`를 선택한 뒤 Cloud Shell을 엽니다.

아래 명령으로 이 브랜치의 스크립트를 내려받고 실행합니다.

```bash
curl -fsSL https://raw.githubusercontent.com/songseung88-sys/chwijae-summary/bootstrap-cloud/infra/bootstrap_gcp.sh -o bootstrap_gcp.sh
bash bootstrap_gcp.sh
```

스크립트가 하는 일:

- 필요한 Google Cloud API 활성화
- Firestore Native mode 기본 DB 생성 (서울)
- Artifact Registry 생성
- GitHub 배포용/수집기 실행용 서비스 계정 생성
- Secret Manager의 secret 리소스 생성
- GitHub Actions용 Workload Identity Federation 구성

## 2. Secret Manager에 새 값 입력

Google Cloud Console → Secret Manager에서 아래 secret을 찾습니다.

- `naver-api-client-id`
- `naver-api-client-secret`
- `openai-api-key`

각 secret에서 **새 버전 추가(Add new version)** 를 눌러 새로 발급한 값을 직접 입력합니다.

OpenAI는 아직 분류 기능을 켜지 않으므로 `openai-api-key`는 당장 비워둬도 됩니다.

중요: NAVER 두 secret의 첫 실제 버전이 version 1이어야 현재 배포 workflow와 바로 연결됩니다.

## 3. 첫 클라우드 수집

bootstrap과 NAVER secret 입력이 끝난 뒤 알려주세요.

그 다음 `bootstrap-cloud` 변경을 main에 합치고, GitHub Actions의 **Deploy collector** workflow를 실행합니다.

첫 실행은 Cloud Run Job을 배포한 뒤 즉시 한 번 수집까지 수행합니다.

## 4. 첫 검증에서 볼 지표

Firestore의 `collector_runs`:

- 후보 기사 수
- 최종 편입 수
- 원문 성공 수
- NAVER fallback 수
- [단독] 기사 수
- 통신사 전재 의심 수
- 파싱 오류 유형

Firestore의 `articles`:

- 원문/NAVER URL
- 원문 카테고리
- 기자/발행·수정 시각
- "취재를 종합하면" 문단
- 보조 표현
- 원문↔NAVER 본문 일치도
- [단독] 여부
- 통신사 전재 의심 여부

이 결과를 확인한 뒤 실패 언론사 전용 parser와 30분 자동 스케줄을 추가합니다.
