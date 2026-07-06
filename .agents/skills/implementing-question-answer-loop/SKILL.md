---
name: implementing-question-answer-loop
description: Implements Damso backend features for the question and answer loop, including sending questions, listing received questions, viewing received question details, read status, answer pending status, home summary, recommendations, and AI processing status. Use when implementing or modifying question APIs, answer APIs, home summary APIs, or navigation flows where Question and Answer are separate tabs.
---

# Implementing Question Answer Loop

## Scope

Use this skill for Damso backend work around the question and answer loop:

- Home summary APIs.
- Question recipient, recommendation, and send APIs.
- Received-question list, detail, read-status, and pending-answer APIs.
- Navigation behavior where Question and Answer are separate bottom-navigation tabs.

Do not implement actual answer video upload, video answer persistence, or AI analysis storage as part of this skill unless the user explicitly expands the scope. Design the question-send data so those later features can attach cleanly.

If an older `implementing-question-loop` skill exists, do not use it for this flow. Keep the old file in place unless the user explicitly asks to remove it; prefer this `implementing-question-answer-loop` skill because it separates Question and Answer tab behavior.

## Required Context

Before implementation, read:

- `docs/MVP_SCOPE.md`
- `docs/SCREEN_FLOW.md`
- `docs/API_DRAFT.md`
- `docs/DB_SCHEMA.md`
- `AGENTS.md`

Project assumptions:

- This is a FastAPI backend-only repository.
- Kakao login, Damso required agreements, role selection, and family connection already exist.
- Use Supabase PostgreSQL, sync SQLAlchemy, and Alembic migrations.
- Keep route handlers thin and place business logic in service classes.
- Do not modify `.env`, `DATABASE_URL`, JWT secrets, Supabase keys, or other real secrets.

## Product Model

Bottom navigation has these tabs:

- Home
- Questions
- Answers
- Diary
- Settings

The Questions tab is for sending questions to family members.

The Answers tab is for viewing questions sent to the current user and answering them.

Keep these as independent flows. Do not block the Questions tab just because the current user has unanswered received questions. A user with pending received questions must still be able to send questions to other family members.

## Domain Rules

### Questions Tab

- A user can send questions only to other members of the same active family.
- Exclude the current user from the recipient list.
- Reject sending a question to oneself.
- Reject sending a question to a user outside the sender's family.
- Question depth values are `tiny`, `medium`, and `deep`.
- Recommended questions are randomly selected active recommendations filtered by depth.
- A user can send either a selected recommendation or a custom question.
- When a question is sent, it must appear in the recipient's Answers tab list.

### Answers Tab

- The current user can list questions sent to them.
- The list must support latest-first and/or unanswered-first sorting.
- Each list item should include read status, answered status, `receivedAt`, sender information, and a short `questionText` representation.
- The current user can view the detail of a received question.
- Viewing detail may mark the item as read, or a separate read API may do so.
- Support filtering to unanswered questions only.
- Already answered questions should still be visible unless explicitly filtered out.
- Do not allow a user to view or mark read a question sent to someone else.
- Actual video upload and answer storage may be implemented later, but the question-send model must expose answered state.

### Home Summary

Home summary should include:

- Whether the current user is connected to a family.
- Whether a child is connected to a mother/father, or a mother/father is connected to a child.
- Today's completed count, defined as question-send pairs where the recipient completed a video answer.
- `0` completed count when no completed pairs exist so the frontend can hide badges.
- Pending received-question status, including arrival time and read status.
- Sent-question status, including whether the recipient read and answered it.
- AI processing status such as `processing`, `completed`, `failed`, or `null`.

## Recommended APIs

Use these endpoint shapes unless project docs or the user request require a narrower change:

- `GET /api/v1/home/summary`
- `GET /api/v1/questions/recipients`
- `GET /api/v1/questions/recommendations`
- `POST /api/v1/questions`
- `GET /api/v1/answers/questions`
- `GET /api/v1/answers/questions/{question_send_id}`
- `PATCH /api/v1/answers/questions/{question_send_id}/read`

API placement rules:

- Put question sending and recommendations under the `questions` area.
- Put received-question list, detail, and read handling under the `answers` area.
- Keep answer video upload APIs out of this skill unless explicitly requested.
- Scope all queries and mutations to the authenticated user.
- Return `404` or another established project-safe error for attempts to access another user's received question.

## Database Guidance

Use these tables for this loop:

- `question_recommendations`
- `question_sends`

`question_recommendations` should support active recommendations filtered by depth.

`question_sends` should include:

- `sender_user_id`
- `recipient_user_id`
- `family_id`
- `question_text`
- `depth`
- `source`
- `recommendation_id`
- `sent_at`
- `read_at`
- `answered_at`
- `status`

Interpretation rules:

- `read_at IS NOT NULL` means the recipient has read the question.
- `answered_at IS NOT NULL` or `status = answered` means the recipient has answered.
- Keep future video answer and AI analysis data extensible through later tables rather than overloading `question_sends`.

## Implementation Pattern

- Add routers under `app/api/v1/` and include them from `app/main.py`.
- Keep FastAPI handlers focused on dependency wiring, request parsing, response shaping, and HTTP error mapping.
- Put selection, permission checks, state transitions, and summary aggregation in services.
- Use Pydantic schemas for request/response contracts.
- Use sync SQLAlchemy sessions and explicit joins to enforce family membership and ownership.
- Prefer stable response aliases such as `receivedAt`, `readAt`, `answeredAt`, `questionText`, and `aiStatus`.
- Do not expose internal records that are not needed by the frontend.

## Validation Checklist

Add focused tests covering:

- Recipient list excludes the current user.
- Recommendations are filtered by depth.
- Sending a question succeeds and appears in the recipient's Answers tab list.
- Received-question list works.
- Received-question detail works.
- Detail lookup fails for a question sent to someone else.
- Only the recipient can mark a received question as read.
- Unanswered-only filtering works.
- Pending received questions do not block sending a new question.
- Sending a question to oneself fails.
- Sending a question to a non-family user fails.
- Home summary returns received-question state, sent-question state, completed count, and AI status.

## Documentation And Verification

After implementation:

- Update `docs/API_DRAFT.md`.
- Update `docs/DB_SCHEMA.md`.
- Record the actual prompt, changed files, human review points, and verification results in `docs/PROMPT_LOG.md`.
- Run `pytest`.
- Run `ruff check .`.
- If migrations were added, run `alembic upgrade head` and confirm the current revision.
