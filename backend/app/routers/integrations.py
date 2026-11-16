"""Settings and integrations: notifications, API keys, webhooks and Slack, usage, support, email-tool exports, a competitor-export importer and HubSpot import."""
import csv
import io
import json
import secrets
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .. import integrations_core as core, lead_sources, models
from ..database import get_db
from ..deps import get_admin_user, get_data_user, get_manager_user
from ..dedup import normalize_linkedin_url
from ..security import decrypt_secret, encrypt_secret

router = APIRouter(prefix="/integrations", tags=["integrations"])


# ---- notifications ------------------------------------------------------------------------------------------------------

@router.get("/events")
def events(user: models.User = Depends(get_data_user)):
    return [{"id": k, "label": v} for k, v in core.EVENTS.items()]


@router.get("/notifications")
def get_notifications(db: Session = Depends(get_db), user: models.User = Depends(get_data_user)):
    return core.notification_settings(db, user.id)


@router.put("/notifications")
def put_notifications(body: dict, db: Session = Depends(get_db), user: models.User = Depends(get_admin_user)):
    try:
        value = core.check_notification_settings(body)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    row = db.get(models.WorkspaceSetting, (user.id, "notifications")) or models.WorkspaceSetting(user_id=user.id, key="notifications")
    row.value = value
    db.add(row)
    db.commit()
    return value


@router.post("/notifications/test")
def test_notification(db: Session = Depends(get_db), user: models.User = Depends(get_admin_user)):
    emails = core.notification_settings(db, user.id)["emails"]
    if not emails:
        raise HTTPException(409, "Add at least one notification email address first.")
    results = [core.send_mail(db, user.id, e, "Synex: test notification", "This is a test. Notifications are working.") for e in emails]
    db.commit()
    return {"results": results, "note": "Emails are always saved in the outbox below. They are sent only when SMTP is set up on the server." if "stored" in results else "Sent."}


@router.get("/outbox")
def outbox(db: Session = Depends(get_db), user: models.User = Depends(get_data_user)):
    rows = db.query(models.OutboxEmail).filter_by(user_id=user.id).order_by(models.OutboxEmail.created_at.desc()).limit(20).all()
    return [{"id": r.id, "to": r.to_address, "subject": r.subject, "status": r.status, "createdAt": r.created_at.isoformat()} for r in rows]


# ---- API keys -----------------------------------------------------------------------------------------------------------

class KeyIn(BaseModel):
    name: str = Field("API key", max_length=80)


@router.get("/api-keys")
def list_keys(db: Session = Depends(get_db), user: models.User = Depends(get_data_user)):
    rows = db.query(models.ApiKey).filter_by(user_id=user.id).order_by(models.ApiKey.created_at.desc()).all()
    return [{"id": r.id, "name": r.name, "prefix": r.prefix, "createdAt": r.created_at.isoformat(), "lastUsedAt": r.last_used_at.isoformat() if r.last_used_at else None,
             "revoked": r.revoked_at is not None} for r in rows]


@router.post("/api-keys", status_code=201)
def create_key(body: KeyIn, db: Session = Depends(get_db), user: models.User = Depends(get_admin_user)):
    row, key = core.create_api_key(db, user.id, body.name)
    db.commit()
    return {"id": row.id, "name": row.name, "prefix": row.prefix, "key": key, "note": "Copy this key now. It is shown only once."}


@router.delete("/api-keys/{key_id}", status_code=204)
def revoke_key(key_id: str, db: Session = Depends(get_db), user: models.User = Depends(get_admin_user)):
    row = db.get(models.ApiKey, key_id)
    if row is None or row.user_id != user.id:
        raise HTTPException(404, "Key not found")
    row.revoked_at = datetime.now(timezone.utc)
    db.commit()
    return Response(status_code=204)


# ---- webhooks and Slack ------------------------------------------------------------------------------------------------

class HookIn(BaseModel):
    kind: Literal["webhook", "slack"] = "webhook"
    url: str = Field(max_length=500)
    events: list[str] = Field(min_length=1, max_length=20)


def _hook_out(h: models.Webhook, secret: bool = False) -> dict:
    out = {"id": h.id, "kind": h.kind, "url": h.url, "events": h.events or [], "enabled": bool(h.enabled), "createdAt": h.created_at.isoformat()}
    if secret and h.kind == "webhook":
        out["secret"] = h.secret
    return out


@router.get("/webhooks")
def list_hooks(db: Session = Depends(get_db), user: models.User = Depends(get_data_user)):
    return [_hook_out(h) for h in db.query(models.Webhook).filter_by(user_id=user.id).order_by(models.Webhook.created_at).all()]


@router.post("/webhooks", status_code=201)
def create_hook(body: HookIn, db: Session = Depends(get_db), user: models.User = Depends(get_admin_user)):
    unknown = [e for e in body.events if e not in core.EVENTS]
    if unknown:
        raise HTTPException(422, "Unknown event: " + ", ".join(unknown) + ".")
    problem = core.check_webhook_url(body.url, body.kind)
    if problem:
        raise HTTPException(422, problem)
    hook = models.Webhook(user_id=user.id, kind=body.kind, url=body.url.strip(), events=body.events, secret="whsec_" + secrets.token_urlsafe(24))
    db.add(hook)
    db.commit()
    return _hook_out(hook, secret=True)


class HookPatch(BaseModel):
    enabled: bool


@router.patch("/webhooks/{hook_id}")
def patch_hook(hook_id: str, body: HookPatch, db: Session = Depends(get_db), user: models.User = Depends(get_admin_user)):
    hook = _owned_hook(db, user, hook_id)
    hook.enabled = body.enabled
    db.commit()
    return _hook_out(hook)


def _owned_hook(db: Session, user: models.User, hook_id: str) -> models.Webhook:
    hook = db.get(models.Webhook, hook_id)
    if hook is None or hook.user_id != user.id:
        raise HTTPException(404, "Webhook not found")
    return hook


@router.delete("/webhooks/{hook_id}", status_code=204)
def delete_hook(hook_id: str, db: Session = Depends(get_db), user: models.User = Depends(get_admin_user)):
    db.delete(_owned_hook(db, user, hook_id))
    db.commit()
    return Response(status_code=204)


@router.post("/webhooks/{hook_id}/test")
def test_hook(hook_id: str, db: Session = Depends(get_db), user: models.User = Depends(get_admin_user)):
    hook = _owned_hook(db, user, hook_id)
    status, error = core._post(hook, "test", {"name": "Test event from Synex"})
    db.add(models.WebhookDelivery(webhook_id=hook.id, event="test", status_code=status, error=error, ok=bool(status and 200 <= status < 300)))
    db.commit()
    return {"ok": bool(status and 200 <= status < 300), "status": status, "error": error}


@router.get("/webhooks/{hook_id}/deliveries")
def deliveries(hook_id: str, db: Session = Depends(get_db), user: models.User = Depends(get_data_user)):
    hook = _owned_hook(db, user, hook_id)
    rows = db.query(models.WebhookDelivery).filter_by(webhook_id=hook.id).order_by(models.WebhookDelivery.created_at.desc()).limit(25).all()
    return [{"id": r.id, "event": r.event, "status": r.status_code, "ok": r.ok, "error": r.error, "createdAt": r.created_at.isoformat()} for r in rows]


# ---- usage and support -------------------------------------------------------------------------------------------------

@router.get("/usage")
def get_usage(db: Session = Depends(get_db), user: models.User = Depends(get_data_user)):
    return core.usage(db, user.id)


class SupportIn(BaseModel):
    subject: str = Field(min_length=3, max_length=120)
    body: str = Field(min_length=10, max_length=4000)


@router.post("/support", status_code=201)
def support(body: SupportIn, db: Session = Depends(get_db), user: models.User = Depends(get_manager_user)):
    db.add(models.SupportMessage(user_id=user.id, subject=body.subject.strip(), body=body.body.strip()))
    db.commit()
    return {"ok": True, "note": "Your message is saved in this workspace. Synex has no support team behind it yet, so ask whoever runs this installation."}


@router.get("/support")
def my_support(db: Session = Depends(get_db), user: models.User = Depends(get_data_user)):
    rows = db.query(models.SupportMessage).filter_by(user_id=user.id).order_by(models.SupportMessage.created_at.desc()).limit(20).all()
    return [{"id": r.id, "subject": r.subject, "createdAt": r.created_at.isoformat()} for r in rows]


# ---- email-tool exports -------------------------------------------------------------------------------------------------

def _list_leads(db: Session, user: models.User, list_id: str) -> list[models.Lead]:
    lead_list = db.get(models.LeadList, list_id)
    if lead_list is None or lead_list.user_id != user.id:
        raise HTTPException(404, "Lead list not found")
    return list(lead_list.leads)


@router.get("/exports/{tool}")
def export_for_email_tool(tool: Literal["smartlead", "instantly"], list_id: str = Query(alias="listId"), db: Session = Depends(get_db), user: models.User = Depends(get_data_user)):
    """The people on a list, in the column names the email tool's CSV import expects. Only people with an email address are included; Synex
    never guesses an address. The sequence is not pushed: copy your messages into the tool."""
    leads = [l for l in _list_leads(db, user, list_id) if (l.email or "").strip()]
    out = io.StringIO()
    writer = csv.writer(out)
    safe = lambda v: "'" + v if (v or "")[:1] in ("=", "+", "-", "@") else (v or "")  # noqa: E731
    if tool == "smartlead":
        writer.writerow(["email", "first_name", "last_name", "company_name", "title", "location", "linkedin_profile", "phone_number"])
        for l in leads:
            writer.writerow([l.email, safe(l.first_name), safe(l.last_name), safe(l.company), safe(l.job_title), safe(l.location), l.linkedin_url or "", l.phone or ""])
    else:
        writer.writerow(["Email", "First Name", "Last Name", "Company Name", "Job Title", "Website", "Personalization"])
        for l in leads:
            writer.writerow([l.email, safe(l.first_name), safe(l.last_name), safe(l.company), safe(l.job_title), l.linkedin_url or "", ""])
    skipped = len(_list_leads(db, user, list_id)) - len(leads)
    return Response(out.getvalue(), media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="synex-{tool}.csv"', "X-Skipped-No-Email": str(skipped)})


# ---- importer for another tool's export --------------------------------------------------------------------------------

class ImportIn(BaseModel):
    csv_text: str = Field(alias="csv", max_length=5_000_000)
    list_column: str | None = Field(None, alias="listColumn")
    default_list: str = Field("Imported leads", alias="defaultList", max_length=100)
    model_config = {"populate_by_name": True}


@router.post("/import/leads")
def import_leads(body: ImportIn, db: Session = Depends(get_db), user: models.User = Depends(get_manager_user)):
    """Leads from another outreach tool's CSV export (HeyReach, OutFlo and similar). Columns are matched by name; a list column (campaign or list name)
    puts people on lists of that name. Campaigns and conversation history are not imported: they do not carry over safely."""
    headers, rows = lead_sources.read_csv(body.csv_text)
    mapping = lead_sources.suggest_mapping(headers)
    if "linkedin_url" not in mapping:
        raise HTTPException(422, "The file needs a column with each person's LinkedIn profile address (for example 'linkedin_url' or 'Profile URL').")
    people, missing = lead_sources.rows_to_people(rows, mapping)
    lists: dict[str, models.LeadList] = {}
    existing = {normalize_linkedin_url(l.linkedin_url): l for l in db.query(models.Lead).filter(models.Lead.user_id == user.id, models.Lead.linkedin_url != "")}
    by_url = {normalize_linkedin_url(r.get(mapping["linkedin_url"]) or ""): r for r in rows}
    created = updated = 0
    for person in people:
        key = normalize_linkedin_url(person["profile_url"])
        list_name = ((by_url.get(key) or {}).get(body.list_column or "") or "").strip() or body.default_list
        lead_list = lists.get(list_name)
        if lead_list is None:
            lead_list = db.query(models.LeadList).filter_by(user_id=user.id, name=list_name).first() or models.LeadList(user_id=user.id, name=list_name)
            db.add(lead_list)
            db.flush()
            lists[list_name] = lead_list
        lead = existing.get(key)
        if lead is None:
            first, _, last = (person["name"] or "").strip().partition(" ")
            lead = models.Lead(user_id=user.id, first_name=first, last_name=last, headline=person["headline"], company=person["company"] or "", location=person["location"],
                               linkedin_url=person["profile_url"], source="import", status="new", email=(person.get("extra") or {}).get("email"))
            db.add(lead)
            db.flush()
            existing[key] = lead
            created += 1
        else:
            updated += 1
        if lead not in lead_list.leads:
            lead_list.leads.append(lead)
    db.commit()
    return {"created": created, "alreadyKnown": updated, "withoutProfileLink": missing, "lists": sorted(lists)}


# ---- HubSpot -------------------------------------------------------------------------------------------------------------

HUBSPOT = "https://api.hubapi.com"


def hubspot_fetch(token: str, after: str | None) -> dict:
    """One page of HubSpot contacts. UNVERIFIED against the real service: built from HubSpot's public CRM v3 documentation, tested with a stand-in."""
    url = f"{HUBSPOT}/crm/v3/objects/contacts?limit=100&properties=firstname,lastname,email,company,jobtitle,hs_linkedin_url,phone,city" + (f"&after={after}" if after else "")
    request = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(request, timeout=20) as response:  # noqa: S310 - fixed host
            return json.loads(response.read().decode())
    except urllib.error.HTTPError as exc:
        raise HTTPException(502, "HubSpot refused the token." if exc.code in (401, 403) else f"HubSpot answered {exc.code}.")
    except Exception:  # noqa: BLE001
        raise HTTPException(502, "HubSpot could not be reached.")


class HubspotToken(BaseModel):
    token: str = Field(min_length=10, max_length=300)


@router.get("/hubspot")
def hubspot_status(db: Session = Depends(get_db), user: models.User = Depends(get_data_user)):
    row = db.get(models.WorkspaceSetting, (user.id, "hubspot"))
    return {"connected": bool(row and row.value.get("token")), "note": "Built from HubSpot's public API documentation and not verified against a real HubSpot account."}


@router.put("/hubspot")
def hubspot_connect(body: HubspotToken, db: Session = Depends(get_db), user: models.User = Depends(get_admin_user)):
    row = db.get(models.WorkspaceSetting, (user.id, "hubspot")) or models.WorkspaceSetting(user_id=user.id, key="hubspot")
    row.value = {"token": encrypt_secret(body.token.strip())}
    db.add(row)
    db.commit()
    return {"connected": True}


@router.delete("/hubspot", status_code=204)
def hubspot_disconnect(db: Session = Depends(get_db), user: models.User = Depends(get_admin_user)):
    row = db.get(models.WorkspaceSetting, (user.id, "hubspot"))
    if row:
        db.delete(row)
        db.commit()
    return Response(status_code=204)


@router.post("/hubspot/import")
def hubspot_import(db: Session = Depends(get_db), user: models.User = Depends(get_manager_user)):
    """Import HubSpot contacts that have a LinkedIn profile address into a list named 'HubSpot contacts'. Up to 500 contacts a run."""
    row = db.get(models.WorkspaceSetting, (user.id, "hubspot"))
    if not row or not row.value.get("token"):
        raise HTTPException(409, "Connect HubSpot first by saving a private app token.")
    token = decrypt_secret(row.value["token"])
    lead_list = db.query(models.LeadList).filter_by(user_id=user.id, name="HubSpot contacts").first() or models.LeadList(user_id=user.id, name="HubSpot contacts")
    db.add(lead_list)
    db.flush()
    existing = {normalize_linkedin_url(l.linkedin_url): l for l in db.query(models.Lead).filter(models.Lead.user_id == user.id, models.Lead.linkedin_url != "")}
    created = skipped = seen = 0
    after = None
    for _ in range(5):
        page = hubspot_fetch(token, after)
        for item in page.get("results", []):
            p = item.get("properties") or {}
            seen += 1
            url = (p.get("hs_linkedin_url") or "").strip()
            key = normalize_linkedin_url(url)
            if not key.startswith("linkedin.com/in/"):
                skipped += 1
                continue
            lead = existing.get(key)
            if lead is None:
                lead = models.Lead(user_id=user.id, first_name=p.get("firstname") or "", last_name=p.get("lastname") or "", company=p.get("company") or "", job_title=p.get("jobtitle") or "",
                                   email=p.get("email"), phone=p.get("phone"), location=p.get("city"), linkedin_url=url, source="hubspot", status="new")
                db.add(lead)
                db.flush()
                existing[key] = lead
                created += 1
            if lead not in lead_list.leads:
                lead_list.leads.append(lead)
        after = ((page.get("paging") or {}).get("next") or {}).get("after")
        if not after:
            break
    db.commit()
    return {"seen": seen, "created": created, "withoutLinkedinAddress": skipped}
