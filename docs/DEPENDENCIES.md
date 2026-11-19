# Dependencies and licences

Synex will be released under AGPL-3.0. Every dependency must be compatible with AGPL-3.0 and allow commercial use. No non-commercial licences.
Last updated 2026-11-16 (area 3). A full audit of the pre-existing packages (every entry of `frontend/package.json` and `backend/requirements.txt`) is part of area 12 and must be finished before the handover.

## Added during this build

| Package or asset | Where | Licence | AGPL-3.0 compatible | Commercial use | Notes |
|---|---|---|---|---|---|
| Piper text-to-speech program (optional, not bundled, not a pip or npm package) | `backend/app/voice.py` (voice notes made from a script, area 5) | MIT (Piper) | yes | yes | Installed by the owner and found through `PIPER_BINARY` and `PIPER_VOICE_EN_US/EN_GB/EN_IN`. Synex ships no voice. Only voices whose data licence allows commercial use may be used: see the voice table below (public domain, CC0, Apache-2.0, CC BY, CC BY-SA are fine; the CC BY-NC-SA voices are not). Piper's own MIT licence was recorded by an earlier session and is to be re-checked against the release actually installed. No Indian English Piper voice exists, so English (India) stays unavailable until one is set. |
| `@xyflow/react` 12.8.4 (React Flow) | `frontend/src/features/campaigns/builder/SmartGraph.tsx` (Smart sequence node canvas) | MIT | yes | yes | Pulls in `@xyflow/system`, `d3-zoom`, `d3-selection`, `classcat`, `zustand` (all MIT or ISC). Attribution banner hidden with `proOptions.hideAttribution`, which the MIT licence permits for the open-source package; we credit React Flow here instead. |
| (no other package added in areas 3 to 10) | | | | | Everything else used was already in `package.json` and `requirements.txt`; their audit is part of area 12. |

## Voice data used by the preset voices (area 3)

Piper voices are trained on public datasets; each voice's own licence matters, not Piper's. Checked on 2026-11-16 against each voice's `MODEL_CARD` in `rhasspy/piper-voices`.

| Voice id | Piper model | Data licence | Used |
|---|---|---|---|
| kristin, bryce, norman | en_US-kristin / bryce / norman-medium | Public domain | yes |
| joe, kathleen | en_US-joe-medium, en_US-kathleen-low | CC0 | yes |
| sam | en_US-sam-medium | Apache-2.0 | yes |
| cori | en_GB-cori-medium | CC BY 4.0 (NVIDIA Hi-Fi TTS dataset): attribution required | yes |
| northern_male, southern_female | en_GB-northern_english_male-medium, en_GB-southern_english_female-low | CC BY-SA 4.0 | yes |
| ryan | en_US-ryan-medium | CC BY-NC-SA 4.0 | NO: non-commercial |
| hfc_female, hfc_male | en_US-hfc_*-medium | CC BY-NC-SA 4.0 | NO: non-commercial |
| amy, alan, jenny_dioco, lessac, arctic | various | "See URL" or a custom licence | NOT USED until the licence is read and confirmed |

Piper has no Indian English voice, so "English (India)" is shown as unavailable.

## Candidates evaluated, not installed

| Candidate | Purpose | Finding |
|---|---|---|
| Piper (`piper-tts`) | Local text to speech for samples and voice notes | Engine is open source (MIT for the archived project, GPL-3.0 for the current maintained one; both compatible with AGPL-3.0). Not installed yet, so samples are disabled with a visible reason. Confirm the exact package licence when installing. |
| Voice cloning model | "Clone my voice" | No model has been verified yet. Known open models either have non-commercial weights or need a GPU. The feature stays disabled with the reason shown until one is chosen and its licence is verified. |
| Whisper (speech to text), Ollama (local models) | Local assistant options (area 8) | To be evaluated in area 8. |
