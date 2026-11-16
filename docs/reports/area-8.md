# Area 8: AI assistant (report)

Date: 2026-11-16. Branch `local-complete`. Local only. Checklist 8.01 to 8.16: 8 done, 6 partial, 2 open.

| Item | Status before | What I did | Test | Result |
|---|---|---|---|---|
| Voice and text assistant on Deepgram | Works | Unchanged | test_assistant (38) | pass |
| Free local-model text assistant (Ollama) | Missing | `POST /assistant/local/chat`: same tool registry, permissions, audit log and confirmation cards; stops after four tool rounds; a clear message when Ollama is not running | test_assistant_local (9); assistant-local.spec (2) | pass |
| Settings card: model status, typed conversation, Confirm and Cancel on proposals | Missing | Added under Settings | assistant-local.spec; axe and 360 px pass | pass |
| Tools for inbox, funnel, do-not-contact | Missing | `search_conversations`, `get_funnel` (read), `add_do_not_contact` (write: card only) | test_assistant_local NewToolsTest; test_assistant ConfirmationTest | pass |
| Whisper speech to text, Piper text to speech | Missing | Not built. Piper is the voice engine candidate (licences in DEPENDENCIES.md); Whisper not evaluated | none | open |
| Provider selector in Settings | Missing | Provider is chosen by `AI_PROVIDER`, `OLLAMA_URL`, `OLLAMA_MODEL`; the card shows status | none | partial |
| Tool to save a reply draft in the inbox; tools that read settings screens | Missing | Not built | none | partial |

Notes: nothing in the assistant can send a message or launch a campaign; that is unchanged. Real model quality was not tested (no Ollama here): the tests use a stand-in server speaking Ollama's chat format.

Standing reminders
- Secret scan broken in CI (deferred by the owner on 15 Nov 2026; must be fixed and run on full history before any public repo or real user).
- Clerk secret and CockroachDB password were exposed in chat on 15 Nov 2026 (rotation deferred; mandatory before any real user, pilot, production deploy or public repo).
