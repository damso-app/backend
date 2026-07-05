# Damso API Draft

## 공통 규칙

- API v1 prefix는 `/api/v1`을 사용한다.
- `/health`는 배포와 모니터링을 위해 prefix 없이 둔다.
- 인증, 권한, 에러 응답 형식은 본격 구현 전에 별도 확정한다.
- DB 스키마와 모델은 ERD 확정 후 작성한다.

## 데이터 모델 참고

인증/온보딩 MVP의 초기 DB 모델은 다음 테이블을 기준으로 한다.

- `users`: Damso 내부 사용자. 외부 노출에는 내부 `id` 대신 `public_id`를 사용한다.
- `social_accounts`: Kakao OAuth 계정 연결 정보. `provider + provider_user_id` 조합은 unique이며 Kakao access token은 저장하지 않는다.
- `oauth_login_codes`: Kakao callback 이후 one-time `login_code` 교환을 위한 저장소. raw `login_code`는 저장하지 않고 `code_hash`만 저장한다.
- `families`: 가족방. 외부 노출에는 내부 `id` 대신 `public_id`를 사용한다.
- `family_members`: 사용자와 가족방의 연결, 가족 내 역할, 합류 상태를 저장한다.

질문, 답변, 영상 클립 테이블은 이번 인증/온보딩 초기 migration 범위에 포함하지 않는다.

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
- `POST /api/v1/auth/login-code/exchange`: one-time `login_code`를 Damso access token으로 교환.
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

Kakao OAuth callback을 수신하고 Damso 로그인 흐름을 완료한다.

Query parameters:

- `code`: Kakao authorization code. 필수.
- `state`: login-url에서 생성한 state. 현재는 수신만 하고 검증은 TODO.

처리 흐름:

- 백엔드가 `code`를 Kakao token API로 교환한다.
- Kakao access token으로 Kakao userinfo API를 호출한다.
- `social_accounts.provider = kakao`, `provider_user_id = kakao_id` 기준으로 기존 사용자를 찾는다.
- 기존 소셜 계정이 없으면 `users`, `social_accounts`를 생성한다.
- one-time `login_code`를 생성하고 DB에는 `code_hash`만 저장한다.
- `FRONTEND_OAUTH_CALLBACK_URL`에 `loginCode` query parameter만 붙여 redirect한다.

Redirect 예시:

```http
302 Location: http://localhost:3000/oauth/kakao/callback?loginCode=one-time-login-code
```

`code`가 없으면 `400`을 반환한다. Kakao token 교환 또는 userinfo 조회가 실패하면 `502`를 반환한다. Kakao access token은 백엔드 내부에서만 사용하며 DB, 프론트 응답, redirect URL에 저장하거나 포함하지 않는다. Damso access token도 redirect URL query로 전달하지 않고, 프론트는 `POST /api/v1/auth/login-code/exchange`로 `loginCode`를 교환해야 한다.

현재 `state`는 수신하지만 서버 저장/검증은 아직 TODO다. 다음 보안 고도화 단계에서 server-side state 저장과 callback 검증을 붙인다.

### Kakao Login 설정

사용할 환경변수:

- `KAKAO_REST_API_KEY`: Kakao Developers REST API key.
- `KAKAO_CLIENT_SECRET`: Kakao client secret.
- `KAKAO_REDIRECT_URI`: Kakao Developers에 등록할 백엔드 callback URI.
- `FRONTEND_OAUTH_CALLBACK_URL`: 백엔드 callback 처리 후 프론트로 이동할 OAuth callback URL.

백엔드는 Kakao authorization code를 callback으로 받은 뒤 Kakao token/userinfo API를 서버에서 호출한다. Kakao access token은 프론트에 전달하지 않고, 최종 Damso access token 전달은 URL query 직접 전달 대신 `login_code` 교환 방식을 사용한다.

### Kakao REST Provider Service

`KakaoAuthService`는 Damso 내부 서비스 계층에서만 사용하는 Kakao REST API 호출 전용 Provider Service다.

- `exchange_code_for_token(code)`: `POST https://kauth.kakao.com/oauth/token`로 authorization code를 Kakao token 응답으로 교환한다. `client_secret`은 설정값이 있을 때만 요청에 포함한다.
- `get_user_info(kakao_access_token)`: `GET https://kapi.kakao.com/v2/user/me`로 Kakao 사용자 정보를 조회한다.

Kakao access token, client secret, REST API key는 프론트 응답에 포함하지 않고 로그로 남기지 않는다. Callback 엔드포인트는 이 Provider Service를 호출해 사용자 조회/생성과 `login_code` 발급을 진행한다. State 검증은 다음 보안 고도화 단계에서 구현한다.

### `POST /api/v1/auth/login-code/exchange`

Kakao callback 처리 후 발급될 one-time `login_code`를 Damso 자체 access token으로 교환한다.

요청:

```json
{
  "loginCode": "one-time-login-code"
}
```

응답:

```json
{
  "accessToken": "Damso access token",
  "tokenType": "bearer"
}
```

`login_code`는 서버에 원문으로 저장하지 않고 `oauth_login_codes.code_hash`로만 저장한다. 교환에 성공하면 해당 코드는 `used` 상태로 변경되어 재사용할 수 없다. 만료됐거나 이미 사용됐거나 존재하지 않는 `login_code`는 `400`을 반환한다.

Damso access token은 JWT이며 payload에는 최소 `sub`, `provider`가 포함된다. 사용자의 역할 선택 전에는 `role`이 없을 수 있다. Kakao access token은 이 응답에 포함하지 않고, Damso access token을 redirect URL query로 전달하지 않는다.

JWT 관련 환경변수:

- `JWT_SECRET_KEY`: Damso access token 서명과 `login_code` hash에 사용할 secret.
- `JWT_ALGORITHM`: JWT 서명 알고리즘. 기본값 `HS256`.
- `ACCESS_TOKEN_EXPIRE_MINUTES`: Damso access token 만료 시간. 기본값 `60`.
- `LOGIN_CODE_EXPIRE_MINUTES`: one-time `login_code` 만료 시간. 기본값 `5`.

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

- `POST /api/v1/answers/upload-url`: 영상 업로드용 presigned URL 발급.
- `POST /api/v1/answers`: 질문 답변 생성 (영상 1개 원본 메타데이터 등록). `upload-url`로 발급받은 경로에 업로드를 마친 뒤 `video_origin_url` 등을 등록한다.
- `GET /api/v1/answers/{answer_id}/clip`: 답변에 대한 영상 클립 상세 조회. 바텀시트 또는 상세에서 영상 재생, 명대사, 요약을 표시할 때 사용한다. `status = completed`가 아니면 클립이 아직 없다. `video_clips`의 내부 PK(`clip_id`)는 API에 노출하지 않고 `answer_id`로만 조회한다.

## Clips

- `GET /api/v1/clips`: 가족 + 날짜 단위 네컷 그리드 목록 조회. `family_id`, `DATE(created_at)` 기준으로 묶어서 반환하며, 각 항목에 `answer_id`, `status`(`submitted`/`processing`/`completed`/`failed`)와 `status = completed`일 때의 `thumbnail_url`을 포함한다.

## Realtime

- AI 처리 완료/실패는 별도 폴링 API 없이 Supabase Realtime **Broadcast**로 전달한다. 원본 `answers`/`video_clips` 테이블을 `postgres_changes`로 직접 구독하지 않는다. 내부 PK/FK(`question_send_id`, `family_id` 등)를 그대로 클라이언트에 노출하지 않기 위해서다.
- 채널: `family:{family_id}`
- 이벤트 payload: `answer_id`, `status`(`completed` 또는 `failed`), 성공 시 `thumbnail_url`. 상세는 `GET /api/v1/answers/{answer_id}/clip`으로 다시 조회한다.
- 백엔드는 `video_clips` insert와 `answers.status = completed` 업데이트를 같은 트랜잭션으로 처리한 뒤 broadcast를 보낸다. 순서가 바뀌면 그리드/클라이언트에는 `completed`로 보이는데 클립 상세 조회가 실패하는 순간이 생길 수 있다.
