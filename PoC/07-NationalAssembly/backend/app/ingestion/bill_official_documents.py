from __future__ import annotations

from datetime import datetime, timezone
from urllib import request as url_request

from ..adapters.national_assembly.base import SourcePayload
from ..db.bill_repository import BillRepository
from ..db.connection import connect
from ..db.schedule_repository import SourceVersionInput
from ..services.bill_official_document import PARSER_VERSION, extract_official_sections, extract_pdf_pages
from ..storage.raw_store import RawStore


def fetch_official_pdf(url: str, referer: str | None) -> SourcePayload:
    request = url_request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 POC-07-NationalAssembly/0.1",
        "Referer": referer or "https://likms.assembly.go.kr/",
    })
    with url_request.urlopen(request, timeout=30) as response:
        content = response.read()
        final_url = response.geturl()
        status = int(response.status)
    if not content.startswith(b"%PDF-"):
        raise ValueError("official bill attachment is not a PDF")
    return SourcePayload(
        source_key="bill_official_pdf", content=content, content_type="application/pdf",
        retrieved_at=datetime.now(timezone.utc), source_url=final_url, http_status=status,
    )


def collect_pending(settings: object, limit: int = 10) -> dict[str, object]:
    with connect(settings.database_url) as connection:
        targets = BillRepository(connection).pending_official_documents(limit=limit)
    result: dict[str, object] = {
        "targets": len(targets), "documents": 0, "semantic_duplicates": 0,
        "sections": 0, "errors": [],
    }
    raw_store = RawStore(settings.raw_data_dir)
    for target in targets:
        urls = [url.strip() for url in (target["pdf_urls"] or "").split(",") if url.strip()]
        if not urls:
            continue
        try:
            payload = fetch_official_pdf(urls[0], target["official_url"])
            artifact = raw_store.save(payload, parser_version=PARSER_VERSION)
            pages = extract_pdf_pages(artifact.content_path)
            sections = extract_official_sections(pages)
            source = SourceVersionInput(
                source_type=payload.source_key, source_url=payload.source_url,
                content_hash=artifact.content_hash, raw_path=artifact.content_path,
                retrieved_at=payload.retrieved_at, parser_version=PARSER_VERSION,
                content_type=payload.content_type,
                metadata={"bill_id": target["bill_id"], "document_index": 1},
            )
            with connect(settings.database_url) as connection:
                saved = BillRepository(connection).ingest_official_document(
                    bill_uuid=target["bill_uuid"], source=source, document_index=1,
                    title=target["bill_name"], pages=pages, sections=sections,
                )
            if saved["semantic_duplicate"]:
                result["semantic_duplicates"] += 1
            else:
                result["documents"] += 1
            result["sections"] += saved["sections_inserted"]
        except Exception as exc:
            result["errors"].append({"bill_id": target["bill_id"], "error": type(exc).__name__})
    return result
