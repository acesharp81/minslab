#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR / "backend"))

from app.adapters.live_sources import (  # noqa: E402
    ASSEMBLY_LIVE_LIST_URL,
    KTV_REFERENCE_URL,
    PARSER_VERSION,
    fetch_public_source,
    parse_assembly_live_list,
    parse_ktv_player_contract,
)
from app.storage.raw_store import RawStore  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Probe official LIVE source contracts")
    parser.add_argument("--raw-dir", type=Path, default=PROJECT_DIR / "data" / "raw")
    parser.add_argument("--output", type=Path, default=PROJECT_DIR / "data" / "processed" / "live_status.json")
    args = parser.parse_args()
    store = RawStore(args.raw_dir)
    assembly_payload = fetch_public_source("assembly_live_list", ASSEMBLY_LIVE_LIST_URL)
    ktv_payload = fetch_public_source("ktv_cabinet_player_reference", KTV_REFERENCE_URL)
    assembly_artifact = store.save(assembly_payload, parser_version=PARSER_VERSION)
    ktv_artifact = store.save(ktv_payload, parser_version=PARSER_VERSION)

    assembly = parse_assembly_live_list(assembly_payload.content)
    ktv = parse_ktv_player_contract(ktv_payload.content)
    snapshot = {
        "schema_version": "live-source-status.v1",
        "checked_at": assembly_payload.retrieved_at.isoformat(),
        "assembly": assembly,
        "executive": {
            **ktv,
            "is_live": None,
            "source_status": "UNRESOLVED",
        },
        "contracts": {
            "assembly_live_list": {
                "url": ASSEMBLY_LIVE_LIST_URL,
                "content_hash": assembly_artifact.content_hash,
                "parser_version": PARSER_VERSION,
            },
            "ktv_player_reference": {
                "url": KTV_REFERENCE_URL,
                "content_hash": ktv_artifact.content_hash,
                "parser_version": PARSER_VERSION,
            },
        },
    }
    output = args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "output": str(output),
        "assembly_live_count": assembly["live_count"],
        "ktv_caption_contract": ktv["caption_contract_status"],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
