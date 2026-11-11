#!/usr/bin/env python3
"""Read-only submission evidence; never invokes a worker or an AI model."""
import argparse
from datetime import datetime, timezone
import json
import hashlib
from pathlib import Path
import subprocess
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", required=True)
    parser.add_argument("--base-url", default="http://127.0.0.1:18070")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "docs/evidence/EXPANSION_TEST_20261111")
    args = parser.parse_args()
    def get(path):
        with urlopen(args.base_url.rstrip("/") + path, timeout=60) as response:
            return json.load(response)
    plans = get("/api/live/expansion-tests")
    history = get("/api/live/broadcasts?collection=expansion_test&limit=20")
    status = get("/api/live/status")
    ids = {entry["meeting_external_id"] for entry in plans["items"]}
    live = [item for item in status.get("assembly", {}).get("items", []) if item.get("meeting_external_id") in ids]
    services = []
    manifest_path = args.output_dir / "build-manifest.json"
    for target in json.loads(manifest_path.read_text()) if manifest_path.exists() else []:
        inspected = json.loads(subprocess.check_output(["sudo", "docker", "inspect", target["service"]]))[0]
        file_names = list(target["files"])
        code = "import hashlib,json,pathlib; print(json.dumps({p:hashlib.sha256((pathlib.Path('/app/backend/app')/p).read_bytes()).hexdigest() for p in " + repr(file_names) + "}))"
        hashes = json.loads(subprocess.check_output(["sudo", "docker", "exec", target["service"], "python", "-c", code]))
        services.append({"service": target["service"], "container_id": inspected["Id"],
                         "image_id": inspected["Image"], "started_at": inspected["State"]["StartedAt"],
                         "running": inspected["State"]["Running"], "files": hashes})
    workspace_paths = ["web/app.js", "web/index.html", "web/workspace.css", "web/meeting-report-document.js",
                       "scripts/manage_assembly_expansion.py", "scripts/collect_assembly_expansion_evidence.py",
                       "scripts/deploy_secure_workers.sh", "docker-compose.yml"]
    workspace_files = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in workspace_paths}
    report = {"phase": args.phase, "checked_at": datetime.now(timezone.utc).isoformat(),
              "kind": "READ_ONLY_EVIDENCE", "additional_llm_calls": 0,
              "plans": plans["items"], "source_status_rows": live, "reports": history["items"], "services": services,
              "workspace_files": workspace_files,
              "interpretation": "Configuration/fixtures do not prove future live capture. Confirm actual speech counts and report completion after the broadcast."}
    args.output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = args.output_dir / (stamp + "-" + args.phase.replace("/", "_") + ".json")
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str) + "\n")
    print(json.dumps({"evidence_file": str(path), "registered_meetings": len(ids),
                      "source_matches": len(live), "active_matches": sum(bool(row.get("is_live")) for row in live),
                      "reports": len(history["items"])}, ensure_ascii=False))


if __name__ == "__main__": main()
