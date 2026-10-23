import csv
import hashlib
import hmac
import io
import json
import os
import threading
import time
from contextlib import asynccontextmanager
from datetime import date, datetime
from collections import Counter
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.gzip import GZipMiddleware
from pydantic import BaseModel, Field
from sqlalchemy import text

from .building_context import BuildingContext
from .infrastructure import InfrastructureContext
from .db import engine_for
from .service import HomeService, today
from .identity import (reconcile_identity_links, identity_summary, plan_summary,
                       identity_review_queue, identity_options, review_identity_alias)
from .sources import SOURCES
from .tiles import tile
from .policy_geo import geometry_view, metrics_view, schematic_view
from . import stage_evidence
from .policy_delivery import build_delivery, settings as delivery_settings, save_settings as save_delivery_settings
from .projection_cache import ProjectionCache, projection_version

ROOT = Path(__file__).resolve().parents[1]
PREFIX = "/poc/home"


def authenticated(request):
    secret = os.environ.get("POC10_INTERNAL_SECRET", "")
    token = request.headers.get("x-home-admin", "")
    try:
        stamp, signature = token.split(":", 1)
        if not secret or abs(time.time() - int(stamp)) > 60:
            return False
        message = f"{stamp}:{request.method}:{request.url.path}".encode()
        return hmac.compare_digest(signature, hmac.new(secret.encode(), message, hashlib.sha256).hexdigest())
    except (ValueError, TypeError):
        return False


class PolicyProfileEdit(BaseModel):
    revision_no: int = Field(ge=0)
    changes: dict = Field(default_factory=dict, max_length=140)
    program_changes: dict[str, dict] = Field(default_factory=dict, max_length=500)
    actor: str = Field(min_length=1, max_length=100)
    reason: str = Field(min_length=1, max_length=1000)


class ProgramProfileEdit(PolicyProfileEdit):
    mapping_revision_no: int = Field(ge=1)


class ProjectProfileEdit(BaseModel):
    progress: dict = Field(default_factory=dict, max_length=6)
    revision_no: int = Field(ge=0)
    mapping_revision_no: int = Field(ge=1)
    changes: dict = Field(default_factory=dict, max_length=20)
    mapping: dict | None = None
    schedules: dict = Field(default_factory=dict, max_length=6)
    approvals: dict = Field(default_factory=dict, max_length=6)
    actor: str = Field(min_length=1, max_length=100)
    reason: str = Field(min_length=1, max_length=1000)


class Review(BaseModel):
    policy_id: str = Field(max_length=80)
    revision_no: int = Field(ge=1)
    status: str = Field(pattern="^(CONFIRMED|REVIEW|RELEASED)$")
    basis: str = Field(min_length=1, max_length=2000)
    evidence_url: str = Field(min_length=10, max_length=2000)

class IdentityReview(BaseModel):
    project_id: str = Field(pattern=r"^HPR_[0-9a-f]{24}$")
    expected_project_id: str = Field(pattern=r"^HPR_[0-9a-f]{24}$")
    expected_status: str = Field(pattern="^(REVIEW|CONFIRMED|RELEASED)$")
    status: str = Field(pattern="^(REVIEW|CONFIRMED|RELEASED)$")
    basis: str = Field(min_length=5, max_length=2000)
    evidence_url: str = Field(min_length=10, max_length=2000)


class ProgramPolicyReview(BaseModel):
    policy_id: str = Field(max_length=80)
    revision_no: int = Field(ge=1)
    status: str = Field(pattern="^(CONFIRMED|REVIEW|RELEASED)$")
    basis: str = Field(min_length=1, max_length=2000)
    evidence_url: str = Field(min_length=10, max_length=2000)


class ProjectProgramReview(BaseModel):
    program_id: str = Field(max_length=36)
    revision_no: int = Field(ge=1)
    status: str = Field(pattern="^(CONFIRMED|REVIEW|RELEASED)$")
    basis: str = Field(min_length=1, max_length=2000)
    evidence_url: str = Field(min_length=10, max_length=2000)


class MappingDecision(BaseModel):
    action: str = Field(pattern="^(EXCLUDE|RESTORE)$")
    revision_no: int = Field(ge=0)
    actor: str = Field(min_length=1, max_length=100)
    reason: str = Field(min_length=1, max_length=1800)
    evidence_url: str = Field(default='', max_length=2000)
    policy_id: str = Field(default='POL_2025_0907', max_length=80)


class AnnualTarget(BaseModel):
    year: int = Field(ge=2000, le=2200)
    stage: str = Field(pattern="^(PLANNING|APPROVAL|CONSTRUCTION|SUPPLY|COMPLETION)$")
    units: int | None = Field(None, ge=0, le=10000000)
    basis: str = Field(min_length=1, max_length=500)
    evidence_url: str | None = Field(None, max_length=500)


class TargetPlan(BaseModel):
    revision_no: int = Field(ge=0)
    targets: list[AnnualTarget] = Field(max_length=31)

class DeliveryTarget(BaseModel):
    scope_kind: str = Field(pattern='^(policy|program|region|project)$')
    scope_id: str = Field(min_length=1,max_length=100)
    stage: str = Field(pattern='^(BUSINESS|APPROVAL|CONSTRUCTION|COMPLETION|SUPPLY|MOVE_IN)$')
    due_date: date
    units: int = Field(ge=0,le=1350000)
    origin: str = Field('MANUAL',pattern='^(MANUAL|SCENARIO|SOURCE_REVIEW)$')
    basis: str = Field(min_length=1,max_length=1000)
    evidence_url: str | None = Field(None,max_length=2000)

class DeliveryEvent(BaseModel):
    project_id: str = Field(min_length=1,max_length=100)
    stage: str = Field(pattern='^(BUSINESS|APPROVAL|CONSTRUCTION|COMPLETION|SUPPLY|MOVE_IN)$')
    event_date: date
    units: int | None = Field(None,ge=0,le=1350000)
    status: str = Field('ACTUAL',pattern='^(ACTUAL|DELAYED)$')
    basis: str = Field(min_length=1,max_length=1000)
    evidence_url: str = Field(min_length=10,max_length=2000)

class OccupancyObservation(BaseModel):
    region: str = Field(pattern='^(수도권|서울특별시)$')
    year: int = Field(ge=2025,le=2035)
    as_of_date: date
    units: int = Field(ge=0,le=1350000)
    evidence_url: str = Field(min_length=10,max_length=2000)
    basis: str = Field(min_length=1,max_length=2000)

class DeliverySettings(BaseModel):
    revision_no: int = Field(ge=0)
    targets: list[DeliveryTarget] = Field(default_factory=list,max_length=1000)
    events: list[DeliveryEvent] = Field(default_factory=list,max_length=1000)
    occupancy_observations: list[OccupancyObservation] | None = Field(None,max_length=200)


class StageEvidenceChoice(BaseModel):
    source_entity_id: str | None = Field(None,max_length=100)
    source_revision_no: int | None = None
    source_id: str | None = Field(None,max_length=100)
    source_name: str = Field('',max_length=500)
    stage: str | None = None
    evidence_url: str = Field(max_length=2000)
    units: int | None = Field(None,ge=0,le=1350000)
    event_date: date | None = None
    observed_on: date | None = None
    method: str = Field('MANUAL',pattern='^(EXACT|SIMILAR|OFFICIAL_DOCUMENT|STAGE_INFERENCE|PREREQUISITE|MANUAL)$')
    relation_type: str | None = Field(None,pattern='^(PART_OF_APPROVAL|PARTIAL_APPROVAL)$')
    source_units: int | None = Field(None,ge=0)
    scope_partial: bool = False
    scope_label: str | None = Field(None,max_length=300)
    event_type: str | None = Field(None,max_length=100)
    score: float | None = Field(None,ge=0,le=1)
    basis: str = Field('',max_length=2000)

class StageEvidenceReview(BaseModel):
    project_id: str = Field(max_length=100)
    stage: str = Field(pattern='^(BUSINESS|APPROVAL)$')
    revision_no: int = Field(ge=0)
    status: str = Field(pattern='^(REVIEW|CONFIRMED|RELEASED)$')
    selected: StageEvidenceChoice | None = None
    basis: str = Field(min_length=1,max_length=2000)



class ExecutionSchedule(BaseModel):
    project_id: str = Field(min_length=1,max_length=100)
    stage: str = Field(pattern='^(BUSINESS|APPROVAL|CONSTRUCTION|SUPPLY|COMPLETION|MOVE_IN)$')
    due_date: date
    units: int | None = Field(None,ge=0,le=1350000)
    status: str = Field('REVIEW',pattern='^(REVIEW|CONFIRMED|RELEASED)$')
    origin: str = Field('MANUAL',pattern='^(MANUAL|SOURCE_REVIEW)$')
    responsible_org: str = Field(min_length=1,max_length=200)
    basis: str = Field(min_length=1,max_length=2000)
    evidence_url: str | None = Field(None,max_length=2000,pattern='^https://')
    change_reason: str = Field('',max_length=2000)

class ExecutionCase(BaseModel):
    project_id: str = Field(min_length=1,max_length=100)
    stage: str = Field(pattern='^(BUSINESS|APPROVAL|CONSTRUCTION|SUPPLY|COMPLETION|MOVE_IN)$')
    units: int | None = Field(None,ge=0,le=1350000)
    cause: str = Field(pattern='^(PERMIT|COMPENSATION|INFRASTRUCTURE|FINANCE|COORDINATION|OTHER)$')
    status: str = Field('OPEN',pattern='^(OPEN|IN_PROGRESS|RESOLVED)$')
    responsible_org: str = Field(min_length=1,max_length=200)
    cooperating_orgs: list[str] = Field(default_factory=list,max_length=20)
    action: str = Field(min_length=1,max_length=2000)
    due_date: date
    basis: str = Field(min_length=1,max_length=2000)
    evidence_url: str | None = Field(None,max_length=2000,pattern='^https://')
    resolution: str = Field('',max_length=2000)

class ExecutionAgency(BaseModel):
    project_id: str = Field(min_length=1,max_length=100)
    stage: str = Field(pattern='^(BUSINESS|APPROVAL|CONSTRUCTION|SUPPLY|COMPLETION|MOVE_IN)$')
    due_date: date
    units: int = Field(ge=0,le=1350000)
    status: str = Field('REVIEW',pattern='^(REVIEW|CONFIRMED|RELEASED)$')
    responsible_org: str = Field(min_length=1,max_length=200)
    cooperating_orgs: list[str] = Field(default_factory=list,max_length=20)
    approving_org: str = Field('',max_length=200)
    basis: str = Field(min_length=1,max_length=2000)
    evidence_url: str | None = Field(None,max_length=2000,pattern='^https://')
    change_reason: str = Field('',max_length=2000)


class ScenarioAdjustment(BaseModel):
    project_id: str = Field(min_length=1,max_length=100)
    stage: str = Field(pattern='^(BUSINESS|APPROVAL|CONSTRUCTION|SUPPLY|COMPLETION|MOVE_IN)$')
    months: int = Field(ge=-60,le=120)

class ExecutionScenario(BaseModel):
    name: str = Field(min_length=1,max_length=200)
    basis: str = Field(min_length=1,max_length=2000)
    adjustments: list[ScenarioAdjustment] = Field(default_factory=list,max_length=200)

class ExecutionSave(BaseModel):
    key: str = Field(min_length=1,max_length=140)
    revision_no: int = Field(ge=0)
    values: dict

class CollectionAssessment(BaseModel):
    project_id: str = Field(min_length=1,max_length=100)
    stage: str = Field(pattern='^(POLICY|BUSINESS|APPROVAL|CONSTRUCTION|SUPPLY|MOVE_IN)$')
    revision_no: int = Field(ge=0)
    status: str = Field(pattern='^(NOT_PLANNED|METHOD_UNKNOWN|COLLECTION_REQUIRED|RELEASED)$')
    basis: str = Field(min_length=1,max_length=2000)


class EvidenceBridgeReview(BaseModel):
    link_id: str = Field(min_length=1,max_length=80)
    revision_no: int = Field(ge=1)
    status: str = Field(pattern='^(REVIEW|CONFIRMED|RELEASED)$')
    basis: str = Field(min_length=1,max_length=2000)


class SnapshotRequest(BaseModel):
    actor: str = Field(min_length=1,max_length=100)
    reason: str = Field(min_length=1,max_length=1000)
    known_at: datetime | None = None


def create_app(engine=None, auto_collect=None):
    from .facility_details import FacilityDetails
    facility_details=FacilityDetails()
    service = HomeService(engine or engine_for(), os.environ.get("POC10_DATA_DIR", str(ROOT / "data")))
    from .projection_cache import delivery_projection_version, delivery_screen_projection_version
    projection_builds = threading.BoundedSemaphore(2)
    # These wrappers call another cached endpoint/input. Only their inner
    # builders acquire the gate, so nested misses cannot exhaust both slots.
    nested_projections = {'project_information','housing_indicators','delivery_view','requirements_status'}
    delivery_cache = ProjectionCache(lambda: delivery_projection_version(service), build_guard=projection_builds)
    delivery_screen_input = ProjectionCache(lambda: delivery_screen_projection_version(service), max_entries=2, build_guard=projection_builds)
    indicator_input_cache = ProjectionCache(lambda: delivery_projection_version(service), max_entries=4, build_guard=projection_builds)
    read_caches = {name: ProjectionCache(lambda: projection_version(service), build_guard=None if name in nested_projections else projection_builds)
                   for name in ('overview', 'policy_metrics', 'supply_dashboard', 'map', 'project_collection', 'requirements_status', 'policy_monitor', 'mappings', 'tree', 'source_year_coverage', 'mapping_workbench', 'history', 'geometry', 'schematic', 'annual_supply', 'area_context', 'area_outlook', 'execution_insights', 'unsold', 'housing_indicators', 'project_workspace', 'project_locations', 'project_information', 'source_summary','delivery_view')}
    from .projection_cache import collection_projection_version, workspace_projection_version, requirements_projection_version
    for name in ('project_collection','project_information','project_locations','policy_monitor','mappings','mapping_workbench'):
        read_caches[name] = ProjectionCache(lambda: collection_projection_version(service), build_guard=None if name in nested_projections else projection_builds)
    read_caches['requirements_status'] = ProjectionCache(lambda: requirements_projection_version(service))
    read_caches['project_workspace'] = ProjectionCache(lambda: workspace_projection_version(service), build_guard=projection_builds)
    for name in ('housing_indicators', 'area_context', 'area_outlook','delivery_view'):
        read_caches[name] = ProjectionCache(lambda: delivery_projection_version(service), build_guard=None if name in nested_projections else projection_builds)
    read_caches['delivery_view'] = ProjectionCache(lambda:delivery_screen_projection_version(service))
    read_caches['policy_metrics'] = ProjectionCache(lambda:delivery_screen_projection_version(service),build_guard=projection_builds)
    def cached_json(name, parameters, build):
        # Relative "today" queries must not reuse yesterday's projection.
        body, status = read_caches[name].get((today(),tuple(sorted(parameters.items()))), build)
        return Response(body, media_type='application/json', headers={'X-Home-Cache': status})

    enabled = auto_collect if auto_collect is not None else os.environ.get("POC10_AUTO_COLLECT", "true").lower() == "true"
    stop = threading.Event()

    def collect_loop():
        from .collection_jobs import enqueue_due
        while not stop.is_set():
            try:
                enqueue_due(service)
            except Exception:
                # Connectivity errors are reflected by /health, never leak credentials.
                pass
            stop.wait(60)

    def collection_worker(lane):
        from .collection_jobs import run_next
        while not stop.is_set():
            try:
                result=run_next(service,lane)
            except Exception:
                result=None
            stop.wait(1 if result else 10)

    @asynccontextmanager
    async def lifespan(app):
        service.recover_interrupted_batches()
        service.reconcile_program_links()
        service.propose_program_policies()
        reconcile_identity_links(service)
        if enabled:
            threading.Thread(target=collect_loop, name="home-collector", daemon=True).start()
            for lane in ('LATEST','BACKFILL'):
                threading.Thread(target=collection_worker, args=(lane,), name=f'home-source-worker-{lane}', daemon=True).start()
        yield
        stop.set()

    app = FastAPI(title="HOME", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
    app.state.service = service
    building_context = BuildingContext()
    infrastructure_context = InfrastructureContext()
    app.add_middleware(GZipMiddleware, minimum_size=16384, compresslevel=4)

    @app.get(PREFIX + '/api/view-version')
    def view_version(view: str = Query(...,pattern='^(projects|policy-progress|program-progress)$')):
        version = collection_projection_version(service) if view=='projects' else delivery_screen_projection_version(service)
        return dict(version=hashlib.sha256(repr((today(),version)).encode()).hexdigest())

    @app.get(PREFIX + '/api/data-integrity')
    def integrity_rounds():
        from .data_integrity import rounds
        return rounds(service)

    @app.get(PREFIX + '/api/data-integrity/diagnostics')
    def integrity_diagnostics():
        from .db import IntegrityRound
        from sqlalchemy import select
        with service.sessions() as db:
            row=db.scalar(select(IntegrityRound).order_by(IntegrityRound.sequence.desc()).limit(1))
            return dict(round_id=row.id if row else None,diagnostics=row.result.get('diagnostics') if row else None,
                        note='선택 회차 평가 시점의 고정 재대조 결과. 기준시각 이후 원천 변화는 다음 평가에서 반영.')

    @app.get(PREFIX + '/api/data-integrity/construction-audit')
    def construction_audit():
        from .construction_audit import latest
        return latest(service)

    @app.get(PREFIX + '/api/data-integrity/rounds/{identity}/report.md')
    def integrity_markdown(identity: str):
        from .data_integrity import get_round
        try: record = get_round(service, identity)
        except ValueError: raise HTTPException(404, '성적표가 없습니다') from None
        body = record['result'].get('report_markdown') if record else None
        if not body: raise HTTPException(404, '보고서가 없습니다')
        return Response(body, media_type='text/markdown; charset=utf-8',
            headers={'Content-Disposition':'attachment; filename="THE_JUTAEK_FIRST_ASSESSMENT_20261022.md"'})

    @app.get(PREFIX + '/api/data-integrity/rounds/{identity}/report.html')
    def integrity_report(identity: str):
        from .data_integrity import get_round
        try:
            return Response(get_round(service,identity,html=True),media_type='text/html')
        except ValueError as error:
            raise HTTPException(404,str(error))

    @app.get(PREFIX + '/api/data-integrity/rounds/{identity}')
    def integrity_detail(identity: str):
        from .data_integrity import get_round
        try:return get_round(service,identity)
        except ValueError as error:raise HTTPException(404,str(error))

    @app.get(PREFIX + '/api/independent-snapshots/{identity}')
    def independent_snapshot(identity: str):
        from .independent_metrics import get_snapshot
        try:return get_snapshot(service,identity)
        except ValueError as error:raise HTTPException(404,str(error))

    @app.get(PREFIX + '/api/independent-snapshots/{identity}/events.csv')
    def independent_snapshot_csv(identity: str):
        from .independent_metrics import get_snapshot
        try:data=get_snapshot(service,identity)
        except ValueError as error:raise HTTPException(404,str(error))
        output=io.StringIO();writer=csv.writer(output)
        keys=('event_id','project_id','name','event_type','event_date','quantity','quantity_scope','source_revision_id','source_payload_hash','evidence_url')
        writer.writerow(('snapshot_id','known_at',*keys))
        for event in data['result']['selected_events']:
            values=[str(event.get(k,'')) for k in keys]
            writer.writerow([data['id'],data['known_at'],*["'"+v if v.startswith(('=','+','-','@')) else v for v in values]])
        return Response('\ufeff'+output.getvalue(),media_type='text/csv',headers={'Content-Disposition':f'attachment; filename="HOME-{identity}-events.csv"'})

    @app.get(PREFIX + '/api/independent-metrics')
    def independent_metrics():
        from .db import MetricSnapshot
        from sqlalchemy import select
        from .independent_metrics import get_snapshot
        with service.sessions() as db:
            identity=db.scalar(select(MetricSnapshot.id).order_by(MetricSnapshot.known_at.desc()).limit(1))
        return get_snapshot(service,identity) if identity else dict(id=None,note='집계 기준본 생성 전입니다')

    @app.get(PREFIX + '/api/collection-jobs')
    def collection_jobs():
        from .collection_jobs import status
        return dict(items=status(service))

    @app.post(PREFIX + '/api/admin/independent-snapshots')
    def create_snapshot(request: Request, payload: SnapshotRequest):
        if not authenticated(request):raise HTTPException(403,'관리자 인증이 필요합니다')
        from .independent_metrics import freeze
        try:return freeze(service,**payload.model_dump())
        except ValueError as error:raise HTTPException(422,str(error))

    @app.middleware("http")
    async def headers(request, call_next):
        private_integrity=request.url.path==PREFIX+'/api/data-integrity' or request.url.path.startswith(PREFIX+'/api/data-integrity/')
        if private_integrity and not authenticated(request):
            response=Response(json.dumps({'detail':'관리자 로그인이 필요합니다.'},ensure_ascii=False),status_code=401,media_type='application/json')
        else:
            response = await call_next(request)
        response.headers["Cache-Control"] = ("public, max-age=3600" if "/api/tiles/" in request.url.path and response.status_code==200
                                            else "no-store" if "/api/" in request.url.path else "no-cache")
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self'; worker-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'self'; base-uri 'self'; form-action 'self'"
        if request.url.path.startswith(PREFIX+'/api/data-integrity/rounds/') and request.url.path.endswith('/report.html'):
            response.headers['Content-Security-Policy']="default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data:; frame-ancestors 'self'; base-uri 'none'; form-action 'none'"
        if request.url.path.startswith(PREFIX+'/integrity-documents/'):
            response.headers['Content-Security-Policy']="default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data:; frame-ancestors 'self'; base-uri 'none'; form-action 'none'"
        return response

    @app.get("/health")
    def health():
        with service.engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return {"status": "ok", "service": "home", "scope": "SEOUL_GYEONGGI"}

    @app.api_route(PREFIX, methods=["GET", "HEAD"])
    @app.api_route(PREFIX + "/", methods=["GET", "HEAD"])
    def index():
        return FileResponse(ROOT / "web" / "index.html", media_type="text/html")

    app.mount(PREFIX + "/assets", StaticFiles(directory=ROOT / "web" / "assets"), name="assets")

    def filters(as_of_date: date | None = None, region: str | None = Query(None, max_length=30),
                policy_id: str | None = Query(None, max_length=80), source_id: str | None = Query(None, max_length=40),
                stage: str | None = Query(None, max_length=30), q: str | None = Query(None, max_length=100),
                mapping_status: str | None = Query(None, pattern="^(REVIEW|CONFIRMED|RELEASED)$")):
        if as_of_date and as_of_date > today():
            raise HTTPException(400, "미래 기준일은 조회할 수 없습니다.")
        if region and region not in {"서울특별시", "경기도", "인천광역시"}:
            raise HTTPException(400, "조회 범위는 수도권입니다.")
        return dict(as_of=as_of_date, region=region, policy_id=policy_id, source_id=source_id, stage=stage, q=q, mapping_status=mapping_status)

    from fastapi import Depends

    @app.get(PREFIX + "/api/overview")
    def overview(f=Depends(filters)):
        return cached_json('overview', f, lambda: service.overview(**f))

    @app.get(PREFIX + "/api/roadmap")
    def roadmap(f=Depends(filters), horizon: int = Query(10, ge=1, le=10)):
        return service.roadmap(horizon=horizon, **f)

    @app.get(PREFIX + "/api/history")
    def historical_data(f=Depends(filters),history_year:int|None=Query(None,ge=2010,le=2100),
                        page:int=Query(1,ge=1),page_size:int=Query(100,ge=1,le=200)):
        return cached_json('history', dict(f, year=history_year, page=page, page_size=page_size), lambda: service.historical_data(year=history_year,page=page,page_size=page_size,**f))

    @app.get(PREFIX + "/api/history/export.csv")
    def history_export(f=Depends(filters),history_year:int|None=Query(None,ge=2010,le=2100)):
        fields=['name','region','district','block','report_date','report_period','date_precision',
                'progress_pct','progress_date_basis','source_registration_date','source_filename',
                'construction_description','planned_units','current_project_id','source_id','evidence_url','recorded_at']
        buffer=io.StringIO()
        writer=csv.DictWriter(buffer,fieldnames=fields)
        writer.writeheader()
        page=1
        while True:
            data=service.historical_data(year=history_year,page=page,page_size=200,**f)
            for row in data['reports']:
                writer.writerow({k:"'"+v if isinstance(v,str) and v.lstrip().startswith(('=','+','-','@')) else v
                                 for k in fields for v in [row.get(k)]})
            if page*200>=data['report_total']:break
            page+=1
        return Response('\ufeff'+buffer.getvalue(),media_type='text/csv; charset=utf-8',
                        headers={'Content-Disposition':f'attachment; filename="home-progress-{history_year or "all"}.csv"'})

    @app.get(PREFIX + "/api/map/buildings")
    def map_buildings(block_id: str | None = Query(None, min_length=4, max_length=150), project_id: str | None = Query(None, min_length=4, max_length=150)):
        try:
            if bool(block_id)==bool(project_id):raise ValueError('사업 또는 블록 중 하나를 선택하세요')
            if project_id:
                from .project_locations import resolve_anchor
                project=next((p for p in service.projects(policy_id='POL_2025_0907') if p['id']==project_id),None)
                if project is None:raise ValueError('연결된 사업을 찾을 수 없습니다')
                anchor=resolve_anchor(project,json.loads(project_locations().body))
                if not anchor:raise ValueError('확보된 대표 위치가 없습니다')
                return building_context.get(project_id,service,anchor)
            return building_context.get(block_id, service)
        except ValueError as error:
            raise HTTPException(422, str(error)) from None
        except RuntimeError:
            raise HTTPException(503, "공식 건물 공간정보 연결 확인 필요") from None

    @app.get(PREFIX + "/api/map/infrastructure")
    def map_infrastructure(block_id: str | None = Query(None, min_length=4, max_length=150),project_id: str | None = Query(None,min_length=4,max_length=150)):
        try:
            if bool(block_id)==bool(project_id):raise ValueError('사업 또는 블록 중 하나를 선택하세요')
            if project_id:
                from .project_locations import resolve_anchor
                project=next((p for p in service.projects(policy_id='POL_2025_0907') if p['id']==project_id),None)
                if project is None:raise ValueError('연결된 사업을 찾을 수 없습니다')
                anchor=resolve_anchor(project,json.loads(project_locations().body))
                if not anchor:raise ValueError('확보된 대표 위치가 없습니다')
                return infrastructure_context.get(project_id,service,anchor)
            return infrastructure_context.get(block_id, service)
        except ValueError as error:
            raise HTTPException(422, str(error)) from None
        except RuntimeError:
            raise HTTPException(503, "공식 주변 시설 연결 확인 필요") from None

    @app.get(PREFIX + "/api/map/facility-details")
    def map_facility_details(place_id: str = Query(min_length=1,max_length=150), kind: str = Query(pattern="^(school|childcare|bus|subway|hospital|mart)$"),
            block_id: str | None = Query(None,min_length=4,max_length=150),project_id: str | None = Query(None,min_length=4,max_length=150)):
        # IDs are resolved against the selected location's public POIs; callers cannot supply URLs.
        data=map_infrastructure(block_id,project_id)
        place=next((p for p in data['items'] if p['id']==place_id and p['kind']==kind),None)
        if place is None:raise HTTPException(404,'선택 위치의 시설을 찾을 수 없습니다')
        return facility_details.get(place,service)

    @app.get(PREFIX + "/api/map/dashboard")
    def supply_dashboard(f=Depends(filters),analysis_year:int|None=Query(None,ge=2010,le=2100),
                         horizon:int=Query(10,ge=1,le=10),measure:str=Query("SUPPLY",pattern="^(SUPPLY|MOVE_IN|COMPLETION)$"),
                         compact:bool=False,
                         schedule_status:str=Query("all",pattern="^(all|future|missing|past|manual)$")):
        if analysis_year and analysis_year>(f["as_of"] or today()).year:
            raise HTTPException(422,"자료 연도는 조회 기준연도 이하여야 합니다")
        parameters=dict(f,analysis_year=analysis_year,horizon=horizon,measure=measure,schedule_status=schedule_status)
        def build():
            data=service.supply_dashboard(**parameters)
            if compact:
                # The supply map uses basemap tiles and location markers. Keep
                # full official polygons for geometry clients, not marker views.
                from .supply_dashboard import marker_view
                data=marker_view(data)
            return data
        return cached_json('supply_dashboard',dict(parameters,compact=compact),build)

    @app.get(PREFIX + "/api/policy-geo/geometry")
    def policy_geo_geometry(as_of_date: date | None = None):
        if as_of_date and as_of_date > today():
            raise HTTPException(400, "미래 기준일은 조회할 수 없습니다.")
        return cached_json('geometry', dict(as_of=as_of_date), lambda: geometry_view(service.supply_dashboard(as_of=as_of_date, policy_id='POL_2025_0907', horizon=1, measure='SUPPLY')))

    @app.get(PREFIX + "/api/policy-geo/schematic")
    def policy_geo_schematic(as_of_date: date | None = None):
        if as_of_date and as_of_date > today():
            raise HTTPException(400, "미래 기준일은 조회할 수 없습니다.")
        return cached_json('schematic', dict(as_of=as_of_date), lambda: schematic_view(service.supply_dashboard(as_of=as_of_date, policy_id='POL_2025_0907', horizon=1, measure='SUPPLY')))

    @app.get(PREFIX + "/api/policy-geo/metrics")
    def policy_geo_metrics(as_of_date: date | None = None,
                           analysis_year: int | None = Query(None, ge=2010, le=2100),
                           measure: str = Query("SUPPLY", pattern="^(SUPPLY|MOVE_IN|COMPLETION)$")):
        day = as_of_date or today()
        if day > today():
            raise HTTPException(400, "미래 기준일은 조회할 수 없습니다.")
        if analysis_year and analysis_year > day.year:
            raise HTTPException(422, "자료 연도는 조회 기준연도 이하여야 합니다")
        return cached_json('policy_metrics', dict(day=day, year=analysis_year, measure=measure),
            lambda: metrics_view(service.supply_dashboard(as_of=day, policy_id='POL_2025_0907', analysis_year=analysis_year,
                                                          horizon=5, measure=measure)))

    from .area_snapshot import SnapshotStore
    area_snapshots=SnapshotStore(service)

    def area_snapshot_response(payload,snapshot):
        return Response(json.dumps(payload,ensure_ascii=False,separators=(',',':')),media_type='application/json',
            headers={'X-Home-Cache':'AREA_SNAPSHOT','X-Home-Snapshot-At':snapshot['generated_at']})

    @app.get(PREFIX + '/api/area-dashboard')
    def area_dashboard_api(region:str=Query(...,pattern='^(서울특별시|경기도|인천광역시)$'),
                           municipality:str|None=Query(None,max_length=30),year:int|None=Query(None,ge=2018,le=2100)):
        year=year or today().year
        if year>today().year:raise HTTPException(422,'자료 연도는 현재 연도 이하여야 합니다')
        try:data=area_snapshots.bundle(region,municipality,year)
        except ValueError as error:raise HTTPException(422,str(error)) from None
        if data is None:raise HTTPException(503,'지역 자료를 처음 준비하고 있습니다. 잠시 후 다시 조회합니다.',headers={'Retry-After':'5'})
        return area_snapshot_response(data,data['snapshot'])

    @app.get(PREFIX + "/api/area-places")
    def area_places_api():
        from .area_stats import area_places
        snapshot=area_snapshots.read(today().year)
        return snapshot['places'] if snapshot else area_places(service)

    @app.get(PREFIX + '/api/unsold')
    def unsold_context(region:str=Query(...,pattern='^(서울특별시|경기도|인천광역시)$'),
                       municipality:str|None=Query(None,max_length=30),as_of_date:date|None=None):
        from .unsold import context
        reference=as_of_date or today()
        if reference>today():raise HTTPException(422,'미래 기준일은 조회할 수 없습니다')
        return cached_json('unsold',{'region':region,'municipality':municipality,'as_of':reference.isoformat()},
                           lambda:context(service,region,municipality,reference))

    @app.get(PREFIX + "/api/area-context")
    def area_context_api(region:str=Query(...,pattern="^(서울특별시|경기도|인천광역시)$"),
                         municipality:str|None=Query(None,max_length=30),year:int|None=Query(None,ge=2018,le=2100)):
        from .area_stats import area_context
        if year and year>today().year:
            raise HTTPException(422,"자료 연도는 현재 연도 이하여야 합니다")
        snapshot=area_snapshots.read(year or today().year)
        if snapshot and (municipality or '') in snapshot['contexts'].get(region,{}):
            return area_snapshot_response(snapshot['contexts'][region][municipality or ''],snapshot)
        try:
            return cached_json('area_context', dict(region=region, municipality=municipality, year=year or today().year), lambda: area_context(service,region,municipality,year or today().year))
        except ValueError as error:
            raise HTTPException(422,str(error)) from None

    @app.get(PREFIX + "/api/area-outlook")
    def area_outlook_api(region:str=Query(...,pattern="^(서울특별시|경기도|인천광역시)$")):
        from .area_outlook import area_outlook
        snapshot=area_snapshots.read(today().year)
        if snapshot and region in snapshot['outlooks']:return area_snapshot_response(snapshot['outlooks'][region],snapshot)
        return cached_json('area_outlook', dict(region=region), lambda: area_outlook(service,region))

    @app.get(PREFIX + "/api/annual-supply")
    def annual_supply_api(region:str|None=Query(None,max_length=30),
                          through_year:int|None=Query(None,ge=2018,le=2100)):
        from .annual_supply import annual_supply,REGIONS
        if region and region not in REGIONS:raise HTTPException(422,"지원하지 않는 시도")
        if through_year and through_year>today().year:
            raise HTTPException(422,"미래 연도는 조회할 수 없습니다")
        snapshot=area_snapshots.read(through_year or today().year)
        if snapshot and region in snapshot['annual']:return area_snapshot_response(snapshot['annual'][region],snapshot)
        return cached_json('annual_supply', dict(region=region, year=through_year or today().year), lambda: annual_supply(service,region,through_year or today().year))

    @app.get(PREFIX + "/api/annual-supply/export.csv")
    def annual_supply_export(region:str|None=Query(None,max_length=30),
                             through_year:int|None=Query(None,ge=2018,le=2100)):
        from .annual_supply import annual_supply,annual_supply_csv,REGIONS
        if region and region not in REGIONS:raise HTTPException(422,"지원하지 않는 시도")
        if through_year and through_year>today().year:
            raise HTTPException(422,"미래 연도는 조회할 수 없습니다")
        data=annual_supply(service,region,through_year or today().year)
        return Response(annual_supply_csv(data),media_type="text/csv; charset=utf-8",
                        headers={"Content-Disposition":'attachment; filename="home-annual-supply.csv"'})

    @app.get(PREFIX + "/api/map/supply.csv")
    def supply_export(f=Depends(filters),analysis_year:int|None=Query(None,ge=2010,le=2100),
                      horizon:int=Query(10,ge=1,le=10),measure:str=Query("SUPPLY",pattern="^(SUPPLY|MOVE_IN|COMPLETION)$"),
                      schedule_status:str=Query("all",pattern="^(all|future|missing|past|manual)$"),
                      group_by:str=Query("all",pattern="^(all|policy|program|region)$"),group_id:str|None=Query(None,max_length=200)):
        from .supply_export import supply_csv
        if analysis_year and analysis_year>(f["as_of"] or today()).year:
            raise HTTPException(422,"자료 연도는 조회 기준연도 이하여야 합니다")
        data=service.supply_dashboard(analysis_year=analysis_year,horizon=horizon,measure=measure,schedule_status=schedule_status,**f)
        if group_id and (group_by=="all" or not any(row["id"]==group_id for row in data["groups"][group_by])):
            raise HTTPException(422,"조회 결과에 없는 그룹입니다")
        return Response(supply_csv(data,group_by,group_id),media_type="text/csv; charset=utf-8",
                        headers={"Content-Disposition":f'attachment; filename="home-supply-{data["analysis_year"]}.csv"'})

    @app.get(PREFIX + "/api/map")
    def map_data(f=Depends(filters)):
        return cached_json('map',f,lambda:service.map_data(**f))

    @app.get(PREFIX + "/api/tiles/{z}/{x}/{y}.png")
    def map_tile(z:int,x:int,y:int):
        try:
            return Response(tile(z,x,y),media_type="image/png")
        except ValueError:
            raise HTTPException(503,"배경지도 조회 조건·연결을 확인하세요") from None

    @app.get(PREFIX + "/api/roadmap/export.csv")
    def roadmap_export(f=Depends(filters), horizon: int = Query(10, ge=1, le=10),
                       target_filter: str = Query("all",pattern="^(all|future|missing|past|manual)$"),
                       target_year: int | None = Query(None,ge=2000,le=2200)):
        fields = ["id","name","region","source_id","stage_label","progress_pct","progress_report_date","planned_units","base_date","move_in_start_date","move_in_start_precision",
                  "year","year_offset","target_stage","target_origin","target_units","target_month","target_basis","status","evidence_url"]
        buffer=io.StringIO()
        writer=csv.DictWriter(buffer,fieldnames=fields)
        writer.writeheader()
        for row in service.roadmap(horizon=horizon,**f)["items"]:
            if ((target_filter=="future" and not row["has_future_target"]) or (target_filter=="missing" and row["has_any_target"])
                or (target_filter=="past" and not row["past_due_count"]) or (target_filter=="manual" and not row["manual_count"])
                or (target_year and not any(annual["year"]==target_year and annual["events"] for annual in row["annual"]))):
                continue
            for annual in row["annual"]:
                for event in annual["events"] or [{}]:
                    item={key:row.get(key) for key in fields}
                    item.update(progress_report_date=(row.get("construction_progress") or {}).get("as_of_date"),
                                move_in_start_date=(row.get("move_in_start") or {}).get("date"),
                                move_in_start_precision=(row.get("move_in_start") or {}).get("precision"))
                    item.update(year=annual["year"],year_offset=annual["offset"],target_stage=event.get("stage"),
                                target_origin=event.get("origin"),target_units=event.get("units"),target_month=event.get("month"),
                                target_basis=event.get("basis"),status=annual["status"],evidence_url=event.get("evidence_url"))
                    writer.writerow({key:"'"+value if isinstance(value,str) and value.startswith(("=","+","-","@")) else value
                                     for key,value in item.items()})
        return Response("\ufeff"+buffer.getvalue(),media_type="text/csv; charset=utf-8",
                        headers={"Content-Disposition":'attachment; filename="home-annual-targets.csv"'})

    @app.get(PREFIX + "/api/projects")
    def projects(f=Depends(filters), page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200)):
        rows = service.projects(**f)
        return {"items": rows[(page - 1) * page_size:page * page_size], "total": len(rows), "page": page, "page_size": page_size}

    @app.get(PREFIX + '/api/project-workspace')
    def project_workspace():
        def build():
            from .read_scope import projection_reads
            with projection_reads():
                keys=('id','name','region','municipality','mapping','planned_units')
                projects=service.projects()
                return dict(items=[{k:p.get(k) for k in keys} for p in projects if p['mapping']['policy_id']=='POL_2025_0907' and p['mapping']['status'] not in ('RELEASED','REJECTED')],
                            programs=[p for p in service.program_links(projects=projects) if p['policy_id']=='POL_2025_0907' and p['status'] not in ('RELEASED','REJECTED')],
                            policies=[p for p in service.mapping_policies() if p.get('monitor_kind')=='POLICY'])
        return cached_json('project_workspace',{},build)

    @app.get(PREFIX + '/api/project-locations')
    def project_locations():
        def build():
            data=service.supply_dashboard(policy_id='POL_2025_0907')
            keys=('id','name','project_ids','latitude','longitude','coordinate_basis','location_evidence_url','evidence_url')
            return {kind:[{k:r.get(k) for k in keys} for r in data[kind]] for kind in ('blocks','municipalities')}
        return cached_json('project_locations',{},build)

    @app.get(PREFIX + '/api/project-information/{project_id}')
    def project_information(project_id: str):
        from .project_profile import view
        from .project_collection import collection_matrix
        from .read_scope import projection_reads
        def build():
            with projection_reads():
                matrix=collection_matrix(service,policy_id='POL_2025_0907',project_ids=(project_id,),include_link_history=False)
                return view(service,project_id,matrix,json.loads(project_locations().body))
        try: return cached_json('project_information',{'project_id':project_id},build)
        except ValueError as error:raise HTTPException(404,str(error)) from None

    @app.post(PREFIX + '/api/admin/project-information/{project_id}')
    def project_information_save(project_id: str,payload: ProjectProfileEdit,request: Request):
        if not authenticated(request):raise HTTPException(401,'관리자 로그인이 필요합니다')
        from .project_profile import save
        try:result=save(service,project_id,**payload.model_dump())
        except (ValueError,TypeError) as error:raise HTTPException(422,str(error)) from None
        if result.get('conflict'):raise HTTPException(409,'사업 또는 연결 근거가 변경됐습니다. 다시 조회하세요')
        return result

    @app.get(PREFIX + "/api/projects/{project_id}")
    def detail(project_id: str, f=Depends(filters)):
        result = service.detail(project_id, f["as_of"])
        if not result:
            raise HTTPException(404, "사업을 찾을 수 없습니다.")
        return result

    @app.get(PREFIX + "/api/projects/{project_id}/targets")
    def targets(project_id: str, f=Depends(filters)):
        result=service.targets(project_id,f["as_of"])
        if result is None:
            raise HTTPException(404,"사업을 찾을 수 없습니다.")
        return result

    @app.get(PREFIX + "/api/policies")
    def policies(f=Depends(filters)):
        return {"items": service.mapping_policies(f["as_of"])}

    @app.get(PREFIX + "/api/policy-monitor")
    def policy_monitor(f=Depends(filters)):
        return cached_json('policy_monitor', f, lambda: service.policy_monitor(**f))

    @app.get(PREFIX + '/api/policy-delivery')
    def policy_delivery(as_of_date: date | None = None, compact: bool = False):
        day=as_of_date or today()
        if day>today():raise HTTPException(422,'미래 실제 기준일은 조회할 수 없습니다')
        body, status = delivery_cache.get((day.isoformat(), compact),
            lambda: build_delivery(service, day, include_portfolio_comparisons=not compact))
        return Response(body, media_type='application/json',
                        headers={'X-Home-Cache': status, 'Cache-Control': 'no-cache'})

    @app.get(PREFIX + '/api/policy-delivery/view')
    def policy_delivery_view(as_of_date: date | None = None,group: str = Query('policy',max_length=150),scope: str | None = Query(None,max_length=300),report: bool = False):
        from .policy_delivery_view import screen_view, policy_report_view
        day=as_of_date or today()
        if day>today():raise HTTPException(422,'미래 실제 기준일은 조회할 수 없습니다')
        if report:
            if group != 'policy':raise HTTPException(422,'정책 보고서만 지원합니다')
            try:return cached_json('delivery_view',dict(day=day,group=group,scope=scope,report=True),lambda:policy_report_view(service,day,scope))
            except ValueError as error:raise HTTPException(422,str(error)) from None
        def build():
            body,_=delivery_screen_input.get(day.isoformat(),lambda:build_delivery(service,day,comparison_scopes=()))
            return screen_view(json.loads(body),group,scope,report=report)
        try:return cached_json('delivery_view',dict(day=day,group=group,scope=scope,report=report),build)
        except ValueError as error:raise HTTPException(422,str(error)) from None

    @app.get(PREFIX + '/api/housing-indicators')
    def housing_indicators_api(kind: str = Query('policy',pattern='^(policy|program|project)$'),
            scope_id: str = Query('POL_2025_0907',min_length=4,max_length=150),
            region: str | None = Query(None,pattern='^(서울특별시|경기도|인천광역시)$'),
            municipality_id: str | None = Query(None,min_length=2,max_length=100),
            as_of_date: date | None = None,year: int | None = Query(None,ge=2018,le=2100),
            baseline_years: int = Query(3,ge=3,le=10),portfolio:bool=False):
        from .housing_indicators import housing_indicators
        day=as_of_date or today()
        if day>today() or year and year>day.year+10 or baseline_years not in (3,5,10):raise HTTPException(422,'비교 기간 또는 기준일을 확인하세요')
        parameters=dict(kind=kind,scope_id=scope_id,reference=day,region=region,municipality_id=municipality_id,year=year or day.year,baseline_years=baseline_years,portfolio=portfolio)
        def build():
            body,_=indicator_input_cache.get(day.isoformat(),lambda:build_delivery(service,day,include_portfolio_comparisons=False,indicators_only=True))
            return housing_indicators(service,json.loads(body),**parameters)
        try:return cached_json('housing_indicators',parameters,build)
        except ValueError as error:raise HTTPException(422,str(error)) from None

    @app.get(PREFIX + '/api/map/progress')
    def map_progress(project_ids: list[str] = Query(default=[]), as_of_date: date | None = None,
                     region: str | None = None, program_id: str | None = None, level: str = 'block'):
        from .map_progress import build_progress
        day = as_of_date or today()
        if day > today() or len(project_ids) > 1000:
            raise HTTPException(422, '기준일 또는 조회 사업 범위를 확인하세요')
        body, _ = delivery_cache.get((day.isoformat(), True),
            lambda: build_delivery(service, day, include_portfolio_comparisons=False))
        model=json.loads(body)
        if model.get('status') != 'READY':
            return dict(status=model.get('status'), as_of_date=day.isoformat(), notice=model.get('notice', '해당 기준일 자료 미확보'))
        return build_progress(model, project_ids, region, program_id, level)

    @app.get(PREFIX + '/api/policy-information')
    def policy_information(request: Request):
        if not authenticated(request): raise HTTPException(401, 'MinsLab 관리자 로그인이 필요합니다')
        from .policy_profile import view
        body, _ = delivery_cache.get((today().isoformat(), True),
            lambda: build_delivery(service, today(), include_portfolio_comparisons=False))
        model = json.loads(body)
        if model.get('status') != 'READY': raise HTTPException(409, '정책 원문 수집이 필요합니다')
        return view(service, model)

    @app.post(PREFIX + '/api/admin/policy-information')
    def policy_information_save(payload: PolicyProfileEdit, request: Request):
        if not authenticated(request): raise HTTPException(401, 'MinsLab 관리자 로그인이 필요합니다')
        from .policy_profile import save
        try:
            result = save(service, **payload.model_dump())
        except ValueError as error: raise HTTPException(422, str(error)) from None
        if result.get('conflict'): raise HTTPException(409, '다른 담당자가 수정했습니다. 입력 내용을 기록한 뒤 다시 열어 주세요')
        return result

    @app.get(PREFIX + '/api/program-information/{program_id}')
    def program_information(program_id: str, request: Request):
        if not authenticated(request): raise HTTPException(401, 'MinsLab 관리자 로그인이 필요합니다')
        from .program_profile import view
        body, _ = delivery_cache.get((today().isoformat(), True),
            lambda: build_delivery(service, today(), include_portfolio_comparisons=False))
        try: return view(service, program_id, json.loads(body))
        except ValueError as error: raise HTTPException(422, str(error)) from None

    @app.post(PREFIX + '/api/admin/program-information/{program_id}')
    def program_information_save(program_id: str, payload: ProgramProfileEdit, request: Request):
        if not authenticated(request): raise HTTPException(401, 'MinsLab 관리자 로그인이 필요합니다')
        from .program_profile import save
        try: result = save(service, program_id, **payload.model_dump())
        except ValueError as error: raise HTTPException(422, str(error)) from None
        if result.get('conflict'): raise HTTPException(409, '다른 담당자가 변경했습니다. 다시 조회하세요')
        return result

    @app.get(PREFIX + '/api/policy-delivery/settings')
    def policy_delivery_settings():
        return delivery_settings(service)

    @app.get(PREFIX + '/api/policy-delivery/export.csv')
    def policy_delivery_csv():
        model=build_delivery(service,today())
        buffer=io.StringIO();fields=['id','name','region','municipality','units','representative_stage','mapping_status','eligibility_status','evidence_url']
        writer=csv.DictWriter(buffer,fieldnames=fields);writer.writeheader()
        # The exported policy ledger uses the same cumulative membership as
        # cards/maps, including approved projects that started in earlier years.
        for row in model.get('portfolio_cohorts',[]):
            item={key:row.get(key) for key in fields}
            writer.writerow({k:"'"+v if isinstance(v,str) and v.startswith(('=','+','-','@')) else v for k,v in item.items()})
        return Response('\ufeff'+buffer.getvalue(),media_type='text/csv; charset=utf-8',
                        headers={'Content-Disposition':'attachment; filename="home-907-cohorts.csv"'})

    @app.post(PREFIX + '/api/admin/policy-delivery')
    def policy_delivery_save(payload: DeliverySettings,request: Request):
        if not authenticated(request):raise HTTPException(401,'MinsLab 관리자 로그인이 필요합니다')
        try:
            result=save_delivery_settings(service,**payload.model_dump(mode='json'))
        except ValueError as error:raise HTTPException(422,str(error)) from None
        if result.get('conflict'):raise HTTPException(409,'다른 담당자가 목표를 수정했습니다. 다시 조회하세요')
        return result

    @app.get(PREFIX + '/api/execution')
    def execution_records(as_of_date: date | None = None):
        from .delivery_operations import records
        if as_of_date and as_of_date>today():raise HTTPException(422,'미래 기준일은 조회할 수 없습니다')
        return records(service,as_of_date)

    @app.get(PREFIX + '/api/execution/insights')
    def execution_insights(as_of_date: date | None = None):
        from .execution_insights import build
        from .project_collection import collection_matrix
        reference=as_of_date or today()
        if reference>today():raise HTTPException(422,'미래 기준일은 조회할 수 없습니다')
        return cached_json('execution_insights', {'as_of_date':reference.isoformat()},
                           lambda:build(service,collection_matrix(service,policy_id='POL_2025_0907',as_of=reference),reference))

    @app.get(PREFIX + '/api/execution/collection-actions')
    def execution_collection_actions():
        from .delivery_operations import collection_actions
        return collection_actions(service)

    @app.get(PREFIX + '/api/execution/{kind}/{key}/history')
    def execution_history(kind: str,key: str):
        from .delivery_operations import history
        try:return dict(items=history(service,kind,key))
        except ValueError as error:raise HTTPException(422,str(error)) from None

    @app.get(PREFIX + '/api/execution/scenario/{key}/comparison')
    def execution_scenario_comparison(key: str):
        from .delivery_operations import scenario_comparison
        try:return scenario_comparison(service,key)
        except ValueError as error:raise HTTPException(422,str(error)) from None

    @app.post(PREFIX + '/api/admin/execution/{kind}')
    def execution_save(kind: str,payload: ExecutionSave,request: Request):
        if not authenticated(request):raise HTTPException(401,'MinsLab 관리자 로그인이 필요합니다')
        from .delivery_operations import save
        model={'schedule':ExecutionSchedule,'case':ExecutionCase,'scenario':ExecutionScenario,'agency':ExecutionAgency}.get(kind)
        if model is None:raise HTTPException(422,'관리 유형 오류')
        try:
            values=model.model_validate(payload.values).model_dump(mode='json')
            result=save(service,kind,payload.key,payload.revision_no,values)
        except ValueError as error:raise HTTPException(422,str(error)) from None
        if result.get('conflict'):raise HTTPException(409,'다른 담당자가 수정했습니다. 다시 조회하세요')
        return result

    @app.get(PREFIX + '/api/stage-evidence')
    def stage_evidence_list(policy_id: str | None = None,as_of_date: date | None = None):
        return stage_evidence.list_links(service,policy_id,as_of_date)

    @app.get(PREFIX + '/api/stage-evidence/{project_id}/{stage}/history')
    def stage_evidence_history(project_id: str,stage: str):
        from sqlalchemy import select
        from .db import Audit, entity_id
        with service.sessions() as db:
            rows=db.scalars(select(Audit).where(Audit.entity_id==entity_id('stage_evidence','stage_match',project_id+':'+stage)).order_by(Audit.recorded_at.desc()).limit(30))
            return dict(items=[dict(action=r.action,before=r.before,after=r.after,recorded_at=r.recorded_at.isoformat()) for r in rows])

    @app.post(PREFIX + '/api/admin/stage-evidence')
    def stage_evidence_save(payload: StageEvidenceReview,request: Request):
        if not authenticated(request):raise HTTPException(401,'MinsLab 관리자 로그인이 필요합니다')
        try:result=stage_evidence.save_link(service,**payload.model_dump(mode='json'))
        except ValueError as error:raise HTTPException(422,str(error)) from None
        if result.get('conflict'):raise HTTPException(409,'다른 담당자가 변경했습니다. 다시 조회하세요')
        return result

    @app.post(PREFIX + '/api/admin/stage-evidence/refresh')
    def stage_evidence_refresh(request: Request):
        if not authenticated(request):raise HTTPException(401,'MinsLab 관리자 로그인이 필요합니다')
        return stage_evidence.refresh(service,refresh_candidates=True)

    @app.get(PREFIX + '/integrity-documents/{document}')
    def integrity_document(document: str, request: Request):
        names={'procedures':'공급유형별_추진절차.html','reliability':'데이터 신뢰도 확인.html'}
        name=names.get(document)
        if not name:raise HTTPException(404,'등록되지 않은 문서입니다')
        path=ROOT/'docs'/name
        if not path.is_file():raise HTTPException(404,'문서 파일이 없습니다')
        stat=path.stat()
        etag='"'+hashlib.sha256(f'{stat.st_mtime_ns}:{stat.st_size}'.encode()).hexdigest()+'"'
        if request.headers.get('if-none-match')==etag:return Response(status_code=304,headers={'ETag':etag})
        return FileResponse(path,media_type='text/html',headers={'ETag':etag},stat_result=stat)

    @app.get(PREFIX + "/api/mappings")
    def mappings(f=Depends(filters),compact:bool=False):
        def build():
            data=service.mappings(**f)
            if compact:
                omitted={'managed_schedules','source_values','manual_fields','construction_plan','quantity_proof'}
                data=dict(data,items=[{k:v for k,v in r.items() if k not in omitted} for r in data['items']])
            return data
        return cached_json('mappings',dict(f,compact=compact),build)

    @app.get(PREFIX + '/api/mapping-workbench')
    def mapping_workbench():
        from .mapping_workbench import build
        return cached_json('mapping_workbench', {}, lambda: build(service))

    @app.get(PREFIX + "/api/programs")
    def programs(f=Depends(filters)):
        rows=service.program_links(f['as_of'])
        if f.get('policy_id'):rows=[p for p in rows if p['policy_id']==f['policy_id'] and p['status'] not in ('RELEASED','REJECTED')]
        return {"items": rows,
                "policy_link_history": "GET /api/programs/{program_id}/history"}

    @app.get(PREFIX + "/api/programs/{program_id}/history")
    def program_history(program_id: str, f=Depends(filters)):
        return {"items": service.program_policy_history(program_id, f["as_of"])}

    @app.get(PREFIX + "/api/documents")
    def documents():
        return {"items": service.rows("document")}

    @app.get(PREFIX + "/api/identities")
    def identities_api(page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200)):
        return identity_summary(service, offset=(page - 1) * page_size, limit=page_size)

    @app.get(PREFIX + "/api/identity-reviews")
    def identity_reviews_api(page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100)):
        return identity_review_queue(service, page=page, page_size=page_size)

    @app.get(PREFIX + "/api/identity-options")
    def identity_options_api():
        return identity_options(service)

    @app.get(PREFIX + "/api/plans")
    def plans_api():
        return plan_summary(service)

    from .source_summary_cache import SourceSummaryCache
    from .source_summary import build as build_source_summary
    source_summary_cache = SourceSummaryCache(service.data_dir / 'runtime/source-summary-result.json',
        lambda: build_source_summary(service), lambda: projection_version(service))

    @app.get(PREFIX + "/api/sources")
    def sources(compact: bool = False):
        return {"items": service.sources(compact=compact)}

    @app.get(PREFIX + "/api/source-summary")
    def source_summary():
        from .source_summary import build
        if service.engine.dialect.name == 'postgresql':
            return source_summary_cache.get()
        return cached_json('source_summary', {}, lambda: build(service))

    @app.get(PREFIX + "/api/sources/year-coverage")
    def source_year_coverage():
        def build():
            from .data_gaps import data_gap_audit
            with service.sessions() as session:
                data = data_gap_audit(session, service.sources(), [], today().year,
                                      regions=("서울특별시", "인천광역시", "경기도"))
            return {"as_of_date": today().isoformat(), "years": data["years"], "rows": data["rows"],
                    "notice": "연도별 추적 대상 자료의 확보 현황입니다. 전체 수집 출처 전수표는 아닙니다. 미입수는 0건이나 미공표를 뜻하지 않으며 공고·계획·실적은 서로 다른 지표입니다."}
        return cached_json('source_year_coverage', {}, build)

    @app.get(PREFIX + '/api/projects/{project_id}/stage-fields/{stage}')
    def project_stage_fields(project_id: str, stage: str):
        from .stage_field_history import build
        try:return build(service,project_id,stage)
        except KeyError:raise HTTPException(404,'사업 또는 단계를 찾을 수 없습니다.')

    @app.get(PREFIX + '/api/collected-records/{entity_id}')
    def collected_record_view(entity_id: str, revision_no: int | None = Query(None, ge=1)):
        from .source_preview import collected_record
        try:return collected_record(service,entity_id,revision_no)
        except KeyError:raise HTTPException(404,'해당 원천 레코드 또는 판본을 찾을 수 없습니다.')

    @app.get(PREFIX + '/api/projects/{project_id}/collected-records')
    def project_collected_record_view(project_id: str, source_url: str = ''):
        from .source_preview import project_collected_records
        from .source_authority import public_url
        try:return project_collected_records(service,project_id,public_url(source_url))
        except KeyError:raise HTTPException(404,'사업 원천을 찾을 수 없습니다.')

    @app.get(PREFIX + "/api/sources/{source_id}/samples")
    def source_samples(source_id: str):
        from .source_preview import source_preview
        try:
            return source_preview(service, source_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="등록되지 않은 수집 원천입니다.")

    @app.get(PREFIX + "/api/coverage")
    def coverage():
        return {"items": service.coverage_details(), "complete_population": False,
                "notice": "조회한 endpoint·지역의 페이지 완결성과 서울·경기 사업 전수는 다릅니다."}

    @app.get(PREFIX + '/api/api-requests/{request_id}/draft.txt')
    def api_request_draft(request_id: str):
        from .api_requests import draft
        try:content=draft(service,request_id)
        except ValueError as error:raise HTTPException(404,str(error)) from None
        return Response(content,media_type='text/plain; charset=utf-8',
                        headers={'Content-Disposition':'attachment; filename="HOME_API_REQUEST.txt"'})

    @app.get(PREFIX + '/api/project-collection/version')
    def project_collection_version():
        import hashlib
        return {'version': hashlib.sha256(repr(collection_projection_version(service)).encode()).hexdigest()}

    @app.get(PREFIX + '/api/project-collection')
    def project_collection(f=Depends(filters)):
        from .project_collection import collection_matrix
        return cached_json('project_collection',f,lambda:collection_matrix(service,**f))

    @app.get(PREFIX + '/api/project-collection/quality-guide.json')
    def collection_quality_guide(f=Depends(filters)):
        from .project_collection import collection_matrix
        from .collection_repairs import quality_guide
        response=cached_json('project_collection',f,lambda:collection_matrix(service,**f))
        data=quality_guide(json.loads(response.body))
        return Response(json.dumps(data,ensure_ascii=False),media_type='application/json',headers={'Content-Disposition':'attachment; filename=home-data-quality-guide.json'})

    @app.get(PREFIX + '/api/requirements-status')
    def requirements_status():
        from .project_collection import collection_matrix
        from .requirements_status import build_status
        from .read_scope import projection_reads
        def build():
            with projection_reads():
                return build_status(service, collection_matrix(service, policy_id='POL_2025_0907', include_link_history=False), json.loads(project_locations().body))
        return cached_json('requirements_status', {}, build)

    @app.post(PREFIX + '/api/admin/evidence-bridge')
    def evidence_bridge_review(payload: EvidenceBridgeReview,request: Request):
        if not authenticated(request):raise HTTPException(401,'관리자 인증 필요')
        from .evidence_bridge import review
        try:result=review(service,**payload.model_dump())
        except ValueError as error:raise HTTPException(422,str(error)) from None
        if result.get('conflict'):raise HTTPException(409,'다른 담당자가 변경했습니다. 다시 조회하세요')
        return result

    @app.get(PREFIX + '/api/project-collection/export.csv')
    def project_collection_export(f=Depends(filters),collection_status: str | None=Query(None,pattern='^(ACQUIRED|NOT_PLANNED|COLLECTION_REQUIRED|METHOD_UNKNOWN)$')):
        from .project_collection import collection_matrix,STAGES,collection_cell_text
        data=collection_matrix(service,**f);buffer=io.StringIO();writer=csv.writer(buffer)
        writer.writerow(['사업','지역','정책','프로그램']+list(STAGES.values()))
        for row in data['items']:
            if collection_status and not any(c['status']==collection_status for c in row['cells'].values()):continue
            writer.writerow([row['name'],row['region'],row['policy_name'],row['program']]+[
                collection_cell_text(row['cells'][s]) for s in STAGES])
        return Response('\ufeff'+buffer.getvalue(),media_type='text/csv; charset=utf-8',headers={'Content-Disposition':'attachment; filename="home-project-collection.csv"'})

    @app.get(PREFIX + '/api/project-collection/dataset.csv')
    def project_dataset_export(f=Depends(filters),collection_status: str | None=Query(None,pattern='^(ACQUIRED|NOT_PLANNED|COLLECTION_REQUIRED|COLLECTION_UNAVAILABLE|LINK_REQUIRED|METHOD_UNKNOWN)$')):
        from .project_collection import collection_matrix
        from .collection_exports import export
        response=cached_json('project_collection',f,lambda:collection_matrix(service,**f))
        matrix=json.loads(response.body)
        return Response(export(service,matrix,collection_status),media_type='text/csv; charset=utf-8',headers={
            'Content-Disposition':'attachment; filename="the-jutaek-project-dataset-'+matrix['as_of_date']+'.csv"'})

    def build_collection_schema():
        from .project_collection import collection_matrix
        from .collection_schema import build
        f=dict(as_of=None,region=None,policy_id='POL_2025_0907',source_id=None,stage=None,q=None,mapping_status=None)
        matrix=json.loads(cached_json('project_collection',f,lambda:collection_matrix(service,**f)).body)
        return build(service,matrix)

    schema_cache=SourceSummaryCache(service.data_dir/'runtime/collection-schema-result.json',
        build_collection_schema,lambda:('publisher-document-cards-20261022-v3',collection_projection_version(service)))

    @app.get(PREFIX + '/api/collection-schema')
    def collection_schema():
        return schema_cache.get()

    @app.get(PREFIX + '/api/collection-schema/export.csv')
    def collection_schema_export():
        from .collection_schema import export
        data=schema_cache.get()
        if data.get('status')!='READY':raise HTTPException(503,'수집 항목 집계 중입니다. 잠시 후 다시 시도하세요.',headers={'Retry-After':'3'})
        return Response(export(data),media_type='text/csv; charset=utf-8',headers={
            'Content-Disposition':'attachment; filename="the-jutaek-collection-schema-'+data['as_of_date']+'.csv"'})

    @app.post(PREFIX + '/api/admin/project-collection/assessment')
    def collection_assessment(payload: CollectionAssessment,request: Request):
        if not authenticated(request):raise HTTPException(401,'관리자 인증 필요')
        from .project_collection import save_assessment
        try:result=save_assessment(service,**payload.model_dump())
        except ValueError as error:raise HTTPException(422,str(error))
        if result.get('conflict'):raise HTTPException(409,'다른 담당자가 변경했습니다. 다시 조회하세요')
        return result

    @app.get(PREFIX + "/api/tree")
    def tree(f=Depends(filters)):
        return cached_json('tree', f, lambda: {'items': service.tree(**f)})

    @app.get(PREFIX + "/api/export.csv")
    def export(f=Depends(filters)):
        fields = ["id", "name", "region", "program", "source_id", "planned_units", "supply_units", "stage_label", "base_date", "schedule_month", "progress_pct", "mapping_status", "policy_id", "evidence_url"]
        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=fields)
        writer.writeheader()
        for row in service.projects(**f):
            item = {k: row.get(k) for k in fields}
            item.update(mapping_status=row["mapping"]["status"], policy_id=row["mapping"]["policy_id"])
            # Spreadsheet formulas are disabled even for untrusted official text.
            item = {k: "'" + v if isinstance(v, str) and v.startswith(("=", "+", "-", "@")) else v for k, v in item.items()}
            writer.writerow(item)
        return Response("\ufeff" + buffer.getvalue(), media_type="text/csv; charset=utf-8", headers={"Content-Disposition": 'attachment; filename="home-seoul-gyeonggi.csv"'})

    @app.get(PREFIX + "/api/admin/status")
    def admin_status(request: Request):
        return {"authenticated": authenticated(request)}

    @app.post(PREFIX + "/api/admin/refresh", status_code=202)
    def refresh(request: Request, mode: str = Query("official", pattern="^(official|sample)$")):
        if not authenticated(request):
            raise HTTPException(401, "MinsLab 관리자 로그인이 필요합니다.")
        if any(s["status"] == "RUNNING" for s in service.sources()):
            raise HTTPException(409, "이미 수집 중입니다.")
        threading.Thread(target=service.collect_samples if mode == "sample" else service.collect_all, daemon=True).start()
        return {"status": "ACCEPTED", "mode": mode}

    @app.post(PREFIX + "/api/admin/identities/{alias_id}")
    def review_identity(alias_id: str, payload: IdentityReview, request: Request):
        if not authenticated(request):
            raise HTTPException(401, "MinsLab 관리자 로그인이 필요합니다.")
        try:
            result = review_identity_alias(service, alias_id, **payload.model_dump())
        except ValueError as error:
            raise HTTPException(422, str(error)) from None
        if result.get('conflict'):
            raise HTTPException(409, "다른 담당자가 먼저 정체성 연결을 변경했습니다. 새로고침 후 다시 검토하세요.")
        return result

    @app.post(PREFIX + "/api/admin/mappings/{project_id}")
    def review(project_id: str, payload: Review, request: Request):
        if not authenticated(request):
            raise HTTPException(401, "MinsLab 관리자 로그인이 필요합니다.")
        try:
            result = service.confirm_mapping(project_id, **payload.model_dump())
            if result.get("conflict"):
                return Response(__import__("json").dumps(result), status_code=409, media_type="application/json")
            return result
        except KeyError:
            raise HTTPException(404, "매핑을 찾을 수 없습니다.") from None
        except ValueError as error:
            raise HTTPException(400, str(error)) from None

    @app.post(PREFIX + '/api/admin/mapping-decisions/{kind}/{target_id}')
    def mapping_decision(kind: str, target_id: str, payload: MappingDecision, request: Request):
        if not authenticated(request):
            raise HTTPException(401, 'MinsLab 관리자 로그인이 필요합니다.')
        from .mapping_decisions import save
        try:
            result = save(service, kind, target_id, **payload.model_dump())
            if result.get('conflict'):
                return Response(json.dumps(result), status_code=409, media_type='application/json')
            return result
        except KeyError:
            raise HTTPException(404, '검토 대상을 찾을 수 없습니다.') from None
        except ValueError as error:
            raise HTTPException(400, str(error)) from None

    @app.post(PREFIX + "/api/admin/programs/{program_id}/policy")
    def review_program_policy(program_id: str, payload: ProgramPolicyReview, request: Request):
        if not authenticated(request):
            raise HTTPException(401, "MinsLab 관리자 로그인이 필요합니다.")
        try:
            result = service.confirm_program_policy(program_id, **payload.model_dump())
            if result.get('conflict'):
                return Response(json.dumps(result), status_code=409, media_type='application/json')
            return result
        except KeyError:
            raise HTTPException(404, "프로그램을 찾을 수 없습니다.") from None
        except ValueError as error:
            raise HTTPException(400, str(error)) from None

    @app.post(PREFIX + "/api/admin/projects/{project_id}/program")
    def review_project_program(project_id: str, payload: ProjectProgramReview, request: Request):
        if not authenticated(request):
            raise HTTPException(401, "MinsLab 관리자 로그인이 필요합니다.")
        try:
            result = service.confirm_project_program(project_id, **payload.model_dump())
            if result.get('conflict'):
                return Response(json.dumps(result), status_code=409, media_type='application/json')
            return result
        except KeyError:
            raise HTTPException(404, "사업을 찾을 수 없습니다.") from None
        except ValueError as error:
            raise HTTPException(400, str(error)) from None

    @app.post(PREFIX + "/api/admin/targets/{project_id}")
    def update_targets(project_id: str, payload: TargetPlan, request: Request):
        if not authenticated(request):
            raise HTTPException(401,"MinsLab 관리자 로그인이 필요합니다.")
        try:
            result=service.save_targets(project_id,**payload.model_dump())
            if result.get("conflict"):
                return Response(__import__("json").dumps(result),status_code=409,media_type="application/json")
            return result
        except KeyError:
            raise HTTPException(404,"사업을 찾을 수 없습니다.") from None
        except ValueError as error:
            raise HTTPException(400,str(error)) from None

    return app


app = create_app() if os.environ.get("POC10_DATABASE_URL") else None
