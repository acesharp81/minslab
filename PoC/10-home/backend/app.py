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
from .sources import SOURCES
from .tiles import tile

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


class Review(BaseModel):
    policy_id: str = Field(max_length=80)
    revision_no: int = Field(ge=1)
    status: str = Field(pattern="^(CONFIRMED|REVIEW|RELEASED)$")
    basis: str = Field(min_length=1, max_length=2000)
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
    stage: str = Field(pattern="^(PLANNING|APPROVAL|CONSTRUCTION|SUPPLY|COMPLETION|MOVE_IN)$")
    units: int | None = Field(None, ge=0, le=10000000)
    basis: str = Field(min_length=1, max_length=500)
    evidence_url: str | None = Field(None, max_length=500)


class TargetPlan(BaseModel):
    revision_no: int = Field(ge=0)
    targets: list[AnnualTarget] = Field(max_length=31)


def create_app(engine=None, auto_collect=None):
    service = HomeService(engine or engine_for(), os.environ.get("POC10_DATA_DIR", str(ROOT / "data")))
    enabled = auto_collect if auto_collect is not None else os.environ.get("POC10_AUTO_COLLECT", "true").lower() == "true"
    stop = threading.Event()

    def collect_loop():
        interval = max(3600, int(os.environ.get("POC10_COLLECTION_INTERVAL_SECONDS", "86400")))
        while not stop.is_set():
            try:
                service.collect_all()
            except Exception:
                # Connectivity errors are reflected by /health, never leak credentials.
                pass
            stop.wait(interval)

    @asynccontextmanager
    async def lifespan(app):
        service.recover_interrupted_batches()
        service.reconcile_program_links()
        service.propose_program_policies()
        if enabled:
            threading.Thread(target=collect_loop, name="home-collector", daemon=True).start()
        yield
        stop.set()

    app = FastAPI(title="HOME", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
    app.state.service = service
    building_context = BuildingContext()
    infrastructure_context = InfrastructureContext()
    app.add_middleware(GZipMiddleware, minimum_size=1000000, compresslevel=4)

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
        if region and region not in {"서울특별시", "경기도"}:
            raise HTTPException(400, "조회 범위는 서울·경기입니다.")
        return dict(as_of=as_of_date, region=region, policy_id=policy_id, source_id=source_id, stage=stage, q=q, mapping_status=mapping_status)

    from fastapi import Depends

    @app.get(PREFIX + "/api/overview")
    def overview(f=Depends(filters)):
        return service.overview(**f)

    @app.get(PREFIX + "/api/roadmap")
    def roadmap(f=Depends(filters), horizon: int = Query(10, ge=1, le=10)):
        return service.roadmap(horizon=horizon, **f)

    @app.get(PREFIX + "/api/history")
    def historical_data(f=Depends(filters),history_year:int|None=Query(None,ge=2010,le=2100),
                        page:int=Query(1,ge=1),page_size:int=Query(100,ge=1,le=200)):
        return service.historical_data(year=history_year,page=page,page_size=page_size,**f)

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
    def map_buildings(block_id: str = Query(..., min_length=4, max_length=150)):
        try:
            return building_context.get(block_id, service)
        except ValueError as error:
            raise HTTPException(422, str(error)) from None
        except RuntimeError:
            raise HTTPException(503, "공식 건물 공간정보 연결 확인 필요") from None

    @app.get(PREFIX + "/api/map/infrastructure")
    def map_infrastructure(block_id: str = Query(..., min_length=4, max_length=150)):
        try:
            return infrastructure_context.get(block_id, service)
        except ValueError as error:
            raise HTTPException(422, str(error)) from None
        except RuntimeError:
            raise HTTPException(503, "공식 주변 시설 연결 확인 필요") from None

    @app.get(PREFIX + "/api/map/dashboard")
    def supply_dashboard(f=Depends(filters),analysis_year:int|None=Query(None,ge=2010,le=2100),
                         horizon:int=Query(10,ge=1,le=10),measure:str=Query("MOVE_IN",pattern="^(SUPPLY|MOVE_IN|COMPLETION)$"),
                         schedule_status:str=Query("all",pattern="^(all|future|missing|past|manual)$")):
        if analysis_year and analysis_year>(f["as_of"] or today()).year:
            raise HTTPException(422,"자료 연도는 조회 기준연도 이하여야 합니다")
        return service.supply_dashboard(analysis_year=analysis_year,horizon=horizon,measure=measure,schedule_status=schedule_status,**f)

    @app.get(PREFIX + "/api/area-places")
    def area_places_api():
        from .area_stats import area_places
        return area_places(service)

    @app.get(PREFIX + "/api/area-context")
    def area_context_api(region:str=Query(...,pattern="^(서울특별시|경기도)$"),
                         municipality:str|None=Query(None,max_length=30),year:int|None=Query(None,ge=2018,le=2100)):
        from .area_stats import area_context
        if year and year>today().year:
            raise HTTPException(422,"자료 연도는 현재 연도 이하여야 합니다")
        try:
            return area_context(service,region,municipality,year or today().year)
        except ValueError as error:
            raise HTTPException(422,str(error)) from None

    @app.get(PREFIX + "/api/area-outlook")
    def area_outlook_api(region:str=Query(...,pattern="^(서울특별시|경기도)$")):
        from .area_outlook import area_outlook
        return area_outlook(service,region)

    @app.get(PREFIX + "/api/annual-supply")
    def annual_supply_api(region:str|None=Query(None,pattern="^(서울특별시|경기도)$"),
                          through_year:int|None=Query(None,ge=2018,le=2100)):
        from .annual_supply import annual_supply
        if through_year and through_year>today().year:
            raise HTTPException(422,"미래 연도는 조회할 수 없습니다")
        return annual_supply(service,region,through_year or today().year)

    @app.get(PREFIX + "/api/annual-supply/export.csv")
    def annual_supply_export(region:str|None=Query(None,pattern="^(서울특별시|경기도)$"),
                             through_year:int|None=Query(None,ge=2018,le=2100)):
        from .annual_supply import annual_supply,annual_supply_csv
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
        return service.map_data(**f)

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
        fields = ["id","name","region","source_id","stage_label","progress_pct","planned_units","base_date",
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
        return service.policy_monitor(**f)

    @app.get(PREFIX + "/api/mappings")
    def mappings(f=Depends(filters)):
        return service.mappings(**f)

    @app.get(PREFIX + "/api/programs")
    def programs(f=Depends(filters)):
        return {"items": service.program_links(f["as_of"]),
                "policy_link_history": "GET /api/programs/{program_id}/history"}

    @app.get(PREFIX + "/api/programs/{program_id}/history")
    def program_history(program_id: str, f=Depends(filters)):
        return {"items": service.program_policy_history(program_id, f["as_of"])}

    @app.get(PREFIX + "/api/documents")
    def documents():
        return {"items": service.rows("document")}

    def sample_filters(f=Depends(filters), kind: str | None = Query(None, pattern="^(notice|permit|location|register|lh_notice|statistic|sh_plan|sh_project|gh_notice|agency_stock|legal_dong|lh_supply|lh_movein_plan|lh_stock)$"),
                       source_year: int | None = Query(None, ge=1900, le=2100)):
        return dict(as_of=f["as_of"], region=f["region"], source_id=f["source_id"], q=f["q"], kind=kind, source_year=source_year)

    @app.get(PREFIX + "/api/samples")
    def samples(f=Depends(sample_filters), page: int = Query(1,ge=1), page_size: int = Query(100,ge=1,le=200)):
        return service.sample_page(page=page,page_size=page_size,**f)

    @app.get(PREFIX + "/api/samples/export.csv")
    def sample_export(f=Depends(sample_filters)):
        fields = ["id", "sample_kind", "name", "region", "address", "source_id", "source_object_id", "source_date",
                  "source_date_label", "base_date", "base_date_basis", "units", "unit_basis", "longitude", "latitude",
                  "resolution_status", "coordinate_basis", "parent_sample_id", "policy_mapping_status", "sample_mode", "evidence_url",
                  "statistic_metric", "statistic_period", "statistic_frequency", "statistic_unit", "form_id", "style_num",
                  "district_name", "block", "total_units", "move_in_plan_month", "source_note", "agency", "dataset_year", "stock_basis", "lat", "lng", "municipality", "main_purpose", "building_dong", "household_count", "family_count", "unit_count", "notice_category", "notice_type", "notice_status", "dataset_version", "latest_dataset_version", "is_latest_dataset", "schedule_month", "housing_type", "business_type", "pre_subscription_units", "main_subscription_units", "rental_units", "source_stage", "native_fields", "dates", "warnings"]
        def generate():
            buffer=io.StringIO();writer=csv.DictWriter(buffer,fieldnames=fields)
            writer.writeheader();yield '\ufeff'+buffer.getvalue();buffer.seek(0);buffer.truncate(0)
            for row in service.iterate_samples(**f):
                item={key:row.get(key) for key in fields}
                for key in ('dates','warnings','native_fields'):
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

    @app.get(PREFIX + "/api/sources")
    def sources():
        return {"items": service.sources()}

    @app.get(PREFIX + "/api/connections")
    def connections():
        from .connection_audit import connection_audit
        return connection_audit(service.sources())

    @app.get(PREFIX + "/api/tree")
    def tree(f=Depends(filters)):
        return {"items": service.tree(**f)}

    @app.get(PREFIX + "/api/validation")
    def validation(f=Depends(filters)):
        rows = service.projects(**f)
        issues = [{"project_id": r["id"], "name": r["name"], "source_id": r["source_id"], "code": code}
                  for r in rows for code in r["warnings"]]
        from .coverage_audit import coverage_audit
        return {"items": issues, "total": len(issues), "baseline_status": "DRAFT", "coverage":coverage_audit(service.sources()),
                "notes": ["자동 매칭·승인 대기 사업은 검토 통계에 포함하며 담당자 확정과 구분합니다. 연결 해제 사업은 정책 통계에서 제외합니다.",
                          "LH 공급계획과 건설공사 원천은 정확한 지구·블록에서 중복 검토하며 승인된 동일 사업으로 자동 확정하지 않습니다.",
                          "서울·경기의 전체 사업 목록이 확정된 상태가 아닙니다. SH·GH 공개본 밖 사업과 지자체 원천 확대가 필요합니다.",
                          "실제 착공·준공·입주 단계는 공고 또는 담당자 근거 확인 후 확정합니다."]}

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
