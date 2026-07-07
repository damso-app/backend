# Damso DB Schema v0.1

이 문서는 Damso MVP ERD를 테이블 설계 초안으로 풀어 쓴 문서다. 현재 `users`, `social_accounts`, `oauth_login_codes`, `user_agreements`, `families`, `family_members`, `question_recommendations`, `question_sends`는 SQLAlchemy 모델과 Alembic migration을 작성했고, 나머지 테이블은 아직 설계 초안이다.

## Global Rules

- 내부 PK는 `BIGINT` auto-increment 계열을 사용한다.
- 외부 API와 공유 URL에는 내부 `id` 대신 `public_id` 또는 code 계열 값을 사용한다.
- Kakao access token은 DB에 저장하지 않는다.
- 영상 파일은 DB에 직접 저장하지 않고 storage object 경로만 저장한다.
- `created_at`, `updated_at`은 변경 가능한 주요 테이블에 둔다.
- 삭제 가능한 주요 콘텐츠에는 `deleted_at`을 둔다.
- 상태 전이가 필요한 흐름에는 `status` 계열 ENUM을 둔다.
- 날짜 단위 집계와 "오늘" 판단은 한국 시간(`Asia/Seoul`) 기준으로 계산한다.
- 영상 원본(`answers.video_origin_url`)과 AI 가공본(`video_clips.video_url`)은 분리해서 저장한다. 가공본은 AI 서버가 자막을 입힌 mp4를 직접 GCS에 업로드한 결과이며, HLS 변환은 하지 않는다(답변 영상 길이가 짧아 시그니드 URL로 mp4를 그대로 재생해도 충분하다고 판단).
- 네컷 그리드 목록은 `answers`를 `family_id`, `DATE(created_at)` 기준으로 `GROUP BY` 조회한다. 별도 그리드 테이블은 두지 않는다.
- `video_clips`는 별도 `status` 컬럼을 두지 않는다. row 존재 여부가 곧 `answers.status = completed`를 의미하는 불변식이다. 백엔드는 `video_clips` insert와 `answers.status = completed` 업데이트를 같은 트랜잭션으로 처리해서, 그리드에는 `completed`로 보이는데 클립 조회가 실패하는 순간이 생기지 않게 한다.
- AI 처리 완료/실패는 폴링 API 대신 Supabase Realtime Broadcast(`family:{family_id}` 채널)로 알린다. 상세 payload는 `docs/API_DRAFT.md`의 Realtime 절을 따른다.
- 답변 제출 직후 백엔드가 ffmpeg으로 추출하는 썸네일(`answers.thumbnail_url`)은 AI 처리 완료 여부와 무관하게 네컷 그리드에 노출한다. AI 가공이 끝나야 생기는 `video_clips`에는 썸네일을 다시 저장하지 않는다.
- AI 서버 pipelineResults 전체 원본 응답은 `video_clip_ai_results.ai_raw_response`에 snapshot으로 보관한다. `video_clips`는 프론트가 바로 쓰는 필드만 정제해서 저장한다.

## AI 처리 파이프라인 (2026-07-06 확정)

```
클라이언트 → GCS Signed URL로 원본 mp4 업로드 → POST /api/v1/answers

백엔드
  → answers insert (status: submitted)
  → BackgroundTasks
      ├── ffmpeg 썸네일 추출 → GCS 업로드 → answers.thumbnail_url 업데이트
      └── AI 서버 POST /api/v1/ai/jobs (fire and forget)
  → 201 반환

AI 서버
  → STT + LLM 파이프라인 (AI-002~AI-009) + VAD 기반 자막 입힌 편집 영상 생성
  → 편집 영상을 미리 받은 editedVideoUploadUrl(signed PUT)로 GCS에 직접 업로드 (백엔드를 거치지 않음)
  → 백엔드 콜백 POST /api/v1/answers/{answer_id}/ai-callback (pipelineResults JSON, Bearer callbackToken)

백엔드 (콜백 수신)
  → video_clips insert (video_url = 결정적 경로, + video_clip_ai_results에 원본 pipelineResults snapshot)
  → answers.status = completed 업데이트
  → Supabase Realtime broadcast
```

이전에는 GCP Pub/Sub을 경유하는 job 큐 방식을 검토했지만, 현재는 백엔드가 AI 서버에 직접 fire-and-forget POST를 보내고 AI 서버가 처리 완료 시 백엔드의 콜백 엔드포인트를 직접 호출하는 방식으로 단순화했다. Supabase에 AI 서버가 직접 write하는 경로는 없다 — 결과 전달은 오직 콜백 하나뿐이다.

AI 서버 요청(`DAMSO-AI-API` 명세 `POST /api/v1/ai/jobs` 기준)은 아래 필드를 실어 보낸다. 원본 영상을 gs:// 경로로 직접 넘기지 않고, 백엔드가 발급한 **signed GET URL**(`mediaUrl`)로 넘긴다 — AI 서버가 우리 GCP 프로젝트 권한을 가질 필요가 없다.

- `answerId`: `answers.id`를 문자열로.
- `questionId`: 별도 question 테이블이 없어 `question_sends.id`(=`answers.question_send_id`)를 문자열로.
- `jobId`: `"JOB_{answer_id}"` 형식. 백엔드가 결정적으로 만들어서 보내고, `answers.ai_job_id`에 저장한다. correlation의 기준은 여전히 `answer_id`이고(같은 값에서 파생), `jobId`는 AI 서버 쪽 참고/추적용이다.
- `send_user`/`send_role`/`question`/`receive_user`/`receive_role`: 답변 제출 시점에 `AnswerService`가 조립해 `answers.ai_input_context`에 저장해둔 값을 그대로 실어 보낸다.
- `mediaUrl`: 원본 영상 signed GET URL. job이 큐에서 대기하다 늦게 처리될 수 있어, 기본 GCS URL 만료(15분)가 아니라 `editedVideoUploadUrl`과 같은 `AI_EDITED_VIDEO_UPLOAD_URL_EXPIRE_MINUTES`(기본 120분)로 발급한다.
- `mediaDurationSeconds`: `answers.video_duration_seconds`.
- `editedVideoUploadUrl`: 편집(자막 입힌) 영상을 AI 서버가 업로드할 signed PUT URL. 백엔드가 결정적 경로(`answers/{family_id}/{question_send_id}/edited.mp4`)로 미리 발급해서 같이 보낸다.
- `includeDownstream`: 고정값 `true`.
- `providerMode`: AI 서버 쪽 `DAMSO-AI-API` 명세(Notion)에 정의된 필드로, 현재는 고정값 `"auto"`만 보낸다.
- `callbackUrl`: `POST /api/v1/answers/{answer_id}/ai-callback` 형태로 answer 단위 경로를 백엔드가 만들어서 보낸다.
- `callbackToken`: 백엔드가 발급한 토큰. AI 서버는 콜백 호출 시 `Authorization: Bearer {callbackToken}`으로 그대로 돌려주고, 백엔드는 이 토큰으로 콜백 요청을 검증한다.

AI 서버는 STT/LLM 처리 후 VAD(Voice Activity Detection)로 자막 세그먼트를 만들고 영상에 자막/질문을 입혀서, 그 결과를 우리가 미리 넘긴 `editedVideoUploadUrl`로 직접 업로드한다 — 편집 영상 바이트는 백엔드를 거치지 않는다. 답변 영상이 짧아 HLS 스트리밍 변환은 하지 않기로 했고, 백엔드는 그 결정적 경로를 그대로 `video_clips.video_url`에 저장한 뒤 조회 시점에 signed GET URL로 변환해서 내려준다.

폴링(`GET /api/v1/ai/jobs/{jobId}?includeResult=false`)은 진행률/소요시간만 반환하며, 실제 결과는 원칙적으로 콜백으로만 온다. 프론트에 진행률 UI가 없으므로 이 폴링은 필수는 아니고, 콜백 유실 시 안전망(reconciliation)으로만 후보로 고려한다.

구현 우선순위는 영상 업로드(`POST /api/v1/answers`, GCS 업로드 흐름)를 먼저 완성하고, AI 연동(BackgroundTask의 AI 서버 POST, 콜백 수신)은 그 다음 단계로 미룬다. 이 절의 계약은 AI 개발자 문서(`DAMSO-AI-API` 명세)와 대화로 확정한 내용이며, 실제 fire-and-forget 호출/콜백 수신 코드는 아직 구현하지 않았다.

## Tables

### users

목적: Damso 내부 사용자 프로필과 역할 선택 상태를 저장한다.

| Column            | Type         | PK  | FK  | Unique | Nullable | Notes                                  |
| ----------------- | ------------ | --- | --- | ------ | -------- | -------------------------------------- |
| id                | BIGINT       | Y   | N   | Y      | N        | 내부 PK                                |
| public_id         | VARCHAR(32)  | N   | N   | Y      | N        | 외부 노출용 사용자 식별자              |
| display_name      | VARCHAR(100) | N   | N   | N      | Y        | Kakao 프로필 또는 사용자가 수정한 이름 |
| profile_image_url | TEXT         | N   | N   | N      | Y        | Kakao profile image URL                |
| role              | user_role    | N   | N   | N      | Y        | `child`, `mother`, `father`            |
| status            | user_status  | N   | N   | N      | N        | 기본값 `active`                        |
| role_selected_at  | TIMESTAMPTZ  | N   | N   | N      | Y        | 역할 선택 시각                         |
| created_at        | TIMESTAMPTZ  | N   | N   | N      | N        | 생성 시각                              |
| updated_at        | TIMESTAMPTZ  | N   | N   | N      | N        | 수정 시각                              |
| deleted_at        | TIMESTAMPTZ  | N   | N   | N      | Y        | soft delete                            |

인덱스 후보:

- `ux_users_public_id` unique index on `(public_id)`
- `ix_users_role_status` on `(role, status)`

### social_accounts

목적: Kakao OAuth 계정과 Damso 사용자를 연결한다. Kakao access token은 저장하지 않는다.

| Column            | Type           | PK  | FK       | Unique | Nullable | Notes                           |
| ----------------- | -------------- | --- | -------- | ------ | -------- | ------------------------------- |
| id                | BIGINT         | Y   | N        | Y      | N        | 내부 PK                         |
| user_id           | BIGINT         | N   | users.id | N      | N        | Damso 사용자                    |
| provider          | oauth_provider | N   | N        | N      | N        | MVP는 `kakao`                   |
| provider_user_id  | VARCHAR(191)   | N   | N        | N      | N        | Kakao user id                   |
| email             | VARCHAR(255)   | N   | N        | N      | Y        | Kakao 제공 범위에 따라 nullable |
| profile_image_url | TEXT           | N   | N        | N      | Y        | Kakao profile image             |
| created_at        | TIMESTAMPTZ    | N   | N        | N      | N        | 생성 시각                       |
| updated_at        | TIMESTAMPTZ    | N   | N        | N      | N        | 수정 시각                       |

인덱스 후보:

- `ux_social_accounts_provider_user` unique index on `(provider, provider_user_id)`
- `ix_social_accounts_user_id` on `(user_id)`

### oauth_login_codes

목적: Kakao callback 이후 URL query로 Damso access token을 직접 전달하지 않기 위한 일회성 교환 코드를 저장한다.

| Column     | Type              | PK  | FK       | Unique | Nullable | Notes                            |
| ---------- | ----------------- | --- | -------- | ------ | -------- | -------------------------------- |
| id         | BIGINT            | Y   | N        | Y      | N        | 내부 PK                          |
| user_id    | BIGINT            | N   | users.id | N      | N        | 로그인 완료 사용자               |
| code_hash  | VARCHAR(255)      | N   | N        | Y      | N        | raw `login_code`는 저장하지 않음 |
| status     | login_code_status | N   | N        | N      | N        | `active`, `used`, `expired`      |
| expires_at | TIMESTAMPTZ       | N   | N        | N      | N        | 짧은 만료 시간                   |
| used_at    | TIMESTAMPTZ       | N   | N        | N      | Y        | 사용 시각                        |
| created_at | TIMESTAMPTZ       | N   | N        | N      | N        | 생성 시각                        |

인덱스 후보:

- `ux_oauth_login_codes_code_hash` unique index on `(code_hash)`
- `ix_oauth_login_codes_user_status` on `(user_id, status)`
- `ix_oauth_login_codes_expires_at` on `(expires_at)`

### user_agreements

목적: Kakao 로그인 이후 Damso 자체 온보딩에서 필요한 필수 동의 3개 상태를 저장한다. Kakao Developers 동의항목과 별개다.

| Column         | Type           | PK  | FK       | Unique | Nullable | Notes                                                            |
| -------------- | -------------- | --- | -------- | ------ | -------- | ---------------------------------------------------------------- |
| id             | BIGINT         | Y   | N        | Y      | N        | 내부 PK                                                          |
| user_id        | BIGINT         | N   | users.id | N      | N        | 동의 사용자                                                      |
| agreement_type | agreement_type | N   | N        | N      | N        | `terms_of_service`, `privacy_policy`, `camera_microphone_notice` |
| agreed         | BOOLEAN        | N   | N        | N      | N        | 기본값 `false`                                                   |
| agreed_at      | TIMESTAMPTZ    | N   | N        | N      | Y        | `agreed = true`가 된 시각                                        |
| created_at     | TIMESTAMPTZ    | N   | N        | N      | N        | 생성 시각                                                        |
| updated_at     | TIMESTAMPTZ    | N   | N        | N      | N        | 수정 시각                                                        |

인덱스 후보:

- `ux_user_agreements_user_type` unique index on `(user_id, agreement_type)`
- `ix_user_agreements_user_agreed` on `(user_id, agreed)`

#### 필수 동의 기준

MVP 필수 동의 타입은 다음 3개다.

- `terms_of_service`: 서비스 이용약관 동의. 질문, 영상 답변, 다이어리 저장 기능 이용.
- `privacy_policy`: 개인정보 처리 동의. 이름, 가족 연결, 질문, 영상, STT 텍스트 처리.
- `camera_microphone_notice`: 카메라·마이크 권한 안내. 영상 답변 촬영 시 브라우저 권한 요청 안내.

3개 항목이 모두 `agreed = true`일 때 온보딩의 필수 동의가 완료된 것으로 판단한다. 선택 동의, 마케팅 동의, 동의 철회 기능은 MVP 범위에서 제외한다.

### families

목적: 가족방 단위를 저장한다.

| Column             | Type          | PK  | FK       | Unique | Nullable | Notes                       |
| ------------------ | ------------- | --- | -------- | ------ | -------- | --------------------------- |
| id                 | BIGINT        | Y   | N        | Y      | N        | 내부 PK                     |
| public_id          | VARCHAR(32)   | N   | N        | Y      | N        | 외부 노출용 가족방 식별자   |
| name               | VARCHAR(100)  | N   | N        | N      | N        | 가족방 이름                 |
| invite_code        | VARCHAR(7)    | N   | N        | Y      | Y        | MVP 초대코드. 예: `A7K-28Q` |
| created_by_user_id | BIGINT        | N   | users.id | N      | N        | 가족방 생성자               |
| status             | family_status | N   | N        | N      | N        | 기본값 `active`             |
| created_at         | TIMESTAMPTZ   | N   | N        | N      | N        | 생성 시각                   |
| updated_at         | TIMESTAMPTZ   | N   | N        | N      | N        | 수정 시각                   |
| deleted_at         | TIMESTAMPTZ   | N   | N        | N      | Y        | soft delete                 |

인덱스 후보:

- `ux_families_public_id` unique index on `(public_id)`
- `ux_families_invite_code` unique index on `(invite_code)`
- `ix_families_created_by_user_id` on `(created_by_user_id)`
- `ix_families_status` on `(status)`

MVP에서는 활성 초대코드 1개를 `families.invite_code`에 저장한다. 초대코드 이력, 만료, revoke가 필요해지면 `family_invite_codes` 테이블을 별도로 구현한다.

### family_members

목적: 사용자와 가족방의 멤버십, 가족 내 역할, 초대 합류 상태를 저장한다.

| Column      | Type                 | PK  | FK          | Unique | Nullable | Notes                                  |
| ----------- | -------------------- | --- | ----------- | ------ | -------- | -------------------------------------- |
| id          | BIGINT               | Y   | N           | Y      | N        | 내부 PK                                |
| family_id   | BIGINT               | N   | families.id | N      | N        | 가족방                                 |
| user_id     | BIGINT               | N   | users.id    | N      | N        | 구성원                                 |
| member_role | family_member_role   | N   | N           | N      | N        | `child`, `mother`, `father`            |
| status      | family_member_status | N   | N           | N      | N        | `active`, `invited`, `left`, `removed` |
| joined_at   | TIMESTAMPTZ          | N   | N           | N      | Y        | 합류 시각                              |
| created_at  | TIMESTAMPTZ          | N   | N           | N      | N        | 생성 시각                              |
| updated_at  | TIMESTAMPTZ          | N   | N           | N      | N        | 수정 시각                              |

인덱스 후보:

- `ux_family_members_family_user` unique index on `(family_id, user_id)`
- `ix_family_members_user_status` on `(user_id, status)`
- `ix_family_members_family_status` on `(family_id, status)`

#### Role 기준

`users.role`과 `family_members.member_role`은 의도적으로 역할 범위가 다르다.

- `users.role`: 온보딩에서 고른 사용자 기본 역할이다. `GET /api/v1/users/me`, 역할 선택 완료 여부, 첫 가족방 생성/합류 UX에 사용한다.
- `family_members.member_role`: 특정 가족방 안에서의 역할이다. 가족방 권한, 질문 발송 권한, 구성원 목록 표시에는 이 값을 기준으로 사용한다.

MVP에서는 가족방 내부 권한 판단에 `family_members.member_role`을 source of truth로 사용한다. `users.role`은 온보딩 기본값과 신규 가족방 멤버십 생성 시 초기값으로만 사용한다. 이후 한 사용자가 여러 가족방에서 다른 역할을 가질 수 있으므로 API 권한 체크는 `users.role`만 보지 않는다. 온보딩 역할은 자식/엄마/아빠 3가지이며 API enum 값은 `child`, `mother`, `father`다.

### family_invite_codes

목적: 가족방 초대 코드 발급, 만료, 사용 상태를 저장한다.

| Column             | Type               | PK  | FK          | Unique | Nullable | Notes                                  |
| ------------------ | ------------------ | --- | ----------- | ------ | -------- | -------------------------------------- |
| id                 | BIGINT             | Y   | N           | Y      | N        | 내부 PK                                |
| family_id          | BIGINT             | N   | families.id | N      | N        | 초대 대상 가족방                       |
| created_by_user_id | BIGINT             | N   | users.id    | N      | N        | 초대 코드 생성자                       |
| invite_code_hash   | VARCHAR(255)       | N   | N           | Y      | N        | raw invite code는 저장하지 않음        |
| status             | invite_code_status | N   | N           | N      | N        | `active`, `used`, `expired`, `revoked` |
| expires_at         | TIMESTAMPTZ        | N   | N           | N      | N        | 만료 시각                              |
| used_at            | TIMESTAMPTZ        | N   | N           | N      | Y        | 사용 시각                              |
| created_at         | TIMESTAMPTZ        | N   | N           | N      | N        | 생성 시각                              |
| updated_at         | TIMESTAMPTZ        | N   | N           | N      | N        | 수정 시각                              |

인덱스 후보:

- `ux_family_invite_codes_hash` unique index on `(invite_code_hash)`
- `ix_family_invite_codes_family_status` on `(family_id, status)`
- `ix_family_invite_codes_expires_at` on `(expires_at)`

### question_recommendations

목적: 질문 탭에서 depth 기준으로 랜덤 노출할 추천 질문 seed를 저장한다.

| Column        | Type                           | PK  | FK  | Unique | Nullable | Notes                    |
| ------------- | ------------------------------ | --- | --- | ------ | -------- | ------------------------ |
| id            | BIGINT                         | Y   | N   | Y      | N        | 내부 PK                  |
| question_text | TEXT                           | N   | N   | N      | N        | 추천 질문 본문           |
| depth         | question_depth                 | N   | N   | N      | N        | `tiny`, `medium`, `deep` |
| category      | VARCHAR(80)                    | N   | N   | N      | Y        | 질문 카테고리            |
| status        | question_recommendation_status | N   | N   | N      | N        | `active`, `archived`     |
| created_at    | TIMESTAMPTZ                    | N   | N   | N      | N        | 생성 시각                |
| updated_at    | TIMESTAMPTZ                    | N   | N   | N      | N        | 수정 시각                |

인덱스 후보:

- `ix_question_recommendations_depth_status` on `(depth, status)`

### question_sends

목적: 사용자가 같은 가족 구성원에게 질문을 보낸 이벤트와 수신자의 읽음/답변 상태를 저장한다.

| Column            | Type                 | PK  | FK                          | Unique | Nullable | Notes                                      |
| ----------------- | -------------------- | --- | --------------------------- | ------ | -------- | ------------------------------------------ |
| id                | BIGINT               | Y   | N                           | Y      | N        | 내부 PK                                    |
| sender_user_id    | BIGINT               | N   | users.id                    | N      | N        | 질문 보낸 사용자                           |
| recipient_user_id | BIGINT               | N   | users.id                    | N      | N        | 질문 받은 사용자                           |
| family_id         | BIGINT               | N   | families.id                 | N      | N        | 가족방 scope                               |
| question_text     | TEXT                 | N   | N                           | N      | N        | 발송 시점의 질문 본문                      |
| depth             | question_depth       | N   | N                           | N      | N        | `tiny`, `medium`, `deep`                   |
| source            | question_send_source | N   | N                           | N      | N        | `recommendation`, `custom`                 |
| recommendation_id | BIGINT               | N   | question_recommendations.id | N      | Y        | 추천 질문을 사용한 경우                    |
| sent_at           | TIMESTAMPTZ          | N   | N                           | N      | N        | 발송 시각                                  |
| read_at           | TIMESTAMPTZ          | N   | N                           | N      | Y        | 수신자가 읽은 시각                         |
| answered_at       | TIMESTAMPTZ          | N   | N                           | N      | Y        | 수신자가 답변을 완료한 시각                |
| status            | question_send_status | N   | N                           | N      | N        | `sent`, `answered`, `cancelled`, `expired` |
| created_at        | TIMESTAMPTZ          | N   | N                           | N      | N        | 생성 시각                                  |
| updated_at        | TIMESTAMPTZ          | N   | N                           | N      | N        | 수정 시각                                  |

인덱스 후보:

- `ix_question_sends_recipient_status` on `(recipient_user_id, status)`
- `ix_question_sends_sender_status` on `(sender_user_id, status)`
- `ix_question_sends_family_sent_at` on `(family_id, sent_at DESC)`

`read_at IS NOT NULL`이면 읽음 상태로 판단한다. `answered_at IS NOT NULL` 또는 `status = answered`이면 답변 완료로 판단한다. 실제 영상 원본, 답변 메타데이터, AI 분석 결과는 후속 테이블에서 `question_sends.id`를 참조해 확장한다.

### answers

목적: 부모님이 제출한 답변 영상 파일 메타데이터를 저장한다.

| Column                 | Type          | PK  | FK                | Unique | Nullable | Notes                                                                                     |
| ---------------------- | ------------- | --- | ----------------- | ------ | -------- | ----------------------------------------------------------------------------------------- |
| id                     | BIGINT        | Y   | N                 | Y      | N        | 내부 PK                                                                                   |
| question_send_id       | BIGINT        | N   | question_sends.id | Y      | N        | MVP는 질문 발송당 답변 1개. 누가 누구에게 언제 보냈는지 추적                              |
| user_id                | BIGINT        | N   | users.id          | N      | N        | 답변자                                                                                    |
| family_id              | BIGINT        | N   | families.id       | N      | N        | `question_sends.family_id` 비정규화 복사. 네컷 그리드 조회용                              |
| video_origin_url       | TEXT          | N   | N                 | N      | Y        | 영상 원본 storage object path, 파일 blob 저장 금지                                        |
| video_mime_type        | VARCHAR(100)  | N   | N                 | N      | Y        | 예: `video/mp4`                                                                           |
| video_duration_seconds | INTEGER       | N   | N                 | N      | Y        | 영상 길이                                                                                 |
| video_size_bytes       | INTEGER       | N   | N                 | N      | Y        | 파일 크기                                                                                 |
| thumbnail_url          | TEXT          | N   | N                 | N      | Y        | 제출 직후 BackgroundTasks에서 ffmpeg으로 추출. AI 처리 상태와 무관하게 네컷 그리드 표시용 |
| status                 | answer_status | N   | N                 | N      | N        | 제출부터 AI 처리까지의 상태. `submitted`, `processing`, `completed`, `failed`             |
| ai_job_id              | VARCHAR(100)  | N   | N                 | N      | Y        | AI 서버 요청에 실어 보내는 job 식별자. `"JOB_{answer_id}"` 형식으로 채움                  |
| ai_retryable           | BOOLEAN       | N   | N                 | N      | N        | AI 콜백이 보고한 재시도 가능 여부. 기본값 `false`                                         |
| ai_fallback_used       | BOOLEAN       | N   | N                 | N      | N        | AI 콜백이 보고한 fallback 처리 사용 여부. 기본값 `false`                                  |
| ai_input_context       | JSONB         | N   | N                 | N      | Y        | submit 시점에 조립해 AI 서버 요청에 사용한 interviewContext snapshot                      |
| submitted_at           | TIMESTAMPTZ   | N   | N                 | N      | N        | 제출 시각                                                                                 |
| created_at             | TIMESTAMPTZ   | N   | N                 | N      | N        | 생성 시각                                                                                 |
| updated_at             | TIMESTAMPTZ   | N   | N                 | N      | N        | 수정 시각                                                                                 |
| deleted_at             | TIMESTAMPTZ   | N   | N                 | N      | Y        | soft delete                                                                               |

인덱스 후보:

- `ux_answers_question_send_id` unique index on `(question_send_id)`
- `ix_answers_user_submitted_at` on `(user_id, submitted_at DESC)`
- `ix_answers_family_created_at` on `(family_id, created_at DESC)`. 네컷 그리드는 이 인덱스로 `family_id`, `DATE(created_at)` 기준 `GROUP BY` 조회

#### ai_input_context 구조

```json
{
  "send_user": "최대현",
  "send_role": "자녀",
  "question": "자녀에게 들었던 말 중 기억에 남는 순간은?",
  "receive_user": "최기섭",
  "receive_role": "아빠"
}
```

`send_role`/`receive_role`은 `family_members.member_role`(`child`/`mother`/`father`)을 각각 `자녀`/`엄마`/`아빠`로 매핑한 값이다. 가족 내 서열(예: 둘째, 첫째)은 구분하지 않는다.

영상 참조(`mediaUrl`, `editedVideoUploadUrl`)는 여기 저장하지 않는다. signed URL이라 만료되므로, AI 서버로 보내는 시점(BackgroundTask)에 `answers.video_origin_url`을 기반으로 그때그때 새로 발급한다.

### video_clips

목적: 답변 영상의 AI 가공 결과 중 프론트가 바로 사용하는 필드(편집 영상 URL, 전사, 제목, 명대사, 요약, 감정 태그)를 저장한다. `status` 컬럼 없음 — row 존재 여부가 곧 `completed`. 썸네일은 제출 직후 `answers.thumbnail_url`에 이미 저장되므로 여기서는 중복 저장하지 않는다.

| Column              | Type         | PK  | FK         | Unique | Nullable | Notes                                                          |
| ------------------- | ------------ | --- | ---------- | ------ | -------- | -------------------------------------------------------------- |
| id                  | BIGINT       | Y   | N          | Y      | N        | 내부 PK                                                        |
| answer_id           | BIGINT       | N   | answers.id | Y      | N        | 원본 답변. MVP는 답변당 클립 1개                               |
| video_url           | TEXT         | N   | N          | N      | Y        | AI 서버가 자막 입힌 뒤 GCS에 직접 업로드한 편집 영상 경로. HLS 변환 없이 mp4를 그대로 저장(조회 시 signed GET URL로 변환) |
| transcript          | TEXT         | N   | N          | N      | Y        | 영상/음성에서 추출한 전체 전사                                 |
| transcript_segments | JSONB        | N   | N          | N      | Y        | 전사 segments. 영상 자막 싱크용                                |
| title               | VARCHAR(200) | N   | N          | N      | Y        | 클립 제목                                                      |
| quote               | TEXT         | N   | N          | N      | Y        | 바텀시트/상세에 노출하는 대표 명대사                           |
| one_line_summary    | TEXT         | N   | N          | N      | Y        | 클립 상세에 노출하는 한 줄 AI 요약                             |
| emotion_tags        | JSONB        | N   | N          | N      | Y        | 감정 태그 배열. 예: `["warm", "nostalgic"]`                    |
| fourcut_title       | VARCHAR(200) | N   | N          | N      | Y        | 네컷 묶음 제목                                                 |
| created_at          | TIMESTAMPTZ  | N   | N          | N      | N        | 생성 시각                                                      |
| updated_at          | TIMESTAMPTZ  | N   | N          | N      | N        | AI 결과 갱신 시각                                              |

인덱스 후보:

- `ux_video_clips_answer_id` unique index on `(answer_id)`

### video_clip_ai_results

목적: AI 서버 pipelineResults 전체 원본 응답을 snapshot으로 보관한다. 재처리, 디버깅, `video_clips`에 없는 필드(예: 향후 공유 기능의 shareTitle)를 추후 꺼내 쓰기 위한 용도다.

| Column          | Type        | PK  | FK             | Unique | Nullable | Notes                         |
| --------------- | ----------- | --- | -------------- | ------ | -------- | ----------------------------- |
| id              | BIGINT      | Y   | N              | Y      | N        | 내부 PK                       |
| video_clip_id   | BIGINT      | N   | video_clips.id | N      | N        | 원본 클립                     |
| ai_raw_response | JSONB       | N   | N              | N      | N        | pipelineResults 전체 snapshot |
| created_at      | TIMESTAMPTZ | N   | N              | N      | N        | 생성 시각                     |

인덱스 후보:

- `ix_video_clip_ai_results_video_clip_id` on `(video_clip_id)`

## ENUM Candidates

| ENUM                           | Values                                                           |
| ------------------------------ | ---------------------------------------------------------------- |
| user_role                      | `child`, `mother`, `father`                                      |
| user_status                    | `active`, `disabled`                                             |
| oauth_provider                 | `kakao`                                                          |
| login_code_status              | `active`, `used`, `expired`                                      |
| agreement_type                 | `terms_of_service`, `privacy_policy`, `camera_microphone_notice` |
| family_status                  | `active`, `archived`                                             |
| family_member_role             | `child`, `mother`, `father`                                      |
| family_member_status           | `active`, `invited`, `left`, `removed`                           |
| invite_code_status             | `active`, `used`, `expired`, `revoked`                           |
| question_depth                 | `tiny`, `medium`, `deep`                                         |
| question_recommendation_status | `active`, `archived`                                             |
| question_send_source           | `recommendation`, `custom`                                       |
| question_send_status           | `sent`, `answered`, `cancelled`, `expired`                       |
| answer_status                  | `submitted`, `processing`, `completed`, `failed`                 |

## TODO

- API path parameter가 내부 `id`인지 `public_id`인지 확정해야 한다. `answers`, `video_clips`는 현재 외부 노출 API가 없어 `public_id`를 두지 않았다.
- 추천 질문 seed 운영 방식과 초기 seed 데이터 적재 방식을 확정해야 한다.
- `video_clips.transcript`, `quote`, `one_line_summary`, `emotion_tags` 구조를 실제 프롬프트 구현 시 확정해야 한다.
- 가족방 탈퇴/삭제 정책과 보존 기간을 확정해야 한다.
- `video_clip_ai_results.ai_raw_response`의 실제 pipelineResults 스키마를 AI 서버 스펙 확정 후 반영해야 한다.
- 영상 업로드(`POST /api/v1/answers`, GCS 업로드 흐름) 구현을 먼저 완료한 뒤 AI 연동(BackgroundTask의 AI 서버 POST, `POST /api/v1/answers/{answer_id}/ai-callback` 수신)을 진행한다.
- `POST /api/v1/answers/{answer_id}/ai-callback`의 `callbackToken` 검증 로직(발급/저장/만료 방식)을 실제 구현 시 확정해야 한다.
