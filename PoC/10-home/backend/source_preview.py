"""Bounded, read-only previews of current source records."""
from sqlalchemy import select, func
from .db import Revision
from .sources import SOURCES
from scripts.export_json import credential_values, scrub


def source_preview(service, source_id):
    if not any(s['id'] == source_id for s in SOURCES):
        raise KeyError(source_id)
    condition = (Revision.source_id == source_id, Revision.superseded_at.is_(None))
    with service.sessions() as session:
        total = session.scalar(select(func.count()).select_from(Revision).where(*condition))
        records = session.scalars(select(Revision).where(*condition)
            .order_by(Revision.recorded_at.desc(), Revision.entity_id).limit(50)).all()
        secrets = credential_values()
        items = [dict(id=r.entity_id, kind=r.kind, recorded_at=r.recorded_at.isoformat(),
                      revision_no=r.revision_no, data=scrub(r.payload, secrets)) for r in records]
    fields = sorted({key for item in items for key in item['data']})
    return dict(source_id=source_id, total=total, limit=50, items=items, fields=fields)
