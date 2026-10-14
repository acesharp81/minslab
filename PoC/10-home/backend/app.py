import csv
import hashlib
import hmac
import io
import json
import os
import threading
import time
from contextlib import asynccontextmanager
from datetime import date
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

class ApiRequestSave(BaseModel):
    revision_no: int = Field(ge=0)
    status: str = Field(pattern='^(DRAFT|SUBMITTED|APPROVED|CONNECTED|BLOCKED)$')
    responsible_org: str = Field(min_length=1,max_length=200)
    receipt_no: str = Field('',max_length=200)
    due_date: date | None = None
    basis: str = Field(min_length=1,max_length=2000)


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


def create_app(engine=None, auto_collect=None):
    service = HomeService(engine or engine_for(), os.environ.get("POC10_DATA_DIR", str(ROOT / "data")))
    delivery_cache = ProjectionCache(lambda: projection_version(service))
    read_caches = {name: ProjectionCache(lambda: projection_version(service))
                   for name in ('overview', 'samples', 'policy_metrics', 'supply_dashboard', 'map', 'project_collection', 'requirements_status', 'policy_monitor', 'mappings', 'tree', 'validation', 'history', 'geometry', 'schematic', 'annual_supply', 'area_context', 'area_outlook', 'execution_insights', 'unsold', 'project_workspace', 'project_locations')}
    def cached_json(name, parameters, build):
        # Relative "today" queries must not reuse yesterday's projection.
        body, status = read_caches[name].get((today(),tuple(sorted(parameters.items()))), build)
        return Response(body, media_type='application/json', headers={'X-Home-Cache': status})
    enabled = auto_collect if auto_collect is not None else os.environ.get("POC10_AUTO_COLLECT", "true").lower() == "true"
    stop = threading.Event()

    def collect_loop():
        interval = max(3600, int(os.environ.get("POC10_COLLECTION_INTERVAL_SECONDS", "86400")))
        while not stop.is_set():
            try:
                service.collect_all(scheduled=True, interval_seconds=interval)
            except Exception:
                # Connectivity errors are reflected by /health, never leak credentials.
                pass
            stop.wait(min(300, interval))

    @asynccontextmanager
    async def lifespan(app):
        service.recover_interrupted_batches()
        service.reconcile_program_links()
        service.propose_program_policies()
        reconcile_identity_links(service)
        if enabled:
            threading.Thread(target=collect_loop, name="home-collector", daemon=True).start()
        yield
        stop.set()

    app = FastAPI(title="HOME", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
    app.state.service = service
    building_context = BuildingContext()
    infrastructure_context = InfrastructureContext()
    app.add_middleware(GZipMiddleware, minimum_size=16384, compresslevel=4)

    @app.middleware("http")
    async def headers(request, call_next):
        response = await call_next(request)
        response.headers["Cache-Control"] = ("public, max-age=3600" if "/api/tiles/" in request.url.path and response.status_code==200
                                            else "no-store" if "/api/" in request.url.path else "no-cache")
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self'; worker-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'self'; base-uri 'self'; form-action 'self'"
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
        return cached_json('geometry', dict(as_of=as_of_date), lambda: geometry_view(service.supply_dashboard(as_of=as_of_date, horizon=1, measure='SUPPLY')))

    @app.get(PREFIX + "/api/policy-geo/schematic")
    def policy_geo_schematic(as_of_date: date | None = None):
        if as_of_date and as_of_date > today():
            raise HTTPException(400, "미래 기준일은 조회할 수 없습니다.")
        return cached_json('schematic', dict(as_of=as_of_date), lambda: schematic_view(service.supply_dashboard(as_of=as_of_date, horizon=1, measure='SUPPLY')))

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
            lambda: metrics_view(service.supply_dashboard(as_of=day, analysis_year=analysis_year,
                                                          horizon=5, measure=measure)))

    @app.get(PREFIX + "/api/area-places")
    def area_places_api():
        from .area_stats import area_places
        return area_places(service)

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
        try:
            return cached_json('area_context', dict(region=region, municipality=municipality, year=year or today().year), lambda: area_context(service,region,municipality,year or today().year))
        except ValueError as error:
            raise HTTPException(422,str(error)) from None

    @app.get(PREFIX + "/api/area-outlook")
    def area_outlook_api(region:str=Query(...,pattern="^(서울특별시|경기도|인천광역시)$")):
        from .area_outlook import area_outlook
        return cached_json('area_outlook', dict(region=region), lambda: area_outlook(service,region))

    @app.get(PREFIX + "/api/annual-supply")
    def annual_supply_api(region:str|None=Query(None,max_length=30),
                          through_year:int|None=Query(None,ge=2018,le=2100)):
        from .annual_supply import annual_supply,REGIONS
        if region and region not in REGIONS:raise HTTPException(422,"지원하지 않는 시도")
        if through_year and through_year>today().year:
            raise HTTPException(422,"미래 연도는 조회할 수 없습니다")
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
            keys=('id','name','region','municipality','mapping','planned_units')
            return dict(items=[{k:p.get(k) for k in keys} for p in service.projects(policy_id='POL_2025_0907') if p['mapping']['status'] not in ('RELEASED','REJECTED')],
                        programs=[p for p in service.program_links() if p['policy_id']=='POL_2025_0907' and p['status'] not in ('RELEASED','REJECTED')],
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
        matrix=cached_json('project_collection',{'policy_id':'POL_2025_0907'},lambda:collection_matrix(service,policy_id='POL_2025_0907'))
        try: return view(service,project_id,json.loads(matrix.body),json.loads(project_locations().body))
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
        for row in model.get('cohorts',[]):
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

    @app.get(PREFIX + "/api/mappings")
    def mappings(f=Depends(filters)):
        return cached_json('mappings', f, lambda: service.mappings(**f))

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

    def sample_filters(f=Depends(filters), kind: str | None = Query(None, pattern="^(notice|permit|location|register|register_recap|lh_notice|statistic|sh_plan|sh_project|gh_notice|gh_completion_evidence|complex_approval_reference|agency_stock|legal_dong|lh_supply|lh_movein_plan|lh_stock|renewal_inventory|lh_completion_plan|permit_dong|permit_parcel|plan_notice)$"),
                       source_year: int | None = Query(None, ge=1900, le=2100)):
        return dict(as_of=f["as_of"], region=f["region"], source_id=f["source_id"], q=f["q"], kind=kind, source_year=source_year)

    @app.get(PREFIX + "/api/samples")
    def samples(f=Depends(sample_filters), page: int = Query(1,ge=1), page_size: int = Query(100,ge=1,le=200)):
        return cached_json('samples', dict(f, page=page, page_size=page_size),
                           lambda: service.sample_page(page=page,page_size=page_size,**f))

    @app.get(PREFIX + "/api/samples/export.csv")
    def sample_export(f=Depends(sample_filters)):
        fields = ["id", "sample_kind", "name", "region", "address", "source_id", "source_object_id", "source_date",
                  "source_date_label", "base_date", "base_date_basis", "units", "unit_basis", "longitude", "latitude",
                  "resolution_status", "coordinate_basis", "parent_sample_id", "policy_mapping_status", "sample_mode", "evidence_url",
                  "statistic_metric", "statistic_period", "statistic_frequency", "statistic_unit", "form_id", "style_num",
                  "district_name", "block", "total_units", "planned_units", "source_planned_units", "value_status", "in_latest_source", "record_role", "completion_plan_date", "schedule_status", "plan_name", "plan_type", "notice_no", "notice_date", "event_type", "original_sha256", "original_url", "verification_status", "legal_status", "move_in_plan_month", "source_note", "agency", "dataset_year", "stock_basis", "lat", "lng", "municipality", "main_purpose", "building_dong", "parent_permit_native_id", "native_dong_id", "household_breakdown", "plat_gb_cd", "bun", "ji", "representative", "related_lot", "household_count", "family_count", "unit_count", "notice_category", "notice_type", "notice_status", "evidence_type", "approval_date", "permit_no", "site_location", "pdf_sha256", "pdf_text_extracted", "approval_scope", "project_link_status", "complex_id", "parcel_id", "complex_type", "building_count", "complex_name_register", "complex_name_road", "dataset_version", "latest_dataset_version", "is_latest_dataset", "schedule_month", "housing_type", "business_type", "pre_subscription_units", "main_subscription_units", "rental_units", "source_stage", "native_fields", "dates", "warnings"]
        def generate():
            buffer=io.StringIO();writer=csv.DictWriter(buffer,fieldnames=fields)
            writer.writeheader();yield '\ufeff'+buffer.getvalue();buffer.seek(0);buffer.truncate(0)
            for row in service.iterate_samples(**f):
                item={key:row.get(key) for key in fields}
                for key in ('dates','warnings','native_fields','household_breakdown'):
                    item[key]=json.dumps(item[key],ensure_ascii=False) if item[key] is not None else None
                writer.writerow({key:"'"+value if isinstance(value,str) and value.startswith(('=','+','-','@')) else value for key,value in item.items()})
                yield buffer.getvalue();buffer.seek(0);buffer.truncate(0)
        return StreamingResponse(generate(),media_type='text/csv; charset=utf-8',
            headers={'Content-Disposition':'attachment; filename="home-api-test-samples.csv"'})

    @app.get(PREFIX + "/api/samples/{sample_id}")
    def sample_detail(sample_id: str, f=Depends(sample_filters)):
        result = service.sample_detail(sample_id, f["as_of"])
        if not result:
            raise HTTPException(404, "표본을 찾을 수 없습니다.")
        return result

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

    @app.get(PREFIX + "/api/sources")
    def sources(compact: bool = False):
        return {"items": service.sources(compact=compact)}

    @app.get(PREFIX + "/api/coverage")
    def coverage():
        return {"items": service.coverage_details(), "complete_population": False,
                "notice": "조회한 endpoint·지역의 페이지 완결성과 서울·경기 사업 전수는 다릅니다."}

    @app.get(PREFIX + '/api/api-requests')
    def api_request_board():
        from .api_requests import board
        return board(service)

    @app.get(PREFIX + '/api/api-requests/{request_id}/draft.txt')
    def api_request_draft(request_id: str):
        from .api_requests import draft
        try:content=draft(service,request_id)
        except ValueError as error:raise HTTPException(404,str(error)) from None
        return Response(content,media_type='text/plain; charset=utf-8',
                        headers={'Content-Disposition':'attachment; filename="HOME_API_REQUEST.txt"'})

    @app.post(PREFIX + '/api/admin/api-requests/{request_id}')
    def api_request_save(request_id: str,payload: ApiRequestSave,request: Request):
        if not authenticated(request):raise HTTPException(401,'MinsLab 관리자 로그인이 필요합니다')
        from .api_requests import save
        values=payload.model_dump(mode='json');version=values.pop('revision_no')
        try:result=save(service,request_id,version,values)
        except ValueError as error:raise HTTPException(422,str(error)) from None
        if result.get('conflict'):raise HTTPException(409,'다른 담당자가 수정했습니다. 다시 조회하세요')
        return result

    @app.get(PREFIX + "/api/connections")
    def connections():
        from .connection_audit import connection_audit
        return connection_audit(service.sources())

    @app.get(PREFIX + '/api/project-collection/version')
    def project_collection_version():
        import hashlib
        return {'version': hashlib.sha256(repr(projection_version(service)).encode()).hexdigest()}

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
        return cached_json('requirements_status', {}, lambda: build_status(service, collection_matrix(service, policy_id='POL_2025_0907'), json.loads(project_locations().body)))

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

    @app.get(PREFIX + "/api/validation")
    def validation(f=Depends(filters)):
        def build():
            rows = service.projects(**f)
            issues = [{"project_id": r["id"], "name": r["name"], "source_id": r["source_id"], "code": code}
                      for r in rows for code in r["warnings"]]
            from .coverage_audit import coverage_audit
            source_rows = service.sources()
            return {"items": issues, "total": len(issues), "baseline_status": "DRAFT", "coverage":coverage_audit(source_rows), "coverage_details":service.coverage_details(),
                    "data_gaps": service.data_gaps(source_rows, rows),
                    "notes": ["자동 매칭·승인 대기 사업은 검토 통계에 포함하며 담당자 확정과 구분합니다. 연결 해제 사업은 정책 통계에서 제외합니다.",
                              "LH 공급계획과 건설공사 원천은 정확한 지구·블록에서 중복 검토하며 승인된 동일 사업으로 자동 확정하지 않습니다.",
                              "서울·경기의 전체 사업 목록이 확정된 상태가 아닙니다. SH·GH 공개본 밖 사업과 지자체 원천 확대가 필요합니다.",
                              "실제 착공·준공·입주 단계는 공고 또는 담당자 근거 확인 후 확정합니다."]}
        return cached_json('validation', f, build)

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
