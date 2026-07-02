# Damso API Draft

## 공통 규칙

- API v1 prefix는 `/api/v1`을 사용한다.
- `/health`는 배포와 모니터링을 위해 prefix 없이 둔다.
- 인증, 권한, 에러 응답 형식은 본격 구현 전에 별도 확정한다.
- DB 스키마와 모델은 ERD 확정 후 작성한다.

## Health

### `GET /health`

응답:

```json
{
  "status": "ok"
}
```

## Auth

- `GET /api/v1/auth/kakao/login-url`: 카카오 로그인 진입 URL 발급.
- `POST /api/v1/auth/kakao/callback`: 카카오 OAuth callback 처리.
- `POST /api/v1/auth/logout`: 현재 세션 또는 토큰 종료.

## Users

- `GET /api/v1/users/me`: 현재 사용자 조회.
- `PATCH /api/v1/users/me/role`: 자녀 또는 부모 역할 선택.
- `PATCH /api/v1/users/me`: 사용자 프로필 수정.

## Families

- `POST /api/v1/families`: 가족 생성.
- `GET /api/v1/families/me`: 내 가족 조회.
- `POST /api/v1/families/invite-code`: 가족 초대 코드 생성.
- `POST /api/v1/families/join`: 초대 코드로 가족 합류.
- `GET /api/v1/families/{family_id}/members`: 가족 구성원 조회.

## Questions

- `GET /api/v1/questions`: 질문 목록 조회.
- `GET /api/v1/questions/{question_id}`: 질문 상세 조회.
- `POST /api/v1/questions/generate`: AI 질문 후보 생성.
- `POST /api/v1/questions/send`: 부모님에게 질문 보내기.

## Answers

- `POST /api/v1/answers`: 질문 답변 생성.
- `GET /api/v1/answers/{answer_id}`: 답변 상세 조회.
- `GET /api/v1/answers/{answer_id}/analysis`: AI 분석 상태 조회.
- `POST /api/v1/answers/{answer_id}/analysis`: AI 분석 요청.

## Diaries

- `GET /api/v1/diaries`: 가족 다이어리 목록 조회.
- `GET /api/v1/diaries/{diary_id}`: 가족 다이어리 상세 조회.

## Memoirs

- `POST /api/v1/memoirs`: 회고록 생성 요청.
- `GET /api/v1/memoirs`: 회고록 목록 조회.
- `GET /api/v1/memoirs/{memoir_id}`: 회고록 상세 조회.
ruff check .

