# Area 9: Templates and saved replies (report)

Date: 2026-11-16. Branch `local-complete`. Local only. Checklist 9.01 to 9.08: 6 done, 2 partial.

| Item | Status before | What I did | Test | Result |
|---|---|---|---|---|
| Message templates: create, edit, delete, copy, search | Works | Unchanged | existing | pass |
| Saved replies with a shortcut | Missing | A shortcut on templates (2 to 20 lowercase letters, digits, dashes; unique per workspace; the server's message is shown); /shortcut plus a space expands it in the inbox reply box; a Saved replies list inserts one | test_templates_and_sequences ShortcutTest (3); templates-and-sequences.spec | pass |
| Insert a template into the message editor | Missing | Template list in the sequence editor, filtered by the kind of message | templates-and-sequences.spec | pass |
| Sequence templates and previous-campaign reuse | Missing | Templates dialog: four bundled sequences and your earlier campaigns; applying asks first | templates-and-sequences.spec | pass |
| Share sequence and import | Share only | Import sequence on the campaigns page makes a draft from a shared file; a bad file is refused with the reason | test_templates_and_sequences SequenceFileTest (2); spec | pass |
| Axe and 360 px for a templates page state | Missing | Not added | none | open |

Standing reminders
- Secret scan broken in CI (deferred by the owner on 15 Nov 2026; must be fixed and run on full history before any public repo or real user).
- Clerk secret and CockroachDB password were exposed in chat on 15 Nov 2026 (rotation deferred; mandatory before any real user, pilot, production deploy or public repo).
