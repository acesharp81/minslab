import os
import threading
from collections import Counter, defaultdict
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy import or_, select, text, update, func

from .collectors import Fetcher, collect
from .api_samples import collect_sample
from .db import Audit, Batch, Mapping, ProgramMapping, Revision, entity_id, factory, now, upsert_revision
from .program_hierarchy import program_id, policy_proposal, effective_mapping
from .matching_rules import policy_members
from .roadmap import build_roadmap, project_roadmap
from .map_data import collect_districts
from .municipality_geo import collect_municipalities
from .history_data import collect_policy_events,collect_project_reports
from .collection_period import ORIGINS,collection_start
from .supply_dashboard import build_dashboard
from .sources import SOURCES
from .lh_public_history import collect_supply, collect_movein, collect_stock
from .lh_block_location import collect_block_locations
from .lh_progress import collect_progress
from .lh_reit_progress import collect_reit_progress
from .public_files import collect_sh_files, collect_gh_files, collect_legal_dongs
from .agency_data import collect_sh_inventory, collect_gh_notices, parse_gh_plan
from .policy_monitor import catalogue, automatic_proposal, build_monitor
from .area_stats import collect_sgis_area, collect_kosis_employment, collect_kosis_household_forecast, collect_kosis_housing, collect_kosis_household_size

KST = ZoneInfo("Asia/Seoul")
LOCAL_LOCK = threading.Lock()


def latest_batches(session, status=None, cutoff=None):
    query=select(Batch.id,func.row_number().over(partition_by=Batch.source_id,order_by=Batch.started_at.desc()).label('rn'))
    if status:query=query.where(Batch.status==status)
    if cutoff:query=query.where(Batch.finished_at<cutoff)
    ranked=query.subquery()
    return session.scalars(select(Batch).where(Batch.id.in_(select(ranked.c.id).where(ranked.c.rn==1)))).all()


def today():
    return datetime.now(KST).date()


def as_utc(value):
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


class HomeService:
    def __init__(self, engine, data_dir="data"):
        self.engine = engine
        self.sessions = factory(engine)
        self.data_dir = Path(data_dir)

    def collect_all(self, source_id=None, samples=False):
        if not LOCAL_LOCK.acquire(blocking=False):
            return {"status": "BUSY"}
        connection = None
        try:
            if self.engine.dialect.name == "postgresql":
                connection = self.engine.connect()
                if not connection.scalar(text("SELECT pg_try_advisory_lock(1018100)")):
                    return {"status": "BUSY"}
            results = []
            for source in SOURCES:
                if source.get("implemented", True) is False or (source_id and source_id != source["id"]):
                    continue
                if samples and source.get("collection_mode") != "TEST_SAMPLE":
                    continue
                if not samples and not source_id and source.get("manual_only"):
                    continue
                results.append(self.collect_one(source))
            return {"status": "FINISHED", "results": results}
        finally:
            if connection:
                connection.execute(text("SELECT pg_advisory_unlock(1018100)"))
                connection.close()
            LOCAL_LOCK.release()

    def collect_samples(self, source_id=None):
        return self.collect_all(source_id, samples=True)

    def collect_one(self, source):
        with self.sessions.begin() as session:
            batch = Batch(source_id=source["id"], status="RUNNING")
            session.add(batch)
            session.flush()
            batch_id = batch.id
        fetcher = Fetcher(source["id"], self.data_dir / "raw")
        try:
            if source['id']=='kosis_housing':
                records,stats=collect_kosis_housing(source,fetcher)
            elif source['id']=='kosis_household_size':
                records,stats=collect_kosis_household_size(source,fetcher)
            elif source['id']=='sgis_area':
                records,stats=collect_sgis_area(source,fetcher,self)
            elif source['id']=='kosis_employment':
                records,stats=collect_kosis_employment(source,fetcher)
            elif source['id']=='kosis_household_forecast':
                records,stats=collect_kosis_household_forecast(source,fetcher)
            elif source['id']=='lh_block_location':
                records,stats=collect_block_locations(source,fetcher,self)
            elif source['id']=='lh_reit_progress':
                records,stats=collect_reit_progress(source,fetcher)
            elif source['id']=='lh_progress':
                records,stats=collect_progress(source,fetcher,self)
            elif source['id']=='lh_movein_history':
                records,stats=collect_movein(source,fetcher,self)
            elif source['id'] in ('lh_supply_history','lh_stock'):
                records,stats={'lh_supply_history':collect_supply,'lh_stock':collect_stock}[source['id']](source,fetcher)
            elif source['id'] in ('sh_files','gh_files','legal_dongs'):
                records,stats={'sh_files':collect_sh_files,'gh_files':collect_gh_files,'legal_dongs':collect_legal_dongs}[source['id']](source,fetcher)
            elif source['id'] == 'sh_inventory':
                records,stats=collect_sh_inventory(source,fetcher,self)
            elif source['id'] == 'gh_supply_plan':
                records,stats=parse_gh_plan(source,fetcher.get(source['url']))
            elif source['id'] == 'gh_notice':
                records,stats=collect_gh_notices(source,fetcher)
            elif source.get("collection_mode")=="MUNICIPALITY_LAYER":
                records,stats=collect_municipalities(source,fetcher,self)
            elif source.get("collection_mode")=="MAP_LAYER":
                records,stats=collect_districts(source,fetcher,self)
            elif source['id']=='policy_history':
                records,stats=collect_policy_events(source,fetcher)
            elif source['id']=='lh_history':
                records,stats=collect_project_reports(source,fetcher,self)
            else:
                records, stats = (collect_sample(source, fetcher, self) if source.get("collection_mode") == "TEST_SAMPLE"
                                  else collect(source, fetcher))
            with self.sessions.begin() as session:
                counts = Counter()
                entity_ids = []
                catalogue_rows = self.mapping_policies()
                policy_ids = {p["policy_id"] for p in catalogue_rows}
                real_policies = {p["policy_id"]: p for p in catalogue_rows if p.get("monitor_kind") == "POLICY"}
                policy_ids.update(payload["id"] for kind, _, payload in records if kind == "policy")
                real_policies.update({payload['id']: dict(payload, policy_id=payload['id'])
                    for kind, _, payload in records if kind == 'policy'})
                for kind, key, payload in records:
                    record, outcome = upsert_revision(session, kind, source["id"], key, payload, batch_id)
                    counts[outcome] += 1
                    entity_ids.append(record.entity_id)
                    if kind == "project":
                        mapping = session.scalar(select(Mapping).where(Mapping.project_id == record.entity_id))
                        if mapping is None:
                            proposal = automatic_proposal(payload, policy_ids)
                            mapping = Mapping(project_id=record.entity_id, policy_id=proposal["policy_id"], status="REVIEW",
                                              basis=proposal["basis"], evidence_url=payload["evidence_url"])
                            session.add(mapping)
                            session.add(Audit(entity_id=record.entity_id, action="MAPPING_AUTO", before={},
                                              after=dict(proposal, status="REVIEW", revision_no=1, evidence_url=payload["evidence_url"])))
                        if mapping.program_id is None:
                            self._attach_program(session, mapping, payload, real_policies)
                if stats.get('incremental'):
                    session.flush()
                    stats['cumulative_record_count']=session.scalar(select(func.count()).select_from(Revision).where(Revision.source_id==source['id'],Revision.superseded_at.is_(None)))
                batch = session.get(Batch, batch_id)
                batch.finished_at, batch.status = now(), "SUCCESS"
                batch.manifest = fetcher.manifest
                batch.stats = dict(stats, **counts, record_count=len(records), entity_ids=entity_ids)
            return {"source_id": source["id"], "status": "SUCCESS", "records": len(records), **counts}
        except Exception as error:
            # No request URLs, credentials or traceback are persisted in public errors.
            message = str(error) if isinstance(error, ValueError) else "수집/적재 실패: 마지막 정상 데이터 유지"
            with self.sessions.begin() as session:
                batch = session.get(Batch, batch_id)
                batch.finished_at, batch.status = now(), "FAILED"
                batch.error = message[:300]
                batch.manifest = fetcher.manifest
            return {"source_id": source["id"], "status": "FAILED", "error": message[:300]}
        finally:
            fetcher.close()

    @staticmethod
    def _attach_program(session, mapping, payload, real_policies):
        name = (payload.get('program') or '프로그램 미분류').strip()
        seed = mapping.policy_id or 'UNASSIGNED'
        pid = program_id(name, seed)
        programme = session.get(ProgramMapping, pid)
        if programme is None:
            proposed_policy, reason = policy_proposal(name, seed, real_policies)
            policy = real_policies.get(proposed_policy)
            programme = ProgramMapping(id=pid, name=name, seed_policy_id=seed,
                policy_id=proposed_policy, status='REVIEW', revision_no=1,
                basis='자동 임시 제안 · ' + reason + ' · 담당자 확인 필요; 개별 사업의 공식 정책 귀속은 미확정',
                evidence_url=(policy or {}).get('evidence_url') or payload.get('evidence_url') or '')
            session.add(programme)
        mapping.program_id = pid
        return programme

    def reconcile_program_links(self):
        """Idempotently migrate legacy direct links without treating them as approvals."""
        real_policies = {p['policy_id']: p for p in self.mapping_policies() if p.get('monitor_kind') == 'POLICY'}
        with self.sessions.begin() as session:
            records = session.scalars(select(Revision).where(Revision.kind == 'project', Revision.superseded_at.is_(None))).all()
            mappings = {row.project_id: row for row in session.scalars(select(Mapping)).all()}
            linked = 0
            for record in records:
                mapping = mappings.get(record.entity_id)
                if mapping is not None and mapping.program_id is None:
                    self._attach_program(session, mapping, record.payload, real_policies)
                    linked += 1
            return linked

    def propose_program_policies(self):
        """Backfill unresolved cohorts without overwriting any staff decision."""
        real_policies = {p['policy_id']: p for p in self.mapping_policies() if p.get('monitor_kind') == 'POLICY'}
        with self.sessions.begin() as session:
            manually_reviewed = set(session.scalars(select(Audit.entity_id).where(
                Audit.action == 'PROGRAM_POLICY_REVIEW')).all())
            updated = 0
            for row in session.scalars(select(ProgramMapping).where(
                    ProgramMapping.policy_id == 'UNASSIGNED', ProgramMapping.status == 'REVIEW').with_for_update()).all():
                if row.id in manually_reviewed or row.reviewed_at is not None:
                    continue
                candidate, reason = policy_proposal(row.name, row.seed_policy_id, real_policies)
                if candidate == 'UNASSIGNED':
                    continue
                before = dict(policy_id=row.policy_id, status=row.status, basis=row.basis,
                              evidence_url=row.evidence_url, revision_no=row.revision_no)
                row.policy_id = candidate
                row.basis = '자동 임시 제안 · ' + reason + ' · 담당자 확인 필요; 개별 사업의 공식 정책 귀속은 미확정'
                row.evidence_url = real_policies[candidate].get('evidence_url') or row.evidence_url
                row.revision_no += 1
                after = dict(policy_id=row.policy_id, status=row.status, basis=row.basis,
                             evidence_url=row.evidence_url, revision_no=row.revision_no)
                session.add(Audit(entity_id=row.id, action='PROGRAM_POLICY_AUTO', before=before, after=after))
                updated += 1
            return updated

    def latest_collection_stats(self, source_id):
        with self.sessions() as session:
            return session.scalar(select(Batch.stats).where(Batch.source_id==source_id,Batch.status=='SUCCESS').order_by(Batch.finished_at.desc()).limit(1)) or {}

    def rows(self, kind, as_of=None, entity_ids=None):
        day = as_of or today()
        cutoff = datetime.combine(day + timedelta(days=1), time.min, KST).astimezone(timezone.utc)
        with self.sessions() as session:
            query=select(Revision).where(Revision.kind==kind,Revision.recorded_at<cutoff,
                or_(Revision.superseded_at.is_(None),Revision.superseded_at>=cutoff))
            if entity_ids is not None:query=query.where(Revision.entity_id.in_(entity_ids))
            records=session.scalars(query).all()
            mappings = {x.project_id: x for x in session.scalars(select(Mapping)).all()} if kind == "project" else {}
            programs = {}
            if kind == "project":
                for program in session.scalars(select(ProgramMapping)).all():
                    if as_utc(program.created_at) >= cutoff:
                        continue
                    state = {"id": program.id, "name": program.name, "policy_id": program.policy_id,
                             "status": program.status, "revision_no": program.revision_no}
                    changes = session.scalars(select(Audit).where(Audit.entity_id == program.id,
                        Audit.action.in_(['PROGRAM_POLICY_REVIEW', 'PROGRAM_POLICY_AUTO']), Audit.recorded_at >= cutoff)
                        .order_by(Audit.recorded_at.desc())).all()
                    for change in changes:
                        state.update(change.before)
                    programs[program.id] = state
            attempts=latest_batches(session,'SUCCESS',cutoff) if kind=='project' else []
            latest_success = {}
            for batch in attempts:
                if batch.status == "SUCCESS" and batch.finished_at and as_utc(batch.finished_at) < cutoff and batch.source_id not in latest_success:
                    latest_success[batch.source_id] = batch
            result = []
            for record in records:
                payload = record.payload
                if payload.get("base_date", "9999") > day.isoformat():
                    continue
                row = dict(payload, id=record.entity_id, source_id=record.source_id, revision_no=record.revision_no,
                           recorded_at=as_utc(record.recorded_at).isoformat())
                age = (day - date.fromisoformat(payload["base_date"])).days
                # Annual plans have year precision, not a source update date.
                row["source_age_days"] = age if payload.get("date_precision") != "YEAR" else None
                row["warnings"] = list(payload.get("warnings", []))
                if kind == "project":
                    if row["source_age_days"] is not None and age > 30:
                        row["warnings"].append("STALE_SOURCE")
                    if row.get("schedule_month") and row["schedule_month"] < day.strftime("%Y-%m") and row.get("stage") != "COMPLETED":
                        row["warnings"].append("PAST_PLAN_UNVERIFIED")
                    if row.get("planned_units") is None:
                        row["warnings"].append("UNITS_UNKNOWN")
                    mapping = mappings.get(record.entity_id)
                    # Mapping revisions after a historical cutoff cannot be projected backwards.
                    row["mapping"] = {"status": mapping.status if mapping else "REVIEW",
                                      "policy_id": mapping.policy_id if mapping else payload.get("proposed_policy"),
                                      "program_id": mapping.program_id if mapping else None,
                                      "revision_no": mapping.revision_no if mapping else 1,
                                      "basis": mapping.basis if mapping else payload.get("mapping_basis"),
                                      "evidence_url": mapping.evidence_url if mapping else payload.get("evidence_url")}
                    history = session.scalars(select(Audit).where(Audit.entity_id == record.entity_id, Audit.action != "TARGETS_UPDATED",
                        Audit.recorded_at >= cutoff).order_by(Audit.recorded_at.desc())).all()
                    for change in history:
                        if change.before:
                            row["mapping"] = change.before
                    row["source_program"] = row.get("program")
                    program = programs.get(row["mapping"].get("program_id"))
                    row["mapping"] = effective_mapping(row["mapping"], program)
                    if program:
                        row["program"] = program["name"]
                    if row["mapping"]["status"] != "CONFIRMED" or row["mapping"].get('policy_status') == 'REVIEW':
                        row["warnings"].append("MAPPING_REVIEW")
                    batch = latest_success.get(record.source_id)
                    row["in_latest_source"] = bool(batch and record.entity_id in batch.stats.get("entity_ids", []))
                    if batch and not row["in_latest_source"]:
                        row["warnings"].append("MISSING_IN_LATEST_SOURCE")
                result.append(row)
            return result

    def projects(self, as_of=None, region=None, policy_id=None, source_id=None, stage=None, q=None, mapping_status=None):
        rows = self.rows("project", as_of)
        # Independent progress evidence enriches the view without overwriting plans,
        # policy approvals or the original project revision.
        latest={}
        for report in self.rows('project_report',as_of):
            if report.get('source_id')!='lh_progress' or report.get('progress_pct') is None:continue
            pid=report.get('current_project_id')
            stamp=report['report_date']
            if pid and (pid not in latest or stamp>latest[pid]['report_date']):latest[pid]=report
        for row in rows:
            report=latest.get(row['id'])
            if report and (row.get('progress_pct') is None or report['report_date']>row.get('progress_date',row['base_date'])):
                row.update(progress_pct=report['progress_pct'],progress_date=report['report_date'],
                    progress_evidence_url=report['evidence_url'],progress_date_basis=report.get('progress_date_basis'),
                    progress_date_precision=report.get('date_precision','DAY'))
        for field, value in (("region", region), ("source_id", source_id), ("stage", stage)):
            if value:
                rows = [r for r in rows if r.get(field) == value]
        if policy_id in ('MON_THIRD_NEW_TOWN', 'MON_URBAN_COMPLEX'):
            rows = policy_members({'policy_id': policy_id, 'monitor_kind': 'PROGRAMME'}, rows)
        elif policy_id:
            rows = [r for r in rows if r["mapping"]["policy_id"] == policy_id]
        if mapping_status:
            rows = [r for r in rows if r["mapping"]["status"] == mapping_status]
        if q:
            rows = [r for r in rows if q.casefold() in " ".join(str(r.get(k, "")) for k in ("name", "program", "municipality", "district")).casefold()]
        return sorted(rows, key=lambda r: (r["region"], r["name"]))

    def sample_select(self, as_of=None, region=None, source_id=None, q=None, kind=None, source_year=None):
        day=as_of or today()
        cutoff=datetime.combine(day+timedelta(days=1),time.min,KST).astimezone(timezone.utc)
        kinds=(kind,) if kind else ('notice','permit','location','register','lh_notice','statistic','sh_plan','sh_project','gh_notice','agency_stock','legal_dong','lh_supply','lh_movein_plan','lh_stock')
        active=Revision.superseded_at.is_(None) if day==today() else or_(Revision.superseded_at.is_(None),Revision.superseded_at>=cutoff)
        query=select(Revision).where(Revision.kind.in_(kinds),Revision.recorded_at<cutoff,
            active,Revision.sample_base_date<=day.isoformat())
        if region:query=query.where(Revision.sample_region==region)
        if source_id:query=query.where(Revision.source_id==source_id)
        if q:
            pattern='%'+q.replace(chr(92),chr(92)*2).replace('%',chr(92)+'%').replace('_',chr(92)+'_')+'%'
            query=query.where(or_(*(Revision.payload[k].as_string().ilike(pattern,escape=chr(92)) for k in ('name','address','source_object_id'))))
        if source_year:query=query.where(func.substr(Revision.sample_source_date,1,4)==str(source_year))
        return query

    def sample_page(self, page=1, page_size=100, **filters):
        day=filters.get('as_of') or today()
        query=self.sample_select(**filters)
        unfiltered=self.sample_select(**dict(filters,source_year=None)).subquery()
        sub=query.subquery()
        with self.sessions() as session:
            counts=dict(session.execute(select(sub.c.kind,func.count()).group_by(sub.c.kind)).all())
            region_expr=sub.c.sample_region.label('region')
            regions=dict(session.execute(select(region_expr,func.count()).group_by(region_expr)).all())
            years=session.scalars(select(func.substr(unfiltered.c.sample_source_date,1,4)).distinct()).all()
            records=session.scalars(query.order_by(Revision.kind,Revision.sample_region,Revision.sample_name,Revision.entity_id).offset((page-1)*page_size).limit(page_size)).all()
            rows=[dict(r.payload,id=r.entity_id,source_id=r.source_id,revision_no=r.revision_no,
                recorded_at=as_utc(r.recorded_at).isoformat(),source_age_days=(day-date.fromisoformat(r.payload['base_date'])).days,
                warnings=list(r.payload.get('warnings',[]))) for r in records]
        return dict(items=rows,total=sum(counts.values()),page=page,page_size=page_size,counts=counts,regions=regions,
            source_years=sorted({int(y) for y in years if y and y.isdigit()},reverse=True),collection_mode='TEST_SAMPLE',
            notice='공식 원천 검증 자료입니다. 기존 재고·행정코드를 신규 정책 공급실적에 합산하지 않습니다.')

    def iterate_samples(self, **filters):
        query=self.sample_select(**filters).order_by(Revision.kind,Revision.sample_region,Revision.sample_name,Revision.entity_id)
        with self.sessions() as session:
            for record in session.scalars(query.execution_options(yield_per=200)):
                yield dict(record.payload,id=record.entity_id,source_id=record.source_id,revision_no=record.revision_no,
                    recorded_at=as_utc(record.recorded_at).isoformat())

    def sample_count(self, **filters):
        with self.sessions() as session:
            return session.scalar(select(func.count()).select_from(self.sample_select(**filters).subquery()))

    def samples(self, as_of=None, region=None, source_id=None, q=None, kind=None, source_year=None):
        rows = [row for category in ((kind,) if kind else ("notice", "permit", "location", "register", "lh_notice", "statistic", "sh_plan", "sh_project", "gh_notice", "agency_stock", "legal_dong", "lh_supply", "lh_movein_plan", "lh_stock")) for row in self.rows(category, as_of)]
        for field, value in (("region", region), ("source_id", source_id)):
            if value:
                rows = [row for row in rows if row.get(field) == value]
        if q:
            rows = [row for row in rows if q.casefold() in " ".join(str(row.get(k, "")) for k in
                    ("name", "address", "source_object_id")).casefold()]
        if source_year is not None:
            rows = [row for row in rows if (row.get("source_date") or "")[:4] == str(source_year)]
        return sorted(rows, key=lambda row: (row["sample_kind"], row["region"], row["name"], row["id"]))

    def sources(self):
        with self.sessions() as session:
            attempts={b.source_id:b for b in latest_batches(session)}
            successes={b.source_id:b for b in latest_batches(session,'SUCCESS')}
            result = []
            for source in SOURCES:
                last=attempts.get(source['id']);success=successes.get(source['id'])
                item = dict(source)
                key_env = source["key_env"]
                item["key_configured"] = bool(key_env and os.environ.get(key_env))
                item["status"] = last.status if last else "CONNECTOR_PENDING" if source.get("implemented") is False else "NOT_COLLECTED"
                item["last_attempt"] = as_utc(last.started_at).isoformat() if last else None
                item["last_success"] = as_utc(success.finished_at).isoformat() if success else None
                item["error"] = last.error if last else None
                item["record_count"] = success.stats.get("cumulative_record_count", success.stats.get("record_count", 0)) if success else 0
                item["stats"] = {k: v for k, v in success.stats.items() if k != "entity_ids"} if success else {}
                item["snapshots"] = success.manifest if success else []
                result.append(item)
            return result

    def roadmap(self, as_of=None, horizon=10, **filters):
        plans = {r["project_id"]:r for r in self.rows("goal",as_of)}
        return build_roadmap([r for r in self.projects(as_of,**filters) if r["mapping"]["status"] != "RELEASED"],plans,as_of or today(),horizon)

    def map_data(self,as_of=None,**filters):
        project_ids={row["id"] for row in self.projects(as_of,**filters)}
        districts=[]
        located=set()
        for row in self.rows("district",as_of):
            linked=sorted(project_ids.intersection(row["project_ids"]))
            if linked:
                districts.append(dict(row,project_ids=linked))
                located.update(linked)
        # API observation points are separate from the policy project layer.
        locations=self.rows('location',as_of)
        parents={r.get('parent_sample_id') for r in locations}
        samples={row['id']:row for kind in ('notice','permit') for row in self.rows(kind,as_of,entity_ids=parents)}
        observations=[]
        for row in locations:
            parent=samples.get(row.get("parent_sample_id"))
            if not parent or row.get("resolution_status")!="OK":
                continue
            if filters.get("region") and row["region"]!=filters["region"]:
                continue
            if filters.get("q") and filters["q"].casefold() not in (parent["name"]+" "+parent.get("address","")).casefold():
                continue
            if filters.get("policy_id") or filters.get("source_id") or filters.get("stage") or filters.get("mapping_status"):
                continue
            observations.append(dict(row,parent_name=parent["name"],parent_source_id=parent["source_id"],
                                     move_in_plan_month=parent.get("move_in_plan_month"),source_date=parent.get("source_date"),units=parent.get("units")))
        return {"districts":districts,"observations":observations,"project_count":len(project_ids),"located_project_count":len(located),
                "unlocated_project_ids":sorted(project_ids-located),"coordinate_basis":"지구 대표 위치 · 개별 블록 연결 검토 전"}

    def observation_year_counts(self,kind,as_of=None,region=None,q=None,through=None):
        # Project dashboards need counts, never hundreds of thousands of permit payloads.
        sub=self.sample_select(as_of=as_of,region=region,q=q,kind=kind).subquery()
        stamp=sub.c.sample_event_day if kind=='permit' else sub.c.sample_source_date
        year=func.coalesce(func.substr(stamp,1,4),'').label('year')
        query=select(year,func.count()).group_by(year)
        if through:query=query.where(stamp<=through.isoformat())
        with self.sessions() as session:return Counter(dict(session.execute(query).all()))

    def supply_dashboard(self,as_of=None,analysis_year=None,horizon=10,measure="MOVE_IN",**filters):
        knowledge=as_of or today()
        reference=min(date(analysis_year or knowledge.year,12,31),knowledge)
        show_market=not any(filters.get(k) for k in ('policy_id','source_id','stage','mapping_status','q'))
        annual_permit_count=self.observation_year_counts('permit',as_of,filters.get('region'),through=reference)[str(reference.year)] if show_market else 0
        return build_dashboard(self.projects(as_of),self.rows("project_report",as_of),self.rows("district",as_of),
            self.mapping_policies(as_of),self.rows("goal",as_of),self.rows("notice",as_of),self.rows("policy_event",as_of),
            knowledge,collection_start().year,analysis_year,horizon,measure,annual_permit_count=annual_permit_count,
            municipalities=self.rows("municipality",as_of),block_locations=self.rows("block_location",as_of),**filters)

    def historical_data(self,as_of=None,year=None,page=1,page_size=100,**filters):
        end=as_of or today()
        start=collection_start()
        projects=self.projects(as_of,**filters)
        project_ids={row['id'] for row in projects}
        origins=set(ORIGINS) if not filters.get('policy_id') else {
            origin for row in projects for origin in ORIGINS
            if (origin=='THIRD_NEW_TOWN' and row.get('program')=='3기 신도시')
            or (origin=='URBAN_COMPLEX' and '복합사업' in row.get('program',''))}
        events=[row for row in self.rows('policy_event',as_of) if row['origin_id'] in origins]
        for policy in self.policy_rows(as_of):
            if filters.get('policy_id') and policy['policy_id']!=filters['policy_id']:continue
            events.append(dict(policy,event_date=policy['announced_at'],basis=policy['metric'],
                date_basis='공식 발표일 · 법적 시행일과 구분',relation_status='REVIEW'))
        events.sort(key=lambda row:row['event_date'])
        reports=self.rows('project_report',as_of)
        for field,value in (('region',filters.get('region')),):
            if value:reports=[row for row in reports if row.get(field)==value]
        if any(filters.get(key) for key in ('policy_id','stage','mapping_status')):
            reports=[row for row in reports if row.get('current_project_id') in project_ids]
        elif filters.get('source_id'):
            reports=[row for row in reports if row.get('source_id')==filters['source_id'] or row.get('current_project_id') in project_ids]
        if filters.get('q'):
            needle=filters['q'].casefold()
            reports=[row for row in reports if needle in (row['name']+' '+row.get('district','')).casefold()]
        annual_notices=Counter();annual_permits=Counter();permit_total=0
        if not any(filters.get(key) for key in ('policy_id','source_id','stage','mapping_status')):
            annual_notices=self.observation_year_counts('notice',as_of,filters.get('region'),filters.get('q'))
            annual_permits=self.observation_year_counts('permit',as_of,filters.get('region'),filters.get('q'))
            permit_total=sum(annual_permits.values())
        years=[]
        for value in range(start.year,end.year+1):
            annual=[row for row in reports if int(row['report_date'][:4])==value]
            notices=annual_notices[str(value)];permits=annual_permits[str(value)]
            years.append({'year':value,'policy_event_count':sum(row['event_date'][:4]==str(value) for row in events),
                'report_count':len({row['report_date'] for row in annual}),'project_report_rows':len(annual),
                'notice_count':notices,'permit_count':permits,
                'coverage_status':'HAS_EVIDENCE' if annual or notices or permits or any(row['event_date'][:4]==str(value) for row in events) else 'NOT_AVAILABLE'})
        selected=[row for row in reports if not year or row['report_date'][:4]==str(year)]
        selected.sort(key=lambda row:(row['report_date'],row['name']),reverse=True)
        coverage=[{key:source[key] for key in ('id','name','status','stats','last_success')}
                  for source in self.sources() if source['id'] in {'cheongyak','building_hub','lh_history','policy_history','lh_progress','lh_reit_progress'}]
        return {'start_year':start.year,'end_year':end.year,'period_start':start.isoformat(),
                'origins':[dict(value,id=key) for key,value in ORIGINS.items() if key in origins],
                'events':[row for row in events if not year or row['event_date'][:4]==str(year)],'years':years,
                'reports':selected[(page-1)*page_size:page*page_size],'report_total':len(selected),'page':page,'page_size':page_size,
                'source_coverage':coverage,
                'unclassified_or_earlier_permits':permit_total-sum(row['permit_count'] for row in years),
                'notice':'자료연도와 실제 수집일은 별개입니다. 과거 발표 목표·공정률은 당시 자료이며, 자료 미확보는 실적 0을 의미하지 않습니다.'}

    def targets(self, project_id, as_of=None):
        project=next((r for r in self.projects(as_of) if r["id"]==project_id),None)
        if project is None:
            return None
        plan = next((r for r in self.rows("goal",as_of) if r["project_id"]==project_id),None)
        result = dict(plan,history=self.history(plan["id"],as_of)) if plan else {"project_id":project_id,"revision_no":0,"targets":[],"history":[]}
        return dict(result,project_name=project["name"],current_year=(as_of or today()).year,
                    source_annual=project_roadmap(project,{},as_of or today(),10)["annual"])

    def save_targets(self, project_id, revision_no, targets):
        years = [target["year"] for target in targets]
        if len(years)!=len(set(years)) or any(year>today().year+10 for year in years):
            raise ValueError("목표 연도 중복 또는 향후 10년 범위 초과")
        if any(not target["basis"].strip() for target in targets):
            raise ValueError("연도별 추진목표 근거·메모가 필요합니다")
        if any(target.get("evidence_url") and not target["evidence_url"].startswith("https://") for target in targets):
            raise ValueError("근거 URL은 HTTPS를 사용하세요")
        with self.sessions.begin() as session:
            mapping = session.scalar(select(Mapping).where(Mapping.project_id==project_id).with_for_update())
            if not mapping:
                raise KeyError(project_id)
            eid = entity_id("goal","manual_targets",project_id)
            old = session.scalar(select(Revision).where(Revision.entity_id==eid,Revision.superseded_at.is_(None)))
            actual_revision = old.revision_no if old else 0
            if actual_revision!=revision_no:
                return {"conflict":True,"revision_no":actual_revision}
            payload = {"project_id":project_id,"base_date":today().isoformat(),"targets":sorted(targets,key=lambda t:t["year"]),
                       "origin":"MANUAL","basis":"관리자 사업별 연도 추진목표 · 공식 원천 예정과 별도"}
            record,outcome = upsert_revision(session,"goal","manual_targets",project_id,payload,"manual")
            if outcome!="unchanged":
                session.add(Audit(entity_id=project_id,action="TARGETS_UPDATED",before=old.payload if old else {},after=payload))
            return {"project_id":project_id,"revision_no":record.revision_no,"targets":payload["targets"],"outcome":outcome}

    def overview(self, as_of=None, **filters):
        projects = [r for r in self.projects(as_of, **filters) if r["mapping"]["status"] != "RELEASED"]
        counts = Counter(r["region"] for r in projects)
        confirmed = [r for r in projects if r["mapping"]["status"] == "CONFIRMED"]
        policies = self.rows("policy", as_of)
        sources = self.sources()
        with self.sessions() as session:
            first = session.scalar(select(Batch.started_at).order_by(Batch.started_at).limit(1))
        return {"as_of_date": (as_of or today()).isoformat(), "region_scope": ["서울특별시", "경기도"],
                "project_count": len(projects), "policy_count": len(policies), "confirmed_count": len(confirmed),
                "api_sample_count":self.sample_count(as_of=as_of,region=filters.get("region"),q=filters.get("q")),
                "review_count": sum(r["mapping"]["status"] == "REVIEW" for r in projects),
                "warning_count": sum(bool(r["warnings"]) for r in projects), "regions": dict(counts),
                "programs": dict(Counter(r["program"] for r in projects)),
                "stages": dict(Counter(r["stage_label"] for r in projects)),
                "source_counts": {s["id"]: s["record_count"] for s in sources},
                "first_collection_date": as_utc(first).astimezone(KST).date().isoformat() if first else None,
                "baseline_status": "DRAFT", "official_total_units": None,
                "notice": "수집 원천의 사업 후보입니다. 범위 기준선·정책 귀속·원천간 동일사업이 승인되기 전 공식 공급총량을 계산하지 않습니다."}

    def detail(self, entity_id, as_of=None):
        current = next((r for r in self.projects(as_of) if r["id"] == entity_id), None)
        if not current:
            return None
        return dict(current, history=self.history(entity_id, as_of), mapping_history=self.mapping_history(entity_id, as_of))

    def mapping_policies(self, as_of=None):
        return catalogue(self.policy_rows(as_of), self.rows("policy_event", as_of))

    def policy_monitor(self, as_of=None, **filters):
        policies = self.mapping_policies(as_of)
        if any(r['mapping']['policy_id'] in (None, 'UNASSIGNED') and r['mapping']['status'] != 'RELEASED'
               for r in self.projects(as_of)):
            policies.append(dict(policy_id='UNASSIGNED', name='정책 미연계 · 검토 필요',
                monitor_kind='UNMAPPED', announced_at=None, target_units=None,
                target_scope='서울·경기 연결 사업', metric='사업계획 · 정책 귀속 미확정', evidence_url=None))
        if filters.get("policy_id"):
            policies = [p for p in policies if p["policy_id"] == filters["policy_id"]]
            filters = dict(filters, policy_id=None)
        return build_monitor(self.projects(as_of, **filters), policies, self.rows("goal", as_of),
                             self.rows("notice", as_of), as_of or today(),
                             reports=self.rows("project_report",as_of),districts=self.rows("district",as_of),
                             municipalities=self.rows("municipality",as_of),policy_events=self.rows("policy_event",as_of))

    def mappings(self, as_of=None, **filters):
        policies = self.mapping_policies(as_of)
        ids = {p["policy_id"] for p in policies}
        rows = self.projects(as_of, **filters)
        programs = self.program_links(as_of, rows)
        return {"items": [dict(r, auto_match=automatic_proposal(r, ids),
                    statistics_included=r["mapping"]["status"] != "RELEASED",
                    policy_statistics_included=r["mapping"]["status"] != "RELEASED" and
                        r["mapping"]["policy_id"] not in (None, "UNASSIGNED")) for r in rows],
                "policies": policies, "programs": programs, "total": len(rows),
                "counts": dict(Counter(r["mapping"]["status"] for r in rows)),
                "audit": {"review_programs": sum(p['status'] == 'REVIEW' for p in programs),
                          "review_projects": sum(r['mapping']['status'] == 'REVIEW' for r in rows),
                          "unlinked_projects": sum(not r["mapping"].get("program_id") or r["mapping"]["program_id"] == "UNASSIGNED" for r in rows),
                          "unlinked_policy_projects": sum(r["mapping"]["policy_id"] in (None, "UNASSIGNED") and r["mapping"]["status"] != "RELEASED" for r in rows),
                          "unlinked_programs": sum(p["policy_id"] == "UNASSIGNED" or p['status'] == 'RELEASED' for p in programs)},
                "notice": "정책–프로그램과 프로그램–사업은 가장 가능성 높은 임시 연결로 제안합니다. 확인 필요 상태도 검토 통계에 포함하며 담당자가 각각 수정·확정할 수 있습니다. 임시 연결은 공식 사업 귀속 확인이 아닙니다."}

    def program_links(self, as_of=None, projects=None):
        projects = projects if projects is not None else self.projects(as_of)
        cutoff = datetime.combine((as_of or today()) + timedelta(days=1), time.min, KST).astimezone(timezone.utc)
        with self.sessions() as session:
            programs = session.scalars(select(ProgramMapping).order_by(ProgramMapping.name, ProgramMapping.id)).all()
            result = []
            for row in programs:
                if as_utc(row.created_at) >= cutoff:
                    continue
                state = dict(id=row.id, name=row.name, seed_policy_id=row.seed_policy_id,
                    policy_id=row.policy_id, status=row.status, revision_no=row.revision_no,
                    basis=row.basis, evidence_url=row.evidence_url)
                for change in session.scalars(select(Audit).where(Audit.entity_id == row.id,
                        Audit.action.in_(['PROGRAM_POLICY_REVIEW', 'PROGRAM_POLICY_AUTO']), Audit.recorded_at >= cutoff)
                        .order_by(Audit.recorded_at.desc())).all():
                    state.update(change.before)
                members = [p for p in projects if p['mapping'].get('program_id') == row.id]
                state['project_count'] = len(members)
                state['active_project_count'] = sum(p['mapping']['status'] != 'RELEASED' for p in members)
                result.append(state)
            return result

    def program_policy_history(self, program_id, as_of=None):
        cutoff = datetime.combine((as_of or today()) + timedelta(days=1), time.min, KST).astimezone(timezone.utc)
        with self.sessions() as session:
            records = session.scalars(select(Audit).where(Audit.entity_id == program_id,
                Audit.action.in_(['PROGRAM_POLICY_REVIEW', 'PROGRAM_POLICY_AUTO']), Audit.recorded_at < cutoff)
                .order_by(Audit.recorded_at.desc())).all()
            return [dict(action=r.action, before=r.before, after=r.after,
                         recorded_at=as_utc(r.recorded_at).isoformat()) for r in records]

    def confirm_program_policy(self, program_id, policy_id, revision_no, status, basis, evidence_url):
        real = {p['policy_id'] for p in self.mapping_policies() if p.get('monitor_kind') == 'POLICY'}
        if policy_id not in real and policy_id != 'UNASSIGNED':
            raise ValueError('공식 정책을 선택해야 합니다')
        if status not in {'CONFIRMED', 'REVIEW', 'RELEASED'} or policy_id == 'UNASSIGNED' and status == 'CONFIRMED':
            raise ValueError('정책 미연계 프로그램은 확정할 수 없습니다')
        if not basis.strip() or not evidence_url.startswith('https://'):
            raise ValueError('근거 설명과 HTTPS 원문 URL이 필요합니다')
        with self.sessions.begin() as session:
            row = session.scalar(select(ProgramMapping).where(ProgramMapping.id == program_id).with_for_update())
            if row is None:
                raise KeyError(program_id)
            if row.revision_no != revision_no:
                return {'conflict': True, 'revision_no': row.revision_no}
            before = dict(policy_id=row.policy_id, status=row.status, basis=row.basis,
                          evidence_url=row.evidence_url, revision_no=row.revision_no)
            row.policy_id, row.status, row.basis, row.evidence_url = policy_id, status, basis, evidence_url
            row.revision_no += 1
            row.reviewed_at = now()
            after = dict(policy_id=row.policy_id, status=row.status, basis=row.basis,
                         evidence_url=row.evidence_url, revision_no=row.revision_no)
            session.add(Audit(entity_id=program_id, action='PROGRAM_POLICY_REVIEW', before=before, after=after))
            return after

    def confirm_project_program(self, project_id, program_id, revision_no, status, basis, evidence_url):
        if status not in {'CONFIRMED', 'REVIEW', 'RELEASED'} or program_id == 'UNASSIGNED' and status == 'CONFIRMED':
            raise ValueError('프로그램 미연계 사업은 확정할 수 없습니다')
        if not basis.strip() or not evidence_url.startswith('https://'):
            raise ValueError('근거 설명과 HTTPS 원문 URL이 필요합니다')
        with self.sessions.begin() as session:
            row = session.scalar(select(Mapping).where(Mapping.project_id == project_id).with_for_update())
            if row is None:
                raise KeyError(project_id)
            if program_id != 'UNASSIGNED' and session.get(ProgramMapping, program_id) is None:
                raise ValueError('수집된 프로그램을 선택해야 합니다')
            if row.revision_no != revision_no:
                return {'conflict': True, 'revision_no': row.revision_no}
            before = dict(program_id=row.program_id, policy_id=row.policy_id, status=row.status,
                          basis=row.basis, evidence_url=row.evidence_url, revision_no=row.revision_no)
            row.program_id, row.status, row.basis, row.evidence_url = program_id, status, basis, evidence_url
            row.revision_no += 1
            row.reviewed_at = now()
            after = dict(program_id=row.program_id, policy_id=row.policy_id, status=row.status,
                         basis=row.basis, evidence_url=row.evidence_url, revision_no=row.revision_no)
            session.add(Audit(entity_id=project_id, action='PROGRAM_PROJECT_REVIEW', before=before, after=after))
            return after

    def mapping_history(self, project_id, as_of=None):
        day = as_of or today()
        cutoff = datetime.combine(day + timedelta(days=1), time.min, KST).astimezone(timezone.utc)
        with self.sessions() as session:
            records = session.scalars(select(Audit).where(Audit.entity_id == project_id, Audit.action.in_(["MAPPING_AUTO", "MAPPING_REVIEW", "PROGRAM_PROJECT_REVIEW"]),
                Audit.recorded_at < cutoff).order_by(Audit.recorded_at.desc())).all()
            return [dict(action=r.action, before=r.before, after=r.after, recorded_at=as_utc(r.recorded_at).isoformat()) for r in records]

    def sample_detail(self, entity_id, as_of=None):
        with self.sessions() as session:
            record=session.scalar(self.sample_select(as_of=as_of).where(Revision.entity_id==entity_id))
            current=dict(record.payload,id=record.entity_id,source_id=record.source_id,revision_no=record.revision_no,
                recorded_at=as_utc(record.recorded_at).isoformat()) if record else None
        return dict(current, history=self.history(entity_id, as_of)) if current else None

    def history(self, entity_id, as_of=None):
        day = as_of or today()
        cutoff = datetime.combine(day + timedelta(days=1), time.min, KST).astimezone(timezone.utc)
        with self.sessions() as session:
            revisions = session.scalars(select(Revision).where(Revision.entity_id == entity_id,
                Revision.recorded_at < cutoff).order_by(Revision.revision_no.desc())).all()
            history = []
            for row in revisions:
                batch = session.get(Batch, row.batch_id)
                history.append({"revision_no": row.revision_no, "recorded_at": as_utc(row.recorded_at).isoformat(),
                                "superseded_at": as_utc(row.superseded_at).isoformat() if row.superseded_at and as_utc(row.superseded_at) < cutoff else None,
                                "base_date": row.payload.get("base_date"), "payload_hash": row.payload_hash,
                                "values": row.payload, "snapshots": batch.manifest if batch else []})
        return history

    def tree(self, as_of=None, **filters):
        branches = defaultdict(lambda: defaultdict(list))
        for row in self.projects(as_of, **filters):
            branches[row["mapping"]["policy_id"]][row["program"]].append(row)
        names = {r["id"]: r["name"] for r in self.rows("policy", as_of)}
        # Policy payload id is the stable business id, unlike storage entity_id.
        names.update({r["policy_id"]: r["name"] for r in self.mapping_policies(as_of)})
        names["UNASSIGNED"] = "정책 미연계 · 프로그램 검토 필요"
        return [{"policy_id": pid, "name": names.get(pid, pid + " (원문 미수집)"),
                 "groups": [{"name": name, "count": len(rows), "projects": rows} for name, rows in groups.items()]} for pid, groups in branches.items()]

    def policy_rows(self, as_of=None):
        records = self.rows("policy", as_of)
        result = []
        with self.sessions() as session:
            for row in records:
                record = session.scalar(select(Revision).where(Revision.entity_id == row["id"], Revision.revision_no == row["revision_no"]))
                result.append(dict(row, policy_id=record.payload["id"], values=record.payload))
        return result

    def confirm_mapping(self, project_id, policy_id, revision_no, status, basis, evidence_url):
        if status not in {"CONFIRMED", "REVIEW", "RELEASED"}:
            raise ValueError("허용되지 않은 매핑 상태")
        with self.sessions() as session:
            old = session.scalar(select(Mapping).where(Mapping.project_id == project_id))
            linked = session.get(ProgramMapping, old.program_id) if old and old.program_id else None
            linked_id = linked.id if linked else None
            linked_policy = linked.policy_id if linked else None
        if linked_id:
            if linked_policy != policy_id:
                raise ValueError("정책 변경은 정책–프로그램 연결 화면에서 검토해야 합니다")
            return self.confirm_project_program(project_id, linked_id, revision_no, status, basis, evidence_url)
        if policy_id not in {p["policy_id"] for p in self.mapping_policies()} and not (policy_id == "UNASSIGNED" and status != "CONFIRMED"):
            raise ValueError("수집된 정책을 선택해야 합니다")
        if not basis.strip() or not evidence_url.startswith("https://"):
            raise ValueError("근거 설명과 HTTPS 원문 URL이 필요합니다")
        with self.sessions.begin() as session:
            mapping = session.scalar(select(Mapping).where(Mapping.project_id == project_id).with_for_update())
            if not mapping:
                raise KeyError(project_id)
            if mapping.revision_no != revision_no:
                return {"conflict": True, "revision_no": mapping.revision_no}
            before = {"policy_id": mapping.policy_id, "status": mapping.status, "basis": mapping.basis,
                      "evidence_url": mapping.evidence_url, "revision_no": mapping.revision_no}
            mapping.policy_id, mapping.status, mapping.basis, mapping.evidence_url = policy_id, status, basis, evidence_url
            mapping.revision_no += 1
            mapping.reviewed_at = now()
            after = dict(before, policy_id=policy_id, status=status, basis=basis, evidence_url=evidence_url, revision_no=mapping.revision_no)
            session.add(Audit(entity_id=project_id, action="MAPPING_REVIEW", before=before, after=after))
            return after

    def recover_interrupted_batches(self):
        with self.sessions.begin() as session:
            session.execute(update(Batch).where(Batch.status == "RUNNING").values(status="INTERRUPTED", finished_at=now(), error="서비스 재시작으로 수집 중단. 마지막 정상 데이터 유지"))
