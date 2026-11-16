"""Company lists: the companies collected from company searches and Sales Navigator accounts. Companies are not people and are never messaged."""
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import func
from sqlalchemy.orm import Session

from .. import dnc, models
from ..database import get_db
from ..deps import get_data_user, get_manager_user

router = APIRouter(prefix="/company-lists", tags=["Company lists"])


def _owned(db: Session, user: models.User, list_id: str) -> models.CompanyList:
    item = db.get(models.CompanyList, list_id)
    if item is None or item.user_id != user.id:
        raise HTTPException(404, "This company list was not found.")
    return item


@router.get("")
def lists(db: Session = Depends(get_db), user: models.User = Depends(get_data_user)):
    counts = dict(db.query(models.CompanyEntry.list_id, func.count()).group_by(models.CompanyEntry.list_id).all())
    rows = db.query(models.CompanyList).filter_by(user_id=user.id).order_by(models.CompanyList.created_at.desc()).all()
    return [{"id": r.id, "name": r.name, "count": counts.get(r.id, 0), "createdAt": r.created_at.isoformat()} for r in rows]


@router.get("/{list_id}")
def entries(list_id: str, limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0), db: Session = Depends(get_db),
            user: models.User = Depends(get_data_user)):
    item = _owned(db, user, list_id)
    query = db.query(models.CompanyEntry).filter_by(list_id=item.id)
    rows = query.order_by(models.CompanyEntry.name).offset(offset).limit(limit).all()
    return {"id": item.id, "name": item.name, "total": query.count(),
            "items": [{"id": r.id, "name": r.name, "url": r.url, "industry": r.industry, "location": r.location} for r in rows]}


@router.post("/{list_id}/do-not-contact")
def add_to_do_not_contact(list_id: str, db: Session = Depends(get_db), user: models.User = Depends(get_manager_user)):
    """Put every company on this list on the do-not-contact list."""
    item = _owned(db, user, list_id)
    rows = db.query(models.CompanyEntry).filter_by(list_id=item.id).all()
    result = dnc.add_entries(db, user.id, "company", [{"value": r.name or r.url} for r in rows], "manual")
    db.commit()
    return result


@router.delete("/{list_id}", status_code=204)
def delete(list_id: str, db: Session = Depends(get_db), user: models.User = Depends(get_manager_user)):
    item = _owned(db, user, list_id)
    db.query(models.CompanyEntry).filter_by(list_id=item.id).delete()
    db.delete(item)
    db.commit()
    return Response(status_code=204)
