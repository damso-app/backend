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

### CORS

로컬 프론트 개발 서버에서 백엔드를 호출하려면 `CORS_ORIGINS`에 허용할 origin을 comma-separated 값으로 등록한다.

```env
CORS_ORIGINS="http://localhost:3000,http://localhost:3001"
```

프론트 배포 URL이 생기면 Cloud Run 환경변수의 같은 값에 배포 origin을 추가한다. `allow_credentials`를 사용하므로 wildcard origin(`*`)은 사용하지 않는다.

### Supabase PostgreSQL

백엔드는 sync SQLAlchemy와 `psycopg` 드라이버로 Supabase PostgreSQL에 연결한다. 로컬 개발에서는 `.env`에 Supabase pooler 기반 `DATABASE_URL`을 넣는다.

```env
DATABASE_URL="postgresql+psycopg://postgres.your-project-ref:your-db-password@aws-your-region.pooler.supabase.com:5432/postgres"
```

Cloud Run 배포에서는 `.env` 파일을 이미지에 포함하지 말고, 같은 `DATABASE_URL` 값을 Cloud Run 환경변수 또는 secret 관리 방식으로 등록한다. 실제 비밀번호, JWT secret, API key는 문서나 커밋 대상 파일에 기록하지 않는다.

Kakao Redirect URI는 Kakao Developers 앱 설정에 백엔드 callback 주소
`KAKAO_REDIRECT_URI` 값과 동일하게 등록한다.

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
docker run --rm -p 8080:8080 --env-file .env damso-backend
```

`.env`에는 실제 운영 비밀값을 넣지 말고, 배포 환경에서는 안전한 secret 관리 방식을 사용한다.
