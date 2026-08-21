from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone


def poll_once(settings: object) -> list[dict[str, object]]:
    from ..adapters.official_minutes_body import OfficialMinutesBodyAdapter
    from ..db.connection import connect
    from ..db.official_publication_repository import OfficialPublicationRepository
    from ..db.schedule_repository import SourceVersionInput
    from ..storage.raw_store import RawStore
    from .committee_sync import sync_committee_bundle
    from .official_minutes_body import fetch_official_minutes_body

    with connect(settings.database_url) as connection:
        dates = OfficialPublicationRepository(connection).pending_dates(limit=7)
    results: list[dict[str, object]] = []
    for meeting_date in dates:
        sync = sync_committee_bundle(
            conference_date=meeting_date.isoformat(),
            assembly_number="22",
            page_size=100,
            api_key=settings.national_assembly_api_key,
            database_url=settings.database_url,
            raw_data_dir=settings.raw_data_dir,
        )
        checked_at = datetime.now(timezone.utc)
        with connect(settings.database_url) as connection:
            reconciliation = OfficialPublicationRepository(connection).reconcile_date(
                meeting_date, checked_at
            )
        results.append({
            "date": meeting_date.isoformat(),
            "official_rows": sync["minute_rows_seen"],
            **reconciliation,
        })
    adapter = OfficialMinutesBodyAdapter()
    with connect(settings.database_url) as connection:
        publications = OfficialPublicationRepository(connection).pending_body_publications(limit=5)
    for publication in publications:
        payload = fetch_official_minutes_body(str(publication["official_url"]))
        artifact = RawStore(settings.raw_data_dir).save(payload, parser_version=adapter.parser_version)
        body = adapter.parse(payload)
        source = SourceVersionInput(
            source_type=payload.source_key, source_url=payload.source_url,
            content_hash=artifact.content_hash, raw_path=artifact.content_path,
            retrieved_at=payload.retrieved_at, parser_version=adapter.parser_version,
            content_type=payload.content_type,
            metadata={"conference_id": body.conference_id, "publication_stage": body.publication_stage},
        )
        with connect(settings.database_url) as connection:
            ingested = OfficialPublicationRepository(connection).ingest_body(
                publication_id=publication["publication_id"],
                meeting_id=publication["meeting_id"],
                expected_conference_id=str(publication["conference_id"]),
                source=source, body=body,
            )
        results.append({"conference_id": body.conference_id, "body": ingested})
    with connect(settings.database_url) as connection:
        meetings = OfficialPublicationRepository(connection).pending_meeting_bodies(limit=10)
    for meeting in meetings:
        payload = fetch_official_minutes_body(str(meeting["official_url"]))
        artifact = RawStore(settings.raw_data_dir).save(payload, parser_version=adapter.parser_version)
        body = adapter.parse(payload)
        source = SourceVersionInput(
            source_type=payload.source_key, source_url=payload.source_url,
            content_hash=artifact.content_hash, raw_path=artifact.content_path,
            retrieved_at=payload.retrieved_at, parser_version=adapter.parser_version,
            content_type=payload.content_type,
            metadata={"conference_id": body.conference_id, "publication_stage": body.publication_stage},
        )
        with connect(settings.database_url) as connection:
            ingested = OfficialPublicationRepository(connection).ingest_body(
                publication_id=None, meeting_id=meeting["meeting_id"],
                expected_conference_id=str(meeting["conference_id"]),
                source=source, body=body,
            )
        results.append({"conference_id": body.conference_id, "meeting_body": ingested})
    with connect(settings.database_url) as connection:
        repository = OfficialPublicationRepository(connection)
        document_ids = repository.pending_annotation_documents(limit=20)
        annotated = sum(
            repository.annotate_document(document_id, datetime.now(timezone.utc))
            for document_id in document_ids
        )
    if document_ids:
        results.append({
            "event": "official.insights.completed",
            "documents": len(document_ids),
            "utterances_annotated": annotated,
        })
    with connect(settings.database_url) as connection:
        agenda_links = OfficialPublicationRepository(connection).reconcile_agenda_links()
    if agenda_links:
        results.append({
            "event": "official.agenda-links.completed",
            "links_inserted": agenda_links,
            "match_method": "EXACT_ITEM_REF_AGENDA_PREFIX",
        })
    try:
        from .executive_briefings import collect
        executive = collect(settings)
        results.append({
            "event": "executive.official.completed",
            "briefings": executive["count"],
            "source_status": executive["source_status"],
        })
    except Exception as exc:
        results.append({
            "event": "executive.official.error",
            "error": type(exc).__name__,
        })
    try:
        from .bill_official_documents import collect_pending
        bill_documents = collect_pending(settings, limit=10)
        results.append({"event": "bills.official-documents.completed", **bill_documents})
    except Exception as exc:
        results.append({
            "event": "bills.official-documents.error",
            "error": type(exc).__name__,
        })
    return results


def main() -> None:
    from ..config import get_settings
    from ..db.migrate import apply_migrations

    parser = argparse.ArgumentParser(description="Poll official committee-minute publication links")
    parser.add_argument("--interval", type=int, default=3600)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    if not 300 <= args.interval <= 86400:
        parser.error("interval must be between 300 and 86400 seconds")
    settings = get_settings()
    if not settings.national_assembly_api_key:
        parser.error("NATIONAL_ASSEMBLY_API_KEY is required")
    apply_migrations(settings.database_url)
    while True:
        try:
            for result in poll_once(settings):
                print(json.dumps(result, ensure_ascii=False), flush=True)
        except Exception as exc:
            print(json.dumps({"event": "official.poll.error", "error": type(exc).__name__}), flush=True)
        if args.once:
            return
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
