"""Local speech for the assistant: the provider choice is a real switch, Whisper and Piper are used when installed and explained when not."""
import base64
import io
import os
import sys
import types
import unittest
import wave
from unittest.mock import patch

from test_assistant_local import LocalAssistantTest as Base  # noqa: E402  (sets the isolated environment)
from app.assistant import speech


def wav(seconds=1.0) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(8000)
        w.writeframes(b"\x00\x00" * int(8000 * seconds))
    return buffer.getvalue()


class FakeWhisper(types.ModuleType):
    """Stands in for faster_whisper: returns two segments for any recording."""

    def __init__(self):
        super().__init__("faster_whisper")

        class WhisperModel:
            def __init__(self, *args, **kwargs):
                self.kwargs = kwargs

            def transcribe(self, path, **kwargs):
                assert kwargs.get("language") == "en"
                return [types.SimpleNamespace(text=" Show me "), types.SimpleNamespace(text="my campaigns ")], None
        self.WhisperModel = WhisperModel


class SpeechTest(unittest.TestCase):
    """Re-uses the local assistant's set-up (a fake Ollama, a signed-in owner, an isolated database) without re-running its tests."""

    def setUp(self):
        Base.setUp(self)
        speech._model = None

    def installed(self, tmp="."):
        return patch.dict(sys.modules, {"faster_whisper": FakeWhisper()}), patch.dict(os.environ, {"WHISPER_MODEL_DIR": tmp})

    def test_the_two_providers_are_listed_with_cost_licence_and_what_is_missing(self):
        r = self.client.get("/assistant/providers").json()
        self.assertEqual(r["selected"], "deepgram")
        by = {p["id"]: p for p in r["providers"]}
        self.assertEqual((by["deepgram"]["cost"], by["local"]["cost"]), ("Paid per minute", "Free"))
        self.assertIn("MIT", by["local"]["licence"])
        parts = {p["id"]: p for p in by["local"]["parts"]}
        self.assertTrue(parts["llm"]["ready"])  # the fake Ollama answers and lists the model
        self.assertFalse(parts["stt"]["ready"])
        self.assertIn("faster-whisper", parts["stt"]["detail"])
        self.assertFalse(parts["tts"]["ready"])
        self.assertIn("Piper", parts["tts"]["detail"])

    def test_choosing_local_needs_the_local_model_and_really_changes_what_the_assistant_does(self):
        self.assertEqual(self.client.put("/assistant/settings", json={"provider": "local"}).status_code, 200)
        self.assertEqual(self.client.get("/assistant/providers").json()["selected"], "local")
        self.assertEqual(self.client.get("/assistant/settings").json()["provider"], "local")
        refused = self.client.post("/assistant/session", json={"mode": "text"})
        self.assertEqual(refused.status_code, 409)  # no Deepgram session while local models are selected
        self.assertIn("local models", refused.json()["detail"])
        self.client.put("/assistant/settings", json={"provider": "deepgram"})
        self.assertNotEqual(self.client.post("/assistant/session", json={"mode": "text"}).status_code, 409)

    def test_local_cannot_be_chosen_while_ollama_is_not_running(self):
        with patch("app.assistant.local.available", return_value={"reachable": False, "model": "llama3.2", "installed": False}):
            r = self.client.put("/assistant/settings", json={"provider": "local"})
        self.assertEqual(r.status_code, 409)
        self.assertEqual(self.client.get("/assistant/settings").json()["provider"], "deepgram")
        self.assertEqual(self.client.put("/assistant/settings", json={"provider": "other"}).status_code, 422)

    def test_whisper_turns_a_recording_into_text_when_installed_and_says_what_is_missing_when_not(self):
        body = {"audio": base64.b64encode(wav()).decode()}
        missing = self.client.post("/assistant/local/transcribe", json=body)
        self.assertEqual(missing.status_code, 422)
        self.assertIn("faster-whisper", missing.json()["detail"])
        modules, env = self.installed()
        with modules, env:
            ok = self.client.post("/assistant/local/transcribe", json=body)
        self.assertEqual((ok.status_code, ok.json()), (200, {"text": "Show me my campaigns"}))

    def test_recordings_are_checked(self):
        modules, env = self.installed()
        with modules, env:
            for audio, reason in ((base64.b64encode(b"not a wav").decode(), "could not be read"), (base64.b64encode(wav(61)).decode(), "most is 60"), ("###", "could not be read")):
                r = self.client.post("/assistant/local/transcribe", json={"audio": audio})
                self.assertEqual(r.status_code, 422)
                self.assertIn(reason, r.json()["detail"])

    def test_piper_speaks_a_reply_when_installed_and_says_so_when_not(self):
        self.assertEqual(self.client.post("/assistant/local/speak", json={"text": "Hello there"}).status_code, 422)
        from test_new_actions import VoiceModuleTest
        launcher, voice_file = VoiceModuleTest("test_the_script_rules").make_fake_piper()
        with patch.dict(os.environ, {"PIPER_BINARY": str(launcher), "PIPER_VOICE_EN_US": str(voice_file)}):
            r = self.client.post("/assistant/local/speak", json={"text": "Hello there friend"})
        self.assertEqual((r.status_code, r.headers["content-type"], r.content[:4]), (200, "audio/wav", b"RIFF"))

    def test_the_assistant_speech_endpoints_need_a_signed_in_user(self):
        from app.deps import get_current_user
        from app.main import app
        app.dependency_overrides.pop(get_current_user, None)
        anonymous = type(self.client)(app)
        self.assertEqual(anonymous.post("/assistant/local/speak", json={"text": "x"}).status_code, 401)
        self.assertEqual(anonymous.post("/assistant/local/transcribe", json={"audio": ""}).status_code, 401)
        self.assertEqual(anonymous.get("/assistant/providers").status_code, 401)


if __name__ == "__main__":
    unittest.main()
