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
