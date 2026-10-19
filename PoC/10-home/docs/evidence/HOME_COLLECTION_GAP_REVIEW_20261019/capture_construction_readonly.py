"""Capture raw construction-date candidates and management link presence, read only."""
import json
from sqlalchemy import text
from backend.db import engine_for
from scripts.export_json import scrub, credential_values

with engine_for().connect().execution_options(isolation_level='REPEATABLE READ') as c:
    with c.begin():
        c.execute(text('SET TRANSACTION READ ONLY'))
        c.execute(text("SET LOCAL statement_timeout='60s'"))
        captured=c.execute(text('SELECT current_timestamp')).scalar()
        # Membership in an evidence_bridge is measured separately from any other relation.
        rows=c.execute(text("""WITH raw AS (
          SELECT entity_id,source_id,kind,sample_region,payload,
            CASE WHEN kind='permit' THEN payload->'dates'->>'원천 착공일 (stcnsDay)'
                 ELSE payload->'dates'->>'실제착공일 (realStcnsDay)' END AS started
          FROM home_revision WHERE superseded_at IS NULL AND kind IN ('permit','general_permit')
        ), bridges AS (
          SELECT DISTINCT payload->>'source_entity_id' AS entity_id FROM home_revision
          WHERE superseded_at IS NULL AND kind='evidence_bridge'
        ), aliases AS (SELECT DISTINCT source_entity_id AS entity_id FROM home_identity_alias)
        SELECT raw.entity_id,raw.source_id,raw.kind,raw.sample_region,raw.started,
          payload->>'name' AS name,payload->>'units' AS units,
          payload->>'main_purpose' AS purpose,payload->>'construction_type' AS construction_type,
          payload->>'construction_type_code' AS construction_type_code,
          payload->>'source_object_id' AS native_id,
          bridges.entity_id IS NOT NULL AS has_bridge,aliases.entity_id IS NOT NULL AS has_identity_alias
        FROM raw LEFT JOIN bridges USING(entity_id) LEFT JOIN aliases USING(entity_id)
        WHERE started BETWEEN '2026-01-01' AND '2026-10-19'
        ORDER BY raw.kind,raw.entity_id""")).mappings().all()
        profiles=c.execute(text("""SELECT entity_id,payload FROM home_revision WHERE superseded_at IS NULL
            AND kind='project_profile'""")).mappings().all()
        mappings=c.execute(text('SELECT project_id,policy_id,program_id,status FROM home_mapping')).mappings().all()
        result=dict(captured_at=captured,period_start='2026-01-01',period_end='2026-10-19',
            raw_start_rows=[dict(r) for r in rows],profiles=[dict(r) for r in profiles],
            mappings=[dict(r) for r in mappings])
print(json.dumps(scrub(result,credential_values()),ensure_ascii=False,default=str))
