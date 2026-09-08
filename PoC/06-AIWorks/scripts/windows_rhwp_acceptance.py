#!/usr/bin/env python3
"""Windows Hancom Office acceptance gate for AI Work Hub HWPX outputs."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def count_tables(hwp) -> int:
    count = 0
    control = getattr(hwp, "HeadCtrl", None)
    while control is not None:
        if str(getattr(control, "CtrlID", "")).lower() == "tbl":
            count += 1
        control = getattr(control, "Next", None)
    return count


def inspect_document(runtime, source: Path, expected_terms: list[str], output_dir: Path) -> dict:
    hwp = runtime.ensure()
    if not hwp.Open(str(source), "", "forceopen:true"):
        raise RuntimeError(f"한컴오피스에서 문서를 열지 못했습니다: {source.name}")
    try:
        before_text = str(hwp.GetTextFile("UNICODE", ""))
        before_tables = count_tables(hwp)
        fields = [item for item in str(hwp.GetFieldList(0, 0)).split("\x02") if item]
        copy_path = output_dir / f"{source.stem}-roundtrip{source.suffix.lower()}"
        pdf_path = output_dir / f"{source.stem}-preview.pdf"
        if not hwp.SaveAs(str(copy_path), "", ""):
            raise RuntimeError("HWPX 왕복 저장에 실패했습니다.")
        if not hwp.SaveAs(str(pdf_path), "PDF", ""):
            raise RuntimeError("PDF 증적 생성에 실패했습니다.")
    finally:
        hwp.XHwpDocuments.Close(False)

    if not hwp.Open(str(copy_path), "", "forceopen:true"):
        raise RuntimeError("저장한 HWPX를 재열지 못했습니다.")
    try:
        after_text = str(hwp.GetTextFile("UNICODE", ""))
        after_tables = count_tables(hwp)
    finally:
        hwp.XHwpDocuments.Close(False)

    term_checks = {term: term in after_text for term in expected_terms}
    return {
        "source": source.name,
        "sourceSha256": sha256(source),
        "roundTrip": copy_path.name,
        "roundTripSha256": sha256(copy_path),
        "previewPdf": pdf_path.name,
        "previewPdfSha256": sha256(pdf_path),
        "previewPdfBytes": pdf_path.stat().st_size,
        "charactersBefore": len(before_text),
        "charactersAfter": len(after_text),
        "tablesBefore": before_tables,
        "tablesAfter": after_tables,
        "fields": len(fields),
        "expectedTerms": term_checks,
        "passed": bool(
            before_text
            and before_text == after_text
            and before_tables == after_tables
            and all(term_checks.values())
            and pdf_path.stat().st_size > 0
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ordinary", required=True, type=Path, help="일반 보고서 HWPX")
    parser.add_argument("--budget", required=True, type=Path, help="예산 보고서 HWPX")
    parser.add_argument("--ordinary-term", action="append", default=[])
    parser.add_argument("--budget-term", action="append", default=[])
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()

    if os.name != "nt":
        print(json.dumps({
            "contractVersion": "windows-rhwp-acceptance/1.0",
            "status": "blocked",
            "reason": "Windows 네이티브 환경이 아닙니다.",
            "platform": platform.platform(),
        }, ensure_ascii=False, indent=2))
        return 2

    for source in (args.ordinary, args.budget):
        if source.suffix.lower() != ".hwpx" or not source.is_file():
            raise SystemExit(f"검증할 HWPX 파일이 없습니다: {source}")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    allowed_roots = {str(args.ordinary.resolve().parent), str(args.budget.resolve().parent), str(args.output_dir.resolve())}
    os.environ["AIWORKS_RHWP_ALLOWED_ROOTS"] = os.pathsep.join(sorted(allowed_roots))

    from rhwp_windows_agent import RhwpRuntime

    runtime = RhwpRuntime()
    capabilities = runtime.invoke("rhwp.capabilities", {})
    checks = [
        inspect_document(runtime, args.ordinary.resolve(), args.ordinary_term, args.output_dir.resolve()),
        inspect_document(runtime, args.budget.resolve(), args.budget_term, args.output_dir.resolve()),
    ]
    result = {
        "contractVersion": "windows-rhwp-acceptance/1.0",
        "status": "passed" if all(item["passed"] for item in checks) else "failed",
        "checkedAt": datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        "platform": platform.platform(),
        "capabilities": capabilities,
        "checks": checks,
    }
    unsigned = json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    result["evidenceSha256"] = hashlib.sha256(unsigned).hexdigest()
    evidence = args.output_dir / "windows-rhwp-acceptance.json"
    evidence.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({**result, "evidence": str(evidence)}, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    sys.exit(main())
