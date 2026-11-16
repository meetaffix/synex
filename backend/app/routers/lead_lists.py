import csv
import io

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import ValidationError
from sqlalchemy.orm import Session

from ..errors import sanitize_errors
from ..database import get_db
from ..deps import get_data_user, get_manager_user
from ..serializers import lead_list_out
from ..schemas import LeadListIn, LeadListUpdateIn
from .. import csv_safe, models

router = APIRouter(prefix="/lead-lists", tags=["lead-lists"])


def _parse(model, body: dict):
    try:
        return model.model_validate(body)
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=sanitize_errors(e.errors()))


def _owned(db: Session, user: models.User, list_id: str) -> models.LeadList:
    ll = db.get(models.LeadList, list_id)
    if not ll or ll.user_id != user.id:
        raise HTTPException(status_code=404, detail="List not found")
    return ll


@router.get("/{list_id}/export")
def export_list(list_id: str, db: Session = Depends(get_db), user: models.User = Depends(get_data_user)):
    """The people on one list as CSV. Text that would run as a spreadsheet formula is neutralised."""
    lead_list = _owned(db, user, list_id)
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["first_name", "last_name", "company", "job_title", "headline", "linkedin_url", "email", "phone", "location", "industry", "status"])
    for lead in sorted(lead_list.leads, key=lambda l: (l.last_name or "", l.first_name or "")):
        writer.writerow(csv_safe.row([lead.first_name, lead.last_name, lead.company, lead.job_title, lead.headline, lead.linkedin_url, lead.email, lead.phone,
                                      lead.location, lead.industry, lead.status]))
    name = "".join(c if c.isalnum() or c in "-_" else "-" for c in lead_list.name)[:60] or "list"
    return Response(out.getvalue(), media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="synex-list-{name}.csv"'})


@router.get("")
def list_lists(
    db: Session = Depends(get_db), user: models.User = Depends(get_data_user)
):
    lists = (
        db.query(models.LeadList)
        .filter(models.LeadList.user_id == user.id)
        .order_by(models.LeadList.created_at.desc())
        .all()
    )
    return [lead_list_out(ll) for ll in lists]


def _create(payload: LeadListIn, db: Session, user: models.User):
    ll = models.LeadList(
        user_id=user.id,
        name=payload.name,
        description=payload.description,
        color=payload.color or "#7C5CFF",
    )
    db.add(ll)
    db.commit()
    db.refresh(ll)
    return lead_list_out(ll)


def _update(list_id: str, payload: LeadListUpdateIn, db: Session, user: models.User):
    ll = _owned(db, user, list_id)
    data = payload.model_dump(exclude_unset=True)
    for field in ("name", "description", "color"):
        if field in data and data[field] is not None:
            setattr(ll, field, data[field])
    db.commit()
    db.refresh(ll)
    return lead_list_out(ll)


def _delete(list_id: str, db: Session, user: models.User):
    ll = _owned(db, user, list_id)
    db.delete(ll)
    db.commit()
    return {"ok": True}


@router.post("")
def write_lists(
    body: dict,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_manager_user),
):
    """Write gateway for lead lists: ``action`` is ``create`` (LeadListIn
    fields), ``update`` (``id`` + changed fields), or ``delete`` (``id``)."""
    action = body.get("action")
    if action == "create":
        return _create(_parse(LeadListIn, body), db, user)
    if action == "update":
        if not body.get("id"):
            raise HTTPException(status_code=400, detail="id is required to update a list")
        return _update(body["id"], _parse(LeadListUpdateIn, body), db, user)
    if action == "delete":
        if not body.get("id"):
            raise HTTPException(status_code=400, detail="id is required to delete a list")
        return _delete(body["id"], db, user)
    raise HTTPException(status_code=400, detail=f"Unknown lead-list action: {action!r}")
