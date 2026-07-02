# Damso Backend

Damso(담소)는 자녀가 부모님에게 AI 인터뷰 질문을 보내고, 부모님의 답변을 가족 다이어리와 회고록으로 기록하는 웹앱이다. 이 레포는 백엔드 전용 레포이며 프론트엔드는 별도 레포에서 관리한다.

## Stack

- Python
- FastAPI
- PostgreSQL via Supabase
- SQLAlchemy
- Alembic
- Pydantic Settings
- pytest
- ruff
- Docker

## Local Setup

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
```

실제 환경변수는 `.env`에 두되, `.env`는 커밋하지 않는다. 필요한 키 이름은 `.env.example`을 참고한다.

## Run

```bash
uvicorn app.main:app --reload
```

헬스 체크:

```bash
curl http://127.0.0.1:8000/health
```

응답:

```json
{
  "status": "ok"
}
```

## Test

```bash
pytest
ruff check .
```

## Docker

```bash
docker build -t damso-backend .
docker run --rm -p 8000:8000 --env-file .env damso-backend
```

`.env`에는 실제 운영 비밀값을 넣지 말고, 배포 환경에서는 안전한 secret 관리 방식을 사용한다.
