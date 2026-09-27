from __future__ import annotations

import argparse
import ctypes
import gc
import json
import time
from datetime import datetime, timezone


def poll_executive_once(settings: object) -> dict[str, object]:
    from ..db.connection import connect
    from ..services.executive_official_match import reconcile_executive_official_matches
    from .executive_briefings import collect

    executive = collect(settings)
    with connect(settings.database_url) as connection:
        matched_live = reconcile_executive_official_matches(
            connection, list(executive.get("items") or []),
        )
    return {
        "event": "executive.official.completed",
        "briefings": executive["count"],
        "source_status": executive["source_status"],
        "parser_version": (executive.get("source") or {}).get("parser_version"),
        "matched_live_broadcasts": matched_live,
    }


def poll_once(
    settings: object, *, include_executive: bool = True,
) -> list[dict[str, object]]:
    from ..adapters.official_minutes_body import OfficialMinutesBodyAdapter, semantic_content_hash
    from ..db.connection import connect
    from ..db.official_publication_repository import OfficialPublicationRepository
    from ..db.schedule_repository import SourceVersionInput
    from ..storage.raw_store import RawStore
    from .committee_sync import sync_committee_bundle, sync_plenary_minutes
    from .official_minutes_body import fetch_official_minutes_body

    with connect(settings.database_url) as connection:
        dates = OfficialPublicationRepository(connection).pending_date_sources(limit=7)
    results: list[dict[str, object]] = []
    for pending in dates:
        meeting_date = pending["date"]
        try:
            official_rows = 0
            if pending["committee_due"]:
                sync = sync_committee_bundle(
                    conference_date=meeting_date.isoformat(),
                    assembly_number="22", page_size=100,
                    api_key=settings.national_assembly_api_key,
                    database_url=settings.database_url,
                    raw_data_dir=settings.raw_data_dir,
                )
                official_rows += int(sync["minute_rows_seen"])
            if pending["plenary_due"]:
                plenary = sync_plenary_minutes(
                    conference_date=meeting_date.isoformat(),
                    assembly_number="22", page_size=100,
                    api_key=settings.national_assembly_api_key,
                    database_url=settings.database_url,
                    raw_data_dir=settings.raw_data_dir,
                )
                official_rows += int(plenary["minute_rows_seen"])
            checked_at = datetime.now(timezone.utc)
            with connect(settings.database_url) as connection:
                reconciliation = OfficialPublicationRepository(connection).reconcile_date(
                    meeting_date, checked_at,
                    broadcast_ids=pending["broadcast_ids"],
                )
            results.append({
                "date": meeting_date.isoformat(),
                "committee_due": pending["committee_due"],
                "plenary_due": pending["plenary_due"],
                "official_rows": official_rows,
                **reconciliation,
            })
        except Exception as exc:  # isolate one meeting date
            results.append({
                "event": "official.date.error", "date": meeting_date.isoformat(),
                "error": type(exc).__name__,
            })
    adapter = OfficialMinutesBodyAdapter()
    with connect(settings.database_url) as connection:
        publications = OfficialPublicationRepository(connection).pending_body_publications(limit=5)
    for publication in publications:
        try:
            payload = fetch_official_minutes_body(
                str(publication["official_url"]),
                source_key=("plenary_minutes_body" if publication["committee_name"] == "본회의"
                            else "committee_minutes_body"),
            )
            artifact = RawStore(settings.raw_data_dir).save(
                payload, parser_version=adapter.parser_version,
            )
            body = adapter.parse(payload)
            source = SourceVersionInput(
                source_type=payload.source_key, source_url=payload.source_url,
                content_hash=semantic_content_hash(body), raw_path=artifact.content_path,
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
        except Exception as exc:  # isolate one publication
            results.append({
                "event": "official.body.error",
                "conference_id": str(publication["conference_id"]),
                "error": type(exc).__name__,
            })
    with connect(settings.database_url) as connection:
        meetings = OfficialPublicationRepository(connection).pending_meeting_bodies(limit=10)
    for meeting in meetings:
        try:
            payload = fetch_official_minutes_body(str(meeting["official_url"]))
            artifact = RawStore(settings.raw_data_dir).save(
                payload, parser_version=adapter.parser_version,
            )
            body = adapter.parse(payload)
            source = SourceVersionInput(
                source_type=payload.source_key, source_url=payload.source_url,
                content_hash=semantic_content_hash(body), raw_path=artifact.content_path,
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
        except Exception as exc:  # isolate one meeting body
            results.append({
                "event": "official.meeting-body.error",
                "conference_id": str(meeting["conference_id"]),
                "error": type(exc).__name__,
            })
    with connect(settings.database_url) as connection:
        document_ids = OfficialPublicationRepository(
            connection,
        ).pending_annotation_documents(limit=20)
    annotated = 0
    annotation_errors = 0
    for document_id in document_ids:
        try:
            with connect(settings.database_url) as connection:
                repository = OfficialPublicationRepository(connection)
                annotated += repository.annotate_document(
                    document_id, datetime.now(timezone.utc),
                )
                repository.record_annotation_document(
                    document_id, succeeded=True,
                )
        except Exception as exc:  # isolate one malformed document
            annotation_errors += 1
            with connect(settings.database_url) as connection:
                OfficialPublicationRepository(connection).record_annotation_document(
                    document_id, succeeded=False, error=type(exc).__name__,
                )
    if document_ids:
        results.append({
            "event": "official.insights.completed",
            "documents": len(document_ids),
            "utterances_annotated": annotated,
            "document_errors": annotation_errors,
        })
    with connect(settings.database_url) as connection:
        agenda_documents = OfficialPublicationRepository(
            connection,
        ).pending_agenda_documents(limit=5)
    for document_id in agenda_documents:
        try:
            with connect(settings.database_url) as connection:
                agenda_result = OfficialPublicationRepository(
                    connection,
                ).reconcile_agenda_document(document_id, batch_size=1000)
            results.append({
                "event": "official.agenda-links.completed",
                "document_id": str(document_id),
                **agenda_result,
            })
        except Exception as exc:
            results.append({
                "event": "official.agenda-links.error",
                "document_id": str(document_id),
                "error": type(exc).__name__,
            })
    try:
        from .bill_sync import sync_pending_target_bill_details
        bill_details = sync_pending_target_bill_details(
            assembly_term="제22대",
            api_key=settings.national_assembly_api_key,
            database_url=settings.database_url,
            raw_data_dir=settings.raw_data_dir,
            limit=20,
        )
        results.append({
            "event": "bills.details.completed",
            **bill_details,
        })
    except Exception as exc:
        results.append({
            "event": "bills.details.error",
            "error": type(exc).__name__,
        })
    if include_executive:
        try:
            results.append(poll_executive_once(settings))
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


def release_cycle_memory() -> None:
    """Return large parser/DB batches to the host before the next poll."""
    gc.collect()
    try:
        malloc_trim = ctypes.CDLL(None).malloc_trim
        malloc_trim.argtypes = [ctypes.c_size_t]
        malloc_trim.restype = ctypes.c_int
        malloc_trim(0)
    except (AttributeError, OSError):
        pass


def main() -> None:
    from ..config import get_settings
    from ..db.migrate import apply_migrations

    parser = argparse.ArgumentParser(description="Poll official committee-minute publication links")
    parser.add_argument("--interval", type=int, default=300)
    parser.add_argument("--executive-interval", type=int, default=3600)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    if not 300 <= args.interval <= 86400:
        parser.error("interval must be between 300 and 86400 seconds")
    if not 300 <= args.executive_interval <= 86400:
        parser.error("executive interval must be between 300 and 86400 seconds")
    settings = get_settings()
    apply_migrations(settings.database_url)
    last_executive_poll: float | None = None
    while True:
        executive_due = (
            last_executive_poll is None
            or time.monotonic() - last_executive_poll >= args.executive_interval
        )
        try:
            if settings.national_assembly_api_key:
                for result in poll_once(
                    settings, include_executive=executive_due,
                ):
                    print(json.dumps(result, ensure_ascii=False), flush=True)
                if executive_due:
                    last_executive_poll = time.monotonic()
            else:
                # The executive official-source collector has no dependency on
                # the National Assembly Open API. Keep it available in an
                # executive-only deployment or while the Assembly credential is
                # temporarily unavailable.
                if executive_due:
                    print(
                        json.dumps(poll_executive_once(settings), ensure_ascii=False),
                        flush=True,
                    )
                    last_executive_poll = time.monotonic()
        except Exception as exc:
            print(json.dumps({"event": "official.poll.error", "error": type(exc).__name__}), flush=True)
            try:
                if executive_due:
                    print(
                        json.dumps(poll_executive_once(settings), ensure_ascii=False),
                        flush=True,
                    )
                    last_executive_poll = time.monotonic()
            except Exception as executive_exc:
                print(json.dumps({
                    "event": "executive.official.error",
                    "error": type(executive_exc).__name__,
                }), flush=True)
        finally:
            release_cycle_memory()
        if args.once:
            return
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
