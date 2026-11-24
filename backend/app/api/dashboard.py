"""Dashboard metrics, computed from persisted records (PRD section 22)."""

import uuid
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query
from sqlalchemy import and_, case, func, select
from sqlalchemy.orm import Session

from app.api.access import is_manager, users_by_id
from app.api.deps import get_current_user
from app.api.serializers import user_ref
from app.core.config import get_settings
from app.core.db import get_db
from app.models import AuditEvent, Conversation, FollowUp, Lead, Message, Property, User

router = APIRouter(prefix="/api/v1", tags=["dashboard"])

ACTIVITY_ACTIONS = ("lead.created", "lead.qualified", "conversation.handoff", "conversation.takeover",
                    "consent.opt_out", "import.batch_completed", "lead.status_change", "lead.owner_change")


@router.get("/dashboard")
def dashboard(days: int = Query(30, ge=1, le=366), db: Session = Depends(get_db),
              user: User = Depends(get_current_user)):
    tz = ZoneInfo(get_settings().timezone)
    now = datetime.now(UTC)
    since = now - timedelta(days=days)
    today_start = datetime.combine(datetime.now(tz).date(), time.min, tz)

    scope = [Lead.created_at >= since]
    if not is_manager(user):
        scope.append(Lead.owner_id == user.id)

    def count(*conds) -> int:
        return db.scalar(select(func.count(Lead.id)).where(*scope, *conds)) or 0

    total = count()
    new_today = count(Lead.created_at >= today_start)
    qualified = count(Lead.status.in_(("qualified", "site_visit", "negotiation", "won")))
    site_visits = count(Lead.status.in_(("site_visit", "negotiation", "won")))
    won = count(Lead.status == "won")
    lost = count(Lead.status == "lost")
    hot = count(Lead.priority == "hot")

    # First response: lead created (eligible) -> WhatsApp accepted the opening template.
    resp = func.extract("epoch", Lead.first_response_at - Lead.created_at)
    p50, p95, within, measured = db.execute(
        select(func.percentile_cont(0.5).within_group(resp), func.percentile_cont(0.95).within_group(resp),
               func.count().filter(resp <= 10), func.count())
        .where(*scope, Lead.first_response_at.is_not(None))
    ).one()
    blocked = count(Lead.consent_status != "opted_in")
    failed = db.scalar(select(func.count(Message.id)).join(Conversation).join(Lead)
                       .where(*scope, Message.status == "failed")) or 0

    # Daily trend (local dates)
    local_day = func.date(func.timezone(get_settings().timezone, Lead.created_at))
    trend_rows = dict(db.execute(select(local_day, func.count()).where(*scope).group_by(local_day)).all())
    qual_rows = dict(db.execute(select(local_day, func.count()).where(*scope, Lead.priority.is_not(None))
                                .group_by(local_day)).all())
    start_day: date = (datetime.now(tz) - timedelta(days=days - 1)).date()
    trend = [{"date": (start_day + timedelta(d)).isoformat(),
              "leads": trend_rows.get(start_day + timedelta(d), 0),
              "qualified": qual_rows.get(start_day + timedelta(d), 0)} for d in range(days)]

    by_property = [
        {"property": name or "Unmapped", "leads": n, "qualified": q, "hot": h, "visits": v}
        for name, n, q, h, v in db.execute(
            select(Property.name, func.count(Lead.id),
                   func.count().filter(Lead.priority.is_not(None)),
                   func.count().filter(Lead.priority == "hot"),
                   func.count().filter(Lead.status.in_(("site_visit", "negotiation", "won"))))
            .select_from(Lead).outerjoin(Property, Property.id == Lead.property_id)
            .where(*scope).group_by(Property.name).order_by(func.count(Lead.id).desc())
        ).all()
    ]

    users = users_by_id(db)
    by_agent = [
        {"agent": user_ref(users.get(oid)), "open": o, "qualified": q, "won": w}
        for oid, o, q, w in db.execute(
            select(Lead.owner_id,
                   func.count().filter(Lead.status.not_in(("won", "lost"))),
                   func.count().filter(Lead.priority.is_not(None)),
                   func.count().filter(Lead.status == "won"))
            .where(*scope, Lead.owner_id.is_not(None)).group_by(Lead.owner_id)
        ).all()
    ]

    events = db.scalars(select(AuditEvent).where(AuditEvent.action.in_(ACTIVITY_ACTIONS))
                        .order_by(AuditEvent.id.desc()).limit(12)).all()
    lead_ids = []
    for e in events:
        if e.entity_type == "lead" and e.entity_id:
            try:
                lead_ids.append(uuid.UUID(e.entity_id))
            except ValueError:
                pass
    names = {str(i): n for i, n in db.execute(select(Lead.id, Lead.full_name).where(Lead.id.in_(lead_ids)))}
    activity = [
        {"at": e.occurred_at, "action": e.action, "details": e.details,
         "lead_id": e.entity_id if e.entity_type == "lead" else None, "lead_name": names.get(e.entity_id or ""),
         "actor": user_ref(users.get(e.actor_user_id))}
        for e in events
    ]

    followups_due = db.scalar(select(func.count(FollowUp.id)).where(
        FollowUp.status == "open", FollowUp.due_at <= now + timedelta(hours=24),
        *([] if is_manager(user) else [FollowUp.assigned_to == user.id]))) or 0

    by_status = dict(db.execute(select(Lead.status, func.count()).where(*scope).group_by(Lead.status)).all())
    by_priority = dict(db.execute(select(Lead.priority, func.count()).where(*scope, Lead.priority.is_not(None))
                                  .group_by(Lead.priority)).all())

    return {
        "window_days": days,
        "pipeline": [{"status": s, "count": by_status.get(s, 0)} for s in
                     ("new", "contacted", "qualified", "site_visit", "negotiation", "won", "lost", "nurture")],
        "priority": {p: by_priority.get(p, 0) for p in ("hot", "warm", "cold")},
        "kpis": {"total": total, "new_today": new_today, "qualified": qualified, "hot": hot,
                 "site_visits": site_visits, "won": won, "lost": lost, "followups_due": followups_due},
        "sla": {"p50": round(p50, 1) if p50 is not None else None, "p95": round(p95, 1) if p95 is not None else None,
                "within_target_pct": round(100 * within / measured, 1) if measured else None,
                "measured": measured, "blocked": blocked, "failed_sends": failed, "target_seconds": 10},
        "trend": trend,
        "by_property": by_property,
        "by_agent": by_agent,
        "activity": activity,
    }


@router.get("/followups")
def follow_ups(scope: str = Query("mine", pattern="^(mine|all)$"), status: str = Query("open", pattern="^(open|done)$"),
               db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    stmt = select(FollowUp, Lead).join(Lead, Lead.id == FollowUp.lead_id).where(FollowUp.status == status)
    if scope == "mine" or not is_manager(user):
        stmt = stmt.where(FollowUp.assigned_to == user.id)
    stmt = stmt.order_by(FollowUp.due_at if status == "open" else FollowUp.completed_at.desc()).limit(200)
    users = users_by_id(db)
    now = datetime.now(UTC)
    return {"items": [
        {"id": f.id, "due_at": f.due_at, "note": f.note, "status": f.status, "overdue": f.status == "open" and f.due_at < now,
         "assigned_to": user_ref(users.get(f.assigned_to)), "completed_at": f.completed_at,
         "lead": {"id": str(l.id), "full_name": l.full_name, "priority": l.priority, "status": l.status,
                  "property": l.prop.name if l.prop else None}}
        for f, l in db.execute(stmt).unique().all()
    ]}


@router.post("/followups/{fid}/done")
def complete_follow_up(fid: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    from app.core.errors import ApiError
    from app.services import audit

    f = db.get(FollowUp, fid)
    if f is None or (not is_manager(user) and f.assigned_to not in (None, user.id)):
        raise ApiError(404, "not_found", "Follow-up not found.")
    f.status = "done"
    f.completed_at = datetime.now(UTC)
    audit.record(db, action="followup.done", entity_type="lead", entity_id=f.lead_id, actor=user)
    db.commit()
    return {"ok": True}
