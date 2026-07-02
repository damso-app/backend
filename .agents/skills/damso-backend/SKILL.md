---
name: damso-backend
description: Use this skill when implementing the Damso FastAPI backend, including API routers, Pydantic schemas, services, Supabase/PostgreSQL integration, AI analysis flows, tests, and required documentation updates.
---

# Damso Backend

## Before Implementation

Read these files before making backend changes:

- `docs/MVP_SCOPE.md`
- `docs/SCREEN_FLOW.md`
- `docs/API_DRAFT.md`
- `AGENTS.md`

Use the Figma-defined MVP as the product boundary. Do not add features that are not in the MVP unless the user explicitly asks for them.

## Backend Conventions

- This is a backend-only repository. Do not create a `backend/` folder or frontend code.
- Keep route handlers thin. Put business logic in services.
- Put environment and application settings in `app/core/config.py`.
- Use `/api/v1` for versioned API routes. Keep `/health` unprefixed.
- Do not hardcode secrets. Do not create or commit a real `.env` file.
- Do not add DB tables, SQLAlchemy models, or Alembic migrations before the ERD is confirmed.

## Expected Workflows

- For API work, update `docs/API_DRAFT.md` with added or changed endpoints.
- For AI question generation, answer summarization, or analysis prompt work, update `docs/PROMPT_LOG.md`.
- Add focused pytest coverage for new behavior.
- Run `pytest` and `ruff check .` when dependencies are available.
