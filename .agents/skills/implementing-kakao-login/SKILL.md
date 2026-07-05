---
name: implementing-kakao-login
description: Codex uses this skill when designing, implementing, or verifying Kakao OAuth login in the Damso FastAPI backend, especially flows where the backend receives a Kakao authorization code, calls Kakao token and userinfo APIs, and issues Damso-owned access tokens.
---

# Implementing Kakao Login

## Core Flow

Use this server-owned OAuth flow as the baseline:

1. Receive the Kakao authorization code in the Damso backend.
2. Exchange the authorization code with Kakao's token API from the backend.
3. Use the Kakao access token only on the backend to call Kakao's userinfo API.
4. Find or create the Damso user identity from Kakao userinfo.
5. Issue a Damso access token for Damso APIs.
6. Return only the Damso authentication result to the frontend.

Do not send the Kakao access token to the frontend. Treat Kakao tokens as server-side provider credentials, and avoid logging them.

## Token Delivery Rule

Prefer a `login_code` exchange pattern instead of placing an access token in a URL query string.

- Redirect browser flows may return a short-lived, one-time `login_code` to the frontend.
- The frontend exchanges `login_code` with the Damso backend for the Damso access token.
- The Damso access token must not be delivered directly through URL query parameters.
- The frontend uses the Damso access token with `Authorization: Bearer <token>` for protected Damso API requests.

## Implementation Guardrails

- Keep FastAPI route handlers thin; put OAuth exchange, user lookup, token issuance, and error mapping in services.
- Put Kakao OAuth settings in `app/core/config.py`.
- Use `/api/v1` for versioned authentication endpoints. Keep `/health` unprefixed.
- Do not hardcode Kakao client secrets, API keys, JWT secrets, Supabase keys, or any real secret values.
- Do not create or commit a real `.env` file. Use placeholders only in `.env.example` when environment documentation is needed.
- Do not add database tables, SQLAlchemy models, or Alembic migrations before the ERD is confirmed.
- Return stable API errors for invalid authorization codes, Kakao API failures, expired `login_code` values, and reused `login_code` values.

## Verification Checklist

- Add focused tests for successful login, Kakao token exchange failure, Kakao userinfo failure, expired `login_code`, and reused `login_code`.
- Confirm Kakao access tokens never appear in frontend responses, redirect URLs, application logs, or test fixtures.
- Confirm protected endpoint examples use `Authorization: Bearer <Damso access token>`.
- Run `pytest` and `ruff check .` when dependencies are available.

## Documentation

After implementing or changing Kakao login behavior:

- Update `docs/API_DRAFT.md` with endpoint contracts, request/response examples, auth header usage, and the `login_code` exchange behavior.
- Update `docs/PROMPT_LOG.md` with the prompt used, changed files, human review points, and verification results.
