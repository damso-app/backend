# Damso API Draft

## 공통 규칙

- API v1 prefix는 `/api/v1`을 사용한다.
- `/health`는 배포와 모니터링을 위해 prefix 없이 둔다.
- 인증, 권한, 에러 응답 형식은 본격 구현 전에 별도 확정한다.
- DB 스키마와 모델은 ERD 확정 후 작성한다.

## 데이터 모델 참고

인증/온보딩 MVP의 초기 DB 모델은 다음 테이블을 기준으로 한다.

- `users`: Damso 내부 사용자. 외부 노출에는 내부 `id` 대신 `public_id`를 사용하며, Kakao profile image URL은 nullable `profile_image_url`에 저장한다.
- `social_accounts`: Kakao OAuth 계정 연결 정보. `provider + provider_user_id` 조합은 unique이며 Kakao access token은 저장하지 않는다.
- `oauth_login_codes`: Kakao callback 이후 one-time `login_code` 교환을 위한 저장소. raw `login_code`는 저장하지 않고 `code_hash`만 저장한다.
- `user_agreements`: Damso 자체 필수 동의 상태. Kakao Developers 동의항목과 별개이며, 온보딩 진행 여부 판단에 사용한다.
- `families`: 가족방. 외부 노출에는 내부 `id` 대신 `public_id`를 사용하며, MVP 초대코드는 `invite_code`에 저장한다.
- `family_members`: 사용자와 가족방의 연결, 가족 내 역할, 합류 상태를 저장한다.
- `question_recommendations`: depth별 추천 질문 seed를 저장한다.
- `question_sends`: 사용자가 가족 구성원에게 보낸 질문, 수신자의 읽음/답변 상태를 저장한다.

영상 답변 원본과 AI 영상 클립 테이블은 후속 기능에서 별도 구현한다.

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
- Kakao userinfo의 `kakao_account.profile.profile_image_url`을 사용자 프로필 이미지로 저장한다. 값이 없으면 `thumbnail_image_url`을 fallback으로 사용하고, 둘 다 없으면 nullable로 둔다.
- `social_accounts.provider = kakao`, `provider_user_id = kakao_id` 기준으로 기존 사용자를 찾는다.
- 기존 소셜 계정이 없으면 `users`, `social_accounts`를 생성한다. 신규 사용자는 Kakao profile image URL을 `users.profile_image_url`에 저장한다.
- 기존 사용자가 다시 로그인했을 때 `users.profile_image_url`이 비어 있으면 Kakao profile image URL로 채우고, 이미 값이 있으면 MVP에서는 덮어쓰지 않는다.
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
- `GET /api/v1/users/me/onboarding`: 내 온보딩 상태 조회.
- `GET /api/v1/users/me/agreements`: 내 필수 동의 상태 조회.
- `POST /api/v1/users/me/agreements`: 내 필수 동의 저장.
- `PATCH /api/v1/users/me/role`: 자식, 엄마, 아빠 역할 선택.
- `PATCH /api/v1/users/me`: 사용자 프로필 수정.

### `GET /api/v1/users/me/onboarding`

현재 access token 사용자 기준으로 온보딩 진행 상태를 조회한다.

Headers:

```http
Authorization: Bearer <Damso access token>
```

응답:

```json
{
  "userId": 1,
  "role": null,
  "requiredAgreementsCompleted": true,
  "familyId": null,
  "familyMemberRole": null,
  "familyConnected": false,
  "onboardingCompleted": false
}
```

`onboardingCompleted`는 필수 동의 완료, 역할 선택 완료, 가족 연결 완료가 모두 충족될 때 `true`다.

### `PATCH /api/v1/users/me/role`

현재 access token 사용자의 온보딩 역할을 저장한다. 역할은 `child`, `mother`, `father`만 허용한다. 필수 동의가 완료되지 않은 사용자는 `400`을 반환한다.

Headers:

```http
Authorization: Bearer <Damso access token>
```

요청:

```json
{
  "role": "child"
}
```

응답:

```json
{
  "userId": 1,
  "role": "child"
}
```

### Damso 필수 동의

Kakao Developers 동의항목과 별개로, Damso 서비스 이용을 위한 자체 필수 동의 3개를 관리한다.

필수 동의 타입:

- `terms_of_service`: 서비스 이용약관 동의. 질문, 영상 답변, 다이어리 저장 기능 이용.
- `privacy_policy`: 개인정보 처리 동의. 이름, 가족 연결, 질문, 영상, STT 텍스트 처리.
- `camera_microphone_notice`: 카메라·마이크 권한 안내. 영상 답변 촬영 시 브라우저 권한 요청 안내.

3개 항목이 모두 `agreed = true`일 때 `requiredAgreementsCompleted = true`로 판단한다. MVP에서는 선택 동의, 마케팅 동의, 동의 철회 기능을 제공하지 않는다.

### `GET /api/v1/users/me/agreements`

현재 access token 사용자 기준으로 필수 동의 상태를 조회한다.

Headers:

```http
Authorization: Bearer <Damso access token>
```

응답:

```json
{
  "requiredAgreementsCompleted": false,
  "agreements": [
    {
      "type": "terms_of_service",
      "agreed": false,
      "agreedAt": null
    },
    {
      "type": "privacy_policy",
      "agreed": false,
      "agreedAt": null
    },
    {
      "type": "camera_microphone_notice",
      "agreed": false,
      "agreedAt": null
    }
  ]
}
```

동의 row가 없어도 필수 3개 항목은 항상 응답에 포함하며, 없는 항목은 `agreed = false`, `agreedAt = null`로 반환한다.

### `POST /api/v1/users/me/agreements`

현재 access token 사용자 기준으로 필수 동의를 저장한다. 같은 항목을 다시 보내면 새 row를 만들지 않고 기존 row를 갱신한다. 이미 `agreed = true`인 항목은 MVP에서 `false`로 되돌리지 않는다.

Headers:

```http
Authorization: Bearer <Damso access token>
```

요청:

```json
{
  "agreements": [
    {
      "type": "terms_of_service",
      "agreed": true
    },
    {
      "type": "privacy_policy",
      "agreed": true
    },
    {
      "type": "camera_microphone_notice",
      "agreed": true
    }
  ]
}
```

응답:

```json
{
  "requiredAgreementsCompleted": true
}
```

## Families

- `POST /api/v1/families`: 가족 생성.
- `GET /api/v1/families/me/invitation`: 내 가족 초대정보 조회.
- `GET /api/v1/families/invitations/{invite_code}`: 초대코드 검증.
- `POST /api/v1/families/join`: 초대 코드로 가족 합류.
- `GET /api/v1/families/{family_id}/members`: 가족 구성원 조회.

### 가족 연결 MVP 정책

- 사용자는 MVP 기준 하나의 활성 가족에만 속할 수 있다.
- 필수 동의가 완료되지 않은 사용자의 가족 생성, 초대정보 조회, 초대코드 검증, 가족 참여는 `400`을 반환한다.
- 역할 선택 전 가족 생성 또는 가족 참여는 `400`을 반환한다.
- 이미 가족에 속한 사용자가 가족을 생성하거나 join하면 `409`를 반환한다.
- 가족 생성자와 초대코드 참여자는 온보딩에서 선택한 `users.role`과 같은 값으로 `family_members.member_role`에 저장한다.
- `mother`, `father` 역할 사용자가 초대코드로 참여하면 각각 `family_members.member_role = mother`, `family_members.member_role = father`로 저장한다.
- 존재하지 않거나 비활성/삭제된 가족의 초대코드는 `404`를 반환한다.
- 백엔드는 초대코드와 invite URL만 제공하며, 카카오톡 공유는 프론트엔드가 처리한다.
- 초대코드는 대문자/숫자 6자를 `XXX-XXX` 형식으로 표시한다.

### `POST /api/v1/families`

가족을 생성하고 초대코드를 발급한다.

Headers:

```http
Authorization: Bearer <Damso access token>
```

요청:

```json
{
  "familyName": "승주의 가족"
}
```

`familyName`은 optional이다. 없으면 Kakao display name이 있는 경우 `{displayName}의 가족`, 없으면 `나의 가족`으로 생성한다.

응답:

```json
{
  "familyId": 1,
  "familyName": "승주의 가족",
  "inviteCode": "A7K-28Q",
  "inviteUrl": "https://frontend-url/invite?code=A7K-28Q",
  "memberRole": "child"
}
```

### `GET /api/v1/families/me/invitation`

현재 사용자가 속한 가족의 초대정보를 조회한다.

응답:

```json
{
  "familyId": 1,
  "familyName": "승주의 가족",
  "inviteCode": "A7K-28Q",
  "inviteUrl": "https://frontend-url/invite?code=A7K-28Q"
}
```

### `GET /api/v1/families/invitations/{invite_code}`

초대코드가 사용 가능한 활성 가족에 연결되는지 확인한다.

응답:

```json
{
  "inviteCode": "A7K-28Q",
  "familyId": 1,
  "familyName": "승주의 가족",
  "available": true
}
```

### `POST /api/v1/families/join`

초대코드로 가족에 참여한다.

요청:

```json
{
  "inviteCode": "A7K-28Q"
}
```

응답:

```json
{
  "familyId": 1,
  "familyName": "승주의 가족",
  "memberRole": "mother",
  "familyConnected": true
}
```

## Home

- `GET /api/v1/home/summary`: 홈 요약 조회.

### `GET /api/v1/home/summary`

현재 사용자 기준 가족 연결 상태, 받은 질문 대기 상태, 보낸 질문 상태, 오늘 처리 건수를 조회한다.

Headers:

```http
Authorization: Bearer <Damso access token>
```

응답:

```json
{
  "familyConnected": true,
  "familyId": 1,
  "role": "child",
  "connectedToChild": false,
  "connectedToParent": true,
  "todayCompletedCount": 1,
  "pendingReceivedQuestion": {
    "questionSendId": 10,
    "sender": {
      "userId": 2,
      "displayName": "엄마",
      "profileImageUrl": null,
      "role": "mother"
    },
    "receivedAt": "2026-07-06T10:00:00Z",
    "read": false,
    "readAt": null
  },
  "latestSentQuestion": {
    "questionSendId": 9,
    "recipient": {
      "userId": 2,
      "displayName": "엄마",
      "profileImageUrl": null,
      "role": "mother"
    },
    "questionText": "오늘 가장 좋았던 순간은 언제였나요?",
    "sentAt": "2026-07-06T09:00:00Z",
    "read": true,
    "readAt": "2026-07-06T09:05:00Z",
    "answered": true,
    "answeredAt": "2026-07-06T09:30:00Z",
    "aiStatus": null
  },
  "aiStatus": null
}
```

`todayCompletedCount`는 한국 시간(`Asia/Seoul`) 기준 오늘에 `question_sends.answered_at`이 포함되는 질문-답변 쌍의 개수다. 실제 영상 업로드와 AI 분석 실행은 후속 기능이므로 이번 범위에서는 `aiStatus = null`일 수 있다.

## Questions

- `GET /api/v1/questions/recipients`: 질문 대상자 목록 조회.
- `GET /api/v1/questions/recommendations`: depth 기준 추천 질문 조회.
- `POST /api/v1/questions`: 가족 구성원에게 질문 보내기.

질문 탭과 답변 탭은 별도 흐름이다. 나에게 답변하지 않은 질문이 있어도 질문 보내기는 계속 가능해야 한다.

### `GET /api/v1/questions/recipients`

같은 활성 가족에 속한 구성원 중 현재 사용자를 제외한 질문 대상자 목록을 조회한다.

응답:

```json
{
  "recipients": [
    {
      "userId": 2,
      "displayName": "엄마",
      "profileImageUrl": null,
      "role": "mother",
      "memberRole": "mother"
    }
  ]
}
```

활성 가족 연결이 없으면 `400`을 반환한다.

### `GET /api/v1/questions/recommendations`

Query parameters:

- `depth`: `tiny`, `medium`, `deep` 중 하나. 필수.
- `limit`: 1~20. 기본값 `3`.

응답:

```json
{
  "recommendations": [
    {
      "recommendationId": 1,
      "questionText": "오늘 가장 많이 웃은 순간은 언제였나요?",
      "depth": "tiny",
      "category": null
    }
  ]
}
```

`question_recommendations.status = active`인 질문만 depth 기준으로 랜덤 조회한다.

### `POST /api/v1/questions`

추천 질문을 선택하거나 직접 작성해 같은 가족 구성원에게 질문을 보낸다.

요청:

```json
{
  "recipientUserId": 2,
  "depth": "medium",
  "questionText": "요즘 가장 마음에 남는 일은 무엇인가요?"
}
```

추천 질문 사용 요청:

```json
{
  "recipientUserId": 2,
  "recommendationId": 1
}
```

응답:

```json
{
  "questionSendId": 10,
  "recipientUserId": 2,
  "questionText": "요즘 가장 마음에 남는 일은 무엇인가요?",
  "depth": "medium",
  "source": "custom",
  "sentAt": "2026-07-06T10:00:00Z",
  "read": false,
  "answered": false
}
```

자기 자신에게 보내면 `400`을 반환한다. 같은 활성 가족에 속하지 않은 사용자에게 보내면 `400`을 반환한다.

## Answers

- `GET /api/v1/answers/questions`: 나에게 온 질문 목록 조회.
- `GET /api/v1/answers/questions/{question_send_id}`: 나에게 온 질문 상세 조회.
- `PATCH /api/v1/answers/questions/{question_send_id}/read`: 나에게 온 질문 읽음 처리.
- `POST /api/v1/answers/upload-url`: 영상 업로드용 presigned URL 발급.
- `POST /api/v1/answers`: 질문 답변 생성 (영상 1개 원본 메타데이터 등록). `upload-url`로 발급받은 경로에 업로드를 마친 뒤 `video_origin_url` 등을 등록한다.
- `POST /api/v1/answers/ai-callback`: AI 서버가 처리 완료/실패 결과를 push하는 콜백 수신 엔드포인트. 클라이언트나 프론트에서는 호출하지 않는다.
- `GET /api/v1/answers/{answer_id}/clip`: 답변에 대한 영상 클립 상세 조회. 바텀시트 또는 상세에서 영상 재생, 명대사, 요약을 표시할 때 사용한다. `status = completed`가 아니면 클립이 아직 없다. `video_clips`의 내부 PK(`clip_id`)는 API에 노출하지 않고 `answer_id`로만 조회한다.

영상 업로드와 실제 답변 저장은 후속 기능이다. 이번 질문/답변 루프 MVP 1차에서는 받은 질문 조회와 읽음 처리까지만 구현한다. 구현 순서는 영상 업로드(`upload-url`, `POST /api/v1/answers`)를 먼저 완성하고, AI 연동(`ai-callback` 수신, 클립 생성)은 그다음 단계로 진행한다.

### `GET /api/v1/answers/questions`

Query parameters:

- `unansweredOnly`: 기본값 `false`. `true`이면 답변하지 않은 질문만 조회한다.
- `sort`: `latest`, `unanswered_first`. 기본값 `latest`.

응답:

```json
{
  "questions": [
    {
      "questionSendId": 10,
      "sender": {
        "userId": 1,
        "displayName": "자녀",
        "profileImageUrl": null,
        "role": "child"
      },
      "questionText": "요즘 가장 마음에 남는 일은 무엇인가요?",
      "depth": "medium",
      "receivedAt": "2026-07-06T10:00:00Z",
      "read": false,
      "readAt": null,
      "answered": false,
      "answeredAt": null,
      "status": "sent"
    }
  ]
}
```

이미 답변한 질문도 기본 목록에 포함된다.

### `GET /api/v1/answers/questions/{question_send_id}`

현재 사용자에게 온 질문 상세를 조회한다. 다른 사용자에게 온 질문은 조회할 수 없으며 `404`를 반환한다.

응답:

```json
{
  "questionSendId": 10,
  "sender": {
    "userId": 1,
    "displayName": "자녀",
    "profileImageUrl": null,
    "role": "child"
  },
  "questionText": "요즘 가장 마음에 남는 일은 무엇인가요?",
  "depth": "medium",
  "receivedAt": "2026-07-06T10:00:00Z",
  "read": false,
  "readAt": null,
  "answered": false,
  "answeredAt": null,
  "status": "sent",
  "source": "custom",
  "recommendationId": null
}
```

### `PATCH /api/v1/answers/questions/{question_send_id}/read`

현재 사용자에게 온 질문을 읽음 처리한다. `read_at`이 이미 있으면 기존 값을 유지한다.

응답:

```json
{
  "questionSendId": 10,
  "read": true,
  "readAt": "2026-07-06T10:05:00Z"
}
```

### `POST /api/v1/answers/upload-url`

영상 업로드용 GCS presigned URL(V4, PUT)을 발급한다. 오브젝트 경로는 클라이언트가 정하지 못하고 서버가 `family_id` + `question_send_id` + `videoMimeType` 기준으로 결정적으로 계산한다(`answers/{family_id}/{question_send_id}/original.{ext}`).

요청:

```json
{
  "questionSendId": 10,
  "videoMimeType": "video/mp4"
}
```

응답:

```json
{
  "uploadUrl": "https://storage.googleapis.com/damso-videos/answers/1/10/original.mp4?X-Goog-Algorithm=...",
  "expiresAt": "2026-07-06T10:15:00Z"
}
```

지원하는 `videoMimeType`: `video/mp4`, `video/quicktime`, `video/webm`, `video/3gpp`.

에러:

- 존재하지 않는 `questionSendId`: `404`
- 현재 사용자가 그 질문의 수신자가 아님: `403`
- 이미 답변이 등록된 질문: `409`
- 지원하지 않는 `videoMimeType`: `415`

### `POST /api/v1/answers`

`upload-url`로 발급받은 URL에 클라이언트가 GCS로 직접 PUT 업로드를 마친 뒤, 원본 영상 메타데이터를 등록해 답변을 완료한다.

요청:

```json
{
  "questionSendId": 10,
  "videoMimeType": "video/mp4",
  "videoDurationSeconds": 42,
  "videoSizeBytes": 10485760
}
```

응답:

```json
{
  "answerId": 7,
  "questionSendId": 10,
  "status": "submitted",
  "submittedAt": "2026-07-06T10:16:00Z"
}
```

`video_origin_url`은 `upload-url` 발급 때와 동일한 규칙으로 서버가 다시 계산해 저장하며, 클라이언트가 별도로 전달하지 않는다. 성공 시 같은 트랜잭션에서 `question_sends.status = answered`, `answered_at`을 갱신한다.

에러:

- 존재하지 않는 `questionSendId`: `404`
- 현재 사용자가 그 질문의 수신자가 아님: `403`
- 이미 답변이 등록된 질문: `409`
- 지원하지 않는 `videoMimeType`: `415`

### AI 처리 흐름 (`POST /api/v1/answers` 이후)

```
클라이언트 → GCS Signed URL로 원본 mp4 업로드 → POST /api/v1/answers

백엔드
  → answers insert (status: submitted)
  → BackgroundTasks
      ├── ffmpeg 썸네일 추출 → GCS 업로드 → answers.thumbnail_url 업데이트
      └── AI 서버 POST (fire and forget, mediaPath JSON 모드)
  → 201 반환

AI 서버
  → STT + LLM 파이프라인 (AI-002~AI-009). 영상 자체는 가공하지 않는다.
  → 백엔드 콜백 POST /api/v1/answers/ai-callback (pipelineResults JSON)

백엔드 (콜백 수신)
  → ffmpeg HLS 변환 → GCS 업로드
  → video_clips insert (+ video_clip_ai_results에 원본 pipelineResults snapshot)
  → answers.status = completed 업데이트
  → Supabase Realtime broadcast
```

백엔드가 AI 서버로 보내는 요청은 AI 서버 API 스펙(`DAMSO-AI-API` 명세)의 JSON Path Mode를 강제한다. Multipart 업로드 모드(`file` 첨부)는 쓰지 않는다 — GCS 경로 문자열만 넘기고, 실제 파일 바이트를 백엔드가 내려받아 재업로드하지 않는다.

```json
POST https://{ai-server-host}/api/v1/ai/stt/transcribe
{
  "answerId": "123",
  "questionId": "10",
  "send_user": "최대현",
  "send_role": "둘째 아들",
  "question": "자녀에게 들었던 말 중 기억에 남는 순간은?",
  "receive_user": "최기섭",
  "receive_role": "아버지",
  "mediaPath": "gs://bucket/videos/ans_123.mp4",
  "includeDownstream": true
}
```

`answerId`에는 `answers.id`를 그대로 문자열로 실어 보낸다. AI API 스펙에 있는 별도 `jobId` 필드는 사용하지 않는다 — 식별자를 이원화하지 않고 `answerId` 하나로 요청과 콜백을 correlate한다.

### `POST /api/v1/answers/ai-callback`

AI 서버가 처리 완료/실패 시 호출하는 콜백이다. 프론트/클라이언트는 호출하지 않는다.

성공 시 요청 본문 (AI 서버 pipelineResults 요약):

```json
{
  "answerId": "123",
  "transcript": "하는 과정에서 초등학교 때든...",
  "segments": [{ "startMs": 0, "endMs": 20000, "text": "..." }],
  "pipelineResults": {
    "AI-003": { "diaryTitle": "...", "oneLineSummary": "..." },
    "AI-004": { "representativeQuote": "..." },
    "AI-005": { "emotionTags": ["담담함", "기록"] },
    "AI-008": { "status": "completed" },
    "AI-009": { "fourCutTitle": "..." }
  }
}
```

실패 시 요청 본문:

```json
{
  "answerId": "123",
  "transcript": "",
  "warnings": ["stt_failed"],
  "pipelineResults": {
    "AI-008": { "status": "failed", "retryable": true, "failedStep": "stt" },
    "AI-010": { "fallbackUsed": true, "retryable": true }
  }
}
```

처리:

- `answerId`로 대상 `answers` row를 찾는다. 존재하지 않으면 `404`를 반환한다.
- 성공(`pipelineResults.AI-008.status = completed`): ffmpeg으로 HLS 변환 후 GCS 업로드 → `video_clips` insert(`transcript`, `transcript_segments`, `title`=AI-003.diaryTitle, `one_line_summary`=AI-003.oneLineSummary, `quote`=AI-004.representativeQuote, `emotion_tags`=AI-005.emotionTags, `fourcut_title`=AI-009.fourCutTitle) → `video_clip_ai_results`에 `pipelineResults` 전체 snapshot insert → `answers.status = completed` 업데이트를 같은 트랜잭션으로 처리한다.
- 실패(`pipelineResults.AI-008.status = failed`): `answers.status = failed`, `answers.ai_retryable`=AI-008.retryable, `answers.ai_fallback_used`=AI-010.fallbackUsed로 업데이트한다. `video_clips`는 생성하지 않는다.
- 두 경우 모두 처리 후 Supabase Realtime Broadcast로 `family:{family_id}` 채널에 알린다.

TODO: 이 엔드포인트는 AI 서버만 호출해야 하므로 인증(공유 시크릿 헤더 등)이 필요하다. 구체적인 인증 방식은 아직 미정이다.

## Clips

- `GET /api/v1/clips`: 가족 + 날짜 단위 네컷 그리드 목록 조회. `family_id`, `DATE(created_at)` 기준으로 묶어서 반환하며, 각 항목에 `answer_id`, `status`(`submitted`/`processing`/`completed`/`failed`), `thumbnail_url`을 포함한다. `thumbnail_url`은 답변 제출 직후 ffmpeg으로 생성되므로 `status`와 무관하게 항상 내려간다.

## Realtime

- AI 처리 완료/실패는 별도 폴링 API 없이 Supabase Realtime **Broadcast**로 전달한다. 원본 `answers`/`video_clips` 테이블을 `postgres_changes`로 직접 구독하지 않는다. 내부 PK/FK(`question_send_id`, `family_id` 등)를 그대로 클라이언트에 노출하지 않기 위해서다.
- 채널: `family:{family_id}`
- 이벤트 payload: `answer_id`, `status`(`completed` 또는 `failed`), 성공 시 `thumbnail_url`. 상세는 `GET /api/v1/answers/{answer_id}/clip`으로 다시 조회한다.
- 백엔드는 `video_clips` insert와 `answers.status = completed` 업데이트를 같은 트랜잭션으로 처리한 뒤 broadcast를 보낸다. 순서가 바뀌면 그리드/클라이언트에는 `completed`로 보이는데 클립 상세 조회가 실패하는 순간이 생길 수 있다.
