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
