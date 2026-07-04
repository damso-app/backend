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
