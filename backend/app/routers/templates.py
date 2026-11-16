from fastapi import APIRouter, Depends, HTTPException
from pydantic import ValidationError
from sqlalchemy.orm import Session

from ..errors import sanitize_errors
from ..database import get_db
from ..deps import get_data_user, get_manager_user
from ..serializers import template_out
from ..schemas import TemplateIn, TemplateUpdateIn
from .. import models

router = APIRouter(prefix="/templates", tags=["templates"])


def _parse(model, body: dict):
    try:
        return model.model_validate(body)
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=sanitize_errors(e.errors()))


def _owned(db: Session, user: models.User, template_id: str) -> models.Template:
    t = db.get(models.Template, template_id)
    if not t or t.user_id != user.id:
        raise HTTPException(status_code=404, detail="Template not found")
    return t


@router.get("")
def list_templates(
    db: Session = Depends(get_db), user: models.User = Depends(get_data_user)
):
    templates = (
        db.query(models.Template)
        .filter(models.Template.user_id == user.id)
        .order_by(models.Template.created_at.desc())
        .all()
    )
    return [template_out(t) for t in templates]


def _unique_shortcut(db: Session, user: models.User, shortcut: str | None, own_id: str | None = None) -> None:
    if shortcut and db.query(models.Template.id).filter(models.Template.user_id == user.id, models.Template.shortcut == shortcut, models.Template.id != (own_id or "")).first():
        raise HTTPException(status_code=409, detail=f"/{shortcut} is already used by another template. Choose a different shortcut.")


def _create(payload: TemplateIn, db: Session, user: models.User):
    _unique_shortcut(db, user, payload.shortcut)
    t = models.Template(
        shortcut=payload.shortcut,
        user_id=user.id,
        name=payload.name,
        category=payload.category or "first_message",
        body=payload.body or "",
    )
    db.add(t)
    db.commit()
    db.refresh(t)
    return template_out(t)


def _update(template_id: str, payload: TemplateUpdateIn, db: Session, user: models.User):
    t = _owned(db, user, template_id)
    data = payload.model_dump(exclude_unset=True)
    if "shortcut" in data:
        _unique_shortcut(db, user, data["shortcut"], t.id)
        t.shortcut = data["shortcut"]
    for field in ("name", "category", "body"):
        if field in data and data[field] is not None:
            setattr(t, field, data[field])
    db.commit()
    db.refresh(t)
    return template_out(t)


def _delete(template_id: str, db: Session, user: models.User):
    t = _owned(db, user, template_id)
    db.delete(t)
    db.commit()
    return {"ok": True}


@router.post("")
def write_templates(
    body: dict,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_manager_user),
):
    """Write gateway for templates: ``action`` is ``create`` (TemplateIn
    fields), ``update`` (``id`` + changed fields), or ``delete`` (``id``)."""
    action = body.get("action")
    if action == "create":
        return _create(_parse(TemplateIn, body), db, user)
    if action == "update":
        if not body.get("id"):
            raise HTTPException(status_code=400, detail="id is required to update a template")
        return _update(body["id"], _parse(TemplateUpdateIn, body), db, user)
    if action == "delete":
        if not body.get("id"):
            raise HTTPException(status_code=400, detail="id is required to delete a template")
        return _delete(body["id"], db, user)
    raise HTTPException(status_code=400, detail=f"Unknown template action: {action!r}")
