"""Read-only, bounded evidence capture; run inside the HOME API container.

Does not invoke collectors, update mappings or publish files.
"""
import json
from sqlalchemy import text
from backend.db import engine_for
from scripts.export_json import scrub, credential_values

queries = {
    'statistics_2026': """SELECT entity_id,source_id,recorded_at,payload FROM home_revision
      WHERE superseded_at IS NULL AND kind='statistic'
      AND payload->>'statistic_period' BETWEEN '202601' AND '202610'
      AND sample_region IN ('서울특별시','경기도','인천광역시') ORDER BY entity_id""",
    'projects': """SELECT entity_id,source_id,recorded_at,payload FROM home_revision
      WHERE superseded_at IS NULL AND kind='project' ORDER BY entity_id""",
    'general_permit_by_region': """SELECT sample_region,count(*) AS records,
      count(*) FILTER (WHERE (payload->>'units')::numeric>0) AS positive_households,
      count(*) FILTER (WHERE (payload->>'units')::numeric=0) AS zero_households,
      count(*) FILTER (WHERE payload->>'units' IS NULL) AS missing_households,
      count(*) FILTER (WHERE payload->'dates'->>'실제착공일 (realStcnsDay)' IS NOT NULL) AS actual_date_present
      FROM home_revision WHERE superseded_at IS NULL AND kind='general_permit' GROUP BY sample_region""",
    'source_kind_counts': """SELECT source_id,kind,count(*) AS records FROM home_revision
      WHERE superseded_at IS NULL GROUP BY source_id,kind ORDER BY source_id,kind""",
    'recent_expansion_batches': """SELECT source_id,started_at,finished_at,status,
      stats->>'scope_completed_dongs' AS completed, stats->>'scope_total_dongs' AS total,
      stats->>'batch_records' AS batch_records FROM home_batch
      WHERE started_at>='2026-10-16' AND source_id IN
      ('building_general_permit','building_hub','building_hub_incheon','molit_statistics')
      ORDER BY source_id,started_at""",
    'targeted_evidence': """SELECT entity_id,source_id,kind,recorded_at,payload FROM home_revision
      WHERE superseded_at IS NULL AND kind IN ('document_evidence','renewal_inventory','permit','general_permit')
      AND sample_name ILIKE ANY(ARRAY['%흑석11%','%중계본동%','%신림2%','%왕숙2%'])
      ORDER BY kind,entity_id""",
}
with engine_for().connect().execution_options(isolation_level='REPEATABLE READ') as c:
    with c.begin():
        c.execute(text('SET TRANSACTION READ ONLY'))
        c.execute(text("SET LOCAL statement_timeout='45s'"))
        result = {'capture':dict(c.execute(text('SELECT current_timestamp AS captured_at, txid_current_snapshot()::text AS snapshot')).mappings().one())}
        for name, sql in queries.items():
            result[name] = [dict(r) for r in c.execute(text(sql)).mappings()]
print(json.dumps(scrub(result, credential_values()),ensure_ascii=False,default=str))
