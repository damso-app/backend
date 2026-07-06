# Prompt Log

## 2026-07-06 영상 업로드(answers) 테스트 작성

### 요청 프롬프트 요약

`docs/API_DRAFT.md` 문서화에 이어 `POST /api/v1/answers/upload-url`, `POST /api/v1/answers`에 대한 정식 테스트 코드를 작성하도록 요청했다. 실제 Supabase DB에 대한 `alembic upgrade head` 적용은 이번 세션에서는 보류하고, 로컬 검증(pytest, ruff)까지만 진행했다.

### 생성/수정 파일

- `tests/test_answers_upload.py`
- `docs/PROMPT_LOG.md`

### 반영 내용

- `app/api/v1/answers.py`의 `get_storage_service`를 오버라이드하는 `FakeStorageService`로 실제 GCS 호출 없이 라우터 테스트를 작성했다(기존 `test_question_answer_loop.py`와 동일한 SQLite in-memory + `TestClient` fixture 패턴).
- 정상 흐름(업로드 URL 발급 → 답변 제출 → `question_sends.status = answered` 반영), 수신자 아닌 사용자 403, 존재하지 않는 `questionSendId` 404, 지원하지 않는 `videoMimeType` 415, 중복 제출 409, 필수 필드 누락 422 케이스를 테스트했다.

### 사람이 확인할 포인트

- 실제 Supabase DB에 `20260706_0008_create_answers_table` 마이그레이션이 아직 적용되지 않았다. 다음에 적용이 필요하다.

### 검증 결과

```bash
.venv/bin/python -m pytest tests/test_answers_upload.py -v
# 6 passed, 1 warning

.venv/bin/python -m pytest -q
# 79 passed, 1 warning

.venv/bin/ruff check .
# All checks passed!

.venv/bin/alembic heads
# 20260706_0008 (head)
```

### 프롬프트 변경 여부

AI 질문 생성, 답변 요약, 분석 프롬프트는 변경하지 않았다.

## 2026-07-06 영상 업로드 API 문서화(`docs/API_DRAFT.md`)

### 요청 프롬프트 요약

앞선 작업(answers 테이블, GCS 연동, `AnswerService`, 라우터)에 이어 `docs/API_DRAFT.md`에 `POST /api/v1/answers/upload-url`, `POST /api/v1/answers`의 실제 요청/응답 예시와 에러 케이스를 문서화하도록 요청했다.

### 수정 파일

- `docs/API_DRAFT.md`
- `docs/DB_SCHEMA.md`
- `docs/PROMPT_LOG.md`

### 반영 내용

- `POST /api/v1/answers/upload-url`, `POST /api/v1/answers` 서브섹션을 추가해 실제 요청/응답 예시와 에러 케이스(404/403/409/415)를 문서화했다.
- `GET /api/v1/clips`의 `thumbnail_url` 설명을 "`status = completed`일 때만 노출"에서 "제출 직후 생성되므로 `status`와 무관하게 항상 노출"로 정정했다 — 이전 세션에서 `thumbnail_url`을 `answers`로 옮기기로 결정한 뒤 이 문구를 놓치고 있었다.
- 이전에 "Leo"라는 인물 이름을 문서에서 지우는 과정에서 문장 일부(" 백엔드", "→  콜백", "가 AI 서버로")가 어색하게 깨져 있던 부분을 `docs/API_DRAFT.md`, `docs/DB_SCHEMA.md`에서 자연스러운 문장으로 정리했다.

### 검증 결과

```bash
.venv/bin/python -m pytest -q
# 73 passed, 1 warning

.venv/bin/ruff check .
# All checks passed!

ruby -e 'ARGV.each do |path| s=File.read(path); fences=s.scan(/^```/).size; abort "#{path}: unbalanced fences" unless fences.even?; puts "#{path}: markdown fences balanced (#{fences})"; end' docs/API_DRAFT.md docs/DB_SCHEMA.md docs/ERD.md docs/PROMPT_LOG.md
# 전부 balanced 확인
```

### 프롬프트 변경 여부

AI 질문 생성, 답변 요약, 분석 프롬프트는 변경하지 않았다.

## 2026-07-06 한국 시간 기준 날짜 계산 반영

### 요청 프롬프트 요약

프로젝트 로직에서 시간 계산이 필요한 부분이 있으면 한국 시간 기준으로 계산하도록 반영해 달라고 요청했다.

### 수정 파일

- `app/core/timezone.py`
- `app/services/question_loop_service.py`
- `tests/test_timezone.py`
- `tests/test_question_answer_loop.py`
- `docs/API_DRAFT.md`
- `docs/DB_SCHEMA.md`
- `docs/PROMPT_LOG.md`

### 반영 내용

- 한국 시간대 상수 `Asia/Seoul`과 KST 날짜 범위를 UTC 범위로 변환하는 helper를 추가했다.
- 홈 요약의 `todayCompletedCount`를 UTC 날짜가 아니라 한국 시간 기준 오늘 범위로 계산하도록 변경했다.
- 토큰 만료 같은 보안 절대시간 계산은 UTC 기준을 유지했다.
- 이벤트 시각 저장은 timezone-aware timestamp로 유지하고, 날짜 단위 비즈니스 집계만 KST 기준으로 계산한다.

### 검증 결과

```bash
pytest
# 73 passed, 1 warning

ruff check .
# All checks passed!
```

### 프롬프트 변경 여부

AI 질문 생성, 답변 요약, 분석 프롬프트는 변경하지 않았다.

## 2026-07-06 영상 업로드(answers) 구현 1차 — GCS 업로드 URL 발급과 답변 등록

### 요청 프롬프트 요약

확정된 AI 연동 파이프라인 문서를 바탕으로 영상 업로드 기능부터 구현하도록 요청했다. 구현 상세 계획을 먼저 대화로 출력받아 승인한 뒤, 작업을 여러 단계로 나눠 각 단계가 끝날 때마다 확인받고 승인하면 다음 단계로 진행하는 방식으로 작업했다. 이번 1차 범위는 ffmpeg 썸네일/HLS, AI 서버 연동, `ai-callback` 수신은 제외하고 GCS 업로드 URL 발급과 `answers` row 등록까지다.

### 생성/수정 파일

- `app/models/answer.py`
- `app/models/__init__.py`
- `alembic/versions/20260706_0008_create_answers_table.py`
- `requirements.txt`
- `app/core/config.py`
- `.env.example`
- `.env`
- `app/services/storage_service.py`
- `app/schemas/answers.py`
- `app/services/answer_service.py`
- `app/api/v1/answers.py`
- `docs/PROMPT_LOG.md`

### 반영 내용

- `answers` 테이블/모델을 `docs/DB_SCHEMA.md` 전체 컬럼 기준으로 생성했다(AI 콜백 관련 컬럼은 이번 단계에서 값이 안 채워지고 비워둠).
- `google-cloud-storage` 의존성과 `gcs_bucket_name`/`gcs_signed_url_expire_minutes`/`gcs_signer_service_account` 설정을 추가했다.
- `StorageService.generate_upload_url`을 V4 signed URL + IAM `signBlob` impersonation 방식으로 구현했다. 로컬 gcloud ADC(사용자 계정)로는 직접 서명이 안 되어 서비스 계정을 impersonate하는 방식을 쓰고, Cloud Run에서는 런타임 서비스 계정이 자기 자신을 impersonate하는 동일한 코드 경로를 쓴다.
- 실제 `damso-videos` 버킷을 대상으로 기본 compute 서비스 계정(`42522835157-compute@developer.gserviceaccount.com`)에 대해 로컬 계정(`l3oojins@gmail.com`)에 `roles/iam.serviceAccountTokenCreator`를 부여하고, signed URL이 실제로 발급되는 것까지 확인했다.
- `AnswerService.create_upload_url` / `submit_answer`를 추가했다. 오브젝트 경로(`answers/{family_id}/{question_send_id}/original.{ext}`)는 클라이언트가 지정하지 못하게 서버가 `family_id` + `question_send_id` + mime type으로 결정적으로 계산한다.
- `submit_answer`는 `answers` row 생성과 함께 `question_sends.status = answered`, `answered_at`을 갱신한다(기존에 이 전이를 처리하는 코드가 없었음).
- `POST /api/v1/answers/upload-url`, `POST /api/v1/answers` 라우트를 추가했다. 에러는 `QuestionSendNotFoundError`→404, `NotRecipientError`→403, `AlreadyAnsweredError`→409, `UnsupportedVideoMimeTypeError`→415로 매핑했다.

### 사람이 확인할 포인트

- 이번 단계에서 안 한 것: ffmpeg 썸네일/HLS 처리, AI 서버 fire-and-forget 연동, `POST /api/v1/answers/ai-callback` 수신, `video_clips`/`video_clip_ai_results` 테이블.
- `docs/API_DRAFT.md`에 새 엔드포인트 두 개가 아직 문서화되지 않았다(다음 작업 예정).
- `tests/test_answers_upload.py` 정식 테스트 코드가 아직 없다 — 지금까지는 임시 스크립트로 수동 검증만 했다(다음 작업 예정).
- Cloud Run 배포 시 런타임 서비스 계정에 스스로에 대한 `roles/iam.serviceAccountTokenCreator` 부여가 필요하다.

### 검증 결과

```bash
.venv/bin/python -m pytest -q
# 70 passed, 1 warning

.venv/bin/ruff check app/models/answer.py app/models/__init__.py app/core/config.py \
  app/services/storage_service.py app/schemas/answers.py app/services/answer_service.py \
  app/api/v1/answers.py alembic/versions/20260706_0008_create_answers_table.py
# All checks passed!

.venv/bin/alembic heads
# 20260706_0008 (head)

# 실제 GCS 버킷 대상 signed URL 발급 수동 확인 (StorageService.generate_upload_url)
# url ok: True

# OpenAPI 스키마에 신규 라우트 노출 확인
# ['post'] /api/v1/answers/upload-url
# ['post'] /api/v1/answers
```

### 프롬프트 변경 여부

AI 질문 생성, 답변 요약, 분석 프롬프트는 변경하지 않았다.

## 2026-07-06 AI 연동 파이프라인 확정과 answers/video_clips 스키마 갱신

### 요청 프롬프트 요약

Notion에서 `DAMSO-BE-API 명세서`와 `DAMSO-AI-API 명세서` 문서를 확인하고 그 내용을 현재 `docs/DB_SCHEMA.md`, `docs/ERD.md`와 비교해서 최신 상태로 업데이트하도록 요청했다. 이어서 실제 영상 업로드~AI 처리 파이프라인(클라이언트 GCS 업로드 → 답변 생성 → BackgroundTasks에서 ffmpeg 썸네일 추출과 AI 서버 fire-and-forget 호출 → AI 서버 콜백 → HLS 변환/video_clips 생성 → Realtime broadcast)을 알려주고 문서에 반영하도록 요청했다. 콜백 correlation identifier로 `ai_job_id`를 쓸지 `answer_id`를 쓸지, 콜백 엔드포인트를 어디에 둘지(어느 서버가 소유하는지, 경로 네이밍)를 논의해 확정했고, 실제 AI 서버 curl 예시를 보고 파일 멀티파트 업로드 방식 대신 `mediaPath` JSON 방식을 강제하기로 했다. 영상 스토리지 provider를 GCS로 재확인했다(이전 세션엔 Supabase Storage로 결정했었음). 앞으로 문서에는 특정 인물 이름을 언급하지 않도록 요청했다.

### 수정 파일

- `docs/DB_SCHEMA.md`
- `docs/ERD.md`
- `docs/API_DRAFT.md`
- `docs/PROMPT_LOG.md`

### 반영 내용

- `answers`에 `thumbnail_url`(제출 직후 ffmpeg 추출, AI 처리 상태와 무관하게 그리드 노출), `ai_retryable`, `ai_fallback_used`, `ai_input_context` 컬럼을 추가했다.
- `video_clips`에서 `thumbnail_url`을 제거하고(`answers`가 소유), `summary`를 `one_line_summary`로 이름을 바꾸고, `transcript_segments`/`fourcut_title`/`updated_at`을 추가했다.
- `video_clip_ai_results` 테이블을 신규 추가해 AI `pipelineResults` 전체 원본 응답을 snapshot으로 보관하도록 했다.
- AI 연동 방식을 GCP Pub/Sub 큐 검토안에서 "백엔드 → AI 서버 fire-and-forget POST(`mediaPath` JSON 모드) → AI 서버 → 백엔드 콜백" 방식으로 확정했다.
- 콜백 correlation은 `answer_id` 하나로 통일하기로 하고, 처음 도입했던 `ai_job_id` 컬럼(별도 correlation용)은 다시 제거했다 — AI 처리 추적도 결국 `answer_id` 기준이 자연스럽다는 판단.
- 콜백 엔드포인트를 `POST /api/v1/ai/callback`이 아니라 `POST /api/v1/answers/ai-callback`으로 확정했다. `api/v1/ai/{기능}`은 AI 서버 자신의 엔드포인트 네이밍 규칙이라 겹치지 않도록 `answers` 리소스 하위로 옮겼다.
- AI 서버 요청은 멀티파트 파일 업로드(`/ai/stt/transcribe-file`) 대신 JSON Path Mode(`mediaPath`)를 강제하기로 했다.
- 영상 가공(썸네일, HLS)은 전량 백엔드 ffmpeg 담당이되, 구현 우선순위는 영상 업로드 → AI 연동 순으로 미루기로 했다.
- `docs/API_DRAFT.md`에 `POST /api/v1/answers/ai-callback` 요청/응답 예시(성공/실패), 처리 로직, 인증 미정 TODO를 새로 문서화했다.

### 사람이 확인할 포인트

- `ai-callback` 엔드포인트 인증(공유 시크릿 등) 방식이 아직 미정이다.
- `video_clip_ai_results.ai_raw_response`의 실제 스키마는 AI 서버 스펙이 최종 확정된 뒤 다시 반영해야 한다.
- 영상 스토리지 provider가 GCS로 재확정됐으므로, 향후 실제 연동 코드(`storage_service.py`)는 Supabase Storage가 아니라 GCS SDK 기준으로 작성해야 한다.

### 검증 결과

문서만 수정했고 코드/DB 변경은 없다.

```bash
grep -rn "Leo" docs/
# (결과 없음, 문서에서 인물 이름 언급 제거 확인)
```

### 프롬프트 변경 여부

AI 질문 생성, 답변 요약, 분석 프롬프트 자체는 변경하지 않았고, 향후 AI 서버와 주고받을 `pipelineResults` 매핑 규칙만 DB 설계 문서에 반영했다.

## 2026-07-06 질문/답변 루프 MVP 1차 구현

### 요청 프롬프트 요약

`implementing-question-answer-loop` Skill을 사용해 홈 요약 조회, 질문 대상자 목록 조회, 추천 질문 조회, 질문 보내기, 나에게 온 질문 목록/상세 조회, 나에게 온 질문 읽음 처리를 구현하도록 요청했다. 질문 탭과 답변 탭은 분리하고, 답변하지 않은 질문이 있어도 질문 보내기는 가능해야 한다. 영상 업로드와 실제 AI 분석 실행은 이번 범위에서 제외한다. 구현 후 `pytest`, `ruff check .`, 필요한 경우 `alembic upgrade head`를 실행하고 `docs/API_DRAFT.md`, `docs/DB_SCHEMA.md`, `docs/PROMPT_LOG.md`를 갱신하도록 요청했다.

### 생성/수정 파일

- `app/api/v1/home.py`
- `app/api/v1/questions.py`
- `app/api/v1/answers.py`
- `app/main.py`
- `app/models/question_recommendation.py`
- `app/models/question_send.py`
- `app/models/__init__.py`
- `app/schemas/question_loop.py`
- `app/services/question_loop_service.py`
- `alembic/versions/20260706_0007_create_question_answer_loop_tables.py`
- `tests/test_models.py`
- `tests/test_question_answer_loop.py`
- `docs/API_DRAFT.md`
- `docs/DB_SCHEMA.md`
- `docs/PROMPT_LOG.md`

### 반영 내용

- `GET /api/v1/home/summary`를 추가해 가족 연결 여부, 자식/부모 연결 여부, 오늘 완료 건수, 받은 질문 대기 상태, 보낸 질문 상태, AI 상태 자리(`null`)를 반환한다.
- `GET /api/v1/questions/recipients`를 추가해 같은 활성 가족 구성원 중 본인을 제외한 질문 대상자를 반환한다.
- `GET /api/v1/questions/recommendations`를 추가해 `tiny`, `medium`, `deep` depth 기준 active 추천 질문을 랜덤 조회한다.
- `POST /api/v1/questions`를 추가해 추천 질문 또는 직접 작성 질문을 같은 가족 구성원에게 보낸다.
- `GET /api/v1/answers/questions`를 추가해 나에게 온 질문 목록을 조회하고, `unansweredOnly`와 `sort`를 지원한다.
- `GET /api/v1/answers/questions/{question_send_id}`를 추가해 현재 사용자에게 온 질문만 상세 조회한다.
- `PATCH /api/v1/answers/questions/{question_send_id}/read`를 추가해 현재 사용자에게 온 질문만 읽음 처리한다.
- `question_recommendations`, `question_sends` SQLAlchemy 모델과 Alembic migration을 추가했다.
- `question_sends.read_at`으로 읽음 여부를 판단하고, `answered_at` 또는 `status = answered`로 답변 여부를 판단한다.
- 영상 업로드, 실제 답변 저장, AI 분석 실행/저장은 구현하지 않고 후속 기능으로 남겼다.

### 검증 결과

```bash
pytest
# 70 passed, 1 warning

ruff check .
# All checks passed!

.venv/bin/alembic current
# 20260706_0006

.venv/bin/alembic upgrade head
# Running upgrade 20260706_0006 -> 20260706_0007, create question answer loop tables

.venv/bin/alembic current
# 20260706_0007 (head)

python -c 'from app.main import app; schema=app.openapi(); ...'
# /api/v1/answers/questions get
# /api/v1/answers/questions/{question_send_id} get
# /api/v1/answers/questions/{question_send_id}/read patch
# /api/v1/home/summary get
# /api/v1/questions post
# /api/v1/questions/recipients get
# /api/v1/questions/recommendations get
```

### 사람이 확인할 포인트

- 추천 질문 seed 데이터 적재 방식은 아직 별도 운영 작업으로 남아 있다.
- 홈 요약의 `aiStatus`는 실제 AI 분석 기능이 붙기 전까지 `null`을 반환한다.
- 오늘 완료 건수는 `question_sends.answered_at` 기준으로 계산한다. 실제 영상 답변 저장 API가 붙으면 그 시점에 완료 상태 전이 기준을 다시 확정해야 한다.

### 프롬프트 변경 여부

AI 질문 생성, 답변 요약, 분석 프롬프트는 변경하지 않았다.

## 2026-07-06 온보딩 역할 선택과 가족 연결 MVP 구현

### 요청 프롬프트 요약

Kakao 로그인과 Damso access token 인증 이후 피그마의 역할 선택 화면과 가족 초대 화면에 필요한 백엔드 기능을 구현하도록 요청했다. 내 온보딩 상태 조회, 역할 선택 저장, 가족 생성 및 초대코드 발급, 내 가족 초대정보 조회, 초대코드 검증, 초대코드로 가족 참여 API를 추가한다. MVP에서는 사용자가 하나의 가족에만 속할 수 있고, 필수 동의 미완료 시 역할/가족 API를 막으며, 역할이 없으면 가족 생성/join을 막는다. 카카오톡 공유 자체, 질문/답변/다이어리 기능, 실제 비밀값 변경은 범위에서 제외한다.

### 생성/수정 파일

- `app/api/v1/users.py`
- `app/api/v1/families.py`
- `app/main.py`
- `app/models/family.py`
- `app/schemas/users.py`
- `app/schemas/families.py`
- `app/services/onboarding_service.py`
- `app/services/family_service.py`
- `app/services/user_agreement_service.py`
- `alembic/versions/20260706_0005_add_family_invite_code.py`
- `tests/test_onboarding_family.py`
- `tests/test_models.py`
- `docs/API_DRAFT.md`
- `docs/DB_SCHEMA.md`
- `docs/PROMPT_LOG.md`

### 반영 내용

- `GET /api/v1/users/me/onboarding`을 추가했다.
- `PATCH /api/v1/users/me/role`을 추가해 `child`, `parent` 역할을 저장한다.
- `POST /api/v1/families`를 추가해 가족 생성, `XXX-XXX` 형식 초대코드 발급, 생성자 멤버십 저장을 처리한다.
- `GET /api/v1/families/me/invitation`을 추가해 현재 사용자의 가족 초대정보를 조회한다.
- `GET /api/v1/families/invitations/{invite_code}`를 추가해 초대코드를 검증한다.
- `POST /api/v1/families/join`을 추가해 초대코드로 가족에 참여한다.
- `families.invite_code` nullable `VARCHAR(7)` 컬럼과 unique index를 추가했다.
- 필수 동의 미완료 사용자는 역할 저장과 가족 API에서 `400`을 반환한다.
- 역할이 없는 사용자는 가족 생성/join에서 `400`을 반환한다.
- 이미 가족에 속한 사용자의 가족 생성/join은 `409`를 반환한다.
- 비활성/삭제 가족 또는 없는 초대코드는 `404`를 반환한다.
- invite URL은 기존 `FRONTEND_OAUTH_CALLBACK_URL`의 origin을 사용해 `/invite?code=...`로 생성한다.

### 검증 결과

```bash
.venv/bin/python -m pytest
# 60 passed, 1 warning

.venv/bin/ruff check .
# All checks passed!

.venv/bin/alembic heads
# 20260706_0005 (head)

.venv/bin/alembic upgrade head
# Running upgrade 20260706_0004 -> 20260706_0005, add family invite code

.venv/bin/alembic current
# 20260706_0005 (head)
```

첫 `alembic upgrade head`는 sandbox DNS 제한으로 Supabase host를 해석하지 못해 실패했고, 네트워크 접근 권한으로 재실행해 성공했다. 실제 `DATABASE_URL`과 비밀번호는 기록하지 않았다.

### 프롬프트 변경 여부

AI 질문 생성, 답변 요약, 분석 프롬프트는 변경하지 않았다.

## 2026-07-06 역할 분기 3종 변경

### 요청 프롬프트 요약

기존에 역할을 자식/부모 2가지로 분기하던 구현을 자식/엄마/아빠 3가지로 바꾸고, 이에 맞춰 DB 테이블과 코드도 수정하며 수정 내역을 로그에 기록하도록 요청했다.

### 수정 파일

- `app/models/user.py`
- `app/models/family_member.py`
- `app/services/family_service.py`
- `alembic/versions/20260706_0006_split_parent_roles.py`
- `tests/test_models.py`
- `tests/test_onboarding_family.py`
- `docs/API_DRAFT.md`
- `docs/DB_SCHEMA.md`
- `docs/ERD.md`
- `docs/SCREEN_FLOW.md`
- `docs/PROMPT_LOG.md`

### 반영 내용

- `UserRole` enum을 `child`, `mother`, `father`로 변경했다.
- `FamilyMemberRole` enum도 가족방 내부 역할이 온보딩 역할과 같은 3가지 값을 쓰도록 `child`, `mother`, `father`로 변경했다.
- 가족 생성/합류 시 `users.role`을 `family_members.member_role` 초기값으로 저장하도록 `FamilyService` 매핑을 수정했다.
- 기존 DB에 이미 저장된 `parent` 값은 새 enum으로 이동할 때 `mother`로 보정한다. 기존 데이터만으로 엄마/아빠를 구분할 수 없기 때문이다.
- 기존에 이론상 존재하던 `family_members.member_role = member` 값은 MVP 3분기 정책에 맞춰 migration에서 `child`로 보정한다.
- downgrade 시 `mother`, `father`는 기존 스키마의 `parent`로 접는다.
- API/DB 문서와 화면 흐름 문서에서 역할 선택 값을 `child`, `mother`, `father`로 갱신했다.

### 검증 결과

```bash
pytest
# 61 passed, 1 warning

ruff check .
# All checks passed!

.venv/bin/alembic heads
# 20260706_0006 (head)

.venv/bin/alembic current
# 20260706_0005

.venv/bin/alembic upgrade head
# Running upgrade 20260706_0005 -> 20260706_0006, split parent roles into mother and father

.venv/bin/alembic current
# 20260706_0006 (head)
```

### 프롬프트 변경 여부

AI 질문 생성, 답변 요약, 분석 프롬프트는 변경하지 않았다.

## 2026-07-06 Damso 필수 동의 확인/저장 구현

### 요청 프롬프트 요약

Kakao 로그인 후 Damso access token을 발급받은 사용자가 온보딩에서 필수 동의 3개(`terms_of_service`, `privacy_policy`, `camera_microphone_notice`)를 완료했는지 조회하고 저장할 수 있도록 요청했다. Kakao Developers 동의항목과 Damso 자체 필수 동의를 구분하고, 선택 동의, 마케팅 동의, 동의 철회 기능은 MVP 범위에서 제외한다.

### 생성/수정 파일

- `app/api/dependencies.py`
- `app/api/v1/users.py`
- `app/main.py`
- `app/models/user.py`
- `app/models/user_agreement.py`
- `app/models/__init__.py`
- `app/schemas/users.py`
- `app/services/user_agreement_service.py`
- `alembic/versions/20260706_0004_create_user_agreements.py`
- `tests/test_user_agreements.py`
- `tests/test_models.py`
- `docs/API_DRAFT.md`
- `docs/DB_SCHEMA.md`
- `docs/PROMPT_LOG.md`

### 반영 내용

- `user_agreements` 테이블과 `agreement_type` enum을 추가했다.
- `user_id + agreement_type` unique index를 추가해 같은 항목이 중복 row로 저장되지 않도록 했다.
- `GET /api/v1/users/me/agreements`를 추가해 현재 access token 사용자 기준 필수 동의 상태를 조회한다.
- `POST /api/v1/users/me/agreements`를 추가해 현재 access token 사용자 기준 필수 동의를 저장한다.
- 동의 row가 없어도 필수 3개 항목은 `agreed = false`로 응답한다.
- 3개 필수 항목이 모두 `agreed = true`일 때 `requiredAgreementsCompleted = true`로 응답한다.
- 이미 동의된 항목을 `false`로 되돌리는 철회 동작은 MVP에서 구현하지 않았다.
- Kakao 로그인 로직, `.env`, 실제 비밀값은 변경하지 않았다.

### 검증 결과

```bash
.venv/bin/python -m pytest
# 48 passed, 1 warning

.venv/bin/ruff check .
# All checks passed!

.venv/bin/alembic heads
# 20260706_0004 (head)

.venv/bin/alembic upgrade head
# Running upgrade 20260705_0003 -> 20260706_0004, create user agreements

.venv/bin/alembic current
# 20260706_0004 (head)
```

첫 `alembic upgrade head`는 sandbox DNS 제한으로 Supabase host를 해석하지 못해 실패했고, 네트워크 접근 권한으로 재실행해 성공했다. 실제 `DATABASE_URL`과 비밀번호는 기록하지 않았다.

### 프롬프트 변경 여부

AI 질문 생성, 답변 요약, 분석 프롬프트는 변경하지 않았다.

## 2026-07-05 Kakao Profile Image 저장 반영

### 요청 프롬프트 요약

Damso 백엔드의 Kakao 로그인에서 Kakao userinfo의 profile image를 Damso 사용자 정보에 저장하도록 요청했다. `kakao_account.profile.profile_image_url`을 우선 사용하고, 없으면 `thumbnail_image_url`을 fallback으로 쓰며, 둘 다 없어도 로그인은 실패하지 않게 nullable로 처리한다. 신규 유저는 `users.profile_image_url`에 저장하고, 기존 유저는 값이 비어 있을 때만 채우며 이미 있으면 덮어쓰지 않는다.

### 생성/수정 파일

- `app/services/kakao_auth_service.py`
- `app/services/kakao_login_service.py`
- `app/models/user.py`
- `alembic/versions/20260705_0003_add_user_profile_image_url.py`
- `tests/test_kakao_auth_service.py`
- `tests/test_kakao_login_service.py`
- `tests/test_models.py`
- `docs/API_DRAFT.md`
- `docs/DB_SCHEMA.md`
- `docs/ERD.md`
- `docs/PROMPT_LOG.md`

### 반영 내용

- Kakao userinfo 파싱에서 `profile_image_url`을 우선 읽고, 값이 없으면 `thumbnail_image_url`을 fallback으로 사용한다.
- `users.profile_image_url` nullable `TEXT` 컬럼을 추가했다.
- 신규 Kakao 로그인 사용자는 `users.profile_image_url`에 Kakao profile image URL을 저장한다.
- 기존 사용자는 `users.profile_image_url`이 비어 있을 때만 새 Kakao profile image URL로 채운다.
- 기존 값이 이미 있으면 MVP 정책상 덮어쓰지 않는다.
- Kakao access token 전달/저장 정책과 `.env`는 변경하지 않았다.

### 검증 결과

```bash
.venv/bin/python -m pytest
# 42 passed, 1 warning

.venv/bin/ruff check .
# All checks passed!

.venv/bin/alembic heads
# 20260705_0003 (head)

.venv/bin/alembic upgrade head
# Running upgrade 20260705_0002 -> 20260705_0003, add user profile image url
```

첫 `alembic upgrade head`는 sandbox DNS 제한으로 Supabase host를 해석하지 못해 실패했고, 네트워크 접근 권한으로 재실행해 성공했다. 실제 `DATABASE_URL`과 비밀번호는 기록하지 않았다.

### 프롬프트 변경 여부

AI 질문 생성, 답변 요약, 분석 프롬프트는 변경하지 않았다.

## 2026-07-05 인증/온보딩 MVP 초기 DB 모델과 Migration 구현

### 요청 프롬프트 요약

Supabase PostgreSQL 연결 설정이 완료된 Damso 백엔드에 인증/온보딩 MVP에 필요한 초기 DB 모델과 Alembic migration을 구현하도록 요청했다. 범위는 `users`, `social_accounts`, `oauth_login_codes`, `families`, `family_members`이며, Kakao access token과 raw `login_code`는 저장하지 않고, 질문/답변/다이어리/회고록 테이블은 만들지 않는다.

### 생성/수정 파일

- `app/models/family.py`
- `app/models/family_member.py`
- `app/models/user.py`
- `app/models/__init__.py`
- `alembic/versions/20260705_0002_create_family_tables.py`
- `tests/test_models.py`
- `docs/API_DRAFT.md`
- `docs/DB_SCHEMA.md`
- `docs/PROMPT_LOG.md`

### 반영 내용

- 기존 `users`, `social_accounts`, `oauth_login_codes` 모델과 migration은 유지했다.
- `families` 모델을 추가하고 `public_id`, `name`, `created_by_user_id`, `status`, `created_at`, `updated_at`, `deleted_at`을 정의했다.
- `family_members` 모델을 추가하고 `family_id`, `user_id`, `member_role`, `status`, `joined_at`, `created_at`, `updated_at`을 정의했다.
- `family_status`, `family_member_role`, `family_member_status` enum을 추가했다.
- `families.public_id`, `family_members(family_id, user_id)` unique index와 조회용 index를 추가했다.
- `20260705_0002_create_family_tables.py` migration을 추가했다.

### 검증 결과

```bash
.venv/bin/python -m pytest
# 37 passed, 1 warning

.venv/bin/ruff check .
# All checks passed!

.venv/bin/alembic heads
# 20260705_0002 (head)

.venv/bin/alembic upgrade head
# Running upgrade  -> 20260705_0001, create kakao auth tables
# Running upgrade 20260705_0001 -> 20260705_0002, create family tables
```

첫 `alembic upgrade head`는 sandbox DNS 제한으로 Supabase host를 해석하지 못해 실패했고, 네트워크 접근 권한으로 재실행해 성공했다. 실제 `DATABASE_URL`과 비밀번호는 기록하지 않았다.

### 프롬프트 변경 여부

AI 질문 생성, 답변 요약, 분석 프롬프트는 변경하지 않았다.

## 2026-07-05 Supabase PostgreSQL 연결 설정 반영

### 요청 프롬프트 요약

Damso FastAPI 백엔드에서 Supabase PostgreSQL에 sync SQLAlchemy + `psycopg` 방식으로 연결할 수 있도록 설정을 정리하도록 요청했다. 실제 `DATABASE_URL`은 로컬 `.env`에만 반영하고, 문서와 예시 파일에는 placeholder 또는 마스킹된 값만 남기도록 했다.

### 생성/수정 파일

- `app/db/__init__.py`
- `app/db/session.py`
- `app/core/database.py`
- `app/models/__init__.py`
- `app/models/user.py`
- `app/models/social_account.py`
- `app/models/oauth_login_code.py`
- `app/api/v1/auth.py`
- `.env.example`
- `.env`
- `README.md`
- `docs/PROMPT_LOG.md`

### 반영 내용

- `app/db/session.py`에 sync SQLAlchemy 기반 `create_engine`, `Session`, `sessionmaker`, `get_db`, `Base = DeclarativeBase` 구성을 추가했다.
- `DATABASE_URL`이 없으면 `RuntimeError("DATABASE_URL is not configured")`를 발생시킨다.
- 기존 `app/core/database.py`는 기존 import 호환을 위해 `app.db.session` 재수출 모듈로 정리했다.
- `.env.example`의 `DATABASE_URL`은 `postgresql+psycopg://` 형식의 placeholder로 유지했다.
- 로컬 `.env`에는 실제 Supabase `DATABASE_URL`을 반영했다.
- `.gitignore`와 `.dockerignore`에 `.env`와 `.env.*`가 포함되어 있음을 확인했다.
- Dockerfile은 Cloud Run 호환을 위해 `EXPOSE 8080`, `--port ${PORT:-8080}` 설정을 유지한다.
- `requirements.txt`는 `psycopg[binary]`, SQLAlchemy, Alembic을 유지하고 `asyncpg`가 없음을 확인했다.

### DATABASE_URL 기록 형식

```env
DATABASE_URL=postgresql+psycopg://postgres.<project-ref>:<password>@aws-0-ap-northeast-1.pooler.supabase.com:5432/postgres
```

### 프롬프트 변경 여부

AI 질문 생성, 답변 요약, 분석 프롬프트는 변경하지 않았다.

## 2026-07-03 Initial Backend Setup

### 요청 프롬프트 요약

Damso(담소) 백엔드 전용 레포 초기세팅을 요청했다. 루트에 `app/`, `tests/`, `docs/`, `.agents/skills/damso-backend/SKILL.md`, `AGENTS.md`를 두고, FastAPI 기반 `/health` API와 환경 설정, 테스트, Docker, ruff, pytest 설정을 만든다. `backend/` 폴더, 프론트엔드 코드, DB 모델, Alembic migration, 실제 `.env`, 실제 비밀값은 만들지 않는다.

### 생성 파일

- `app/__init__.py`
- `app/main.py`
- `app/core/__init__.py`
- `app/core/config.py`
- `tests/test_health.py`
- `docs/MVP_SCOPE.md`
- `docs/SCREEN_FLOW.md`
- `docs/API_DRAFT.md`
- `docs/PROMPT_LOG.md`
- `.agents/skills/damso-backend/SKILL.md`
- `AGENTS.md`
- `.env.example`
- `.gitignore`
- `.dockerignore`
- `Dockerfile`
- `requirements.txt`
- `requirements-dev.txt`
- `pyproject.toml`
- `README.md`

### 사람이 검토할 내용

- MVP 화면 흐름이 실제 Figma와 일치하는지 확인한다.
- `docs/API_DRAFT.md`의 엔드포인트 명칭과 리소스 경계를 확정한다.
- Supabase 연결 방식, 인증 토큰 정책, 파일 업로드 저장소 정책을 확정한다.
- ERD 확정 후 SQLAlchemy 모델과 Alembic migration을 작성한다.
- OpenAI 질문 생성/요약/분석 프롬프트는 실제 기능 구현 시 별도 기록한다.

### 검증 명령어

```bash
python -m pip install -r requirements-dev.txt
pytest
ruff check .
```

## 2026-07-04 Kakao Login Skill 검증

### 요청 프롬프트 요약

Damso 백엔드 레포에 추가한 `.agents/skills/implementing-kakao-login/SKILL.md`를 공식 `quick_validate.py`로 검증하기 위해 PyYAML을 설치하되, 프로젝트 의존성에는 추가하지 않고 검증용으로만 사용하도록 요청했다.

### Verification

- 검증용 임시 venv: `/private/tmp/damso-skill-validate-venv`
- 검증용 패키지: `PyYAML 6.0.3`
- 프로젝트 의존성 파일에는 PyYAML을 추가하지 않았다.
- 공식 Skill 검증 통과:

```bash
/private/tmp/damso-skill-validate-venv/bin/python /Users/eun07213/.codex/skills/.system/skill-creator/scripts/quick_validate.py .agents/skills/implementing-kakao-login
# Skill is valid!
```

### 프롬프트 변경 여부

AI 질문 생성, 답변 요약, 분석 프롬프트는 변경하지 않았다.

## 2026-07-05 Kakao Callback 실제 로그인 흐름 통합

### 요청 프롬프트 요약

`implementing-kakao-login` Skill을 사용해 Kakao callback을 실제 Damso 로그인 흐름으로 통합하도록 요청했다. 먼저 `AGENTS.md`, `docs/API_DRAFT.md`, `docs/DB_SCHEMA.md`, `.agents/skills/implementing-kakao-login/SKILL.md`만 확인한 뒤, callback에서 authorization code를 Kakao token/userinfo API로 처리하고, `social_accounts` 기준으로 사용자를 찾거나 생성하며, one-time `login_code`만 프론트 redirect URL에 붙인다. Kakao access token과 Damso access token은 redirect query나 DB에 저장하지 않고, state 저장/검증은 TODO로 유지한다.

### 생성/수정 파일

- `app/api/v1/auth.py`
- `app/services/kakao_login_service.py`
- `tests/test_auth.py`
- `tests/test_kakao_login_service.py`
- `docs/API_DRAFT.md`
- `docs/PROMPT_LOG.md`

### 반영 내용

- `KakaoLoginService`를 추가해 callback 비즈니스 로직을 route handler에서 분리했다.
- Callback에서 `KakaoAuthService.exchange_code_for_token`, `get_user_info`를 호출하도록 연결했다.
- `provider = kakao`, `provider_user_id = kakao_id` 기준으로 기존 `social_accounts`를 조회한다.
- 기존 계정이 없으면 `users`, `social_accounts`를 생성한다.
- `LoginCodeService`로 one-time `login_code`를 생성하고, 프론트 callback URL에는 `loginCode`만 붙여 `302` redirect한다.
- Kakao access token은 DB, 응답, redirect URL에 포함하지 않는다.
- Damso access token도 redirect URL query에 포함하지 않는다.
- `state` 저장/검증은 아직 TODO로 유지했다.

### 사람이 확인할 포인트

- `FRONTEND_OAUTH_CALLBACK_URL`이 실제 프론트 OAuth callback 경로와 일치해야 한다.
- `state` server-side 저장/검증은 다음 보안 고도화 작업에서 구현해야 한다.
- 신규 사용자 `public_id` 생성 정책은 현재 token 기반 최소 구현이며, 운영 정책에 맞춘 충돌 처리/형식 확정이 필요할 수 있다.
- Kakao userinfo 동의항목에 따라 nickname, email, profile image가 nullable일 수 있다.

### 검증 결과

```bash
.venv/bin/python -m pytest
# 35 passed, 1 warning

.venv/bin/ruff check .
# All checks passed!
```

### 프롬프트 변경 여부

AI 질문 생성, 답변 요약, 분석 프롬프트는 변경하지 않았다.

## 2026-07-05 Damso Access Token과 Login Code Exchange 구현

### 요청 프롬프트 요약

`implementing-kakao-login` Skill을 사용해 Damso 자체 access token 발급과 one-time `login_code` 교환 서비스를 구현하도록 요청했다. 먼저 `AGENTS.md`, `docs/API_DRAFT.md`, `docs/DB_SCHEMA.md`, `.agents/skills/implementing-kakao-login/SKILL.md`만 확인한 뒤, JWT 유틸, `LoginCodeService`, `POST /api/v1/auth/login-code/exchange` API를 구현한다. Kakao callback 통합, KakaoAuthService와 사용자 생성/조회 연결, refresh token, logout, 실제 `.env`, 실제 secret 값은 만들지 않는다.

### 생성/수정 파일

- `app/core/config.py`
- `app/core/security.py`
- `app/services/login_code_service.py`
- `app/schemas/auth.py`
- `app/api/v1/auth.py`
- `.env.example`
- `requirements.txt`
- `tests/test_config.py`
- `tests/test_login_code.py`
- `docs/API_DRAFT.md`
- `docs/PROMPT_LOG.md`

### 반영 내용

- `create_access_token`, `verify_access_token`을 추가했다.
- JWT payload는 `sub`, `provider`를 포함하고, `role`은 역할 선택 전 nullable/optional로 처리한다.
- `login_code`는 원문 저장 없이 HMAC-SHA256 기반 `code_hash`만 DB에 저장한다.
- `login_code` 기본 만료 시간은 `5`분으로 설정했다.
- 교환 성공 시 `oauth_login_codes.status = used`, `used_at`을 기록하고 Damso access token만 반환한다.
- 만료 코드와 재사용 코드는 실패 처리한다.
- Kakao access token은 반환하지 않고, access token을 redirect URL query로 전달하는 흐름도 만들지 않았다.

### 사람이 확인할 포인트

- 운영 환경에는 `JWT_SECRET_KEY`를 충분히 긴 secret으로 안전하게 주입해야 한다.
- access token 만료 시간과 `login_code` 만료 시간은 제품 보안 정책에 맞게 조정할 수 있다.
- 다음 단계에서 Kakao callback 처리와 Damso 사용자 생성/조회가 완료되면 `LoginCodeService.create_login_code`를 callback 흐름에 연결해야 한다.
- refresh token과 logout은 아직 구현하지 않았다.

### 검증 결과

```bash
.venv/bin/python -m pytest
# 30 passed, 1 warning

.venv/bin/ruff check .
# All checks passed!
```

### 프롬프트 변경 여부

AI 질문 생성, 답변 요약, 분석 프롬프트는 변경하지 않았다.

## 2026-07-05 Kakao 로그인 최소 DB 모델과 Migration 구현

### 요청 프롬프트 요약

`implementing-kakao-login` Skill을 사용해 Kakao 로그인에 필요한 최소 DB 모델과 Alembic migration을 구현하도록 요청했다. 먼저 `AGENTS.md`, `docs/DB_SCHEMA.md`, `docs/ERD.md`, `docs/API_DRAFT.md`, `.agents/skills/implementing-kakao-login/SKILL.md`만 확인한 뒤, `users`, `social_accounts`, `oauth_login_codes` 모델과 migration을 추가한다. Kakao access token과 refresh token은 저장하지 않고, raw `login_code` 대신 `code_hash`만 저장한다. family/question/answer 관련 테이블, callback 통합, login_code exchange API, 실제 DB 접속 테스트, 실제 `.env`는 만들지 않는다.

### 생성/수정 파일

- `app/core/database.py`
- `app/models/__init__.py`
- `app/models/user.py`
- `app/models/social_account.py`
- `app/models/oauth_login_code.py`
- `alembic.ini`
- `alembic/env.py`
- `alembic/script.py.mako`
- `alembic/versions/20260705_0001_create_kakao_auth_tables.py`
- `tests/test_models.py`
- `docs/DB_SCHEMA.md`
- `docs/PROMPT_LOG.md`

### 생성된 Migration

- `20260705_0001_create_kakao_auth_tables.py`

### 사람이 확인할 포인트

- 운영 환경의 `DATABASE_URL`은 실제 secret 관리 방식으로 주입해야 한다.
- 실제 DB/Supabase에 migration을 적용하기 전에 PostgreSQL 권한, schema, migration 실행 계정을 확인해야 한다.
- `public_id` 생성 정책과 `code_hash` 생성/검증 정책은 login flow 구현 시 별도 서비스에서 확정해야 한다.
- Kakao access token과 refresh token 저장 컬럼은 만들지 않았다.
- callback 통합, Damso 사용자 생성/조회 서비스, one-time `login_code` exchange API는 아직 구현하지 않았다.

### 검증 결과

```bash
.venv/bin/python -m pytest
# 22 passed, 1 warning

.venv/bin/ruff check .
# All checks passed!

.venv/bin/alembic heads
# 20260705_0001 (head)
```

### 프롬프트 변경 여부

AI 질문 생성, 답변 요약, 분석 프롬프트는 변경하지 않았다.

## 2026-07-05 KakaoAuthService 자체 코드 리뷰

### 요청 프롬프트 요약

방금 구현한 `KakaoAuthService` 작업을 코드 리뷰 관점에서 자체 검증하도록 요청했다. Kakao REST API endpoint, form-urlencoded token 요청, Bearer userinfo 요청, secret/token 노출 여부, `.env` 생성 여부, 에러 처리, mock 기반 테스트, route handler 분리, callback/DB/login_code 미구현 상태를 확인하고 필요한 수정은 최소 범위로 반영한다.

### 검토 결과와 수정 내용

- Kakao token endpoint와 userinfo endpoint, 요청 method/header/form payload가 요구사항과 일치함을 확인했다.
- route handler에는 외부 HTTP 호출 로직이 없고, callback 통합, DB 저장, `login_code` 교환은 아직 구현하지 않았음을 확인했다.
- 실제 `.env` 파일은 없고, 로그 출력 코드나 실제 secret 값은 추가되지 않았음을 확인했다.
- `id: null` userinfo 응답이 `str(None)`으로 통과할 수 있는 문제를 막기 위해 Kakao user id 검증을 보강했다.
- invalid JSON 응답 테스트와 nullable userinfo 필드 테스트를 보강했다.
- 테스트용 provider token 값은 실제 토큰처럼 보이지 않는 mock sentinel 값으로 정리했다.

### 수정 파일

- `app/services/kakao_auth_service.py`
- `tests/test_kakao_auth_service.py`
- `docs/PROMPT_LOG.md`

### 검증 결과

```bash
.venv/bin/python -m pytest
# 17 passed, 1 warning

.venv/bin/ruff check .
# All checks passed!
```

### 프롬프트 변경 여부

AI 질문 생성, 답변 요약, 분석 프롬프트는 변경하지 않았다.

## 2026-07-05 Kakao REST Provider Service 구현

### 요청 프롬프트 요약

`implementing-kakao-login` Skill을 사용해 Damso 백엔드에 Kakao REST API 호출 전용 Provider Service를 구현하도록 요청했다. `AGENTS.md`, `docs/API_DRAFT.md`, `docs/DB_SCHEMA.md`, `.agents/skills/implementing-kakao-login/SKILL.md`만 먼저 확인한 뒤, `KakaoAuthService`를 만들고 Kakao token 교환과 userinfo 조회를 `httpx.AsyncClient` 기반으로 구현한다. 실제 Kakao 서버 호출은 테스트에서 mock 처리하고, callback 통합, state 검증, `login_code` 교환, DB 모델과 migration은 만들지 않는다.

### 생성/수정 파일

- `app/services/__init__.py`
- `app/services/kakao_auth_service.py`
- `app/schemas/__init__.py`
- `app/schemas/auth.py`
- `tests/test_kakao_auth_service.py`
- `requirements.txt`
- `docs/API_DRAFT.md`
- `docs/PROMPT_LOG.md`

### 사람이 확인할 포인트

- 운영 환경의 `KAKAO_REST_API_KEY`, `KAKAO_CLIENT_SECRET`, `KAKAO_REDIRECT_URI`는 실제 secret 관리 방식으로 주입해야 한다.
- Kakao Developers에 등록된 Redirect URI와 `KAKAO_REDIRECT_URI`가 정확히 일치해야 한다.
- callback 라우터에는 아직 `KakaoAuthService`를 연결하지 않았다. 다음 단계에서 state 검증, Kakao token/userinfo 호출, Damso 사용자 조회/생성, one-time `login_code` 발급을 붙여야 한다.
- Kakao access token은 내부 DTO에서만 다루며 프론트 응답 스키마에 포함하지 않는다.
- Kakao SDK, DB 모델, SQLAlchemy 모델, Alembic migration은 추가하지 않았다.

### 검증 결과

```bash
.venv/bin/python -m pytest
# 14 passed, 1 warning

.venv/bin/ruff check .
# All checks passed!
```

### 프롬프트 변경 여부

AI 질문 생성, 답변 요약, 분석 프롬프트는 변경하지 않았다.

## 2026-07-04 Kakao OAuth 로그인 진입 흐름 구현

### 요청 프롬프트 요약

`implementing-kakao-login` Skill을 사용해 Damso 백엔드에 Kakao OAuth 로그인 진입 흐름을 구현하도록 요청했다. 먼저 `AGENTS.md`, `docs/API_DRAFT.md`, `docs/DB_SCHEMA.md`, `.agents/skills/implementing-kakao-login/SKILL.md`만 확인하고, Kakao OAuth 설정값, auth 라우터, `GET /api/v1/auth/kakao/login-url`, `GET /api/v1/auth/kakao/callback` 골격, 테스트, API 문서 갱신을 진행한다. Kakao token API 호출, Damso access token 발급, DB 조회/저장, `login_code` 교환, 프론트엔드 코드는 아직 만들지 않는다.

### 수정 파일

- `app/api/__init__.py`
- `app/api/v1/__init__.py`
- `app/api/v1/auth.py`
- `app/main.py`
- `docs/API_DRAFT.md`
- `docs/PROMPT_LOG.md`
- `tests/test_auth.py`

### 확인한 기존 파일

- `app/core/config.py`: Kakao OAuth 설정 필드가 이미 존재함을 확인했다.
- `.env.example`: Kakao OAuth placeholder가 이미 존재함을 확인했다.

### 사람이 확인할 포인트

- `KAKAO_REDIRECT_URI`가 Kakao Developers에 등록된 Redirect URI와 정확히 일치해야 한다.
- 현재 `state`는 생성해 응답과 Kakao authorize URL에 포함하지만 저장/검증은 TODO다.
- callback은 `code`와 `state` 수신만 하며, 다음 단계에서 `KakaoAuthService`로 token 교환과 userinfo 조회를 붙여야 한다.
- Kakao access token은 프론트에 반환하지 않았고, access token을 URL query로 전달하는 코드도 만들지 않았다.
- `login_code` 교환은 다음 단계에서 구현한다.

### 검증 결과

실제 DB 모델, SQLAlchemy 모델, Alembic migration은 만들지 않았다.

```bash
.venv/bin/python -m pytest
# 5 passed, 1 warning

.venv/bin/ruff check .
# All checks passed!
```

### 프롬프트 변경 여부

AI 질문 생성, 답변 요약, 분석 프롬프트는 변경하지 않았다.

## 2026-07-04 DB Schema v0.1 리뷰 반영

### 요청 프롬프트 요약

방금 작성한 `docs/DB_SCHEMA.md`를 리뷰 기준에 맞춰 수정하도록 요청했다. `ai_analyses`에 `transcript`, `highlight_quote`, `emotion_tags`를 추가하고, `diaries`가 MVP에서 꼭 필요한지 재검토해 답변 기록 목록이 `answers` 기반 조회로 충분하면 보류 테이블로 표시한다. `memoir_diaries` 대신 `memoir_items` 구조를 제안하고, `users.role`과 `family_members.member_role`의 중복 및 MVP 기준값을 정리한다. `answers.status`와 `ai_analyses.status`의 책임을 분리하고, 실제 migration은 만들지 않는다.

### 수정 파일

- `docs/DB_SCHEMA.md`
- `docs/PROMPT_LOG.md`

### 반영 내용

- `ai_analyses`에 `transcript`, `highlight_quote`, `emotion_tags` 컬럼 후보를 추가했다.
- `diaries`, `diary_answers`를 `deferred`로 표시하고, MVP 답변 기록 목록은 `answers -> question_sends.family_id`와 `ai_analyses` 조인으로 우선 처리할 수 있다고 정리했다.
- `memoir_diaries` 섹션을 `memoir_items`로 바꾸고 `source_type`, `answer_id`, `diary_id`, `sort_order` 구조를 제안했다.
- 가족방 내부 권한 판단은 `family_members.member_role`을 source of truth로 쓰고, `users.role`은 온보딩 기본 역할과 초기 멤버십 생성에만 쓰도록 정리했다.
- `answers.status`는 답변 자체의 제출/노출 상태, `ai_analyses.status`는 AI 분석 job 상태로 분리했다.

### 사람이 확인할 포인트

- 다이어리 목록/상세가 독립 큐레이션 기능인지, 답변 기록 목록의 표현인지 제품 관점에서 확정해야 한다.
- 회고록 source가 MVP에서 답변 기반이면 `memoir_items.source_type = answer`만 먼저 migration하고, `diary`는 다이어리 확정 후 열어도 된다.
- `emotion_tags`의 허용 값과 `highlight_quote` 생성 기준은 AI 분석 프롬프트 설계 시 확정해야 한다.
- 공유 링크가 보류된 다이어리를 직접 공유해야 하는지, 회고록 또는 답변 상세 공유로 충분한지 확정해야 한다.

### 검증 결과

실제 DB 모델, SQLAlchemy 모델, Alembic migration은 만들지 않았다.

```bash
ruby -e 'ARGV.each do |path| s=File.read(path); fences=s.scan(/^```/).size; abort "#{path}: unbalanced fences" unless fences.even?; puts "#{path}: markdown fences balanced (#{fences})"; end' docs/DB_SCHEMA.md docs/PROMPT_LOG.md
# docs/DB_SCHEMA.md: markdown fences balanced (0)
# docs/PROMPT_LOG.md: markdown fences balanced (10)
```

### 프롬프트 변경 여부

AI 질문 생성, 답변 요약, 분석 프롬프트 자체는 변경하지 않았고, 향후 확정할 AI 분석 결과 필드 후보만 DB 설계 문서에 추가했다.

## 2026-07-04 Kakao 로그인 설정값 추가

### 요청 프롬프트 요약

`implementing-kakao-login` Skill을 사용해 실제 로그인 API는 만들지 않고 Kakao 로그인 구현에 필요한 설정값만 추가하도록 요청했다. `app/core/config.py`에 Kakao 설정 필드를 추가하고, `.env.example`에는 placeholder만 넣으며, 실제 `.env`와 실제 키 값은 만들거나 기록하지 않는다. README에는 Kakao Redirect URI 설정 위치를 짧게 적고, `docs/API_DRAFT.md`에는 환경변수와 백엔드 callback 방식 개요를 추가한다.

### 수정 파일

- `app/core/config.py`
- `.env.example`
- `README.md`
- `docs/API_DRAFT.md`
- `docs/PROMPT_LOG.md`
- `tests/test_config.py`

### 사람이 확인할 포인트

- Kakao Developers 앱 설정의 Redirect URI가 `KAKAO_REDIRECT_URI`와 정확히 일치하는지 확인한다.
- 프론트 OAuth callback 경로가 `FRONTEND_OAUTH_CALLBACK_URL` placeholder와 같은 정책으로 확정되는지 확인한다.
- 운영 환경에는 실제 Kakao key와 secret을 안전한 secret 관리 방식으로 주입한다.
- Kakao access token을 프론트에 전달하지 않고 `login_code` 교환 방식을 우선 적용하는 정책을 실제 API 구현 시 유지한다.

### 검증 결과

초기 셸에서는 `pytest` 실행 파일이 없어 `.venv`의 도구로 검증했다.

```bash
.venv/bin/python -m pytest
# 2 passed, 1 warning

.venv/bin/ruff check .
# All checks passed!
```

### 프롬프트 변경 여부

AI 질문 생성, 답변 요약, 분석 프롬프트는 변경하지 않았다.

## 2026-07-04 Damso MVP ERD v0.1

### 요청 프롬프트 요약

`docs/MVP_SCOPE.md`, `docs/SCREEN_FLOW.md`, `docs/API_DRAFT.md`, `AGENTS.md`를 먼저 읽고 Damso MVP를 위한 ERD v0.1 문서를 작성하도록 요청했다. 실제 DB 모델, SQLAlchemy 모델, Alembic migration은 만들지 않고, Kakao 로그인, 사용자, 가족방, 구성원, 초대 코드, 질문, 답변, AI 분석, 다이어리, 회고록, 공유 링크를 포함한 문서 설계를 작성한다. 결제, 관리자, 공개 커뮤니티, 댓글, 좋아요, 팔로우, PDF 내보내기는 제외한다.

### 수정 파일

- `docs/ERD.md`
- `docs/DB_SCHEMA.md`
- `docs/PROMPT_LOG.md`

### 사람이 확인할 포인트

- `MVP_SCOPE.md`에서 공유 링크가 포함 기능과 제외 기능에 동시에 적혀 있어 실제 MVP 포함 여부를 확정해야 한다.
- `docs/API_DRAFT.md`에는 공유 링크 API가 아직 없으므로, 공유 링크를 MVP에 유지한다면 API 초안에 `share-links` 엔드포인트를 추가하는 것이 자연스럽다.
- 외부 API path parameter에 내부 `BIGINT id` 대신 `public_id`를 사용할지 확정해야 한다.
- 질문 기본 데이터가 전역 seed인지, 가족별 질문 사본인지 확정해야 한다.
- 답변 제출에서 텍스트와 영상 중 하나만 필수인지, 둘 다 허용인지 확정해야 한다.
- 공유/초대 raw code를 DB에 저장하지 않고 hash만 저장하는 정책이 제품 요구와 맞는지 확인해야 한다.

### 검증 결과

실제 DB 모델, SQLAlchemy 모델, Alembic migration은 만들지 않았다.

```bash
ruby -e 'ARGV.each do |path| s=File.read(path); fences=s.scan(/^```/).size; abort "#{path}: unbalanced fences" unless fences.even?; puts "#{path}: markdown fences balanced (#{fences})"; end' docs/ERD.md docs/DB_SCHEMA.md docs/PROMPT_LOG.md
# docs/ERD.md: markdown fences balanced (2)
# docs/DB_SCHEMA.md: markdown fences balanced (0)
# docs/PROMPT_LOG.md: markdown fences balanced (8)

ruby -e 's=File.read(%q(docs/ERD.md)); m=s.match(/^```mermaid\n(.*?)^```/m); abort %q(no mermaid block) unless m; d=m[1]; abort %q(no erDiagram) unless d.include?(%q(erDiagram)); opens=d.scan(/\{\s*$/).size; closes=d.scan(/^\s*\}/).size; abort "entity brace mismatch #{opens}/#{closes}" unless opens == closes; bad=d.lines.grep(/--/).reject { |line| line =~ /^\s*[A-Z_]+\s+\|[|o]\s*--\s*[o|][{|]\s+[A-Z_]+\s+:\s+[A-Za-z_]+\s*$/ }; abort "bad relationship line: #{bad.first}" unless bad.empty?; puts "docs/ERD.md: mermaid erDiagram structure looks valid (#{opens} entities)"'
# docs/ERD.md: mermaid erDiagram structure looks valid (15 entities)
```

`mmdc` Mermaid CLI는 설치돼 있지 않아 이미지 렌더링 검증은 수행하지 못했다.

### 프롬프트 변경 여부

AI 질문 생성, 답변 요약, 분석 프롬프트는 변경하지 않았다.

## 2026-07-05 다이어리/회고록/공유 링크 제거, VideoClip 도메인 도입

### 요청 프롬프트 요약

도메인 구조를 `Auth → Family → Question → Answer → Diary → Share(MVP 보류)`에서 `Auth → Family → Question → Answer → VideoClip`으로 바꾸도록 요청했다. `diary_entries`, `memoirs`, `memoir_diaries`, `share_links`, `ai_analyses`, `diary_answers`, `diaries` 테이블을 전부 제거하고, `answers`에 `family_id`와 영상 메타데이터 컬럼(`video_origin_url`, `video_mime_type`, `video_duration_seconds`, `video_size_bytes`, `submitted_at`)을 반영하며, `video_clips` 테이블(썸네일, HLS URL, 전사, 제목, 명대사, 요약, 감정 태그)을 신규 추가하도록 요청했다. 영상 원본과 가공본을 분리 저장하고, 네컷 그리드 목록은 별도 테이블 없이 `answers`를 `family_id`, `DATE(created_at)` 기준 `GROUP BY`로 조회하도록 결정했다. MVP 핵심 흐름은 `... → AI 처리 → 네컷 그리드 → 컷 탭 → 바텀시트/상세(영상 재생 + 명대사 + 요약)`로 바뀌었고, 제외 항목에는 공유 링크(`/s/:shareSlug`)가 남는다. `API_DRAFT.md`, `DB_SCHEMA.md`, `ERD.md`, `MVP_SCOPE.md`, `SCREEN_FLOW.md`를 순서대로 하나씩 수정했다.

진행 중 `answers`의 FK 구조와 나머지 컬럼 처리에 대해 추가로 확인했다. `question_send_id`는 "누가 누구에게 언제 보냈는지" 추적이 필요하다는 이유로 `question_sends.id` 참조를 유지하기로 했고(명세의 `question_id` 표기는 이 관계의 축약 표현으로 해석), `family_id`는 `question_sends.family_id`를 비정규화 복사해 네컷 그리드 조회 성능을 확보한다. `public_id`는 제거(answers 상세 조회 API가 더 이상 없음), `updated_at`은 유지, `text_answer`는 제거(영상 전용 정책)로 확정했다.

이어서 기획자 관점으로 "영상 촬영/업로드 → AI 처리 → 네컷 그리드 → 컷 탭 → 바텀시트" 구간을 점검하고 다음을 추가로 확정했다. `answer_status`는 `hidden`을 빼고 `submitted → processing → completed → failed` 4단계로만 반영한다. 영상 업로드 흐름에 실제 파일 업로드 API가 빠져 있어 `POST /api/v1/answers/upload-url`(presigned URL 발급)을 추가한다. 답변 상태 폴링 API는 만들지 않고, Supabase Realtime **Broadcast**(`family:{family_id}` 채널, `postgres_changes`로 원본 테이블을 직접 노출하지 않음)로 AI 처리 완료/실패를 알린다. `video_clips`는 여전히 별도 status 컬럼을 두지 않되, "row 존재 = `answers.status = completed`" 불변식을 문서에 명시하고, 백엔드가 `video_clips` insert와 `answers.status = completed` 업데이트를 같은 트랜잭션으로 처리해야 한다는 점을 못박았다. processing/failed 셀 UX는 프론트에서 결정하기로 하고, `video_clips` 편집 기능은 MVP에서 제외했다.

그리드-상세 연결은 다시 논의해서 방향을 바꿨다. 처음엔 `GET /api/v1/clips` 응답에 `answer_id`, `status`, `clip_id`, `thumbnail_url`을 함께 내려주고 상세는 `GET /api/v1/clips/{clip_id}`로 `video_clips`의 내부 PK로 조회하는 방식이었다. 영상 재녹화(제출 전 클라이언트 단계)와는 무관하고, `answer → AI 처리 → video_clip`이 파이프라인상 항상 1:1이며 클립 재처리(다중 버전)가 MVP 스코프 밖이라는 점을 확인한 뒤, 상세 조회를 `GET /api/v1/answers/{answer_id}/clip`으로 통일하고 `clip_id`는 API에서 완전히 제거했다. 그리드 응답도 `answer_id`, `status`, `thumbnail_url`만 남겼고, Realtime broadcast payload에서도 `clip_id`를 뺐다. 이 변경으로 프론트가 화면 전체(그리드 → 탭 → 상세 → Realtime 이벤트)에서 `answer_id` 하나만 다루면 되고, `video_clips`의 내부 PK를 API로 노출하지 않아도 된다. 다만 나중에 답변 하나에 클립을 여러 버전으로 재처리하는 기능이 생기면 그때는 클립 자체를 가리키는 식별자가 다시 필요해질 수 있다.

### 수정 파일

- `docs/API_DRAFT.md`
- `docs/DB_SCHEMA.md`
- `docs/ERD.md`
- `docs/MVP_SCOPE.md`
- `docs/SCREEN_FLOW.md`
- `docs/PROMPT_LOG.md`

### 반영 내용

- `API_DRAFT.md`: `Answers`는 `POST /api/v1/answers`(영상 원본 등록)만 남기고, `Diaries`/`Memoirs`/AI 분석 엔드포인트를 제거한 뒤 `Clips` 섹션(`GET /api/v1/clips`, `GET /api/v1/clips/{clip_id}`)을 추가했다. 이후 `POST /api/v1/answers/upload-url`을 추가하고, Broadcast 채널/payload/트랜잭션 순서를 설명하는 `Realtime` 섹션을 신규 추가했다. 최종적으로 상세 조회를 `GET /api/v1/answers/{answer_id}/clip`으로 옮기고, `GET /api/v1/clips` 응답과 Realtime payload에서 `clip_id`를 제거해 `answer_id` 기준으로 통일했다.
- `DB_SCHEMA.md`: `diaries`, `diary_answers`, `memoirs`, `memoir_items`, `share_links`, `ai_analyses` 테이블과 관련 ENUM(`analysis_status`, `diary_status`, `generation_status`, `memoir_item_source_type`, `share_target_type`, `share_permission_scope`, `share_link_status`)을 제거했다. `answers`를 `question_send_id` + `user_id` + `family_id` + 영상 메타데이터 구조로 재정의하고 `video_clips` 테이블을 신규 추가했다. Global Rules와 TODO도 새 구조에 맞게 정리했다. 이후 `answer_status`를 `submitted`/`processing`/`completed`/`failed` 4단계로 확정하고, `video_clips` 무상태 불변식과 트랜잭션 순서, Realtime Broadcast 알림 방식을 Global Rules에 추가했다.
- `ERD.md`: mermaid erDiagram에서 `AI_ANALYSES`/`DIARIES`/`DIARY_ANSWERS`/`MEMOIRS`/`MEMOIR_DIARIES`/`SHARE_LINKS`를 제거하고 `VIDEO_CLIPS`를 추가했다. Scope, Design Principles, Entity Relationships, Deletion and Status Strategy, API Draft Notes 서술도 함께 갱신했다. 이후 Deletion and Status Strategy의 답변 상태 서술을 4단계로 갱신했다.
- `MVP_SCOPE.md`: 서비스 목적·사용자·포함 기능을 영상 클립 중심으로 수정하고, 제외 기능의 "공유 링크"에 `/s/:shareSlug` 경로를 표기했다(중복 추가 없이 기존 항목 보강). 구현 순서 6~7단계를 AI 질문 생성 / 영상 AI 가공·네컷 그리드·클립 상세 API로 바꿨다.
- `SCREEN_FLOW.md`: "AI 분석 상태", "다이어리 목록/상세", "회고록 결과", "공유 링크" 화면을 "네컷 그리드", "컷 상세"로 교체하고, "답변 기록" 화면의 API 후보와 저장 데이터를 새 `answers` 구조에 맞게 수정했다.

### 사람이 확인할 포인트

- `answers.question_send_id`가 `question_sends.id`를 참조하는 구조를 유지하기로 했으므로, 향후 API 설계에서 답변 제출 시 `question_send_id`를 어떻게 클라이언트에 전달할지 확정해야 한다.
- 공유 링크(`/s/:shareSlug`)가 제외 기능으로 남아있는 것이 맞는지, 완전히 삭제할지 향후 재확인해야 한다.
- Supabase Realtime Broadcast 채널(`family:{family_id}`) 구독 권한(누가 어떤 채널을 구독할 수 있는지)을 실제 인증/인가 설계 시 확정해야 한다.
- 영상 업로드용 presigned URL 발급 시 실제 storage 공급자(Supabase Storage 등)와 URL 만료 정책을 확정해야 한다.

### 검증 결과

실제 DB 모델, SQLAlchemy 모델, Alembic migration은 만들지 않았다.

```bash
ruby -e 'ARGV.each do |path| s=File.read(path); fences=s.scan(/^```/).size; abort "#{path}: unbalanced fences" unless fences.even?; puts "#{path}: markdown fences balanced (#{fences})"; end' docs/API_DRAFT.md docs/DB_SCHEMA.md docs/ERD.md docs/MVP_SCOPE.md docs/SCREEN_FLOW.md
# docs/API_DRAFT.md: markdown fences balanced (6)
# docs/DB_SCHEMA.md: markdown fences balanced (0)
# docs/ERD.md: markdown fences balanced (2)
# docs/MVP_SCOPE.md: markdown fences balanced (0)
# docs/SCREEN_FLOW.md: markdown fences balanced (0)

ruby -e 's=File.read(%q(docs/ERD.md)); m=s.match(/^```mermaid\n(.*?)^```/m); abort %q(no mermaid block) unless m; d=m[1]; abort %q(no erDiagram) unless d.include?(%q(erDiagram)); opens=d.scan(/\{\s*$/).size; closes=d.scan(/^\s*\}/).size; abort "entity brace mismatch #{opens}/#{closes}" unless opens == closes; puts "docs/ERD.md: mermaid erDiagram structure looks valid (#{opens} entities)"'
# docs/ERD.md: mermaid erDiagram structure looks valid (10 entities)

grep -rn "diary\|diaries\|memoir\|ai_analys\|share_link\|share-link\|hidden" docs/API_DRAFT.md docs/DB_SCHEMA.md docs/ERD.md docs/MVP_SCOPE.md docs/SCREEN_FLOW.md
# (결과 없음, 제거 대상 키워드 및 answer_status의 hidden 잔여 참조 없음 확인)

grep -rn "clips/{clip_id}" docs/API_DRAFT.md docs/DB_SCHEMA.md docs/ERD.md docs/MVP_SCOPE.md docs/SCREEN_FLOW.md
# (결과 없음, 상세 조회 경로가 GET /api/v1/answers/{answer_id}/clip으로 통일됐는지 확인)
```

### 프롬프트 변경 여부

AI 질문 생성, 답변 요약, 분석 프롬프트는 변경하지 않았다.
