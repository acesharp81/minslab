"""Read-only Phase 1 acceptance over repository and published HWPX templates."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import sqlite3
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_backend():
    isolated = Path(tempfile.mkdtemp(prefix="aiworks-phase1-")) / "isolated.sqlite3"
    os.environ["AIWORKS_DB_PATH"] = str(isolated)
    os.environ["AIWORKS_ENABLE_DEMO_SEED"] = "0"
    spec = importlib.util.spec_from_file_location("aiworks_phase1_template_backend", ROOT / "backend.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


def published_template_samples(db_path: Path) -> list[tuple[str, bytes]]:
    if not db_path.is_file():
        return []
    connection = sqlite3.connect(f"file:{db_path.resolve()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        rows = connection.execute(
            "SELECT f.package_id,f.version,f.content_blob,p.manifest_json "
            "FROM mcp_package_files f JOIN mcp_packages p "
            "ON p.package_id=f.package_id AND p.version=f.version "
            "WHERE f.media_type='application/hwp+zip' ORDER BY f.package_id,f.version,f.reference_id"
        ).fetchall()
    finally:
        connection.close()
    samples = []
    seen = set()
    for row in rows:
        manifest = json.loads(row["manifest_json"] or "{}")
        if manifest.get("mcpType") != "template":
            continue
        data = bytes(row["content_blob"])
        digest = hashlib.sha256(data).hexdigest()
        if digest in seen:
            continue
        seen.add(digest)
        samples.append((f"{row['package_id']}@{row['version']}", data))
    return samples


def run(db_path: Path, minimum_samples: int = 3) -> dict:
    backend = load_backend()
    repository_data = (ROOT / "web" / "rhwp" / "samples" / "form-002.hwpx").read_bytes()
    samples = [("repository/form-002", repository_data), *published_template_samples(db_path)]
    unique = []
    seen = set()
    for reference, data in samples:
        digest = hashlib.sha256(data).hexdigest()
        if digest in seen:
            continue
        seen.add(digest)
        unique.append((reference, data, digest))

    checks = []
    for reference, data, digest in unique:
        parsed = backend.parse_hwpx(data, "source.hwpx")
        converted, authoring = backend._build_template_authoring_sample(data, "source.hwpx")
        quality = backend._evaluate_hwpx_template_quality(converted, "converted.hwpx")
        passed = bool(authoring["schema"].get("structuralBindingReady") and quality.get("passed"))
        checks.append(
            {
                "reference": reference,
                "sourceSha256": digest,
                "sourceBytes": len(data),
                "sourceStats": parsed["stats"],
                "structuralBindingReady": bool(authoring["schema"].get("structuralBindingReady")),
                "qualityPassed": bool(quality.get("passed")),
                "mappingCoverage": (quality.get("metrics") or {}).get("mappingCoverage"),
                "renderMapCoverage": (quality.get("metrics") or {}).get("renderMapCoverage"),
                "passed": passed,
            }
        )
    enough = len(checks) >= minimum_samples
    result = {
        "contractVersion": "phase1-template-golden-set/1.0",
        "status": "passed" if enough and all(item["passed"] for item in checks) else "failed",
        "minimumSamples": minimum_samples,
        "sampleCount": len(checks),
        "contentLogged": False,
        "checks": checks,
    }
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=ROOT / "data" / "aiworks.sqlite3")
    parser.add_argument("--minimum-samples", type=int, default=3)
    args = parser.parse_args()
    result = run(args.db, max(1, args.minimum_samples))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    sys.exit(main())
