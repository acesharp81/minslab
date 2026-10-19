import json
from datetime import datetime,timezone
from sqlalchemy import text
from backend.db import engine_for
from scripts.export_json import scrub,credential_values
terms=['대장','창릉','계양','교산','왕숙','중계','흑석','신림','고덕강일','광교','과천지식','과천 지식']
# Explicit read-only consistent snapshot. No collectors, refresh, mapping or writes.
with engine_for().connect().execution_options(isolation_level='REPEATABLE READ') as c:
 with c.begin():
  c.execute(text('SET TRANSACTION READ ONLY'))
  stamps=c.execute(text('SELECT current_timestamp AS captured_at, txid_current_snapshot()::text AS snapshot')).mappings().one()
  kinds=['policy','policy_delivery_plan','policy_profile','program_profile','goal','delivery_setting','statistic','policy_task','policy_event']
  data=c.execute(text('SELECT entity_id,kind,source_id,revision_no,recorded_at,payload FROM home_revision WHERE superseded_at IS NULL AND kind=ANY(:kinds) ORDER BY kind,entity_id'),{'kinds':kinds}).mappings().all()
  targeted=c.execute(text('SELECT entity_id,kind,source_id,revision_no,recorded_at,payload FROM home_revision WHERE superseded_at IS NULL AND kind IN (\'project\',\'permit\',\'renewal_inventory\',\'sh_project\',\'document_evidence\',\'notice\',\'lh_stock\',\'lh_movein_history\',\'lh_completion_plan\') AND sample_name ILIKE ANY(:patterns) ORDER BY kind,entity_id'),{'patterns':['%'+t+'%' for t in terms]}).mappings().all()
  total=c.execute(text('SELECT kind,count(*) AS n FROM home_revision WHERE superseded_at IS NULL AND kind=ANY(:kinds) GROUP BY kind'),{'kinds':kinds}).mappings().all()
  output={'capture':dict(stamps),'selected_kinds':[dict(x) for x in total],'records':[dict(x) for x in data],'targeted_raw':[dict(x) for x in targeted],'targeted_terms':terms,'targeted_limit':None}
print(json.dumps(scrub(output,credential_values()),ensure_ascii=False,default=str))
