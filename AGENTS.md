# Damso Backend Agent Guide

이 레포는 Damso(담소) 백엔드 전용 레포다. 프론트엔드는 별도 레포에서 관리하므로 `backend/` 폴더나 프론트엔드 코드를 만들지 않는다.

## Architecture Rules

- FastAPI route handler는 얇게 유지하고, 비즈니스 로직은 `services` 계층에 둔다.
- 설정과 환경변수 관리는 `app/core/config.py`에 둔다.
- 버전이 있는 API는 `/api/v1` prefix를 사용한다.
- `/health`는 배포와 모니터링을 위해 prefix 없이 둔다.
- DB 테이블, SQLAlchemy 모델, Alembic migration은 ERD가 확정된 뒤 만든다.

## Security Rules

- API key, Supabase key, JWT secret 같은 비밀값을 하드코딩하지 않는다.
- 실제 `.env` 파일을 만들거나 커밋하지 않는다.
- `.env.example`에는 placeholder만 둔다.

## Documentation Rules

- 기능을 구현하거나 API 계약을 바꾸면 `docs/API_DRAFT.md`를 갱신한다.
- AI 질문 생성, 답변 요약, 분석 프롬프트를 추가하거나 수정하면 `docs/PROMPT_LOG.md`를 갱신한다.
- MVP에 없는 기능을 임의로 추가하지 않는다.
