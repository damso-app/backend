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
- `GET /api/v1/auth/kakao/callback`: 카카오 OAuth callback 수신.
- `POST /api/v1/auth/logout`: 현재 세션 또는 토큰 종료.

### `GET /api/v1/auth/kakao/login-url`

Kakao authorize URL을 생성한다.

응답:

```json
{
  "loginUrl": "https://kauth.kakao.com/oauth/authorize?client_id=...&redirect_uri=...&response_type=code&state=...",
  "state": "generated-state"
}
```

현재 `state`는 URL과 응답에 포함하지만 서버 저장/검증은 아직 구현하지 않는다. 다음 단계에서 server-side state 저장과 callback 검증을 붙인다.

### `GET /api/v1/auth/kakao/callback`

Kakao OAuth callback을 수신한다.

Query parameters:

- `code`: Kakao authorization code. 필수.
- `state`: login-url에서 생성한 state. 현재는 수신만 하고 검증은 TODO.

응답:

```json
{
  "status": "received",
  "state": "generated-state"
}
```

`code`가 없으면 `400`을 반환한다. 이 엔드포인트는 아직 Kakao token API 호출, userinfo 조회, Damso access token 발급, DB 조회/저장을 수행하지 않는다. Kakao access token은 프론트에 반환하지 않으며, access token을 URL query로 전달하지 않는다. 다음 단계에서 `KakaoAuthService`와 `login_code` 교환 흐름을 붙인다.

### Kakao Login 설정

사용할 환경변수:

- `KAKAO_REST_API_KEY`: Kakao Developers REST API key.
- `KAKAO_CLIENT_SECRET`: Kakao client secret.
- `KAKAO_REDIRECT_URI`: Kakao Developers에 등록할 백엔드 callback URI.
- `FRONTEND_OAUTH_CALLBACK_URL`: 백엔드 callback 처리 후 프론트로 이동할 OAuth callback URL.

백엔드는 Kakao authorization code를 callback으로 받은 뒤 Kakao token/userinfo API를 서버에서 호출한다. Kakao access token은 프론트에 전달하지 않고, 최종 Damso access token 전달은 URL query 직접 전달 대신 `login_code` 교환 방식을 우선 고려한다.

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
