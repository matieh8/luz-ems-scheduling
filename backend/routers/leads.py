"""Leads (people who asked but are not clients yet), conversion by source, and referrals."""
from collections import defaultdict
from datetime import date, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from backend.database import get_db
from backend import models, schemas
from backend.tz import utcnow

router = APIRouter(prefix="/api/leads", tags=["Leads"])
SOURCES = "^(instagram|whatsapp|referral|google|walk-in|website|tiktok|facebook|other)$"
STATUSES = "^(new|contacted|trial_booked|won|lost)$"


class LeadIn(BaseModel):
    name: str = Field(..., min_length=1)
    phone: Optional[str] = None
    email: Optional[str] = None
    source: str = Field("other", pattern=SOURCES)
    interest: Optional[str] = None
    status: str = Field("new", pattern=STATUSES)
    lost_reason: Optional[str] = None
    next_follow_up: Optional[date] = None
    notes: Optional[str] = None
    referred_by_client_id: Optional[int] = None


class LeadUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1)
    phone: Optional[str] = None
    email: Optional[str] = None
    source: Optional[str] = Field(None, pattern=SOURCES)
    interest: Optional[str] = None
    status: Optional[str] = Field(None, pattern=STATUSES)
    lost_reason: Optional[str] = None
    next_follow_up: Optional[date] = None
    notes: Optional[str] = None
    referred_by_client_id: Optional[int] = None


def _out(l: models.Lead, db: Session) -> dict:
    ref = db.query(models.Client).filter(models.Client.id == l.referred_by_client_id).first() if l.referred_by_client_id else None
    return {"id": l.id, "name": l.name, "phone": l.phone, "email": l.email, "source": l.source, "interest": l.interest,
            "status": l.status, "lost_reason": l.lost_reason, "next_follow_up": l.next_follow_up, "notes": l.notes,
            "referred_by_client_id": l.referred_by_client_id, "referred_by_name": ref.name if ref else None,
            "converted_client_id": l.converted_client_id, "won_at": l.won_at, "created_at": l.created_at}


def _get(db: Session, lead_id: int) -> models.Lead:
    l = db.query(models.Lead).filter(models.Lead.id == lead_id).first()
    if not l:
        raise HTTPException(status_code=404, detail="Lead not found")
    return l


def _apply(l: models.Lead, data: dict):
    if "next_follow_up" in data:
        data["next_follow_up"] = data["next_follow_up"].isoformat() if data["next_follow_up"] else None
    for k, v in data.items():
        setattr(l, k, v)
    if l.status == "won" and not l.won_at:
        l.won_at = utcnow()


@router.get("/")
def list_leads(status: Optional[str] = None, db: Session = Depends(get_db)):
    q = db.query(models.Lead)
    if status:
        q = q.filter(models.Lead.status == status)
    rows = q.order_by(models.Lead.created_at.desc(), models.Lead.id.desc()).all()
    return [_out(l, db) for l in rows]


@router.post("/")
def create_lead(body: LeadIn, db: Session = Depends(get_db)):
    l = models.Lead()
    _apply(l, body.model_dump())
    db.add(l)
    db.commit()
    db.refresh(l)
    return _out(l, db)


@router.put("/{lead_id}")
def update_lead(lead_id: int, body: LeadUpdate, db: Session = Depends(get_db)):
    l = _get(db, lead_id)
    _apply(l, body.model_dump(exclude_unset=True))
    db.commit()
    db.refresh(l)
    return _out(l, db)


@router.delete("/{lead_id}")
def delete_lead(lead_id: int, db: Session = Depends(get_db)):
    db.delete(_get(db, lead_id))
    db.commit()
    return {"detail": "deleted"}


@router.post("/{lead_id}/convert")
def convert(lead_id: int, db: Session = Depends(get_db)):
    """Turn the lead into a client (or link the client with the same phone) and mark it won."""
    l = _get(db, lead_id)
    if l.converted_client_id:
        raise HTTPException(status_code=409, detail="This lead is already a client")
    client = db.query(models.Client).filter(models.Client.phone == l.phone).first() if l.phone else None
    if not client:
        client = models.Client(name=l.name, phone=l.phone or "-", email=l.email, source=l.source,
                               referred_by_client_id=l.referred_by_client_id,
                               notes=f"From lead: {l.interest}" if l.interest else None)
        db.add(client)
        db.flush()
    elif l.referred_by_client_id and not client.referred_by_client_id:
        client.referred_by_client_id = l.referred_by_client_id
    l.converted_client_id, l.status, l.won_at = client.id, "won", l.won_at or utcnow()
    db.commit()
    db.refresh(client)
    return {"lead": _out(l, db), "client": schemas.ClientResponse.model_validate(client).model_dump()}


@router.get("/report")
def report(days: int = Query(90, ge=7, le=730), db: Session = Depends(get_db)):
    """Enquiry to client conversion by source, plus where current clients came from."""
    since = utcnow() - timedelta(days=days)
    leads = db.query(models.Lead).filter(models.Lead.created_at >= since).all()
    rows = defaultdict(lambda: {"leads": 0, "won": 0, "lost": 0, "open": 0, "days_to_win": []})
    for l in leads:
        r = rows[l.source]
        r["leads"] += 1
        if l.status == "won":
            r["won"] += 1
            if l.won_at:
                r["days_to_win"].append((l.won_at - l.created_at).days)
        elif l.status == "lost":
            r["lost"] += 1
        else:
            r["open"] += 1
    by_source = []
    for src, r in rows.items():
        closed = r["won"] + r["lost"]
        by_source.append({"source": src, "leads": r["leads"], "won": r["won"], "lost": r["lost"], "open": r["open"],
                          "conversion_pct": round(r["won"] / r["leads"] * 100, 1) if r["leads"] else 0.0,
                          "win_rate_closed_pct": round(r["won"] / closed * 100, 1) if closed else None,
                          "avg_days_to_win": round(sum(r["days_to_win"]) / len(r["days_to_win"]), 1) if r["days_to_win"] else None})
    by_source.sort(key=lambda r: (-r["won"], -r["leads"]))
    total = len(leads)
    won = sum(r["won"] for r in by_source)
    lost_reasons = defaultdict(int)
    for l in leads:
        if l.status == "lost" and l.lost_reason:
            lost_reasons[l.lost_reason.strip().capitalize()] += 1
    clients = db.query(models.Client).filter(models.Client.active == True).all()  # noqa: E712
    cs = defaultdict(lambda: {"clients": 0, "revenue": 0.0})
    for c in clients:
        r = cs[(c.source or "unknown").lower()]
        r["clients"] += 1
        r["revenue"] += float(sum(p.amount for p in c.payments))
    return {
        "days": days,
        "total": {"leads": total, "won": won, "lost": sum(r["lost"] for r in by_source), "open": sum(r["open"] for r in by_source),
                  "conversion_pct": round(won / total * 100, 1) if total else 0.0},
        "by_source": by_source,
        "lost_reasons": sorted(({"reason": k, "count": v} for k, v in lost_reasons.items()), key=lambda r: -r["count"]),
        "clients_by_source": sorted(({"source": k, "clients": v["clients"], "revenue": round(v["revenue"], 2)} for k, v in cs.items()),
                                    key=lambda r: -r["revenue"]),
        "follow_ups_due": sum(1 for l in db.query(models.Lead).filter(models.Lead.status.in_(("new", "contacted", "trial_booked"))).all()
                              if l.next_follow_up and l.next_follow_up <= date.today().isoformat()),
    }


@router.get("/referrals")
def referrals(db: Session = Depends(get_db)):
    """Clients who brought new clients, with the revenue those clients brought and rewards still owed."""
    referred = db.query(models.Client).filter(models.Client.referred_by_client_id.isnot(None)).all()
    by = defaultdict(list)
    for c in referred:
        by[c.referred_by_client_id].append(c)
    out = []
    for rid, kids in by.items():
        ref = db.query(models.Client).filter(models.Client.id == rid).first()
        if not ref:
            continue
        paid = [k for k in kids if sum(p.amount for p in k.payments) > 0]
        out.append({"client_id": ref.id, "name": ref.name, "phone": ref.phone, "referred": len(kids),
                    "referred_revenue": round(float(sum(p.amount for k in kids for p in k.payments)), 2),
                    "rewards_pending": sum(1 for k in paid if not k.referral_reward_given),
                    "rewards_given": sum(1 for k in kids if k.referral_reward_given),
                    "referred_clients": [{"id": k.id, "name": k.name, "paid": bool(sum(p.amount for p in k.payments)),
                                          "reward_given": bool(k.referral_reward_given), "reward_note": k.referral_reward_note}
                                         for k in kids]})
    return sorted(out, key=lambda r: (-r["referred"], -r["referred_revenue"]))
