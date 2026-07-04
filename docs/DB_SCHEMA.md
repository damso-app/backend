# Damso DB Schema v0.1

이 문서는 Damso MVP ERD를 테이블 설계 초안으로 풀어 쓴 문서다. 실제 migration, SQLAlchemy 모델, DB 테이블은 아직 만들지 않는다.

## Global Rules

- 내부 PK는 `BIGINT` auto-increment 계열을 사용한다.
- 외부 API와 공유 URL에는 내부 `id` 대신 `public_id` 또는 code 계열 값을 사용한다.
- Kakao access token은 DB에 저장하지 않는다.
- 영상 파일은 DB에 직접 저장하지 않고 storage object 경로만 저장한다.
- `created_at`, `updated_at`은 변경 가능한 주요 테이블에 둔다.
- 삭제 가능한 주요 콘텐츠에는 `deleted_at`을 둔다.
- 상태 전이가 필요한 흐름에는 `status` 계열 ENUM을 둔다.
- MVP의 답변 기록 목록은 우선 `answers` 기반 조회로 처리한다. 별도 큐레이션 단위가 확정되기 전까지 `diaries`, `diary_answers`는 보류 테이블로 둔다.

## Tables

### users

목적: Damso 내부 사용자 프로필과 역할 선택 상태를 저장한다.

| Column | Type | PK | FK | Unique | Nullable | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| id | BIGINT | Y | N | Y | N | 내부 PK |
| public_id | VARCHAR(32) | N | N | Y | N | 외부 노출용 사용자 식별자 |
| display_name | VARCHAR(100) | N | N | N | Y | Kakao 프로필 또는 사용자가 수정한 이름 |
| role | user_role | N | N | N | Y | `child`, `parent` |
| status | user_status | N | N | N | N | 기본값 `active` |
| role_selected_at | TIMESTAMPTZ | N | N | N | Y | 역할 선택 시각 |
| created_at | TIMESTAMPTZ | N | N | N | N | 생성 시각 |
| updated_at | TIMESTAMPTZ | N | N | N | N | 수정 시각 |
| deleted_at | TIMESTAMPTZ | N | N | N | Y | soft delete |

인덱스 후보:

- `ux_users_public_id` unique index on `(public_id)`
- `ix_users_role_status` on `(role, status)`

### social_accounts

목적: Kakao OAuth 계정과 Damso 사용자를 연결한다. Kakao access token은 저장하지 않는다.

| Column | Type | PK | FK | Unique | Nullable | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| id | BIGINT | Y | N | Y | N | 내부 PK |
| user_id | BIGINT | N | users.id | N | N | Damso 사용자 |
| provider | oauth_provider | N | N | N | N | MVP는 `kakao` |
| provider_user_id | VARCHAR(191) | N | N | N | N | Kakao user id |
| email | VARCHAR(255) | N | N | N | Y | Kakao 제공 범위에 따라 nullable |
| profile_image_url | TEXT | N | N | N | Y | Kakao profile image |
| created_at | TIMESTAMPTZ | N | N | N | N | 생성 시각 |
| updated_at | TIMESTAMPTZ | N | N | N | N | 수정 시각 |

인덱스 후보:

- `ux_social_accounts_provider_user` unique index on `(provider, provider_user_id)`
- `ix_social_accounts_user_id` on `(user_id)`

### oauth_login_codes

목적: Kakao callback 이후 URL query로 Damso access token을 직접 전달하지 않기 위한 일회성 교환 코드를 저장한다.

| Column | Type | PK | FK | Unique | Nullable | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| id | BIGINT | Y | N | Y | N | 내부 PK |
| user_id | BIGINT | N | users.id | N | N | 로그인 완료 사용자 |
| code_hash | VARCHAR(255) | N | N | Y | N | raw `login_code`는 저장하지 않음 |
| status | login_code_status | N | N | N | N | `active`, `used`, `expired` |
| expires_at | TIMESTAMPTZ | N | N | N | N | 짧은 만료 시간 |
| used_at | TIMESTAMPTZ | N | N | N | Y | 사용 시각 |
| created_at | TIMESTAMPTZ | N | N | N | N | 생성 시각 |

인덱스 후보:

- `ux_oauth_login_codes_code_hash` unique index on `(code_hash)`
- `ix_oauth_login_codes_user_status` on `(user_id, status)`
- `ix_oauth_login_codes_expires_at` on `(expires_at)`

### families

목적: 가족방 단위를 저장한다.

| Column | Type | PK | FK | Unique | Nullable | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| id | BIGINT | Y | N | Y | N | 내부 PK |
| public_id | VARCHAR(32) | N | N | Y | N | 외부 노출용 가족방 식별자 |
| name | VARCHAR(100) | N | N | N | N | 가족방 이름 |
| created_by_user_id | BIGINT | N | users.id | N | N | 가족방 생성자 |
| status | family_status | N | N | N | N | 기본값 `active` |
| created_at | TIMESTAMPTZ | N | N | N | N | 생성 시각 |
| updated_at | TIMESTAMPTZ | N | N | N | N | 수정 시각 |
| deleted_at | TIMESTAMPTZ | N | N | N | Y | soft delete |

인덱스 후보:

- `ux_families_public_id` unique index on `(public_id)`
- `ix_families_created_by_user_id` on `(created_by_user_id)`
- `ix_families_status` on `(status)`

### family_members

목적: 사용자와 가족방의 멤버십, 가족 내 역할, 초대 합류 상태를 저장한다.

| Column | Type | PK | FK | Unique | Nullable | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| id | BIGINT | Y | N | Y | N | 내부 PK |
| family_id | BIGINT | N | families.id | N | N | 가족방 |
| user_id | BIGINT | N | users.id | N | N | 구성원 |
| member_role | family_member_role | N | N | N | N | `child`, `parent`, `member` |
| status | family_member_status | N | N | N | N | `active`, `invited`, `left`, `removed` |
| joined_at | TIMESTAMPTZ | N | N | N | Y | 합류 시각 |
| created_at | TIMESTAMPTZ | N | N | N | N | 생성 시각 |
| updated_at | TIMESTAMPTZ | N | N | N | N | 수정 시각 |

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

| Column | Type | PK | FK | Unique | Nullable | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| id | BIGINT | Y | N | Y | N | 내부 PK |
| family_id | BIGINT | N | families.id | N | N | 초대 대상 가족방 |
| created_by_user_id | BIGINT | N | users.id | N | N | 초대 코드 생성자 |
| invite_code_hash | VARCHAR(255) | N | N | Y | N | raw invite code는 저장하지 않음 |
| status | invite_code_status | N | N | N | N | `active`, `used`, `expired`, `revoked` |
| expires_at | TIMESTAMPTZ | N | N | N | N | 만료 시각 |
| used_at | TIMESTAMPTZ | N | N | N | Y | 사용 시각 |
| created_at | TIMESTAMPTZ | N | N | N | N | 생성 시각 |
| updated_at | TIMESTAMPTZ | N | N | N | N | 수정 시각 |

인덱스 후보:

- `ux_family_invite_codes_hash` unique index on `(invite_code_hash)`
- `ix_family_invite_codes_family_status` on `(family_id, status)`
- `ix_family_invite_codes_expires_at` on `(expires_at)`

### questions

목적: 질문 목록 화면에 표시할 질문 원문과 AI/기본 질문 출처를 저장한다.

| Column | Type | PK | FK | Unique | Nullable | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| id | BIGINT | Y | N | Y | N | 내부 PK |
| public_id | VARCHAR(32) | N | N | Y | N | 외부 노출용 질문 식별자 |
| family_id | BIGINT | N | families.id | N | Y | 가족별 AI 질문이면 값 존재 |
| created_by_user_id | BIGINT | N | users.id | N | Y | AI 생성 요청자 또는 직접 작성자 |
| source | question_source | N | N | N | N | `seed`, `ai`, `custom` |
| category | VARCHAR(80) | N | N | N | Y | 질문 카테고리 |
| question_text | TEXT | N | N | N | N | 질문 본문 |
| status | question_status | N | N | N | N | `active`, `archived` |
| created_at | TIMESTAMPTZ | N | N | N | N | 생성 시각 |
| updated_at | TIMESTAMPTZ | N | N | N | N | 수정 시각 |
| deleted_at | TIMESTAMPTZ | N | N | N | Y | soft delete |

인덱스 후보:

- `ux_questions_public_id` unique index on `(public_id)`
- `ix_questions_family_status` on `(family_id, status)`
- `ix_questions_source_category` on `(source, category)`

### question_sends

목적: 자녀가 특정 부모님에게 질문을 보낸 이벤트와 답변 대기 상태를 저장한다.

| Column | Type | PK | FK | Unique | Nullable | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| id | BIGINT | Y | N | Y | N | 내부 PK |
| public_id | VARCHAR(32) | N | N | Y | N | 외부 노출용 발송 식별자 |
| family_id | BIGINT | N | families.id | N | N | 가족방 scope |
| question_id | BIGINT | N | questions.id | N | N | 질문 원문 |
| sender_user_id | BIGINT | N | users.id | N | N | 질문 보낸 사용자 |
| recipient_user_id | BIGINT | N | users.id | N | N | 답변할 사용자 |
| status | question_send_status | N | N | N | N | `sent`, `answered`, `cancelled`, `expired` |
| sent_at | TIMESTAMPTZ | N | N | N | N | 발송 시각 |
| due_at | TIMESTAMPTZ | N | N | N | Y | TODO: MVP에서 답변 기한이 필요한지 확정 |
| created_at | TIMESTAMPTZ | N | N | N | N | 생성 시각 |
| updated_at | TIMESTAMPTZ | N | N | N | N | 수정 시각 |

인덱스 후보:

- `ux_question_sends_public_id` unique index on `(public_id)`
- `ix_question_sends_recipient_status` on `(recipient_user_id, status)`
- `ix_question_sends_family_sent_at` on `(family_id, sent_at DESC)`

### answers

목적: 부모님이 제출한 답변 텍스트와 영상 파일 메타데이터를 저장한다.

| Column | Type | PK | FK | Unique | Nullable | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| id | BIGINT | Y | N | Y | N | 내부 PK |
| public_id | VARCHAR(32) | N | N | Y | N | 외부 노출용 답변 식별자 |
| question_send_id | BIGINT | N | question_sends.id | Y | N | MVP는 질문 발송당 답변 1개 |
| respondent_user_id | BIGINT | N | users.id | N | N | 답변자 |
| text_answer | TEXT | N | N | N | Y | 텍스트 답변 |
| video_storage_path | TEXT | N | N | N | Y | storage object path, 파일 blob 저장 금지 |
| video_mime_type | VARCHAR(100) | N | N | N | Y | 예: `video/mp4` |
| video_duration_seconds | INTEGER | N | N | N | Y | 영상 길이 |
| video_size_bytes | INTEGER | N | N | N | Y | 파일 크기 |
| status | answer_status | N | N | N | N | 답변 자체의 제출/노출 상태. AI 처리 상태는 포함하지 않음 |
| submitted_at | TIMESTAMPTZ | N | N | N | N | 제출 시각 |
| created_at | TIMESTAMPTZ | N | N | N | N | 생성 시각 |
| updated_at | TIMESTAMPTZ | N | N | N | N | 수정 시각 |
| deleted_at | TIMESTAMPTZ | N | N | N | Y | soft delete |

인덱스 후보:

- `ux_answers_public_id` unique index on `(public_id)`
- `ux_answers_question_send_id` unique index on `(question_send_id)`
- `ix_answers_respondent_submitted_at` on `(respondent_user_id, submitted_at DESC)`

### ai_analyses

목적: 답변 transcript, 요약, 하이라이트 문장, 감정 태그, 키워드, AI 분석 상태와 실패 정보를 저장한다.

| Column | Type | PK | FK | Unique | Nullable | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| id | BIGINT | Y | N | Y | N | 내부 PK |
| answer_id | BIGINT | N | answers.id | N | N | 분석 대상 답변 |
| status | analysis_status | N | N | N | N | AI 분석 job 상태 |
| transcript | TEXT | N | N | N | Y | 영상/음성에서 추출한 전체 전사 또는 텍스트 정규화 결과 |
| summary | TEXT | N | N | N | Y | 답변 요약 |
| highlight_quote | TEXT | N | N | N | Y | 다이어리/회고록에 노출하기 좋은 대표 문장 |
| emotion_tags | JSONB | N | N | N | Y | 감정 태그 배열. 예: `["warm", "nostalgic"]` |
| keywords | JSONB | N | N | N | Y | 키워드 배열 |
| model_name | VARCHAR(100) | N | N | N | Y | 사용 모델 |
| model_metadata | JSONB | N | N | N | Y | 토큰 사용량 등 |
| error_reason | TEXT | N | N | N | Y | 실패 사유 |
| requested_at | TIMESTAMPTZ | N | N | N | N | 요청 시각 |
| completed_at | TIMESTAMPTZ | N | N | N | Y | 완료 시각 |
| created_at | TIMESTAMPTZ | N | N | N | N | 생성 시각 |
| updated_at | TIMESTAMPTZ | N | N | N | N | 수정 시각 |

인덱스 후보:

- `ix_ai_analyses_answer_status` on `(answer_id, status)`
- `ix_ai_analyses_status_requested_at` on `(status, requested_at)`

#### answers.status와 ai_analyses.status 책임 분리

`answers.status`는 답변 레코드 자체의 제출 여부와 노출 가능 여부만 표현한다. 예를 들어 답변이 저장됐는지, 사용자에게 숨김 처리됐는지 같은 상태다.

`ai_analyses.status`는 요약, transcript, 감정 태그 생성 같은 AI 분석 job의 처리 상태만 표현한다. AI 분석이 실패해도 원본 답변은 `answers.status = submitted`로 남을 수 있다. 반대로 숨김 처리된 답변은 AI 분석이 완료됐더라도 목록에서 제외할 수 있다.

### diaries (deferred)

목적: 가족 다이어리 목록/상세 화면의 큐레이션 단위를 저장한다.

MVP 재검토 결과, 현재 화면의 "답변 기록" 목록은 `answers`를 `question_sends.family_id`, `submitted_at`, `respondent_user_id` 기준으로 조회하고 `ai_analyses.summary`, `highlight_quote`, `emotion_tags`를 조인하면 우선 구현 가능하다. 별도 다이어리 편집/묶음/발행 개념이 명확해지기 전까지 `diaries`는 보류 테이블로 둔다.

| Column | Type | PK | FK | Unique | Nullable | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| id | BIGINT | Y | N | Y | N | 내부 PK |
| public_id | VARCHAR(32) | N | N | Y | N | 외부 노출용 다이어리 식별자 |
| family_id | BIGINT | N | families.id | N | N | 가족방 |
| created_by_user_id | BIGINT | N | users.id | N | Y | 시스템 생성이면 nullable |
| title | VARCHAR(200) | N | N | N | N | 다이어리 제목 |
| preview | TEXT | N | N | N | Y | 목록 미리보기 |
| status | diary_status | N | N | N | N | `draft`, `published`, `hidden` |
| created_at | TIMESTAMPTZ | N | N | N | N | 생성 시각 |
| updated_at | TIMESTAMPTZ | N | N | N | N | 수정 시각 |
| deleted_at | TIMESTAMPTZ | N | N | N | Y | soft delete |

인덱스 후보:

- `ux_diaries_public_id` unique index on `(public_id)`
- `ix_diaries_family_created_at` on `(family_id, created_at DESC)`
- `ix_diaries_family_status` on `(family_id, status)`

### diary_answers (deferred)

목적: 다이어리와 답변의 다대다 관계를 저장한다.

`diaries`가 MVP 보류이므로 이 조인 테이블도 함께 보류한다. 답변 기록 목록은 우선 `answers` 직접 조회로 처리한다.

| Column | Type | PK | FK | Unique | Nullable | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| id | BIGINT | Y | N | Y | N | 내부 PK |
| diary_id | BIGINT | N | diaries.id | N | N | 다이어리 |
| answer_id | BIGINT | N | answers.id | N | N | 연결 답변 |
| created_at | TIMESTAMPTZ | N | N | N | N | 생성 시각 |

인덱스 후보:

- `ux_diary_answers_diary_answer` unique index on `(diary_id, answer_id)`
- `ix_diary_answers_answer_id` on `(answer_id)`

### memoirs

목적: 가족 답변 또는 향후 다이어리 기반 회고록 생성 결과와 생성 상태를 저장한다.

| Column | Type | PK | FK | Unique | Nullable | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| id | BIGINT | Y | N | Y | N | 내부 PK |
| public_id | VARCHAR(32) | N | N | Y | N | 외부 노출용 회고록 식별자 |
| family_id | BIGINT | N | families.id | N | N | 가족방 |
| requested_by_user_id | BIGINT | N | users.id | N | N | 생성 요청자 |
| title | VARCHAR(200) | N | N | N | Y | 회고록 제목 |
| generated_text | TEXT | N | N | N | Y | 생성 결과 |
| generation_status | generation_status | N | N | N | N | `pending`, `running`, `completed`, `failed` |
| error_reason | TEXT | N | N | N | Y | 실패 사유 |
| requested_at | TIMESTAMPTZ | N | N | N | N | 요청 시각 |
| completed_at | TIMESTAMPTZ | N | N | N | Y | 완료 시각 |
| created_at | TIMESTAMPTZ | N | N | N | N | 생성 시각 |
| updated_at | TIMESTAMPTZ | N | N | N | N | 수정 시각 |
| deleted_at | TIMESTAMPTZ | N | N | N | Y | soft delete |

인덱스 후보:

- `ux_memoirs_public_id` unique index on `(public_id)`
- `ix_memoirs_family_created_at` on `(family_id, created_at DESC)`
- `ix_memoirs_generation_status` on `(generation_status)`

### memoir_items

목적: 회고록 생성에 사용된 source item 목록과 정렬 순서를 저장한다.

`memoir_diaries`보다 `memoir_items` 구조를 우선 제안한다. MVP에서 다이어리를 보류하더라도 회고록은 답변 기반으로 생성할 수 있고, 이후 다이어리 단위가 확정되면 같은 테이블에서 `source_type = diary`를 추가로 사용할 수 있다.

| Column | Type | PK | FK | Unique | Nullable | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| id | BIGINT | Y | N | Y | N | 내부 PK |
| memoir_id | BIGINT | N | memoirs.id | N | N | 회고록 |
| source_type | memoir_item_source_type | N | N | N | N | `answer`, `diary` |
| answer_id | BIGINT | N | answers.id | N | Y | `source_type = answer`일 때 값 존재 |
| diary_id | BIGINT | N | diaries.id | N | Y | `source_type = diary`일 때 값 존재. diaries 보류 중 |
| sort_order | INTEGER | N | N | N | N | 회고록 구성 순서 |
| created_at | TIMESTAMPTZ | N | N | N | N | 생성 시각 |

제약 후보:

- `CHECK ((source_type = 'answer' AND answer_id IS NOT NULL AND diary_id IS NULL) OR (source_type = 'diary' AND diary_id IS NOT NULL AND answer_id IS NULL))`

인덱스 후보:

- `ux_memoir_items_memoir_sort_order` unique index on `(memoir_id, sort_order)`
- `ux_memoir_items_memoir_answer` unique index on `(memoir_id, answer_id)` where `answer_id IS NOT NULL`
- `ux_memoir_items_memoir_diary` unique index on `(memoir_id, diary_id)` where `diary_id IS NOT NULL`
- `ix_memoir_items_answer_id` on `(answer_id)`
- `ix_memoir_items_diary_id` on `(diary_id)`

### share_links

목적: 다이어리 또는 회고록을 외부 가족에게 공유하는 링크를 저장한다.

`diaries`가 MVP 보류라면 공유 링크의 MVP 1차 대상은 `memoir` 또는 답변 기반 상세 화면으로 재검토해야 한다. 현재 스키마는 다이어리 공유 요구가 확정될 경우를 대비한 후보 구조다.

| Column | Type | PK | FK | Unique | Nullable | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| id | BIGINT | Y | N | Y | N | 내부 PK |
| family_id | BIGINT | N | families.id | N | N | 공유 대상이 속한 가족방 |
| created_by_user_id | BIGINT | N | users.id | N | N | 공유 링크 생성자 |
| diary_id | BIGINT | N | diaries.id | N | Y | `target_type = diary`일 때 값 존재. diaries 보류 중 |
| memoir_id | BIGINT | N | memoirs.id | N | Y | `target_type = memoir`일 때 값 존재 |
| share_code_hash | VARCHAR(255) | N | N | Y | N | raw share code는 저장하지 않음 |
| target_type | share_target_type | N | N | N | N | `diary`, `memoir` |
| permission_scope | share_permission_scope | N | N | N | N | MVP는 `read_only` |
| status | share_link_status | N | N | N | N | `active`, `expired`, `revoked` |
| expires_at | TIMESTAMPTZ | N | N | N | Y | 만료 시각 |
| revoked_at | TIMESTAMPTZ | N | N | N | Y | 회수 시각 |
| created_at | TIMESTAMPTZ | N | N | N | N | 생성 시각 |
| updated_at | TIMESTAMPTZ | N | N | N | N | 수정 시각 |

제약 후보:

- `CHECK ((target_type = 'diary' AND diary_id IS NOT NULL AND memoir_id IS NULL) OR (target_type = 'memoir' AND memoir_id IS NOT NULL AND diary_id IS NULL))`

인덱스 후보:

- `ux_share_links_code_hash` unique index on `(share_code_hash)`
- `ix_share_links_family_status` on `(family_id, status)`
- `ix_share_links_diary_id` on `(diary_id)`
- `ix_share_links_memoir_id` on `(memoir_id)`
- `ix_share_links_expires_at` on `(expires_at)`

## ENUM Candidates

| ENUM | Values |
| --- | --- |
| user_role | `child`, `parent` |
| user_status | `active`, `disabled` |
| oauth_provider | `kakao` |
| login_code_status | `active`, `used`, `expired` |
| family_status | `active`, `archived` |
| family_member_role | `child`, `parent`, `member` |
| family_member_status | `active`, `invited`, `left`, `removed` |
| invite_code_status | `active`, `used`, `expired`, `revoked` |
| question_source | `seed`, `ai`, `custom` |
| question_status | `active`, `archived` |
| question_send_status | `sent`, `answered`, `cancelled`, `expired` |
| answer_status | `submitted`, `hidden` |
| analysis_status | `pending`, `running`, `completed`, `failed` |
| diary_status | `draft`, `published`, `hidden` |
| generation_status | `pending`, `running`, `completed`, `failed` |
| memoir_item_source_type | `answer`, `diary` |
| share_target_type | `diary`, `memoir` |
| share_permission_scope | `read_only` |
| share_link_status | `active`, `expired`, `revoked` |

## TODO

- `MVP_SCOPE.md`에서 공유 링크가 포함 기능과 제외 기능에 동시에 적혀 있어 제품 범위를 확정해야 한다.
- `docs/API_DRAFT.md`에 공유 링크 API를 유지할지 확정해야 한다. 유지한다면 `POST /api/v1/share-links`, `GET /api/v1/share-links/{share_code}` 추가를 권장한다.
- API path parameter가 내부 `id`인지 `public_id`인지 확정해야 한다. DB 설계상 `public_id` 사용을 권장한다.
- 질문 목록의 기본 질문이 전역 seed인지, 가족별 복사본인지 확정해야 한다. 현재 설계는 전역 질문은 `family_id = NULL`, 가족별 AI/custom 질문은 `family_id` 존재로 처리한다.
- 답변이 텍스트와 영상 중 하나만 필수인지, 둘 다 허용인지 확정해야 한다.
- AI 분석 결과의 `transcript`, `highlight_quote`, `emotion_tags`, `keywords`, `model_metadata` 구조를 실제 프롬프트 구현 시 확정해야 한다.
- 다이어리 목록/상세가 독립 큐레이션 화면인지, 답변 기록 목록의 다른 표현인지 확정해야 한다. 답변 기반 조회로 충분하면 `diaries`, `diary_answers`는 MVP migration에서 제외한다.
- 공유 링크가 보류된 `diaries`를 직접 공유해야 하는지, `memoirs` 또는 답변 상세를 공유하면 충분한지 확정해야 한다.
- 공유 링크 raw code를 재표시해야 하는 요구가 있는지 확정해야 한다. 현재 설계는 raw code 저장 없이 생성 시 1회 표시를 우선한다.
- 가족방 탈퇴/삭제 정책과 보존 기간을 확정해야 한다.
