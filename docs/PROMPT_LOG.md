# Prompt Log

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
