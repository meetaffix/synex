"""The do-not-contact list: add, import, export, search, remove."""
import csv
import io
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import or_
from sqlalchemy.orm import Session

from .. import csv_safe, dnc, models
from ..database import get_db
from ..deps import get_data_user, get_manager_user

router = APIRouter(prefix="/do-not-contact", tags=["Do not contact"])
Kind = Literal["person", "company"]
MAX_LINES = 5000


def _row(item: models.DoNotContact) -> dict:
    return {"id": item.id, "kind": item.kind, "name": item.name, "profileUrl": item.profile_url, "source": item.source, "addedAt": item.created_at.isoformat()}


@router.get("")
def list_entries(kind: Kind = "person", q: str = "", limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0),
                 db: Session = Depends(get_db), workspace: models.User = Depends(get_data_user)):
    query = db.query(models.DoNotContact).filter_by(user_id=workspace.id, kind=kind)
    if q.strip():
        like = f"%{q.strip().lower()}%"
        from sqlalchemy import func
        query = query.filter(or_(func.lower(models.DoNotContact.name).like(like), func.lower(models.DoNotContact.profile_url).like(like), models.DoNotContact.key.like(like)))
    total = query.count()
    rows = query.order_by(models.DoNotContact.created_at.desc(), models.DoNotContact.id).offset(offset).limit(limit).all()
    return {"items": [_row(r) for r in rows], "total": total}


class AddIn(BaseModel):
    kind: Kind
    text: str = Field(max_length=500_000)


@router.post("")
def add(body: AddIn, db: Session = Depends(get_db), workspace: models.User = Depends(get_manager_user)):
    lines = [line.strip() for line in body.text.splitlines() if line.strip()]
    if not lines:
        raise HTTPException(422, "Paste at least one line.")
    if len(lines) > MAX_LINES:
        raise HTTPException(422, f"Add at most {MAX_LINES} lines at a time.")
    result = dnc.add_entries(db, workspace.id, body.kind, [{"value": line} for line in lines], "manual")
    db.commit()
    return result


class ImportIn(BaseModel):
    kind: Kind
    csv_text: str = Field(alias="csv", max_length=2_000_000)


@router.post("/import")
def import_csv(body: ImportIn, db: Session = Depends(get_db), workspace: models.User = Depends(get_manager_user)):
    try:
        headers, rows = csv_safe.parse(body.csv_text, max_rows=MAX_LINES)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    fields = {(f or "").strip().lower(): f for f in headers}
    column = fields.get("linkedin_url") if body.kind == "person" else (fields.get("company") or fields.get("name") or fields.get("linkedin_url"))
    if column is None:
        need = "linkedin_url" if body.kind == "person" else "company"
        raise HTTPException(422, f"The file needs a column named {need}.")
    name_col = fields.get("name")
    entries = [{"value": row.get(column) or "", "name": (row.get(name_col) or "") if name_col and name_col != column else ""} for row in rows]
    result = dnc.add_entries(db, workspace.id, body.kind, entries, "csv")
    db.commit()
    return result


@router.get("/export")
def export(kind: Kind = "person", db: Session = Depends(get_db), workspace: models.User = Depends(get_data_user)):
    rows = db.query(models.DoNotContact).filter_by(user_id=workspace.id, kind=kind).order_by(models.DoNotContact.created_at).all()
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["linkedin_url", "name", "source", "added"] if kind == "person" else ["company", "source", "added"])
    for r in rows:
        writer.writerow(csv_safe.row([r.profile_url, r.name, r.source, r.created_at.date().isoformat()]) if kind == "person"
                        else csv_safe.row([r.name, r.source, r.created_at.date().isoformat()]))
    filename = "synex-do-not-contact-people.csv" if kind == "person" else "synex-do-not-contact-companies.csv"
    return Response(out.getvalue(), media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.delete("/{entry_id}", status_code=204)
def remove(entry_id: str, db: Session = Depends(get_db), workspace: models.User = Depends(get_manager_user)):
    item = db.get(models.DoNotContact, entry_id)
    if item is None or item.user_id != workspace.id:
        raise HTTPException(404, "That entry was not found.")
    db.delete(item)
    db.commit()
    return Response(status_code=204)
