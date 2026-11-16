"""Voice notes: upload or make the audio before launch, preview it, and see which senders are ready to send one."""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .. import account_policy, engine, models, voice
from ..database import get_db
from ..deps import get_data_user, get_manager_user

router = APIRouter(prefix="/voice-notes", tags=["voice notes"])


def _out(row: models.VoiceAudio) -> dict:
    return {"id": row.id, "kind": row.kind, "language": row.language, "filename": row.filename, "size": row.size, "durationSeconds": row.duration_seconds,
            "durationChecked": row.duration_seconds is not None, "script": row.script}


def _owned(db: Session, user: models.User, audio_id: str) -> models.VoiceAudio:
    row = db.get(models.VoiceAudio, audio_id)
    if row is None or row.user_id != user.id:
        raise HTTPException(404, "Voice note not found")
    return row


@router.get("/status")
def status(user: models.User = Depends(get_data_user)):
    return {"limits": {"maxSeconds": voice.MAX_SECONDS, "maxBytes": voice.MAX_BYTES, "maxScript": voice.MAX_SCRIPT, "formats": [".m4a", ".mp3", ".wav"]},
            "languages": [{"id": k, "label": v} for k, v in voice.LANGUAGES.items()], "tts": voice.tts_status()}


class UploadIn(BaseModel):
    filename: str = Field(max_length=200)
    data: str = Field(max_length=4 * ((voice.MAX_BYTES + 2) // 3) + 8)
    language: str = "en-US"


@router.post("/upload", status_code=201)
def upload(body: UploadIn, db: Session = Depends(get_db), user: models.User = Depends(get_manager_user)):
    try:
        data = voice.decode_upload(body.data)
        content_type, seconds = voice.check_audio(body.filename, data)
    except voice.VoiceError as exc:
        raise HTTPException(422, str(exc))
    row = voice.save(db, user.id, kind="upload", language=body.language if body.language in voice.LANGUAGES else "en-US", filename=body.filename,
                     content_type=content_type, data=data, seconds=seconds)
    db.commit()
    return _out(row)


class SynthIn(BaseModel):
    script: str = Field(max_length=voice.MAX_SCRIPT + 200)
    language: str = "en-US"


@router.post("/estimate")
def estimate(body: SynthIn, user: models.User = Depends(get_data_user)):
    return voice.estimate(body.script)


@router.post("/synthesize", status_code=201)
def synthesize(body: SynthIn, db: Session = Depends(get_db), user: models.User = Depends(get_manager_user)):
    """Make the audio from the script, once, now (never while a campaign is sending)."""
    try:
        data = voice.synthesize(body.script, body.language)
        content_type, seconds = voice.check_audio("speech.wav", data)
    except voice.VoiceError as exc:
        raise HTTPException(422, str(exc))
    row = voice.save(db, user.id, kind="tts", language=body.language, filename="voice-note.wav", content_type=content_type, data=data, seconds=seconds,
                     script=body.script.strip())
    db.commit()
    return _out(row)


@router.get("/readiness")
def readiness(campaign_id: str | None = Query(None, alias="campaignId"), db: Session = Depends(get_db), user: models.User = Depends(get_data_user)):
    """For each sender of a campaign (or all connected senders): can it send a voice note today, and if not, why."""
    now = datetime.now(timezone.utc)
    accounts = db.query(models.LinkedInAccount).filter(models.LinkedInAccount.user_id == user.id, models.LinkedInAccount.status.notin_(["deleted", "deactivated"])).all()
    if campaign_id:
        campaign = db.get(models.Campaign, campaign_id)
        if campaign is None or campaign.user_id != user.id:
            raise HTTPException(404, "Campaign not found")
        wanted = {campaign.account_id, *(campaign.account_ids or [])}
        accounts = [a for a in accounts if a.id in wanted]
    out = []
    for account in accounts:
        reasons = []
        if not engine.account_is_live(account, now):
            reasons.append("The account is paused or not connected. Reconnect or resume it.")
        if engine.effective_daily_limit(account, now) <= 0:
            reasons.append("Its daily action limit is 0, so it sends nothing yet. Set a limit on the account.")
        room = account_policy.action_room(db, account, "send_voice_note", now)
        if account_policy.bounds(account, "send_voice_note", now)[2] <= 0:
            reasons.append("Its daily voice-note limit is 0. Set a limit on the account's Sender limits tab.")
        elif room <= 0:
            reasons.append("It has used today's voice-note limit.")
        out.append({"accountId": account.id, "name": account.name, "ready": not reasons, "reasons": reasons, "roomToday": max(0, room)})
    return out


@router.get("/{audio_id}")
def meta(audio_id: str, db: Session = Depends(get_db), user: models.User = Depends(get_data_user)):
    return _out(_owned(db, user, audio_id))


@router.get("/{audio_id}/audio")
def audio(audio_id: str, db: Session = Depends(get_db), user: models.User = Depends(get_data_user)):
    row = _owned(db, user, audio_id)
    return Response(row.data, media_type=row.content_type, headers={"Content-Disposition": f'inline; filename="{row.filename}"'})


@router.delete("/{audio_id}", status_code=204)
def delete(audio_id: str, db: Session = Depends(get_db), user: models.User = Depends(get_manager_user)):
    db.delete(_owned(db, user, audio_id))
    db.commit()
    return Response(status_code=204)
