"""검증 결과를 JSON·Markdown 리포트와 격리 파일로 쓴다."""
from __future__ import annotations

import csv
import json
import shutil
from collections import Counter
from datetime import date
from pathlib import Path

from .model import RegionResult
from .spec import Spec

MAX_ISSUES_PER_REGION = 200
SEVERITY_RANK = {"error": 0, "warn": 1, "info": 2}


def build_report(results: list[RegionResult], spec: Spec, today: date, input_label: str) -> dict:
    issues = [i.as_dict() for r in results for i in r.issues]
    severity = Counter(i["severity"] for i in issues)
    regions = []
    for r in results:
        counts = {name: {"rows": len(t.rows), "quarantined": len(r.quarantined.get(name, {}))}
                  for name, t in r.tables.items()}
        regions.append({"slug": r.slug, "rejected": r.rejected, "counts": counts, "scope": r.scope})
    return {
        "schema_version": spec.schema_version,
        "validated_on": today.isoformat(),
        "input": input_label,
        "summary": {
            "error": severity["error"], "warn": severity["warn"], "info": severity["info"],
            "regions": len(results), "regions_rejected": sum(1 for r in results if r.rejected),
        },
        "regions": regions,
        "issues": issues,
    }


def render_markdown(report: dict) -> str:
    s = report["summary"]
    lines = [
        "# 입력 검증 리포트", "",
        f"- 검증일: {report['validated_on']}",
        f"- 입력: {report['input']}",
        f"- 규격 버전: {report['schema_version']}",
        f"- 결과: error {s['error']} · warn {s['warn']} · info {s['info']} "
        f"(지역 {s['regions']}개, 거부 {s['regions_rejected']}개)",
        "",
        "행 번호는 헤더를 뺀 데이터 행의 순번이다(스프레드시트에서는 번호 + 1행).", "",
    ]
    for reg in report["regions"]:
        lines += [f"## {reg['slug']} — {'거부' if reg['rejected'] else '검증 완료'}", ""]
        if reg["counts"]:
            lines += ["| 파일 | 행 | 격리 |", "|---|---|---|"]
            lines += [f"| {n} | {c['rows']} | {c['quarantined']} |" for n, c in reg["counts"].items()]
            lines.append("")
        if reg["scope"]:
            sc = reg["scope"]
            lines += [f"지도에 올라가는 단지: 공공 {sc['public']} · 공공택지 민간 {sc['private_on_public_land']} · "
                      f"범위 밖 {sc['out_of_scope']} · 시행자 미확인(제외) {sc['unknown']}", ""]
        issues = sorted((i for i in report["issues"] if i["region"] == reg["slug"]),
                        key=lambda i: (SEVERITY_RANK[i["severity"]], i["rule"], i["file"], i["row"] or 0))
        if issues:
            lines += ["| 규칙 | 심각도 | 파일 | 행 | 내용 |", "|---|---|---|---|---|"]
            for i in issues[:MAX_ISSUES_PER_REGION]:
                message = i["message"].replace("|", "\\|")
                lines.append(f"| {i['rule']} | {i['severity']} | {i['file']} | {i['row'] or ''} | {message} |")
            if len(issues) > MAX_ISSUES_PER_REGION:
                lines.append(f"\n(이하 {len(issues) - MAX_ISSUES_PER_REGION}건 생략 — validation_report.json 참고)")
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _write_quarantine(results: list[RegionResult], root: Path) -> None:
    if root.exists():
        shutil.rmtree(root)  # 이전 실행의 찌꺼기를 남기지 않는다
    for res in results:
        for name, by_row in res.quarantined.items():
            table = res.tables.get(name)
            if table is None:
                continue
            dest = root / res.slug
            dest.mkdir(parents=True, exist_ok=True)
            if name.endswith(".geojson"):
                features = []
                for n in sorted(by_row):
                    feature = dict(res.features[n - 1])
                    props = dict(feature.get("properties") or {})
                    props["_issues"] = [{"rule": i.rule, "message": i.message} for i in by_row[n]]
                    feature["properties"] = props
                    features.append(feature)
                (dest / name).write_text(
                    json.dumps({"type": "FeatureCollection", "features": features}, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")
            else:
                with open(dest / name, "w", encoding="utf-8-sig", newline="") as fh:
                    writer = csv.writer(fh)
                    writer.writerow(table.header + ["_rule", "_message"])
                    for row in table.rows:
                        if row.n in by_row:
                            issues = by_row[row.n]
                            writer.writerow([row.get(h) for h in table.header]
                                            + [";".join(sorted({i.rule for i in issues})),
                                               " | ".join(i.message for i in issues)])


def write_report(report: dict, results: list[RegionResult], out_dir: Path | str) -> None:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "validation_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (out / "validation_report.md").write_text(render_markdown(report), encoding="utf-8")
    _write_quarantine(results, out / "quarantine")


def exit_code(report: dict, strict: bool) -> int:
    s = report["summary"]
    return 1 if s["error"] or (strict and s["warn"]) else 0
