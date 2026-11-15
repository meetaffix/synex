from fastapi import APIRouter, Depends

from ..deps import get_data_user
from ..schemas import AIGenerateIn
from ..providers import get_ai_provider
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
    body = provider.generate_message(payload.step_type or "message", payload.tone or "friendly", ctx)
    return {"body": body}
