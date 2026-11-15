"""A scripted stand-in for Deepgram's Voice Agent websocket (wss://agent.deepgram.com/v1/agent/converse).

It speaks the same protocol the relay uses: Welcome, Settings -> SettingsApplied, InjectUserMessage,
FunctionCallRequest / FunctionCallResponse, ConversationText, AgentAudioDone, binary audio, KeepAlive. It records
everything it receives, including the request headers, so tests can check what the backend sent. No network.

A script maps a substring of the user's message to steps:
    ("text", "assistant", "words")      ConversationText
    ("call", "tool_name", {args})       FunctionCallRequest, then waits for the FunctionCallResponse
    ("audio",)                          one binary audio frame
    ("done",)                           AgentAudioDone
    ("user_speaking",)                  UserStartedSpeaking
"""
import asyncio
import json
import threading

from websockets.asyncio.server import serve


class MockDeepgram:
    def __init__(self, script: dict | None = None, expected_auth: str | None = None):
        self.script = script or {}
        self.expected_auth = expected_auth
        self.received: list[dict] = []
        self.audio_frames = 0
        self.headers: list[dict] = []
        self.call_results: list[dict] = []
        self.url = ""
        self._loop: asyncio.AbstractEventLoop | None = None
        self._stop: asyncio.Event | None = None
        self._ready = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._counter = 0

    # ---- lifecycle ---------------------------------------------------------------------------------------
    def __enter__(self):
        self._thread.start()
        self._ready.wait(10)
        return self

    def __exit__(self, *exc):
        if self._loop and self._stop:
            self._loop.call_soon_threadsafe(self._stop.set)
        self._thread.join(10)

    def _run(self):
        asyncio.run(self._main())

    async def _main(self):
        self._loop = asyncio.get_running_loop()
        self._stop = asyncio.Event()
        async with serve(self._handle, "127.0.0.1", 0, process_request=self._check_auth) as server:
            port = next(iter(server.sockets)).getsockname()[1]
            self.url = f"ws://127.0.0.1:{port}/v1/agent/converse"
            self._ready.set()
            await self._stop.wait()

    def _check_auth(self, connection, request):
        self.headers.append({k.lower(): v for k, v in request.headers.raw_items()})
        if self.expected_auth is not None and request.headers.get("Authorization") != self.expected_auth:
            return connection.respond(401, "Unauthorized\n")
        return None

    # ---- helpers ------------------------------------------------------------------------------------------
    def settings(self) -> dict | None:
        return next((m for m in self.received if m.get("type") == "Settings"), None)

    def messages(self, kind: str) -> list[dict]:
        return [m for m in self.received if m.get("type") == kind]

    # ---- protocol -----------------------------------------------------------------------------------------
    async def _handle(self, ws):
        await ws.send(json.dumps({"type": "Welcome", "request_id": "mock-request"}))
        pending_calls: dict[str, asyncio.Future] = {}
        async for raw in ws:
            if isinstance(raw, bytes):
                self.audio_frames += 1
                continue
            msg = json.loads(raw)
            self.received.append(msg)
            kind = msg.get("type")
            if kind == "Settings":
                await ws.send(json.dumps({"type": "SettingsApplied"}))
            elif kind == "FunctionCallResponse":
                self.call_results.append(msg)
                fut = pending_calls.get(msg.get("id"))
                if fut and not fut.done():
                    fut.set_result(msg)
            elif kind == "InjectUserMessage":
                asyncio.create_task(self._reply(ws, msg["content"], pending_calls))

    async def _reply(self, ws, content: str, pending_calls: dict):
        steps = next((s for trigger, s in self.script.items() if trigger.lower() in content.lower()), [("text", "assistant", "Okay."), ("done",)])
        await ws.send(json.dumps({"type": "AgentThinking", "content": "thinking"}))
        for step in steps:
            kind = step[0]
            if kind == "text":
                await ws.send(json.dumps({"type": "ConversationText", "role": step[1], "content": step[2]}))
            elif kind == "audio":
                await ws.send(b"\x01\x02" * 64)
            elif kind == "done":
                await ws.send(json.dumps({"type": "AgentAudioDone"}))
            elif kind == "user_speaking":
                await ws.send(json.dumps({"type": "UserStartedSpeaking"}))
            elif kind == "call":
                self._counter += 1
                call_id = f"call-{self._counter}"
                fut = asyncio.get_running_loop().create_future()
                pending_calls[call_id] = fut
                await ws.send(json.dumps({"type": "FunctionCallRequest", "functions": [
                    {"id": call_id, "name": step[1], "arguments": json.dumps(step[2]), "client_side": True}]}))
                await asyncio.wait_for(fut, 10)
