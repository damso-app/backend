# Damso DB Schema v0.1

이 문서는 Damso MVP ERD를 테이블 설계 초안으로 풀어 쓴 문서다. 현재 `users`, `social_accounts`, `oauth_login_codes`는 Kakao 로그인 최소 범위로 SQLAlchemy 모델과 Alembic migration을 작성했고, 나머지 테이블은 아직 설계 초안이다.

## Global Rules

- 내부 PK는 `BIGINT` auto-increment 계열을 사용한다.
- 외부 API와 공유 URL에는 내부 `id` 대신 `public_id` 또는 code 계열 값을 사용한다.
- Kakao access token은 DB에 저장하지 않는다.
- 영상 파일은 DB에 직접 저장하지 않고 storage object 경로만 저장한다.
- `created_at`, `updated_at`은 변경 가능한 주요 테이블에 둔다.
- 삭제 가능한 주요 콘텐츠에는 `deleted_at`을 둔다.
- 상태 전이가 필요한 흐름에는 `status` 계열 ENUM을 둔다.
- 영상 원본(`answers.video_origin_url`)과 AI 가공본(`video_clips.hls_url`)은 분리해서 저장한다.
- 네컷 그리드 목록은 `answers`를 `family_id`, `DATE(created_at)` 기준으로 `GROUP BY` 조회한다. 별도 그리드 테이블은 두지 않는다.
- `video_clips`는 별도 `status` 컬럼을 두지 않는다. row 존재 여부가 곧 `answers.status = completed`를 의미하는 불변식이다. 백엔드는 `video_clips` insert와 `answers.status = completed` 업데이트를 같은 트랜잭션으로 처리해서, 그리드에는 `completed`로 보이는데 클립 조회가 실패하는 순간이 생기지 않게 한다.
- AI 처리 완료/실패는 폴링 API 대신 Supabase Realtime Broadcast(`family:{family_id}` 채널)로 알린다. 상세 payload는 `docs/API_DRAFT.md`의 Realtime 절을 따른다.

## Tables

### users

목적: Damso 내부 사용자 프로필과 역할 선택 상태를 저장한다.

| Column           | Type         | PK  | FK  | Unique | Nullable | Notes                                  |
| ---------------- | ------------ | --- | --- | ------ | -------- | -------------------------------------- |
| id               | BIGINT       | Y   | N   | Y      | N        | 내부 PK                                |
| public_id        | VARCHAR(32)  | N   | N   | Y      | N        | 외부 노출용 사용자 식별자              |
| display_name     | VARCHAR(100) | N   | N   | N      | Y        | Kakao 프로필 또는 사용자가 수정한 이름 |
| role             | user_role    | N   | N   | N      | Y        | `child`, `parent`                      |
| status           | user_status  | N   | N   | N      | N        | 기본값 `active`                        |
| role_selected_at | TIMESTAMPTZ  | N   | N   | N      | Y        | 역할 선택 시각                         |
| created_at       | TIMESTAMPTZ  | N   | N   | N      | N        | 생성 시각                              |
| updated_at       | TIMESTAMPTZ  | N   | N   | N      | N        | 수정 시각                              |
| deleted_at       | TIMESTAMPTZ  | N   | N   | N      | Y        | soft delete                            |

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

### families

목적: 가족방 단위를 저장한다.

| Column             | Type          | PK  | FK       | Unique | Nullable | Notes                     |
| ------------------ | ------------- | --- | -------- | ------ | -------- | ------------------------- |
| id                 | BIGINT        | Y   | N        | Y      | N        | 내부 PK                   |
| public_id          | VARCHAR(32)   | N   | N        | Y      | N        | 외부 노출용 가족방 식별자 |
| name               | VARCHAR(100)  | N   | N        | N      | N        | 가족방 이름               |
| created_by_user_id | BIGINT        | N   | users.id | N      | N        | 가족방 생성자             |
| status             | family_status | N   | N        | N      | N        | 기본값 `active`           |
| created_at         | TIMESTAMPTZ   | N   | N        | N      | N        | 생성 시각                 |
| updated_at         | TIMESTAMPTZ   | N   | N        | N      | N        | 수정 시각                 |
| deleted_at         | TIMESTAMPTZ   | N   | N        | N      | Y        | soft delete               |

인덱스 후보:

- `ux_families_public_id` unique index on `(public_id)`
- `ix_families_created_by_user_id` on `(created_by_user_id)`
- `ix_families_status` on `(status)`

### family_members

목적: 사용자와 가족방의 멤버십, 가족 내 역할, 초대 합류 상태를 저장한다.

| Column      | Type                 | PK  | FK          | Unique | Nullable | Notes                                  |
| ----------- | -------------------- | --- | ----------- | ------ | -------- | -------------------------------------- |
| id          | BIGINT               | Y   | N           | Y      | N        | 내부 PK                                |
| family_id   | BIGINT               | N   | families.id | N      | N        | 가족방                                 |
| user_id     | BIGINT               | N   | users.id    | N      | N        | 구성원                                 |
| member_role | family_member_role   | N   | N           | N      | N        | `child`, `parent`, `member`            |
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

MVP에서는 가족방 내부 권한 판단에 `family_members.member_role`을 source of truth로 사용한다. `users.role`은 온보딩 기본값과 신규 가족방 멤버십 생성 시 초기값으로만 사용한다. 이후 한 사용자가 여러 가족방에서 다른 역할을 가질 수 있으므로 API 권한 체크는 `users.role`만 보지 않는다.

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

### questions

목적: 질문 목록 화면에 표시할 질문 원문과 AI/기본 질문 출처를 저장한다.

| Column             | Type            | PK  | FK          | Unique | Nullable | Notes                           |
| ------------------ | --------------- | --- | ----------- | ------ | -------- | ------------------------------- |
| id                 | BIGINT          | Y   | N           | Y      | N        | 내부 PK                         |
| public_id          | VARCHAR(32)     | N   | N           | Y      | N        | 외부 노출용 질문 식별자         |
| family_id          | BIGINT          | N   | families.id | N      | Y        | 가족별 AI 질문이면 값 존재      |
| created_by_user_id | BIGINT          | N   | users.id    | N      | Y        | AI 생성 요청자 또는 직접 작성자 |
| source             | question_source | N   | N           | N      | N        | `seed`, `ai`, `custom`          |
| category           | VARCHAR(80)     | N   | N           | N      | Y        | 질문 카테고리                   |
| question_text      | TEXT            | N   | N           | N      | N        | 질문 본문                       |
| status             | question_status | N   | N           | N      | N        | `active`, `archived`            |
| created_at         | TIMESTAMPTZ     | N   | N           | N      | N        | 생성 시각                       |
| updated_at         | TIMESTAMPTZ     | N   | N           | N      | N        | 수정 시각                       |
| deleted_at         | TIMESTAMPTZ     | N   | N           | N      | Y        | soft delete                     |

인덱스 후보:

- `ux_questions_public_id` unique index on `(public_id)`
- `ix_questions_family_status` on `(family_id, status)`
- `ix_questions_source_category` on `(source, category)`

### question_sends

목적: 자녀가 특정 부모님에게 질문을 보낸 이벤트와 답변 대기 상태를 저장한다.

| Column            | Type                 | PK  | FK           | Unique | Nullable | Notes                                      |
| ----------------- | -------------------- | --- | ------------ | ------ | -------- | ------------------------------------------ |
| id                | BIGINT               | Y   | N            | Y      | N        | 내부 PK                                    |
| public_id         | VARCHAR(32)          | N   | N            | Y      | N        | 외부 노출용 발송 식별자                    |
| family_id         | BIGINT               | N   | families.id  | N      | N        | 가족방 scope                               |
| question_id       | BIGINT               | N   | questions.id | N      | N        | 질문 원문                                  |
| sender_user_id    | BIGINT               | N   | users.id     | N      | N        | 질문 보낸 사용자                           |
| recipient_user_id | BIGINT               | N   | users.id     | N      | N        | 답변할 사용자                              |
| status            | question_send_status | N   | N            | N      | N        | `sent`, `answered`, `cancelled`, `expired` |
| sent_at           | TIMESTAMPTZ          | N   | N            | N      | N        | 발송 시각                                  |
| due_at            | TIMESTAMPTZ          | N   | N            | N      | Y        | TODO: MVP에서 답변 기한이 필요한지 확정    |
| created_at        | TIMESTAMPTZ          | N   | N            | N      | N        | 생성 시각                                  |
| updated_at        | TIMESTAMPTZ          | N   | N            | N      | N        | 수정 시각                                  |

인덱스 후보:

- `ux_question_sends_public_id` unique index on `(public_id)`
- `ix_question_sends_recipient_status` on `(recipient_user_id, status)`
- `ix_question_sends_family_sent_at` on `(family_id, sent_at DESC)`

### answers

목적: 부모님이 제출한 답변 영상 파일 메타데이터를 저장한다.

| Column                 | Type          | PK  | FK                | Unique | Nullable | Notes                                                                         |
| ---------------------- | ------------- | --- | ----------------- | ------ | -------- | ----------------------------------------------------------------------------- |
| id                     | BIGINT        | Y   | N                 | Y      | N        | 내부 PK                                                                       |
| question_send_id       | BIGINT        | N   | question_sends.id | Y      | N        | MVP는 질문 발송당 답변 1개. 누가 누구에게 언제 보냈는지 추적                  |
| user_id                | BIGINT        | N   | users.id          | N      | N        | 답변자                                                                        |
| family_id              | BIGINT        | N   | families.id       | N      | N        | `question_sends.family_id` 비정규화 복사. 네컷 그리드 조회용                  |
| video_origin_url       | TEXT          | N   | N                 | N      | Y        | 영상 원본 storage object path, 파일 blob 저장 금지                            |
| video_mime_type        | VARCHAR(100)  | N   | N                 | N      | Y        | 예: `video/mp4`                                                               |
| video_duration_seconds | INTEGER       | N   | N                 | N      | Y        | 영상 길이                                                                     |
| video_size_bytes       | INTEGER       | N   | N                 | N      | Y        | 파일 크기                                                                     |
| status                 | answer_status | N   | N                 | N      | N        | 제출부터 AI 처리까지의 상태. `submitted`, `processing`, `completed`, `failed` |
| submitted_at           | TIMESTAMPTZ   | N   | N                 | N      | N        | 제출 시각                                                                     |
| created_at             | TIMESTAMPTZ   | N   | N                 | N      | N        | 생성 시각                                                                     |
| updated_at             | TIMESTAMPTZ   | N   | N                 | N      | N        | 수정 시각                                                                     |
| deleted_at             | TIMESTAMPTZ   | N   | N                 | N      | Y        | soft delete                                                                   |

인덱스 후보:

- `ux_answers_question_send_id` unique index on `(question_send_id)`
- `ix_answers_user_submitted_at` on `(user_id, submitted_at DESC)`
- `ix_answers_family_created_at` on `(family_id, created_at DESC)`. 네컷 그리드는 이 인덱스로 `family_id`, `DATE(created_at)` 기준 `GROUP BY` 조회

### video_clips

목적: 답변 영상의 AI 가공 결과(썸네일, HLS 스트리밍 URL, 전사, 제목, 명대사, 요약, 감정 태그)를 저장한다.

| Column        | Type         | PK  | FK         | Unique | Nullable | Notes                                       |
| ------------- | ------------ | --- | ---------- | ------ | -------- | ------------------------------------------- |
| id            | BIGINT       | Y   | N          | Y      | N        | 내부 PK                                     |
| answer_id     | BIGINT       | N   | answers.id | Y      | N        | 원본 답변. MVP는 답변당 클립 1개            |
| thumbnail_url | TEXT         | N   | N          | N      | Y        | 네컷 그리드/썸네일 표시용                   |
| hls_url       | TEXT         | N   | N          | N      | Y        | 가공된 스트리밍용 영상 URL                  |
| transcript    | TEXT         | N   | N          | N      | Y        | 영상/음성에서 추출한 전체 전사              |
| title         | VARCHAR(200) | N   | N          | N      | Y        | 클립 제목                                   |
| quote         | TEXT         | N   | N          | N      | Y        | 바텀시트/상세에 노출하는 대표 명대사        |
| summary       | TEXT         | N   | N          | N      | Y        | 답변 요약                                   |
| emotion_tags  | JSONB        | N   | N          | N      | Y        | 감정 태그 배열. 예: `["warm", "nostalgic"]` |
| created_at    | TIMESTAMPTZ  | N   | N          | N      | N        | 생성 시각                                   |

인덱스 후보:

- `ux_video_clips_answer_id` unique index on `(answer_id)`

## ENUM Candidates

| ENUM                 | Values                                           |
| -------------------- | ------------------------------------------------ |
| user_role            | `child`, `parent`                                |
| user_status          | `active`, `disabled`                             |
| oauth_provider       | `kakao`                                          |
| login_code_status    | `active`, `used`, `expired`                      |
| family_status        | `active`, `archived`                             |
| family_member_role   | `child`, `parent`, `member`                      |
| family_member_status | `active`, `invited`, `left`, `removed`           |
| invite_code_status   | `active`, `used`, `expired`, `revoked`           |
| question_source      | `seed`, `ai`, `custom`                           |
| question_status      | `active`, `archived`                             |
| question_send_status | `sent`, `answered`, `cancelled`, `expired`       |
| answer_status        | `submitted`, `processing`, `completed`, `failed` |

## TODO

- API path parameter가 내부 `id`인지 `public_id`인지 확정해야 한다. `answers`, `video_clips`는 현재 외부 노출 API가 없어 `public_id`를 두지 않았다.
- 질문 목록의 기본 질문이 전역 seed인지, 가족별 복사본인지 확정해야 한다. 현재 설계는 전역 질문은 `family_id = NULL`, 가족별 AI/custom 질문은 `family_id` 존재로 처리한다.
- `video_clips.transcript`, `quote`, `summary`, `emotion_tags` 구조를 실제 프롬프트 구현 시 확정해야 한다.
- 가족방 탈퇴/삭제 정책과 보존 기간을 확정해야 한다.
