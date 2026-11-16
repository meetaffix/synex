"""Voice notes: the audio is prepared BEFORE a campaign runs and kept in the database; the worker only attaches a finished file.

Two ways to get the audio:
  * direct: the owner records or uploads a file (.m4a, .mp3 or .wav, up to 20 MB and 60 seconds);
  * ai: the owner writes a script (up to 1,000 characters) and a text-to-speech engine on this computer makes the audio once.

The engine is Piper (MIT licence, runs offline, free). Synex does not bundle it or any voice: install the `piper` program and a voice model, then set
PIPER_BINARY and PIPER_VOICES_DIR. A voice model has its own licence: check that it allows commercial use before using it (see docs/DEPENDENCIES.md).
The same recording goes to every person: a script cannot use {{variables}}, because audio made per person would be generated while sending.
"""
from __future__ import annotations

import base64
import binascii
import io
import os
import shutil
import struct
import subprocess
import tempfile
import wave
from pathlib import Path

from sqlalchemy.orm import Session

from . import models
from .database import SessionLocal

MAX_BYTES = 20 * 1024 * 1024
MAX_SECONDS = 60
MAX_SCRIPT = 1000
LANGUAGES = {"en-US": "English (US)", "en-GB": "English (UK)", "en-IN": "English (India)"}
EXTENSIONS = {".m4a": "audio/mp4", ".mp3": "audio/mpeg", ".wav": "audio/wav"}


class VoiceError(ValueError):
    """A problem with the audio or script, in words the person can act on."""


# ------------------------------------------------------------------ checking uploaded audio

def _mp4_seconds(data: bytes) -> float | None:
    """Duration from the movie header (mvhd) of an .m4a file, or None when it cannot be read."""
    at = data.find(b"mvhd")
    if at < 4 or at + 24 > len(data):
        return None
    version = data[at + 4]
    try:
        if version == 1:
            timescale, duration = struct.unpack(">IQ", data[at + 24:at + 36])
        else:
            timescale, duration = struct.unpack(">II", data[at + 16:at + 24])
    except struct.error:
        return None
    return duration / timescale if timescale else None


def _mp3_seconds(data: bytes) -> float | None:
    """An estimate from the first frame's bitrate, assuming a constant bitrate. Good enough to refuse a file that is clearly too long."""
    start = 0
    if data[:3] == b"ID3" and len(data) > 10:
        start = 10 + ((data[6] & 0x7F) << 21 | (data[7] & 0x7F) << 14 | (data[8] & 0x7F) << 7 | (data[9] & 0x7F))
    for i in range(start, min(len(data) - 4, start + 4096)):
        if data[i] == 0xFF and data[i + 1] & 0xE0 == 0xE0:
            bitrates = (0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320, 0)
            rate = bitrates[data[i + 2] >> 4] * 1000
            return (len(data) - start) * 8 / rate if rate else None
    return None


def check_audio(filename: str, data: bytes) -> tuple[str, float | None]:
    """(content type, seconds or None). Raises VoiceError for a file that is not an allowed audio file, too big, or too long."""
    extension = Path(filename or "").suffix.lower()
    if extension not in EXTENSIONS:
        raise VoiceError("Use an .m4a, .mp3 or .wav file.")
    if not data:
        raise VoiceError("The file is empty.")
    if len(data) > MAX_BYTES:
        raise VoiceError("The file is larger than 20 MB.")
    if extension == ".wav":
        try:
            with wave.open(io.BytesIO(data)) as wav:
                seconds = wav.getnframes() / wav.getframerate()
        except (wave.Error, EOFError, ZeroDivisionError):
            raise VoiceError("That does not look like a valid .wav file.") from None
    elif extension == ".m4a":
        if data[4:8] != b"ftyp":
            raise VoiceError("That does not look like a valid .m4a file.")
        seconds = _mp4_seconds(data)
    else:
        if not (data[:3] == b"ID3" or (data[0] == 0xFF and data[1] & 0xE0 == 0xE0)):
            raise VoiceError("That does not look like a valid .mp3 file.")
        seconds = _mp3_seconds(data)
    if seconds is not None and seconds > MAX_SECONDS + 0.5:
        raise VoiceError(f"The voice note is {round(seconds)} seconds long. The most is {MAX_SECONDS}.")
    return EXTENSIONS[extension], seconds


def decode_upload(encoded: str) -> bytes:
    try:
        return base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError):
        raise VoiceError("The file could not be read. Try choosing it again.") from None


# ------------------------------------------------------------------ text to speech (Piper, optional, local)

def _binary() -> str | None:
    return shutil.which(os.environ.get("PIPER_BINARY", "piper"))


def _voice_model(language: str) -> Path | None:
    """The .onnx voice for a language: PIPER_VOICE_EN_US, PIPER_VOICE_EN_GB or PIPER_VOICE_EN_IN (a file path, or a name inside PIPER_VOICES_DIR)."""
    value = os.environ.get("PIPER_VOICE_" + language.upper().replace("-", "_"))
    if not value:
        return None
    path = Path(value)
    if not path.is_absolute() and os.environ.get("PIPER_VOICES_DIR"):
        path = Path(os.environ["PIPER_VOICES_DIR"]) / value
    return path if path.is_file() else None


def tts_status() -> dict:
    missing = []
    if _binary() is None:
        missing.append("the piper program (set PIPER_BINARY)")
    languages = {code: {"label": label, "ready": _voice_model(code) is not None} for code, label in LANGUAGES.items()}
    ready = _binary() is not None and any(v["ready"] for v in languages.values())
    return {"engine": "piper", "ready": ready, "languages": languages, "missing": missing, "free": True,
            "note": "Made on this computer with Piper, which is free and works offline. Nothing is sent to a paid service.",
            "howTo": "Install Piper (MIT licence), download a voice for each language, set PIPER_BINARY and PIPER_VOICE_EN_US (and _EN_GB, _EN_IN). "
                     "Check that each voice's licence allows commercial use."}


def synthesize(script: str, language: str) -> bytes:
    """WAV bytes for the script. Raises VoiceError with the fix when the engine or the voice is not installed."""
    script = (script or "").strip()
    if not script:
        raise VoiceError("Write the script first.")
    if len(script) > MAX_SCRIPT:
        raise VoiceError(f"The script can be up to {MAX_SCRIPT:,} characters.")
    if "{{" in script:
        raise VoiceError("The same recording goes to everyone, so the script cannot use variables like {{first_name}}.")
    if language not in LANGUAGES:
        raise VoiceError("Choose English US, UK or India.")
    binary, model = _binary(), _voice_model(language)
    if binary is None:
        raise VoiceError("The text-to-speech engine (Piper) is not installed on this computer. Install it, or record or upload the voice note instead.")
    if model is None:
        raise VoiceError(f"No Piper voice is set for {LANGUAGES[language]}. Set PIPER_VOICE_{language.upper().replace('-', '_')}, or record the voice note instead.")
    with tempfile.TemporaryDirectory() as folder:
        out = Path(folder) / "speech.wav"
        try:
            subprocess.run([binary, "--model", str(model), "--output_file", str(out)], input=script.encode("utf-8"), capture_output=True, timeout=90, check=True)
        except (subprocess.SubprocessError, OSError):
            raise VoiceError("The text-to-speech engine failed. Check that Piper and the voice are installed correctly.") from None
        data = out.read_bytes() if out.exists() else b""
    if not data:
        raise VoiceError("The text-to-speech engine made no audio.")
    return data


# ------------------------------------------------------------------ storage

def save(db: Session, user_id: str, *, kind: str, language: str, filename: str, content_type: str, data: bytes, seconds: float | None,
         script: str | None = None) -> models.VoiceAudio:
    row = models.VoiceAudio(user_id=user_id, kind=kind, language=language, script=script, filename=filename[:120], content_type=content_type,
                            size=len(data), duration_seconds=seconds, data=data)
    db.add(row)
    db.flush()
    return row


def audio_file(audio_id: str | None) -> Path | None:
    """The prepared audio as a temporary file for the worker to attach, or None when it is gone. The caller deletes the file and its folder after sending."""
    if not audio_id:
        return None
    with SessionLocal() as db:
        row = db.get(models.VoiceAudio, audio_id)
        if row is None:
            return None
        folder = Path(tempfile.mkdtemp(prefix="synex-voice-"))
        path = folder / (Path(row.filename).name or "voice-note.wav")  # the person's own file name travels with the file
        path.write_bytes(row.data)
        return path


def estimate(script: str) -> dict:
    """What making this voice note costs: nothing, since the engine is local. Length is a guess from the word count (about 150 words a minute)."""
    words = len((script or "").split())
    return {"costUsd": 0, "estimatedSeconds": round(words / 150 * 60, 1), "note": "Free: made on this computer."}
