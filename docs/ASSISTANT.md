# Synex assistant

One assistant the user talks or types to. It looks things up, plans and drafts, and prepares changes that the user confirms with a click. Built on Deepgram's Voice Agent API (docs read 2026-11-15).

## How it connects

```
browser ──(WebSocket, single-use ticket)──> Synex backend ──(WebSocket, DEEPGRAM_API_KEY)──> Deepgram agent
```

- `DEEPGRAM_API_KEY` is read from the root `.env` only (`app/assistant/config.py`). It is used in one place, the `Authorization: Token …` header of the upstream connection in `app/assistant/relay.py`. It is never in a response, a log line or the browser. Errors are logged by exception type only, and `scrub()` removes the key from anything user-facing.
- `POST /assistant/session` (signed in) checks the workspace switch, the monthly cap and that the key exists, then returns a 30-second single-use ticket and the non-secret agent config. The browser opens `WS /assistant/ws`, sends `{"type":"auth","ticket":…}` as its first message (not in the URL, so it never reaches access logs), and the Origin must be one of `CORS_ORIGINS`.
- Microphone audio (16 kHz linear16) goes up the relay; the agent's speech (24 kHz linear16) comes back as binary frames. Typing sends `InjectUserMessage`.

### Why a relay and not a browser token

Deepgram does offer temporary tokens (`POST /v1/auth/grant`, JWT, 30 s default) and says they work with the Voice Agent socket. We still relay because: (1) the docs describe no way to scope such a token below its API key's own access, so it is not "narrowly scoped"; (2) a token only has to be valid at the handshake, and the socket stays open after it expires, so a browser-held connection could not enforce the minute cap or idle timeout; (3) the docs show no worked example of the Voice Agent socket with a JWT from a browser, and the exact `Sec-WebSocket-Protocol` value for a JWT is not stated. With the relay, the cap, idle timeout, audit log and permission checks all sit on the server.

## Model and voice

| Part | Choice | Why |
|---|---|---|
| STT | `nova-3` (v1), language `en` or `en-IN` per workspace | `en-IN` is listed for Nova-3 but not for Flux, and the brief needs both. |
| LLM | Anthropic `claude-haiku-4-5` (Standard tier) | Standard tier is included in the flat per-minute rate ($0.075/min pay-as-you-go; Advanced is $0.163/min). Haiku 4.5 follows tool schemas and short spoken-style instructions well and is fast. Change with `ASSISTANT_LLM_PROVIDER` / `ASSISTANT_LLM_MODEL`. |
| TTS | `aura-2-hera-en` ("smooth, warm, professional") | Warm and clear. No Indian-English voice is listed; `en-IN` only changes recognition. Change with `ASSISTANT_VOICE`. |
| Privacy flag | `mip_opt_out: true` | Keeps workspace data out of Deepgram's model-improvement programme. |

## Tools

Registry: `app/assistant/registry.py`. Add a tool by calling `register(Tool(...))` in `tools.py`; the agent's function list, JSON schema (from the pydantic model), role check, audit entry and confirmation flow follow. Functions are declared without an `endpoint`, so Deepgram asks the client (our relay) to run them and the relay runs them on the server.

| Tool | Kind | Minimum role |
|---|---|---|
| `get_dashboard_summary`, `search_campaigns`, `get_campaign`, `explain_campaign_status`, `search_leads`, `get_lead`, `list_lead_lists`, `list_templates`, `list_sender_accounts`, `explain_account_status` | read | member |
| `draft_message`, `propose_sequence`, `suggest_limits` | draft (text only, nothing saved or sent) | member |
| `create_lead_list`, `create_template`, `update_template`, `create_campaign_draft`, `set_campaign_state` (pause, or resume a campaign launched before) | write → proposal | manager |
| `set_daily_limits` | write → proposal | manager for a campaign; admin for a sender account (checked again inside) |
| `set_account_state` (pause/resume) | write → proposal | admin |

Not available, and answered plainly: sending messages, replying in the inbox, launching a campaign for the first time, deleting anything, importing from LinkedIn searches.

Limits: `set_daily_limits` and `create_campaign_draft` check the hard ceilings in `app/config.py` (200 actions, 40 invites, 100 messages a day; 150 invites a week), show the current value from `engine.configured_daily_limit` / `engine.campaign_type_limit`, and apply through the same `AccountPatch` / `CampaignUpdateIn` the API uses. 0 means stopped.

## Confirmation

A write tool only creates a row in `assistant_proposals`. The browser shows a card; `POST /assistant/proposals/{id}/confirm` applies it, after re-checking the role and re-validating the arguments (ceilings included). Nothing in the voice session or tool list can call that endpoint. A spoken or typed "yes" is just text to the agent. After the click, the relay tells the agent what happened, read from the database.

## Audit log

Every tool call writes `assistant_audit`: user, tool, kind, arguments with personal data minimised (names, contact details and message text become markers or lengths), status (`ok`, `denied`, `invalid`, `error`, `proposed`, `applied`, `cancelled`, `failed`), a short result, `via = "assistant"`, time. Admins read it at `GET /assistant/audit`.

## Cost and privacy controls

Workspace settings (`/assistant/settings`; admins edit): on/off, monthly minute cap (default 60; 0 stops it), idle timeout (default 120 s), history (default off), language. Usage is counted in seconds while a session is open and saved every 15 s. At the cap the session ends and new ones are refused with a clear message. Synex stores no audio. Transcript lines are stored only when history is on; users can clear their own. Disclosure: in the panel and on `/privacy`.

## Where the docs differed from the brief

- Temporary tokens cannot be narrowed below their key and the socket outlives them (see above).
- The agent `language` field is deprecated; language is set on `listen.provider`. Flux (recommended for agents) has no `en-IN`.
- Audio input default sample rate is 24000 on one page and 16000 on another; Synex sets both input and output explicitly.
- The token guide moved to `/guides/fundamentals/token-based-authentication`; the old `/docs/token-based-auth` is a 404.
- The Browser Agent SDK (`@deepgram/agents`, `@deepgram/react`, `@deepgram/ui`, `@deepgram/agents-widget`) exists, takes a `tokenFactory`, and its docs do not say GA or beta. Not used: it would put the socket in the browser.
- Deepgram-hosted LLMs are Early Access and not for production.

## Manual test with the real key

1. In the root `.env` set `DEEPGRAM_API_KEY=…` (the existing file has a misspelt name, `DEEPGRAM_APY_KEP`; rename it). Restart the backend.
2. Sign in as an admin. Settings → Assistant: check it is on, see the usage meter, cap 60.
3. Press Ctrl+J. Type "Summarise my dashboard". Expect a reply with your real numbers.
4. Type "Why is my campaign paused?" on a paused campaign. Expect a reason and a next step.
5. Press the mic. Read the explanation, press Continue, allow the browser prompt. Hold the mic and say "List my sender accounts". Release. Expect a spoken and written reply; a red Recording label shows while held.
6. Switch to Hands-free, press the mic, say "Make a list called Fintech CTOs with Asha Rao at PayCo". Expect a confirmation card. Say "yes". Nothing changes. Press Confirm. The list appears under Leads.
7. Say "Set the daily limit on my account to 500". Expect a refusal naming the 200 ceiling.
8. Focus a template text field, ask "Draft a connection note for Priya". Press Insert on the card. Expect the text in the field, not sent.
9. Ask "Send a message to Priya". Expect "not available yet".
10. Stay silent for 2 minutes. Expect the session to end and the panel to say so. Settings usage meter should have gone up by roughly the session length.
11. Turn the assistant off in Settings. Open the panel. Expect "The assistant is turned off".

## Drafts: AI is used before launch, never while sending

The outreach engine never calls Deepgram. It sends finished text only (`engine.message_for`): the **approved draft** for
that lead and step, otherwise the step's template with variables and `{a|b|c}` spintax (the spin is chosen per lead,
so the dry run shows exactly what is sent).

AI drafts are prepared in campaign preparation (`app/drafts.py`, routes under `/campaigns/{id}/drafts`):

1. `POST .../estimate` shows the count, the minutes and the dollars (Voice Agent Standard, $0.075 a minute, 10 seconds
   assumed per draft) before anything is generated.
2. `POST .../generate` needs the count the user saw (`confirmedCount`); a different count returns 409 with the new
   estimate. It runs in the background, in batches of 5, up to 200 drafts a campaign.
3. Drafts start as `proposed`. The user edits (`PATCH`), approves (`POST .../approve`) or discards (`DELETE`) them. An
   edit needs a fresh approval. Only `approved` drafts are sent; a lead without one gets the template.

No database transaction is open while Deepgram is called: the plan is read and its session closed, and each batch is
written afterwards in its own short transaction. The same holds for `/ai/generate-message`, `/publishing/assist` and the
assistant's draft tool. The review screen is not built yet (roadmap: campaign builder); the API is complete and tested.
