"""Speech for the local assistant: Whisper turns a recording into text, Piper turns a reply into a voice. Both run on this computer, are free, and send nothing out.

Nothing is bundled and nothing is downloaded by Synex. Install the optional parts yourself:
  * speech to text: `pip install faster-whisper` (MIT) and a Whisper model folder, then set WHISPER_MODEL_DIR (a folder that holds the model) and, if you like, WHISPER_MODEL
    (default `base.en`). Synex loads it with `local_files_only`, so it never reaches out for a model;
  * voice: the Piper program and a voice (see app/voice.py and docs/DEPENDENCIES.md), PIPER_BINARY and PIPER_VOICE_EN_US.
"""
from __future__ import annotations

import io
import os
import tempfile
import wave
from pathlib import Path

from .. import voice

MAX_SECONDS = 60
_model = None


class SpeechError(Exception):
    """A problem in words the person can act on."""


def stt_status() -> dict:
    try:
        import faster_whisper  # noqa: F401
        installed = True
    except ImportError:
        installed = False
    folder = os.environ.get("WHISPER_MODEL_DIR", "")
    has_model = bool(folder) and Path(folder).is_dir()
    missing = ([] if installed else ["the faster-whisper package (pip install faster-whisper)"]) + ([] if has_model else ["a Whisper model folder (set WHISPER_MODEL_DIR)"])
    return {"id": "whisper", "ready": installed and has_model, "missing": missing, "model": os.environ.get("WHISPER_MODEL", "base.en")}


def _load():
    global _model
    if _model is None:
        from faster_whisper import WhisperModel
        _model = WhisperModel(os.environ.get("WHISPER_MODEL", "base.en"), device="cpu", compute_type="int8", download_root=os.environ["WHISPER_MODEL_DIR"], local_files_only=True)
    return _model


def check_wav(data: bytes) -> float:
    """Seconds of audio in a .wav recording, or a SpeechError when it is not one or is too long."""
    try:
        with wave.open(io.BytesIO(data)) as w:
            seconds = w.getnframes() / w.getframerate()
    except (wave.Error, EOFError, ZeroDivisionError):
        raise SpeechError("That recording could not be read. Try again.") from None
    if seconds > MAX_SECONDS + 0.5:
        raise SpeechError(f"The recording is {round(seconds)} seconds long. The most is {MAX_SECONDS}.")
    return seconds


def transcribe(data: bytes) -> str:
    """The words in a .wav recording. Raises SpeechError with the fix when Whisper is not set up."""
    check_wav(data)
    status = stt_status()
    if not status["ready"]:
        raise SpeechError("Speech to text (Whisper) is not set up on this computer. Missing: " + "; ".join(status["missing"]) + ". You can type instead.")
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "speech.wav"
        path.write_bytes(data)
        try:
            segments, _ = _load().transcribe(str(path), language="en", vad_filter=True)
            text = " ".join(segment.text.strip() for segment in segments).strip()
        except Exception:  # noqa: BLE001 - the engine's own errors are not for the person
            raise SpeechError("Whisper could not read that recording. Try again.") from None
    if not text:
        raise SpeechError("No speech was heard. Try again, closer to the microphone.")
    return text


def speak(text: str, language: str = "en-US") -> bytes:
    """A .wav voice for a reply. Long replies are read up to the first 1,000 characters."""
    try:
        return voice.synthesize(text.strip()[: voice.MAX_SCRIPT].replace("{{", "{ {"), language)
    except voice.VoiceError as exc:
        raise SpeechError(str(exc)) from None


def providers() -> list[dict]:
    """The choices the assistant can run on, with what each costs, where it runs, its licence and whether it is ready."""
    from . import local
    llm = local.available()
    stt, tts = stt_status(), voice.tts_status()
    local_ready = bool(llm["reachable"] and llm["installed"])
    return [
        {"id": "deepgram", "label": "Deepgram voice agent", "cost": "Paid per minute", "runs": "Deepgram's servers", "licence": "Commercial service (default)",
         "ready": True, "detail": "Voice and text in the assistant panel. The default.", "parts": []},
        {"id": "local", "label": "Local models", "cost": "Free", "runs": "This computer or network", "licence": "Ollama MIT, Whisper MIT, Piper MIT; each model has its own licence",
         "ready": local_ready, "detail": "Typed questions need Ollama. Speaking needs Whisper; spoken replies need Piper.",
         "parts": [
             {"id": "llm", "label": "Language model (Ollama)", "ready": local_ready, "detail": f"{llm['model']} " + ("is running." if local_ready else "is not ready: start Ollama and pull the model.")},
             {"id": "stt", "label": "Speech to text (Whisper)", "ready": stt["ready"], "detail": "Ready." if stt["ready"] else "Not set up. Missing: " + "; ".join(stt["missing"])},
             {"id": "tts", "label": "Voice (Piper)", "ready": tts["ready"], "detail": "Ready." if tts["ready"] else "Not set up. " + tts["howTo"]},
         ]},
    ]
