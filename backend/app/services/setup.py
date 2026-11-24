from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import QuestionFlow
from app.services.flows_default import DEFAULT_FLOWS


def ensure_default_flows(db: Session, overwrite: bool = False) -> int:
    """Create the default question flows if missing. With overwrite=True, reset them
    to the built-in defaults (bumping the version). Returns how many were written."""
    existing = {f.key: f for f in db.scalars(select(QuestionFlow))}
    written = 0
    for f in DEFAULT_FLOWS:
        cur = existing.get(f["key"])
        if cur is None:
            db.add(QuestionFlow(key=f["key"], name=f["name"], intro_message=f["intro_message"],
                                questions=f["questions"], rules=f["rules"], closing_message=f["closing_message"]))
            written += 1
        elif overwrite:
            cur.name, cur.intro_message, cur.closing_message = f["name"], f["intro_message"], f["closing_message"]
            cur.questions, cur.rules = f["questions"], f["rules"]
            cur.version += 1
            written += 1
    db.commit()
    return written
