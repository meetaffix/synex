import { test, expect, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { mockApi, newApi } from "./mock-api";
import { API_PORT, API_URL } from "./support";

/* The assistant, with the API and the relay WebSocket both mocked in the browser. No backend, no Deepgram, no microphone hardware. */

const SETTINGS = {
  available: true,
  enabled: true,
  monthlyMinuteCap: 60,
  usedSeconds: 600,
  remainingSeconds: 3000,
  capReached: false,
  idleTimeoutSeconds: 120,
  historyEnabled: false,
  language: "en",
  voice: "aura-2-hera-en",
  model: "claude-haiku-4-5",
  month: "2026-11",
  canEdit: true,
};

interface Mock {
  settings: Record<string, unknown>;
  sessionStatus: number;
  sessionDetail: string;
  sessions: Record<string, unknown>[];
  confirms: string[];
  cancels: string[];
  puts: Record<string, unknown>[];
  socketMessages: unknown[];
  binaryFrames: number;
  sockets: number;
}

async function mockAssistant(page: Page, over: Partial<Mock> = {}): Promise<Mock> {
  const state: Mock = {
    settings: { ...SETTINGS },
    sessionStatus: 200,
    sessionDetail: "",
    sessions: [],
    confirms: [],
    cancels: [],
    puts: [],
    socketMessages: [],
    binaryFrames: 0,
    sockets: 0,
    ...over,
  };
  await mockApi(page, newApi());
  await page.route(
    (url) => url.port === API_PORT && url.pathname.startsWith("/assistant"),
    async (route) => {
      const request = route.request();
      const path = new URL(request.url()).pathname;
      const cors = {
        "access-control-allow-origin": request.headers()["origin"] ?? "*",
        "access-control-allow-credentials": "true",
        "access-control-allow-headers": "content-type",
        "access-control-allow-methods": "GET,POST,PUT,PATCH,DELETE,OPTIONS",
      };
      const json = (status: number, data: unknown) => route.fulfill({ status, headers: { ...cors, "content-type": "application/json" }, body: JSON.stringify(data) });
      if (request.method() === "OPTIONS") return route.fulfill({ status: 204, headers: cors });
      if (path === "/assistant/settings" && request.method() === "GET") return json(200, state.settings);
      if (path === "/assistant/settings" && request.method() === "PUT") {
        const body = request.postDataJSON();
        state.puts.push(body);
        state.settings = { ...state.settings, ...body };
        return json(200, state.settings);
      }
      if (path === "/assistant/session") {
        const body = request.postDataJSON();
        state.sessions.push(body);
        if (state.sessionStatus !== 200) return json(state.sessionStatus, { detail: state.sessionDetail });
        return json(200, { ticket: `ticket-${state.sessions.length}`, wsPath: "/assistant/ws", mode: body.mode, language: "en", idleTimeoutSeconds: 120, remainingSeconds: 3000,
          agent: { model: "claude-haiku-4-5", voice: "aura-2-hera-en", inputSampleRate: 16000, outputSampleRate: 24000, encoding: "linear16" }, historyEnabled: false });
      }
      const act = path.match(/^\/assistant\/proposals\/([^/]+)\/(confirm|cancel)$/);
      if (act) {
        (act[2] === "confirm" ? state.confirms : state.cancels).push(act[1]);
        return json(200, { id: act[1], tool: "create_lead_list", summary: "", changes: [], status: act[2] === "confirm" ? "applied" : "cancelled", needsRole: "manager" });
      }
      if (path === "/assistant/history") return route.fulfill({ status: 204, headers: cors });
      return json(404, { detail: "Not mocked" });
    },
  );
  await page.routeWebSocket(/\/assistant\/ws$/, (ws) => {
    state.sockets += 1;
    const send = (message: unknown) => ws.send(JSON.stringify(message));
    ws.onMessage((raw) => {
      if (typeof raw !== "string") {
        state.binaryFrames += 1;
        return;
      }
      const msg = JSON.parse(raw);
      state.socketMessages.push(msg);
      if (msg.type === "auth") return send({ type: "ready", mode: "text", remainingSeconds: 3000, idleTimeoutSeconds: 120 });
      if (msg.type !== "user_text") return;
      const text: string = msg.text;
      send({ type: "transcript", role: "user", text, typed: true });
      send({ type: "thinking" });
      if (/dashboard/i.test(text)) {
        send({ type: "tool", name: "get_dashboard_summary", status: "running" });
        send({ type: "tool", name: "get_dashboard_summary", status: "done" });
        send({ type: "transcript", role: "assistant", text: "You have 12 leads and 2 active campaigns." });
      } else if (/list/i.test(text)) {
        send({ type: "proposal", proposal: { id: `p-${state.confirms.length + state.cancels.length + 1}`, tool: "create_lead_list", summary: 'Create the list "Fintech CTOs" with 2 leads.',
          changes: ['A new lead list named "Fintech CTOs".', "2 leads added to it.", "Nothing is sent to anyone."], status: "pending", needsRole: "manager" } });
        send({ type: "transcript", role: "assistant", text: "I've prepared it. Please press Confirm on the card." });
      } else if (/draft/i.test(text)) {
        send({ type: "draft", text: "Hi Priya, loved your work at Finlytics.", label: "connection note", warnings: [] });
        send({ type: "transcript", role: "assistant", text: "Here is a draft. It is not sent." });
      } else if (/idle/i.test(text)) {
        send({ type: "closed", reason: "idle" });
      } else {
        send({ type: "transcript", role: "assistant", text: "Okay." });
      }
      send({ type: "agent_audio_done" });
    });
  });
  return state;
}

const panel = (page: Page) => page.getByRole("complementary", { name: "Assistant" });
const openButton = (page: Page) => page.getByRole("button", { name: "Assistant", exact: true });

async function ask(page: Page, text: string) {
  await panel(page).getByLabel("Message the assistant").fill(text);
  await panel(page).getByRole("button", { name: "Send message" }).click();
}

test.describe("assistant panel", () => {
  test("opens from the top bar button and from Ctrl+J and Cmd+J, and Escape closes it and returns focus", async ({ page }) => {
    await mockAssistant(page);
    await page.goto("/templates");
    await expect(panel(page)).toBeHidden();
    await openButton(page).click();
    await expect(panel(page)).toBeVisible();
    await expect(panel(page).getByLabel("Message the assistant")).toBeFocused();
    await page.keyboard.press("Escape");
    await expect(panel(page)).toBeHidden();
    await expect(openButton(page)).toBeFocused();
    await page.keyboard.press("Control+j");
    await expect(panel(page)).toBeVisible();
    await page.keyboard.press("Control+j");
    await expect(panel(page)).toBeHidden();
    await page.keyboard.press("Meta+j");
    await expect(panel(page)).toBeVisible();
    await expect(panel(page).getByTestId("assistant-disclosure")).toContainText("Deepgram and the language model it uses");
  });

  test("a typed conversation works fully without voice, and the session carries the page the user is on", async ({ page }) => {
    const mock = await mockAssistant(page);
    await page.goto("/templates");
    await openButton(page).click();
    expect(mock.sessions).toHaveLength(0); // opening costs nothing: a session starts with the first message
    await ask(page, "Summarise my dashboard");
    await expect(panel(page).getByText("You said: Summarise my dashboard")).toBeVisible();
    await expect(panel(page).getByText("You have 12 leads and 2 active campaigns.")).toBeVisible();
    expect(mock.sessions).toEqual([{ mode: "text", page: { path: "/templates" } }]);
    expect(mock.socketMessages[0]).toEqual({ type: "auth", ticket: "ticket-1" });
    expect(mock.binaryFrames).toBe(0);
    await expect(panel(page).getByTestId("assistant-status")).toHaveText("Connected");
  });

  test("a confirmation card changes nothing until Confirm is clicked; Cancel applies nothing", async ({ page }) => {
    const mock = await mockAssistant(page);
    await page.goto("/templates");
    await openButton(page).click();
    await ask(page, "Make a list of fintech CTOs");
    const card = panel(page).getByTestId("proposal-card");
    await expect(card).toContainText('Create the list "Fintech CTOs" with 2 leads.');
    await expect(card).toContainText("Nothing is sent to anyone.");
    await ask(page, "yes, do it"); // saying yes is only a message
    await expect(panel(page).getByText("Okay.")).toBeVisible();
    expect(mock.confirms).toEqual([]);
    await card.getByRole("button", { name: "Confirm" }).click();
    await expect(card.getByText("Done")).toBeVisible();
    expect(mock.confirms).toHaveLength(1);
    expect(mock.socketMessages).toContainEqual({ type: "note", proposalId: mock.confirms[0] });
    await expect(card.getByRole("button", { name: "Confirm" })).toHaveCount(0);

    await ask(page, "Make another list");
    const second = panel(page).getByTestId("proposal-card").last();
    await second.getByRole("button", { name: "Cancel" }).click();
    await expect(second.getByText("Cancelled")).toBeVisible();
    expect(mock.cancels).toHaveLength(1);
    expect(mock.confirms).toHaveLength(1);
  });

  test("a draft is inserted into the field the user is working on, for editing, and nothing is sent", async ({ page }) => {
    const mock = await mockAssistant(page);
    await page.goto("/templates");
    await page.evaluate(() => {
      const field = document.createElement("textarea");
      field.id = "note";
      field.setAttribute("aria-label", "Connection note");
      document.body.append(field);
    });
    await page.locator("#note").fill("Existing: ");
    await openButton(page).click();
    await ask(page, "Draft a note for Priya");
    const card = panel(page).getByTestId("draft-card");
    await expect(card).toContainText("It is not sent.");
    await expect(card.getByRole("button", { name: "Insert into Connection note" })).toBeVisible();
    await card.getByRole("button", { name: "Insert into Connection note" }).click();
    await expect(page.locator("#note")).toHaveValue("Existing: Hi Priya, loved your work at Finlytics.");
    await expect(card).toContainText("Edit it before you use it.");
    expect(mock.confirms).toEqual([]);
  });

  test("microphone: explained first, asked only after Continue, and a refusal leaves typing working", async ({ page }) => {
    await page.addInitScript(() => {
      (window as unknown as { __mic: number }).__mic = 0;
      Object.defineProperty(navigator, "mediaDevices", {
        configurable: true,
        value: {
          getUserMedia: () => {
            (window as unknown as { __mic: number }).__mic += 1;
            return Promise.reject(new DOMException("Permission denied", "NotAllowedError"));
          },
        },
      });
    });
    const mock = await mockAssistant(page);
    await page.goto("/templates");
    await openButton(page).click();
    const asked = () => page.evaluate(() => (window as unknown as { __mic: number }).__mic);
    expect(await asked()).toBe(0);
    await panel(page).getByTestId("mic-button").click();
    await expect(panel(page).getByTestId("mic-explain")).toContainText("Synex stores no audio");
    expect(await asked()).toBe(0); // the browser has not been asked yet
    await panel(page).getByRole("button", { name: "Continue" }).click();
    await expect(panel(page).getByTestId("mic-denied")).toContainText("You can keep typing");
    expect(await asked()).toBe(1);
    expect(mock.sessions).toHaveLength(0);
    await ask(page, "Summarise my dashboard");
    await expect(panel(page).getByText("You have 12 leads and 2 active campaigns.")).toBeVisible();
  });

  test("hands-free shows a clear Recording state and streams audio, and stopping releases it", async ({ page }) => {
    await page.addInitScript(() => {
      localStorage.setItem("synex.assistant.mic-explained", "1");
      localStorage.setItem("synex.assistant.voice-mode", "hands-free");
      Object.defineProperty(navigator, "mediaDevices", {
        configurable: true,
        value: {
          getUserMedia: async () => {
            const context = new AudioContext();
            const oscillator = context.createOscillator();
            const destination = context.createMediaStreamDestination();
            oscillator.connect(destination);
            oscillator.start();
            return destination.stream;
          },
        },
      });
    });
    const mock = await mockAssistant(page);
    await page.goto("/templates");
    await openButton(page).click();
    await panel(page).getByRole("button", { name: "Start listening" }).click();
    await expect(panel(page).getByTestId("recording-indicator")).toContainText("Recording");
    await expect(panel(page).getByTestId("assistant-status")).toHaveText("Recording");
    expect(mock.sessions[0]).toMatchObject({ mode: "voice" });
    await expect.poll(() => mock.binaryFrames, { timeout: 10_000 }).toBeGreaterThan(0);
    await panel(page).getByRole("button", { name: "Stop listening" }).click();
    await expect(panel(page).getByTestId("recording-indicator")).toHaveCount(0);
  });

  test("voice unavailable: the reason is shown, the mic is disabled and typing still works", async ({ page }) => {
    await page.addInitScript(() => Object.defineProperty(navigator, "mediaDevices", { configurable: true, value: undefined }));
    await mockAssistant(page);
    await page.goto("/templates");
    await openButton(page).click();
    await expect(panel(page).getByTestId("voice-unavailable")).toContainText("Typing works fully");
    await expect(panel(page).getByTestId("mic-button")).toBeDisabled();
    await ask(page, "Summarise my dashboard");
    await expect(panel(page).getByText("You have 12 leads and 2 active campaigns.")).toBeVisible();
  });

  test("cap reached: a clear message, with typing disabled", async ({ page }) => {
    await mockAssistant(page, { settings: { ...SETTINGS, capReached: true, usedSeconds: 3600, remainingSeconds: 0 } });
    await page.goto("/templates");
    await openButton(page).click();
    await expect(panel(page).getByTestId("assistant-blocked")).toContainText("Monthly assistant minutes used up");
    await expect(panel(page).getByTestId("assistant-blocked")).toContainText("raise the cap in Settings");
    await expect(panel(page).getByLabel("Message the assistant")).toBeDisabled();
  });

  test("cap reached while starting a session shows the server's message", async ({ page }) => {
    await mockAssistant(page, { sessionStatus: 429, sessionDetail: "This workspace has used its 60 assistant minutes for 2026-11." });
    await page.goto("/templates");
    await openButton(page).click();
    await ask(page, "hello");
    await expect(panel(page).getByTestId("assistant-blocked")).toBeVisible();
    await expect(panel(page).getByLabel("Message the assistant")).toBeDisabled();
  });

  test("off for the workspace has its own state", async ({ page }) => {
    await mockAssistant(page, { settings: { ...SETTINGS, enabled: false } });
    await page.goto("/templates");
    await openButton(page).click();
    await expect(panel(page).getByTestId("assistant-blocked")).toContainText("The assistant is turned off");
  });

  test("not configured on the server has its own state", async ({ page }) => {
    await mockAssistant(page, { settings: { ...SETTINGS, available: false } });
    await page.goto("/templates");
    await openButton(page).click();
    await expect(panel(page).getByTestId("assistant-blocked")).toContainText("isn't set up yet");
  });

  test("offline: the panel says so and sending is disabled", async ({ page, context }) => {
    await mockAssistant(page);
    await page.goto("/templates");
    await openButton(page).click();
    await context.setOffline(true);
    await expect(panel(page).getByTestId("assistant-offline")).toBeVisible();
    await expect(panel(page).getByTestId("assistant-status")).toHaveText("Offline");
    await panel(page).getByLabel("Message the assistant").fill("hello");
    await expect(panel(page).getByRole("button", { name: "Send message" })).toBeDisabled();
    await context.setOffline(false);
    await expect(panel(page).getByTestId("assistant-offline")).toHaveCount(0);
  });

  test("a session that ends for inactivity says so, and the next message starts a new one", async ({ page }) => {
    const mock = await mockAssistant(page);
    await page.goto("/templates");
    await openButton(page).click();
    await ask(page, "go idle");
    await expect(panel(page).getByText(/ended after 2 minutes with no activity/)).toBeVisible();
    await ask(page, "Summarise my dashboard");
    await expect(panel(page).getByText("You have 12 leads and 2 active campaigns.")).toBeVisible();
    expect(mock.sessions).toHaveLength(2);
  });
});

test.describe("assistant settings and privacy", () => {
  test("an admin sees the usage meter and changes the settings; a member sees them read-only", async ({ page }) => {
    const mock = await mockAssistant(page);
    await page.goto("/settings");
    const meter = page.getByTestId("usage-meter");
    await expect(meter).toContainText("10 of 60 minutes used");
    await page.getByRole("switch", { name: "Turn on the assistant for this workspace" }).click();
    await expect.poll(() => mock.puts).toContainEqual({ enabled: false });
    await page.getByLabel("Monthly minute limit").fill("90");
    await page.getByRole("button", { name: "Save limit" }).click();
    await expect.poll(() => mock.puts).toContainEqual({ monthlyMinuteCap: 90 });
    await page.getByRole("switch", { name: "Keep conversation history" }).click();
    await expect.poll(() => mock.puts).toContainEqual({ historyEnabled: true });

    const member = await page.context().newPage();
    await mockAssistant(member, { settings: { ...SETTINGS, canEdit: false } });
    await member.goto("/settings");
    await expect(member.getByText("Only a workspace admin can change these settings.")).toBeVisible();
    await expect(member.getByRole("switch", { name: "Turn on the assistant for this workspace" })).toBeDisabled();
  });

  test("the privacy page is public and carries the disclosure", async ({ page }) => {
    await mockApi(page, newApi({ signedOut: true }));
    await page.goto("/privacy");
    await expect(page.getByRole("heading", { name: "Privacy" })).toBeVisible();
    await expect(page.getByText("processed by Deepgram")).toBeVisible();
    await expect(page.getByText("Synex stores no audio")).toBeVisible();
  });
});

test.describe("axe: no serious or critical violations", () => {
  test.setTimeout(120_000);
  for (const theme of ["light", "dark"] as const) {
    for (const width of [1280, 360]) {
      test(`panel with a conversation, ${theme}, ${width}px`, async ({ page }) => {
        await page.emulateMedia({ colorScheme: theme });
        await page.setViewportSize({ width, height: 900 });
        await mockAssistant(page);
        await page.goto("/templates");
        await openButton(page).click();
        await ask(page, "Make a list of fintech CTOs");
        await expect(panel(page).getByTestId("proposal-card")).toBeVisible();
        await ask(page, "Draft a note");
        await expect(panel(page).getByTestId("draft-card")).toBeVisible();
        await panel(page).getByTestId("mic-button").click();
        await expect(panel(page).getByTestId("mic-explain")).toBeVisible();
        await page.waitForTimeout(400);
        const results = await new AxeBuilder({ page }).analyze();
        const blocking = results.violations.filter((v) => v.impact === "serious" || v.impact === "critical");
        expect(blocking.map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(" ")).join(" | ")}`)).toEqual([]);
      });

      test(`blocked and offline states, settings and privacy pages, ${theme}, ${width}px`, async ({ page }) => {
        await page.emulateMedia({ colorScheme: theme });
        await page.setViewportSize({ width, height: 900 });
        await mockAssistant(page, { settings: { ...SETTINGS, capReached: true, usedSeconds: 3600, remainingSeconds: 0 } });
        const scan = async (label: string) => {
          await page.waitForTimeout(300);
          const results = await new AxeBuilder({ page }).analyze();
          const blocking = results.violations.filter((v) => v.impact === "serious" || v.impact === "critical");
          expect(blocking.map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(" ")).join(" | ")}`), label).toEqual([]);
        };
        await page.goto("/templates");
        await openButton(page).click();
        await expect(panel(page).getByTestId("assistant-blocked")).toBeVisible();
        await scan("blocked");
        await page.context().setOffline(true);
        await expect(panel(page).getByTestId("assistant-offline")).toBeVisible();
        await scan("offline");
        await page.context().setOffline(false);
        await page.goto("/settings");
        await expect(page.getByTestId("usage-meter")).toBeVisible();
        await scan("settings");
        await page.goto("/privacy");
        await expect(page.getByRole("heading", { name: "Privacy" })).toBeVisible();
        await scan("privacy");
      });
    }
  }
});

test("the API URL used by these specs is the fixture port, never the real one", () => {
  expect(new URL(API_URL).port).not.toBe("8010");
});
