"""Read-only evidence for PoC 7 and 10; never issue data-changing SQL.

Row counts and two independent sums of (ctid, xmin) hashes detect PostgreSQL
row-version changes without reading large text/JSON payloads. Running collectors
may legitimately change these fingerprints, which is reported explicitly.
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import json
from pathlib import Path
import re
import subprocess
import sys
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[3]
STATE = ROOT / "data/maintenance/poc11-12-20261021"
DATABASES = (("poc07-national-assembly-db", "national_assembly"), ("poc10-home-db", "home"))
SQL = r"""
BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;
SET LOCAL statement_timeout = '600s';
SET LOCAL lock_timeout = '2s';
SET LOCAL max_parallel_workers_per_gather = 0;
SELECT json_build_object('kind','identity','database',current_database(),
    'system_identifier',system_identifier::text,'postmaster_start',pg_postmaster_start_time(),
    'read_only',current_setting('transaction_read_only'),
    'snapshot',txid_current_snapshot()::text) FROM pg_control_system();
SELECT format(
    'SELECT json_build_object(''kind'',''table'',''schema'',%L,''table'',%L,''oid'',%s,
     ''filenode'',%s,''rows'',count(*) FILTER (WHERE __BASELINE_FILTER__),''current_rows'',count(*),
     ''version_sum_a'',coalesce(sum(hashtextextended(ctid::text || '':'' || xmin::text,0)::numeric)
         FILTER (WHERE __BASELINE_FILTER__),0)::text,
     ''version_sum_b'',coalesce(sum(hashtextextended(ctid::text || '':'' || xmin::text,1)::numeric)
         FILTER (WHERE __BASELINE_FILTER__),0)::text)
     FROM %I.%I;', n.nspname,c.relname,c.oid,pg_relation_filenode(c.oid),n.nspname,c.relname)
FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
WHERE c.relkind='r' AND n.nspname NOT IN ('pg_catalog','information_schema')
    AND n.nspname NOT LIKE 'pg_toast%'
ORDER BY n.nspname,c.relname
\gexec
SELECT json_build_object('kind','schema','columns',jsonb_agg(to_jsonb(x) ORDER BY x.table_schema,x.table_name,x.ordinal_position))
FROM (SELECT table_schema,table_name,column_name,ordinal_position,data_type,is_nullable,column_default
      FROM information_schema.columns WHERE table_schema NOT IN ('pg_catalog','information_schema')) x;
COMMIT;
"""


def run(args, **kwargs):
    return subprocess.run(args, check=True, capture_output=True, text=True, **kwargs).stdout


def database(spec):
    container, name, baseline, label = spec
    sql = SQL.replace("__BASELINE_FILTER__", "TRUE")
    if baseline is not None:
        snapshot_id = baseline["identity"]["snapshot"]
        if not re.fullmatch(r"[0-9:,]+", snapshot_id):
            raise RuntimeError("Unexpected PostgreSQL snapshot format")
        condition = "txid_visible_in_snapshot(xmin::text::bigint,(SELECT current_setting(''poc.baseline_snapshot'')::txid_snapshot))"
        sql = SQL.replace("__BASELINE_FILTER__", condition)
        sql = sql.replace("SET LOCAL statement_timeout", f"SET LOCAL poc.baseline_snapshot = '{snapshot_id}';\nSET LOCAL statement_timeout", 1)
    try:
        output = run(["sudo", "-n", "docker", "exec", "-i", container, "psql", "-X", "-q", "-A", "-t",
                      "-v", "ON_ERROR_STOP=1", "-U", name, "-d", name], input=sql, timeout=1800)
    except subprocess.CalledProcessError as error:
        completed = [json.loads(line) for line in error.stdout.splitlines() if line.strip()]
        print(json.dumps({"database": container, "read_only_check_error": error.stderr,
                          "completed_tables": len([row for row in completed if row["kind"] == "table"])}), flush=True)
        raise
    rows = [json.loads(line) for line in output.splitlines() if line.strip()]
    result = {"identity": next(row for row in rows if row["kind"] == "identity"),
              "tables": {row["schema"] + "." + row["table"]: row for row in rows if row["kind"] == "table"},
              "schema": next(row for row in rows if row["kind"] == "schema")}
    (STATE / f"protected-{label}-{container}.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"database": container, "phase": label, "tables_completed": len(result["tables"])}), flush=True)
    return container, result


def containers():
    names = run(["sudo", "-n", "docker", "ps", "-a", "--format", "{{.Names}}"]).splitlines()
    names = [name for name in names if name.startswith(("poc07-", "poc10-"))]
    details = json.loads(run(["sudo", "-n", "docker", "inspect", *names]))
    return {item["Name"].lstrip("/"): {"id": item["Id"], "started_at": item["State"]["StartedAt"],
                                       "running": item["State"]["Running"], "restart_count": item["RestartCount"],
                                       "mounts": item["Mounts"]} for item in details}


def snapshot(label):
    STATE.mkdir(parents=True, mode=0o700, exist_ok=True)
    os_containers = containers()
    protected_roots = [(ROOT / path).resolve() for path in ("PoC/07-NationalAssembly", "PoC/10-home")]
    deletion_roots = [(ROOT / path).resolve() for path in ("PoC/11-consultation-cases", "PoC/12-housing-board")]
    protected_mounts = [Path(mount["Source"]).resolve() for item in os_containers.values() for mount in item["mounts"]]
    for protected in protected_roots + protected_mounts:
        for target in deletion_roots:
            if protected == target or protected in target.parents or target in protected.parents:
                raise RuntimeError(f"Protected storage overlaps deletion target: {protected}")
    baseline = json.loads((STATE / "protected-before.json").read_text()) if label == "after" else None
    with ThreadPoolExecutor(max_workers=2) as pool:
        specs = [(container, name, baseline["databases"][container] if baseline else None, label) for container, name in DATABASES]
        databases = dict(pool.map(database, specs))
    evidence = {"captured_at": datetime.now(ZoneInfo("Asia/Seoul")).isoformat(),
                "method": "read-only PostgreSQL row-version fingerprints and container/mount identity",
                "containers": os_containers, "databases": databases}
    destination = STATE / f"protected-{label}.json"
    destination.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"saved": str(destination), "tables": {name: len(db["tables"]) for name, db in databases.items()}}, ensure_ascii=False), flush=True)


def compare():
    before = json.loads((STATE / "protected-before.json").read_text())
    after = json.loads((STATE / "protected-after.json").read_text())
    def normalized_containers(values):
        return {name: {**item, "mounts": sorted(item["mounts"], key=lambda mount: (mount["Destination"], mount["Source"]))}
                for name, item in values.items()}
    report = {"container_identity_and_mounts_unchanged": normalized_containers(before["containers"]) == normalized_containers(after["containers"]), "databases": {}}
    for name, old in before["databases"].items():
        new = after["databases"][name]
        changed = {}
        stable = []
        for table, baseline in old["tables"].items():
            current = new["tables"].get(table)
            fields = ("oid", "filenode", "rows", "version_sum_a", "version_sum_b")
            if current is not None and all(current[key] == baseline[key] for key in fields):
                stable.append(table)
            else:
                changed[table] = {"before_rows": baseline["rows"],
                                  "surviving_original_versions": current["rows"] if current else None,
                                  "current_rows": current["current_rows"] if current else None}
        report["databases"][name] = {
            "database_identity_unchanged": all(old["identity"][key] == new["identity"][key]
                for key in ("database", "system_identifier", "postmaster_start", "read_only")),
            "schema_unchanged": old["schema"] == new["schema"],
            "table_set_unchanged": set(old["tables"]) == set(new["tables"]),
            "original_row_versions_unchanged_tables": stable,
            "changed_during_live_collection": changed,
            "tables_with_row_count_decrease": [table for table, baseline in old["tables"].items()
                if table in new["tables"] and new["tables"][table]["current_rows"] < baseline["rows"]],
            "total_rows_before": sum(table["rows"] for table in old["tables"].values()),
            "total_rows_after": sum(table["current_rows"] for table in new["tables"].values())}
    path = STATE / "protected-comparison.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in {"before", "after", "compare"}:
        raise SystemExit("Usage: protected_data.py before|after|compare")
    if sys.argv[1] == "compare":
        compare()
    else:
        snapshot(sys.argv[1])
