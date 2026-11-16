"""Like a post, InMail, free InMail and voice note: the browser actions on the mock site, the worker running them from a campaign, and the result handling.
All of it is built and tested against the mock site only: the real LinkedIn pages are unverified."""
import base64
import io
import os
import stat
import sys
import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

from test_outreach import MOCK, OutreachCase, SessionLocal  # noqa: E402  (sets the isolated environment)
from app import models, voice
from app.linkedin_session import actions

from test_graph import tree  # noqa: E402


def wav_bytes(seconds=1.0) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(8000)
        w.writeframes(b"\x00\x00" * int(8000 * seconds))
    return buffer.getvalue()


class ActionTest(OutreachCase):
    def test_like_the_latest_post_once_and_report_when_there_is_nothing_to_like(self):
        MOCK.profile("pia")["posts"] = 1
        MOCK.profile("zoe")["posts"] = 0
        self.assertEqual(self.open_session(lambda s: actions.like_post(s, MOCK.profile_url("pia"))), actions.LikeResult.LIKED)
        self.assertEqual(MOCK.likes, ["pia"])
        self.assertEqual(self.open_session(lambda s: actions.like_post(s, MOCK.profile_url("pia"))), actions.LikeResult.ALREADY_LIKED)
        self.assertEqual(MOCK.likes, ["pia"])  # nothing clicked the second time
        self.assertEqual(self.open_session(lambda s: actions.like_post(s, MOCK.profile_url("zoe"))), actions.LikeResult.NO_POSTS)
        MOCK.profile("gone")["available"] = False
        self.assertEqual(self.open_session(lambda s: actions.like_post(s, MOCK.profile_url("gone"))), actions.LikeResult.PROFILE_UNAVAILABLE)

    def inmail(self, user, free=False):
        return self.open_session(lambda s: actions.send_inmail(s, MOCK.profile_url(user), "Quick question", "Hello there", free))

    def test_an_inmail_spends_a_credit_and_a_free_inmail_spends_none(self):
        MOCK.profile("cred")["inmail"] = "credit"
        MOCK.profile("open")["inmail"] = "free"
        self.assertEqual(self.inmail("cred"), actions.InMailResult.SENT)
        self.assertEqual(MOCK.inmails, [("cred", "Quick question", "Hello there")])
        self.assertEqual(MOCK.inmail_credits, 4)
        self.assertEqual(self.inmail("open", free=True), actions.InMailResult.SENT)
        self.assertEqual(MOCK.inmail_credits, 4)

    def test_inmail_refuses_when_it_should_not_be_sent(self):
        MOCK.profile("cred")["inmail"] = "credit"
        MOCK.profile("friend")["state"] = "connected"
        MOCK.profile("closed")["inmail"] = "none"
        MOCK.inmail_credits = 0
        self.assertEqual(self.inmail("cred"), actions.InMailResult.NO_CREDITS)
        MOCK.inmail_credits = 5
        self.assertEqual(self.inmail("cred", free=True), actions.InMailResult.NOT_FREE)  # a free one was asked for, this profile does not offer it
        self.assertEqual(self.inmail("friend"), actions.InMailResult.ALREADY_CONNECTED)  # a normal message does it: no credit spent
        self.assertEqual(self.inmail("closed"), actions.InMailResult.NOT_AVAILABLE)
        self.assertEqual(MOCK.inmails, [])
        self.assertEqual(MOCK.inmail_credits, 5)

    def test_a_voice_note_attaches_the_prepared_file_for_a_connection_only(self):
        MOCK.profile("friend")["state"] = "connected"
        path = Path(tempfile.mkdtemp()) / "note.wav"
        path.write_bytes(wav_bytes())
        self.assertEqual(self.open_session(lambda s: actions.send_voice_note(s, MOCK.profile_url("friend"), str(path))), actions.VoiceResult.SENT)
        self.assertEqual(MOCK.voice_notes, [("friend", "note.wav", path.stat().st_size)])
        self.assertEqual(self.open_session(lambda s: actions.send_voice_note(s, MOCK.profile_url("stranger"), str(path))), actions.VoiceResult.NOT_CONNECTED)
        self.assertEqual(len(MOCK.voice_notes), 1)


class WorkerFlowTest(OutreachCase):
    """A campaign step becomes a task, the worker runs it on the mock site, and the run moves on."""

    def run_steps(self, spec, status="connected"):
        campaign_id = self.make_campaign([{"user": "ann", "status": status}], steps=[], launch=False)
        with SessionLocal() as db:
            from app import engine
            campaign = db.get(models.Campaign, campaign_id)
            tree(db, campaign, spec)
            engine.launch_campaign(db, campaign)
            db.commit()

    def run_until(self, until, rounds=14):
        for _ in range(rounds):
            self.tick()
            self.worker.run_once(wait=True)
            if until():
                return
        self.fail("the sequence did not reach the expected state")

    def test_like_then_inmail_then_the_run_completes(self):
        MOCK.profile("ann")["state"] = "not_connected"
        MOCK.profile("ann")["inmail"] = "credit"
        self.run_steps([("l", "like_post", None, None, {}), ("i", "inmail", None, None, {"message": "Hello {{first_name}}", "config": {"subject": "Hi"}})], status="new")
        self.run_until(lambda: self.run_of("ann").status == "completed")
        self.assertEqual(MOCK.likes, ["ann"])
        self.assertEqual(MOCK.inmails, [("ann", "Hi", "Hello Ann")])
        with SessionLocal() as db:
            self.assertEqual(db.query(models.Message).filter(models.Message.body.like("Subject: Hi%")).count(), 1)

    def test_a_voice_note_step_sends_the_prepared_audio(self):
        MOCK.profile("ann")["state"] = "connected"
        with SessionLocal() as db:
            row = voice.save(db, self.user_id, kind="upload", language="en-US", filename="intro.wav", content_type="audio/wav", data=wav_bytes(), seconds=1.0)
            db.commit()
            audio_id, size = row.id, row.size
        self.run_steps([("v", "voice_note", None, None, {"config": {"mode": "direct", "language": "en-US", "audioId": audio_id}})])
        self.run_until(lambda: self.run_of("ann").status == "completed")
        self.assertEqual(MOCK.voice_notes, [("ann", "intro.wav", size)])

    def test_no_inmail_credits_stops_the_run_with_a_clear_reason_and_spends_no_allowance(self):
        MOCK.profile("ann")["inmail"] = "credit"
        MOCK.inmail_credits = 0
        self.run_steps([("i", "inmail", None, None, {"message": "Hello"})], status="new")
        self.run_until(lambda: self.run_of("ann").status == "stopped")
        self.assertEqual(self.run_of("ann").stop_reason, "no_inmail_credits")

    def test_withdraw_step_inside_a_campaign_withdraws_and_moves_on(self):
        MOCK.profile("ann")["state"] = "pending"
        self.run_steps([("w", "withdraw_invite", None, None, {})], status="contacted")
        self.run_until(lambda: self.run_of("ann").status == "completed")
        self.assertEqual(MOCK.withdrawals, ["ann"])


class VoiceModuleTest(OutreachCase):
    def test_uploads_are_checked_for_type_size_and_length(self):
        self.assertEqual(voice.check_audio("a.wav", wav_bytes(2))[0], "audio/wav")
        for name, data, reason in (("a.txt", b"x", ".m4a, .mp3 or .wav"), ("a.wav", b"not a wav", "valid .wav"), ("a.wav", b"", "empty"),
                                   ("a.m4a", b"0000notftyp", "valid .m4a"), ("a.mp3", b"nope", "valid .mp3"), ("a.wav", wav_bytes(61), "most is 60"),
                                   ("a.wav", b"RIFF" + b"0" * (voice.MAX_BYTES + 1), "larger than 20 MB")):
            with self.assertRaises(voice.VoiceError, msg=name) as caught:
                voice.check_audio(name, data)
            self.assertIn(reason, str(caught.exception))

    def test_an_mp3_and_an_m4a_too_long_are_refused_from_their_headers(self):
        mp3 = b"\xff\xfb\x90\x00" + b"\x00" * (128_000 // 8 * 120)  # 128 kbit/s, about 120 seconds
        with self.assertRaises(voice.VoiceError):
            voice.check_audio("long.mp3", mp3)
        mvhd = b"\x00\x00\x00\x00" + b"\x00" * 8 + (1000).to_bytes(4, "big") + (120_000).to_bytes(4, "big") + b"\x00" * 80  # 120 s at timescale 1000
        m4a = b"\x00\x00\x00\x18ftypM4A " + b"\x00" * 8 + b"mvhd" + mvhd
        with self.assertRaises(voice.VoiceError):
            voice.check_audio("long.m4a", m4a)

    def test_the_script_rules(self):
        with patch.dict(os.environ, {}, clear=False):
            for script, reason in (("", "Write the script"), ("x" * 1001, "1,000"), ("Hi {{first_name}}", "variables")):
                with self.assertRaises(voice.VoiceError) as caught:
                    voice.synthesize(script, "en-US")
                self.assertIn(reason, str(caught.exception))
            with self.assertRaises(voice.VoiceError) as caught:
                voice.synthesize("Hello", "fr-FR")
            self.assertIn("US, UK or India", str(caught.exception))

    def make_fake_piper(self):
        folder = Path(tempfile.mkdtemp())
        voice_file = folder / "en_US-test.onnx"
        voice_file.write_bytes(b"model")
        script = folder / "piper_fake.py"
        script.write_text("import sys, wave\nout = sys.argv[sys.argv.index('--output_file') + 1]\ntext = sys.stdin.read()\n"
                          "w = wave.open(out, 'wb'); w.setnchannels(1); w.setsampwidth(2); w.setframerate(8000); w.writeframes(b'\\x00\\x00' * 8000 * max(1, len(text.split()))); w.close()\n")
        launcher = folder / ("piper.bat" if os.name == "nt" else "piper")
        launcher.write_text(f'@echo off\r\n"{sys.executable}" "{script}" %*\r\n' if os.name == "nt" else f'#!/bin/sh\nexec "{sys.executable}" "{script}" "$@"\n')
        launcher.chmod(launcher.stat().st_mode | stat.S_IEXEC)
        return launcher, voice_file

    def test_text_to_speech_runs_the_local_engine_once_and_says_what_is_missing_when_it_is_not_installed(self):
        with patch.dict(os.environ, {"PIPER_BINARY": "definitely-not-installed"}):
            status = voice.tts_status()
            self.assertFalse(status["ready"])
            with self.assertRaises(voice.VoiceError) as caught:
                voice.synthesize("Hello there", "en-US")
            self.assertIn("not installed", str(caught.exception))
        launcher, voice_file = self.make_fake_piper()
        with patch.dict(os.environ, {"PIPER_BINARY": str(launcher), "PIPER_VOICE_EN_US": str(voice_file)}):
            self.assertTrue(voice.tts_status()["ready"])
            self.assertTrue(voice.tts_status()["languages"]["en-US"]["ready"])
            self.assertFalse(voice.tts_status()["languages"]["en-GB"]["ready"])
            data = voice.synthesize("Hello there friend", "en-US")
            self.assertEqual(voice.check_audio("speech.wav", data)[0], "audio/wav")
            with self.assertRaises(voice.VoiceError) as caught:
                voice.synthesize("Hello", "en-GB")
            self.assertIn("No Piper voice is set for English (UK)", str(caught.exception))

    def test_the_api_uploads_synthesizes_previews_and_deletes_for_its_own_workspace_only(self):
        body = {"filename": "hi.wav", "data": base64.b64encode(wav_bytes(2)).decode(), "language": "en-GB"}
        made = self.client.post("/voice-notes/upload", json=body)
        self.assertEqual(made.status_code, 201, made.text)
        item = made.json()
        self.assertEqual((item["kind"], item["language"], item["durationChecked"]), ("upload", "en-GB", True))
        self.assertEqual(self.client.get(f"/voice-notes/{item['id']}/audio").content[:4], b"RIFF")
        self.assertEqual(self.client.post("/voice-notes/upload", json={**body, "filename": "x.exe"}).status_code, 422)
        self.assertEqual(self.client.post("/voice-notes/upload", json={**body, "data": "not base64!!"}).status_code, 422)
        refused = self.client.post("/voice-notes/synthesize", json={"script": "Hello there", "language": "en-US"})
        self.assertEqual(refused.status_code, 422)  # no engine installed in the test environment
        self.assertEqual(self.client.post("/voice-notes/estimate", json={"script": "word " * 150}).json(), {"costUsd": 0, "estimatedSeconds": 60.0, "note": "Free: made on this computer."})
        launcher, voice_file = self.make_fake_piper()
        with patch.dict(os.environ, {"PIPER_BINARY": str(launcher), "PIPER_VOICE_EN_US": str(voice_file)}):
            ai = self.client.post("/voice-notes/synthesize", json={"script": "Hello there friend", "language": "en-US"})
        self.assertEqual((ai.status_code, ai.json()["kind"], ai.json()["script"]), (201, "tts", "Hello there friend"))
        with SessionLocal() as db:
            other = models.User(email="other@example.com", full_name="O", hashed_password="x")
            db.add(other)
            db.flush()
            row = voice.save(db, other.id, kind="upload", language="en-US", filename="o.wav", content_type="audio/wav", data=wav_bytes(), seconds=1.0)
            db.commit()
            other_id = row.id
        self.assertEqual(self.client.get(f"/voice-notes/{other_id}").status_code, 404)
        self.assertEqual(self.client.get(f"/voice-notes/{other_id}/audio").status_code, 404)
        self.assertEqual(self.client.delete(f"/voice-notes/{other_id}").status_code, 404)
        self.assertEqual(self.client.delete(f"/voice-notes/{item['id']}").status_code, 204)
        self.assertEqual(self.client.get(f"/voice-notes/{item['id']}").status_code, 404)
        info = self.client.get("/voice-notes/status").json()
        self.assertEqual(info["limits"], {"maxSeconds": 60, "maxBytes": 20 * 1024 * 1024, "maxScript": 1000, "formats": [".m4a", ".mp3", ".wav"]})
        self.assertEqual([l["id"] for l in info["languages"]], ["en-US", "en-GB", "en-IN"])

    def test_readiness_says_why_a_sender_cannot_send_a_voice_note(self):
        ready_id = self.make_account("ready")
        new_id = self.make_account("new", daily_limit=0)  # a new account starts stopped
        paused_id = self.make_account("paused")
        with SessionLocal() as db:
            db.get(models.LinkedInAccount, paused_id).status = "paused"
            db.commit()
        rows = {r["accountId"]: r for r in self.client.get("/voice-notes/readiness").json()}
        self.assertEqual((rows[ready_id]["ready"], rows[ready_id]["roomToday"]), (True, 20))
        self.assertEqual([r.split(".")[0] for r in rows[new_id]["reasons"]], ["Its daily action limit is 0, so it sends nothing yet"])
        self.assertFalse(rows[paused_id]["ready"])
        self.assertIn("paused or not connected", rows[paused_id]["reasons"][0])
        campaign_id = self.make_campaign(["ann"], steps=[], launch=False, accounts=[ready_id])
        self.assertEqual([r["accountId"] for r in self.client.get(f"/voice-notes/readiness?campaignId={campaign_id}").json()], [ready_id])
        self.assertEqual(self.client.get("/voice-notes/readiness?campaignId=nope").status_code, 404)


if __name__ == "__main__":
    unittest.main()
