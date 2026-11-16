"""Preset voices for voice notes. Every entry is a Piper voice whose training data is licensed for commercial use.

Voices were checked against each voice's MODEL_CARD on 2026-11-16. Voices trained on non-commercial data (for example ryan, hfc_female
and hfc_male, CC BY-NC-SA) are deliberately absent. Piper has no Indian English voice, so that accent is not offered.
"""
import importlib.util

VOICES = [
    {"id": "kristin", "label": "Kristin", "gender": "Female", "accent": "English (US)", "model": "en_US-kristin-medium", "licence": "Public domain"},
    {"id": "bryce", "label": "Bryce", "gender": "Male", "accent": "English (US)", "model": "en_US-bryce-medium", "licence": "Public domain"},
    {"id": "norman", "label": "Norman", "gender": "Male", "accent": "English (US)", "model": "en_US-norman-medium", "licence": "Public domain"},
    {"id": "joe", "label": "Joe", "gender": "Male", "accent": "English (US)", "model": "en_US-joe-medium", "licence": "CC0"},
    {"id": "kathleen", "label": "Kathleen", "gender": "Female", "accent": "English (US)", "model": "en_US-kathleen-low", "licence": "CC0"},
    {"id": "sam", "label": "Sam", "gender": "Female", "accent": "English (US)", "model": "en_US-sam-medium", "licence": "Apache-2.0"},
    {"id": "cori", "label": "Cori", "gender": "Female", "accent": "English (UK)", "model": "en_GB-cori-medium", "licence": "CC BY 4.0 (NVIDIA Hi-Fi TTS dataset; attribution required)"},
    {"id": "northern_male", "label": "Northern", "gender": "Male", "accent": "English (UK)", "model": "en_GB-northern_english_male-medium", "licence": "CC BY-SA 4.0"},
    {"id": "southern_female", "label": "Southern", "gender": "Female", "accent": "English (UK)", "model": "en_GB-southern_english_female-low", "licence": "CC BY-SA 4.0"},
]
VOICE_IDS = {voice["id"] for voice in VOICES}

CLONE_REASON = ("Cloning needs an open voice-cloning model with a commercial licence and a recording of your own voice. "
                "None is installed, and the best known candidates are either non-commercial or need a GPU. It is switched off until one is added.")


def engine_available() -> bool:
    return importlib.util.find_spec("piper") is not None


def catalogue() -> dict:
    available = engine_available()
    return {"voices": VOICES, "engine": {"name": "Piper", "available": available,
                                          "reason": None if available else "The local voice engine (Piper) is not installed, so samples cannot be played yet."},
            "clone": {"available": False, "reason": CLONE_REASON},
            "accents": [{"label": "English (US)", "available": True}, {"label": "English (UK)", "available": True},
                        {"label": "English (India)", "available": False, "reason": "No Indian English voice with a commercial licence exists in Piper."}]}
