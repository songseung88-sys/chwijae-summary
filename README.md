# 취재를 종합하면 — 운영·데이터 아카이브

한국 언론이 사용하는 **「취재를 종합하면」**과 **「본지 취재 결과」**(「본지 취재결과」 포함)의 용례를 주기적으로 수집하고, 언론사·기자·주제·무주체형 표현과 함께 기록하는 연구용 대시보드입니다.

- 공개 대시보드: https://chwijae-api-ejmdmrnztq-du.a.run.app/
- 관리자(표시 문구·언론사 이름 편집): https://chwijae-api-ejmdmrnztq-du.a.run.app/admin
- **비공개 데이터 아카이브**: https://docs.google.com/spreadsheets/d/1pLRILhu02VX1_KYDgEaRjOeL4WgBP_1Wmh-mm-iFcaY/edit

## 자동 운영 일정 (KST)

| 작업 | 일정 | 실행 환경 |
|---|---|---|
| 네이버 검색 기반 후보 수집 및 본문 확인 | 매시 07·37분 | Cloud Scheduler → Cloud Run Job `chwijae-collector` |
| AI 주제 분류(신규 미분류) | 매시 20분 | Cloud Scheduler → Cloud Run Job `chwijae-classifier-test` |
| **수집 실행 로그 → Google Sheets** | 매시 16·46분 (실행 시각은 다소 지연될 수 있음) | GitHub Actions → Cloud Run Job `chwijae-daily-archive` (`--mode logs --days 2`) |
| **기사·일별/언론사/기자/주제/표현 통계 → Google Sheets** | 매일 오전 02:13 | GitHub Actions → Cloud Run Job `chwijae-daily-archive` (`--mode full --days 7`) |

**중요:** 기존 수집·분류 일정을 중단하거나 중복 등록하지 않습니다. 코드 배포용 GitHub Actions `deploy-collector.yml`은 수집기 변경이 있을 때만 한 번 더 실행됩니다. 정기 스프레드시트 작업은 `run-daily-archive.yml`에 정의합니다.

## 데이터 보관과 검증 원칙

1. **Firestore `articles`가 원본 데이터베이스**입니다. 기사 ID를 기준으로 반복 처리를 멱등적으로 수행합니다. 공개 대시보드가 읽는 최근 1,200건 제한은 아카이브 저장에 적용하지 않습니다.
2. **인증된 본문만 통계에 포함**합니다. '찾은 기사'라는 이유로 표현이 실제 본문에 없는 글을 강제로 통계에 넣지 않습니다. 추출에 실패한 언론사도 이후 수집 대상에서 제외하지 않습니다.
3. 장기 보관용 기사 전문은 **언론사 원문을 우선** 확인하고, 공백·비정상 HTML·메타데이터·대상 표현 부재 등 검사를 통과하지 못하면 **네이버 전송본**을 시도합니다. 성공한 전문은 비공개 Firestore의 `archive_body_text`에 캐시하여 매번 다시 긁지 않습니다.
4. 둘 다 부적합하면 **`수집 실패`**라고 기록하고 상세 오류를 남깁니다. 구글 시트에는 붉은색 조건부 서식을 적용합니다. 실패는 다음 정기 실행에서 재시도하며, 일일 갱신의 신규 본문 확인은 회당 최대 100건으로 제한합니다. 세 번째 상태 **`수집 대기`**는 실패가 아니라 아직 시도 전이라는 뜻입니다.
5. 셀당 5만 글자 제한을 고려해 장문은 최대 3개 본문 열에 나누어 보존합니다. 길이 상한을 초과한 경우 임의로 잘라 '성공'이라고 하지 않습니다.
6. 기본 언론사명(`publisher_original`)과 관리자 수정 표시명은 따로 저장합니다. 기사 원자료·분류 버전·원문·네이버 주소를 보존해 이후 연구자가 추적할 수 있도록 합니다.
7. 아카이브 내 기사 전문은 **연구용 비공개 자료**이며 외부에 무단 재배포하지 않습니다.

## Google Sheets 9개 시트

| 시트 | 내용/고유 키 |
|---|---|
| 일별 통계 | 날짜 단위: 기사의 수·언론사·기자·[단독]·양대 표현·분류 실적 |
| 언론사별 | 날짜+**원본** 언론사명: 표시명 및 기사·표현 빈도 |
| 기자별 | 날짜+**원본** 언론사명+기자명 |
| 주제별 | 날짜+분류 버전+1/2/3차 분류 |
| 무주체형 표현 | 날짜+규칙 버전+표현명; 횟수와 포함 기사 수 구분 |
| 기사 목록 | 기사 ID: **전문(필요시 분할)**·본문 출처·상태·실패 사유·원문/네이버 URL |
| 동기화 기록 | 개별 일별 전체 동기화의 실행 시각과 갱신 행 수 |
| 30분 수집 로그 | `collector_runs` 실행 ID: 후보·승인·제외·새 기사·원문/네이버 대체·오류 |
| 언론사 수집 진단 | 실행 ID+도메인: 시도·성공·실패와 오류 종류 및 사례 |

모든 시트의 숨긴 `동기화 키` 열로 중복 행을 방지하고, 이미 존재하는 행은 업데이트합니다. **과거 수집 로그에서 상위 20개만 보존됐던 제외 예시는 '일부 사례'라고 별도로 표시**하므로 전수 통계와 혼동하지 않습니다.

## 장애 복구·수동 실행

- Cloud Run 콘솔 → Jobs에서 `chwijae-daily-archive`의 실행 성공 여부를 확인합니다.
- 저장소 Actions → **Keep Google Sheets archive in sync** → **Run workflow**에서 모드(`full` 또는 `logs`)와 기간(1–90일)을 지정해 재실행할 수 있습니다.
- **Verify Google Sheets archive log sync**는 `logs` 모드의 단독 동작을 재검증할 때 사용합니다.
- Google Sheets API(`sheets.googleapis.com`)는 GCP 프로젝트 `chwijae-summary`에서 활성화돼 있어야 합니다. Sheets 파일은 `collector-runtime@chwijae-summary.iam.gserviceaccount.com` 계정에 편집 권한이 필요합니다.
- 연결 실패와 서비스 계정 권한 오류는 재시도만으로 해결되지 않습니다. 관련 Google Cloud 설정부터 점검합니다.
- GitHub Actions/Cloud Run 실행 로그와 Firestore `archive_status` 문서에 동기화 상태를 기록합니다.
- 계정 비밀번호, 네이버 API 키, OpenAI 키는 **Google Secret Manager** 등 비밀 저장소에만 두고 코드나 시트에 쓰지 않습니다.

이 README는 재현·운영을 위한 설명입니다. 정확한 현황은 Cloud Run 실행 기록과 시트의 **동기화 기록**, **30분 수집 로그**를 함께 확인해주세요.
