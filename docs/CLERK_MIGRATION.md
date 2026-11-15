# Clerk authentication: plan and design

Status: implemented behind `AUTH_PROVIDER` (default `local`); see "How to switch" at the end. Sources: Clerk's docs
read on 15 Nov 2026 (React quickstart, session tokens, manual JWT verification, webhooks overview, backend
`authenticateRequest`, migration overview) and `clerk/clerk-sdk-python`.

## Goals

- Clerk is the only way to sign in once the switch is made. No password is typed into, stored by or reset through Synex.
- Nobody loses data. An existing Synex user is matched to their Clerk account by **verified email**, and keeps the same
  `users.id`, so every campaign, lead, conversation and sender account stays attached.
- Nothing about the workspace model changes: roles, team seats and `resolve_workspace` are untouched.

## How a request is authenticated

1. The browser signs in with Clerk's `<SignIn />` and gets a short-lived session JWT (`getToken()`, refreshed about
   every 60 s).
2. Every API call sends `Authorization: Bearer <jwt>`. The cookie path is not used in Clerk mode.
3. `app/clerk_auth.py` verifies the token with PyJWT and Clerk's JWKS (`<frontend api>/.well-known/jwks.json`):
   RS256 only, `exp`, `nbf` and `iss` checked, and `azp` (if present) must be one of `CORS_ORIGINS`. Keys are cached.
4. The token's `sub` (a Clerk user id) is mapped to a Synex user:
   - `users.clerk_user_id` matches: done.
   - Otherwise the backend asks Clerk's Backend API for that user (`GET /v1/users/{sub}`, authenticated with
     `CLERK_SECRET_KEY`), takes the **primary email**, and links only if that email is **verified**:
     an existing row with the same email gets its `clerk_user_id` set; no row means a new user is created.
   - An unverified email is never linked or created (that would let anyone claim an existing account).
   The email is looked up rather than read from a session-token claim, so no Dashboard customisation is needed.
5. The rest of the app (`resolve_workspace`, roles, the assistant tickets) is unchanged.

## Webhook (optional, keeps profiles in step)

`POST /clerk/webhook`, public, verified with the Standard Webhooks scheme Clerk uses (Svix): HMAC-SHA256 over
`svix-id.svix-timestamp.body` with the base64 key after `whsec_`, a 5 minute timestamp tolerance, constant-time
compare. `user.created` and `user.updated` update name, avatar and verified primary email on a linked user;
`user.deleted` only unlinks (data is never deleted by a webhook). Delivery is at least once, so every handler is an
idempotent update: repeating an event changes nothing. Without a signing secret the route answers 503.

## Environment names

Docs and the owner's list differ on the webhook secret name; both are accepted.

| Variable | Where | Notes |
|---|---|---|
| `AUTH_PROVIDER` | backend | `local` (default, used by the tests) or `clerk` |
| `CLERK_SECRET_KEY` | backend | Backend API calls; never sent to the browser |
| `CLERK_PUBLISHABLE_KEY` or `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` | backend | Used to derive the issuer and JWKS URL |
| `CLERK_ISSUER` | backend, optional | Overrides the derived issuer |
| `CLERK_WEBHOOK_SECRET` or `CLERK_WEBHOOK_SIGNING_SECRET` | backend | `whsec_...`, only for the webhook |
| `VITE_CLERK_PUBLISHABLE_KEY` | frontend, build time | Presence turns Clerk mode on in the UI |

## What changes in the product

- `/login` and `/register` render Clerk's `<SignIn />` and `<SignUp />`. Forgot and reset password redirect to
  `/login`. The user menu signs out through Clerk.
- In Clerk mode `POST /auth` login, register and reset actions answer 410, and `POST /auth/logout` is a no-op.
  `GET /auth/me` and `PUT /auth/me` work through the Clerk token.
- Old cookie sessions stop being accepted in Clerk mode.

## Risks and how they are handled

| Risk | Handling |
|---|---|
| Locked out by a misconfiguration | The switch is one variable. Setting `AUTH_PROVIDER=local` and restarting restores password sign-in. Existing password hashes are left in place. |
| Account takeover by email | Link only a verified primary email. |
| Stale or forged tokens | Signature, expiry, issuer and authorized party all checked. A bad token is a 401 with no detail. |
| Webhook replay or forgery | Signature and a 5 minute tolerance; handlers are idempotent updates. |
| Test and CI breakage | Tests run in `local` mode. Clerk paths are tested with locally generated RSA keys and a mocked Backend API. No call to Clerk is made in automated tests. |
| Passwords | Not migrated. Existing users set a Clerk password the first time, or use an emailed code, with the same email. Clerk can import bcrypt hashes through its Backend API if wanted later. |

## How to switch (owner)

1. In Clerk, enable the sign-in methods wanted (email code or password) and add the app's origin.
2. Make sure the backend `.env` has `CLERK_SECRET_KEY` and the publishable key, the frontend `.env` has
   `VITE_CLERK_PUBLISHABLE_KEY`, and set `AUTH_PROVIDER=clerk` in the backend `.env`.
3. Back up `backend/synex.db`, restart the API (migration `008_clerk_user_id` adds one nullable column), rebuild the frontend.
4. Sign in with the same email as the existing Synex account. The first request links the accounts.
