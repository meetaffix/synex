from fastapi import APIRouter, Depends

from ..deps import get_data_user
from ..schemas import AIGenerateIn
from ..providers import TemplateAIProvider, get_ai_provider
from .. import models

router = APIRouter(prefix="/ai", tags=["ai"])


@router.post("/generate-message")
def generate_message(
    payload: AIGenerateIn,
    _: models.User = Depends(get_data_user),
):
    provider = get_ai_provider()
    ctx = {
        "first_name": payload.first_name,
        "company": payload.company,
        "job_title": payload.job_title,
    }
    step, tone = payload.step_type or "message", payload.tone or "friendly"
    try:
        body = provider.generate_message(step, tone, ctx)
    except Exception:  # Deepgram unreachable, refused or empty: the local draft is still a usable starting point
        body = TemplateAIProvider().generate_message(step, tone, ctx)
    return {"body": body}
