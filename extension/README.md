# SYNEX Publishing Companion v2

The browser extension is retained. It captures draft ideas and opens the same SYNEX account and publishing workflows used by the web app.

1. Open Chrome/Edge → Extensions. Enable Developer mode.
2. Choose **Load unpacked** and select this `extension` folder.
3. Pin SYNEX. Open the popup and enter your workspace URL (`http://localhost:5173` in normal local development).
4. Write an idea, then choose **Open in Content studio**. Sign in if needed and save the draft in SYNEX.
5. **Connect LinkedIn** opens account management; **Sign in to SYNEX** opens email/LinkedIn sign-in.

Your captured idea persists in local extension storage until replaced. It is passed to the studio in the URL; avoid placing secrets in drafts. Normal browser history may retain that URL. Publishing requires explicit approval in the studio and an authorized LinkedIn connection.

Only `storage` permission is requested. The extension never reads LinkedIn cookies, passwords, sessions, page content, or connection lists. The server worker handles publishing; closing the browser does not cancel a schedule. Legacy pairing tokens in extension storage are removed on upgrade. Reload the extension after replacing its files.

The Chromium automated test loads the actual extension, checks idea persistence and handoff through sign-in, opens connection management, and rejects unsafe workspace URL schemes. Live LinkedIn authorization is a separate credential-dependent verification step.
