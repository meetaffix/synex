# LinkedIn integration

## Two distinct flows

`GET /linkedin/login` starts platform sign-in with `openid profile email`. `POST /linkedin/connect` requires an authenticated workspace administrator and starts the publishing authorization with the configured scopes. Both return to `GET /linkedin/callback`; a server-side one-time state identifies the intended flow.

State is random, hashed in the database, expires after ten minutes, and is atomically consumed. It is bound to an HttpOnly SameSite cookie. Connection callbacks also recheck the current session and workspace role. A nonce binds the ID token. The code exchange uses the configured exact redirect URI and client secret. ID tokens require RS256 signature verification against LinkedIn JWKS, correct issuer/audience, expiry/issued-at, subject and nonce; userinfo must return the same subject. Access tokens are Fernet-encrypted using a dedicated configured secret; neither token nor secret is serialized to the browser.

Provider failures result in an error redirect, never a connected record. Account identity uses the LinkedIn subject, not user-entered profile fields. Reauthorization updates the existing connection in the same workspace. Expiry and granted scopes drive capabilities. When the token response omits scope, the requested grant is recorded according to OAuth 2.0 semantics. Upstream product approval is still enforced by LinkedIn when called; a listed scope is not proof of every API product being approved.

Sign-in identities are separate from publishing connections. Existing email accounts must explicitly link a sign-in identity via Settings (`POST /linkedin/link-sign-in`), from the same authenticated actor. Publishing consent never grants sign-in access. Unlinking requires the SYNEX password to avoid locking out a LinkedIn-only account. New LinkedIn sign-ups require a verified returned email. Publishing disconnect deletes the local token and pauses pending work, while keeping post history and the sign-in identity. Automatic refresh is not assumed; users reauthorize when needed. Upstream consent can be revoked in LinkedIn permitted services settings.

## Capability matrix

| Operation | Implementation / gate |
|---|---|
| Platform LinkedIn sign-in | OIDC, verified identity, no publishing permission assumed |
| Profile details / health check | Official `/v2/userinfo`; successful OAuth and matching subject |
| Public member text post | Official `POST /rest/posts`; active connection and `w_member_social` |
| Scheduled text post | Same adapter, persistent queue and separate worker |
| Single member image | Private validated JPEG/PNG draft attachment; official Images API initialization/upload only after approval, member publishing scope required |
| Video/document/multiple images | Not implemented |
| Member/organization analytics | Additional approved access required; not implemented; internal metrics only |
| Company-page publishing | Not implemented; organization authorization is not inferred from member scopes |
| Direct messages / invitations / scraping / automated engagement | Not executed by this app; manual LinkedIn links and preserved drafts/history |

Posts use `LinkedIn-Version: 202610`, `X-Restli-Protocol-Version: 2.0.0`, author `urn:li:person:{subject}`, PUBLIC visibility, MAIN_FEED distribution and PUBLISHED lifecycle. Success requires HTTP 201 **and** `x-restli-id`. The API version is configurable and must be maintained as LinkedIn sunsets versions.

429 responses receive bounded backoff (up to four attempts); authorization errors fail and request reconnection. Timeouts, 5xx, missing result identifiers, and process interruption never cause blind automatic resends. Those posts are locked in `needs_review`. Inspect the LinkedIn profile before making a new post. This avoids claiming exactly-once external delivery when the provider offers no verified idempotency guarantee in this implementation.

## Browser extension retained

The v2 companion captures a local draft and opens SYNEX for review, sign-in, or connection. It requests only browser storage permission. It has no LinkedIn host permission, cookie permission, scraping code, or private Voyager client. Server scheduling is independent of the extension. Reconnecting an existing account validates that the returned subject is the intended account. This supersedes the initial audit’s proposed extension retirement: the user explicitly requested keeping it.

## Exact live blockers

A dedicated `ENCRYPTION_KEY` was generated and saved locally without displaying its value. `LINKEDIN_CLIENT_ID` and `LINKEDIN_CLIENT_SECRET` are still absent. Configure those server-side, enable the OIDC and Share on LinkedIn products, and register the exact callback. Product approval cannot be established from this environment. The code is mock-verified, **not live-verified**. No live LinkedIn write was attempted.

## Official references checked 4 November 2026

- [OpenID Connect, claims, JWKS and userinfo](https://learn.microsoft.com/en-us/linkedin/consumer/integrations/self-serve/sign-in-with-linkedin-v2)
- [API access and product permissions](https://learn.microsoft.com/en-us/linkedin/shared/authentication/getting-access)
- [Posts API and returned identifiers](https://learn.microsoft.com/en-us/linkedin/marketing/community-management/shares/posts-api?view=li-lms-2026-10)
- [Images API requirements](https://learn.microsoft.com/en-us/linkedin/marketing/community-management/shares/images-api?view=li-lms-2026-10) — single-image upload implemented and mock-tested; write-only member scopes do not imply image-read access.
