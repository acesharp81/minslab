from . import inheritance, report_interactions, demo_policy
import copy
import asyncio
import threading
import html
import json
import os
import secrets
from datetime import datetime
from zoneinfo import ZoneInfo
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlparse

from dotenv import dotenv_values
from fastapi import FastAPI, File, Header, HTTPException, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .employees import EMPLOYEES, employee_from, memberships, member_role
from .demo import demo_archive, expanded_archive
from .submission import submission_archive
from .flow_demo import flow_archive
from .practice_demo import practice_archive
from .prompts import EXTRACTION_PROMPT
from .timeline import project_latest
from .engine import FIELDS, annotate_items, empty_field, llm_discover, search_blocks, warnings_for
from .jobs import JobRunner
from .billing import Meter
from .vision import Vision
from .reports import build_report, render_html, render_markdown, render_docx
from .questions import answer_question
from .workflow import briefing, readiness
from .parsers import MAX_FILES, MAX_TOTAL, PARSER_VERSION, InputError, unpack_upload
from .store import Store, digest, dump, now, uid

ROOT = Path(__file__).resolve().parent.parent


class CaseInput(BaseModel):
    title: str = Field(min_length=1, max_length=150)
    predecessor: str = Field(default="전임자", max_length=80)
    successor: str = Field(default="후임자", max_length=80)
    predecessor_id: str | None = None
    successor_id: str | None = None


class DemoSetInput(BaseModel):
    kind: str = Field(pattern="^(comprehensive|practice|versions|inheritance)$")
    predecessor_id: str
    successor_id: str


class GenerateInput(BaseModel):
    mode: str = "rules"
    external_consent: bool = False
    image_consent: bool = False
    basis_case_id: str | None = Field(default=None, max_length=80)
    basis_revision_id: str | None = Field(default=None, max_length=80)
    request_id: str | None = Field(default=None, max_length=80)


class ModelInput(BaseModel):
    key: str = Field(min_length=10, max_length=512, repr=False)
    model: str = "solar-pro4"


class EditInput(BaseModel):
    expected_hash: str
    fields: dict[str, str] = Field(default_factory=dict)
    reason: str = Field(min_length=1, max_length=1000)
    delete: bool = False


class QuestionInput(BaseModel):
    include_sources: bool = False
    previous_questions: list[str] = Field(default_factory=list, max_length=4)
    question: str = Field(min_length=2, max_length=500)
    expected_revision: str
    mode: str = "local"
    external_consent: bool = False


class MatchInput(BaseModel):
    expected_hash: str
    target_id: str
    source_id: str
    owner: str = Field(min_length=1, max_length=200)
    reason: str = Field(min_length=1, max_length=1000)


class WorkGroupInput(BaseModel):
    item_ids: list[str] = Field(min_length=1,max_length=200)
    title: str = Field(min_length=1,max_length=200)
    owner: str = Field(min_length=1,max_length=200)

class GroupInput(BaseModel):
    expected_hash: str
    groups: list[WorkGroupInput] = Field(min_length=1,max_length=200)
    reason: str = Field(default="인계자가 업무 묶음과 담당자를 확인했습니다.",min_length=1,max_length=1000)

class DeliveryInput(BaseModel):
    revision_id: str = Field(min_length=1,max_length=80)
    expected_hash: str = Field(min_length=1,max_length=80)
    recipient_id: str
    message: str = Field(min_length=1,max_length=2000)


class ConfirmInput(BaseModel):
    expected_hash: str
    acknowledge_warnings: bool = False


def create_app(data_dir=None, model_config=None):
    # Explicit test/embedded data directories never load deployment .env settings.
    local_settings = dotenv_values(ROOT / ".env") if data_dir is None else {}
    def setting(name, default=""):
        return os.getenv(name, local_settings.get(name) or default)
    store = Store(data_dir or setting("HANDOVER_DATA_DIR", str(ROOT / "data")))
    model = model_config or {"url": setting("HANDOVER_LLM_URL", "https://api.upstage.ai/v1"), "key": setting("HANDOVER_LLM_KEY"), "model": setting("HANDOVER_LLM_MODEL", "solar-pro4")}
    shared_solar=None
    if setting('HANDOVER_SOLAR_SHARED_POOL')=='key2':
        from .shared_solar import SharedSolar
        shared_solar=SharedSolar(store,setting('HANDOVER_USAGE_GATEWAY_URL'),setting('HANDOVER_USAGE_METER_TOKEN'),model)
    meter = Meter(store, setting("HANDOVER_LLM_BUDGET_USD", "100"),shared_solar)
    model["_meter"] = meter
    meter.summary(model)
    access_token = setting("HANDOVER_ACCESS_TOKEN")
    vision = Vision(store, {"key":setting("HANDOVER_VISION_KEY"),"url":setting("HANDOVER_VISION_URL","https://api.openai.com/v1"),"gateway":setting("HANDOVER_USAGE_GATEWAY_URL"),"meter_token":setting("HANDOVER_USAGE_METER_TOKEN")})
    runner = JobRunner(store, model, vision)

    @asynccontextmanager
    async def lifespan(app):
        yield
        runner.close()

    app = FastAPI(title="업무바통", version="1.6.7", lifespan=lifespan)
    app.state.store, app.state.runner = store, runner

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        # Pydantic's default error includes rejected inputs, potentially including API keys.
        names = sorted({str(error["loc"][-1]) for error in exc.errors()})
        return JSONResponse({"detail": "입력값을 확인해 주세요: " + ", ".join(names)}, status_code=422)

    @app.middleware("http")
    async def boundary(request, call_next):
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            length = request.headers.get("content-length", "0")
            if not length.isdigit() or int(length) > MAX_TOTAL + 1048576:
                return JSONResponse({"detail": "요청 용량 제한을 초과했습니다."}, status_code=413)
            origin = request.headers.get("origin")
            if origin and urlparse(origin).netloc != request.headers.get("host"):
                return JSONResponse({"detail": "동일 출처 요청만 허용합니다."}, status_code=403)
        if access_token and request.url.path.startswith("/api/") and request.url.path not in {"/api/login", "/api/health"}:
            supplied = request.cookies.get("handover_access", "") or request.headers.get("authorization", "").removeprefix("Bearer ")
            if not secrets.compare_digest(supplied, access_token):
                return JSONResponse({"detail": "접속 코드가 필요합니다."}, status_code=401)
        employee = employee_from(request)
        if employee and employee not in EMPLOYEES:
            return JSONResponse({"detail":"직원 1~4 중 선택해 주세요."}, status_code=422)
        parts = request.url.path.strip("/").split("/")
        role = "predecessor"
        if employee and len(parts) >= 3 and parts[:2] == ["api", "cases"]:
            found = store.one("SELECT id FROM cases WHERE id=?", (parts[2],))
            if found:
                role = member_role(store, parts[2], employee)
                if not role:
                    return JSONResponse({"detail":"선택한 직원의 인수인계함이 아닙니다."}, status_code=403)
        if employee:
            request.scope["headers"] = [(k,v) for k,v in request.scope["headers"] if k.lower()!=b"x-role"] + [(b"x-role",role.encode())]
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["Cache-Control"] = "no-store, no-transform" if response.headers.get("content-type", "").startswith("text/event-stream") else "no-store"
        response.headers.setdefault("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'self'; base-uri 'self'; form-action 'self'")
        return response

    def case(case_id):
        row = store.one("SELECT * FROM cases WHERE id=?", (case_id,))
        if not row:
            raise HTTPException(404, "인수인계함을 찾을 수 없습니다.")
        return row

    def predecessor(role):
        if role != "predecessor":
            raise HTTPException(403, "전임자 역할에서만 수정·확정할 수 있습니다. 역할은 시연용입니다.")

    def idle(case_id):
        if store.one("SELECT id FROM jobs WHERE case_id=? AND status IN ('QUEUED','RUNNING')", (case_id,)):
            raise HTTPException(409, "자료 처리 중입니다. 완료 후 다시 시도해 주세요.")

    def get_revision(case_id, revision_id):
        row = store.one("SELECT * FROM revisions WHERE case_id=? AND id=?", (case_id, revision_id))
        if not row:
            raise HTTPException(404, "해당 인수인계함의 판본이 아닙니다.")
        row["payload"] = json.loads(row["payload"])
        row["warnings"] = warnings_for(row["payload"])
        row["readiness"] = readiness(row["payload"])
        row["confirmation"] = store.one("SELECT * FROM confirmations WHERE case_id=? AND revision=?", (case_id, revision_id))
        return row

    def validate_evidence(db, case_id, payload):
        def check_field(field):
            for ref in field["evidence"]:
                block = db.execute("SELECT * FROM blocks WHERE id=? AND case_id=?", (ref["block_id"], case_id)).fetchone()
                if not block or block["parse_id"] not in payload["corpus"] or ref["document_revision_id"] != block["doc_id"] or ref["parse_id"] != block["parse_id"] or not ref["quote"] or ref["quote"] not in block["text"] or digest(ref["quote"]) != ref["quote_hash"]:
                    raise HTTPException(422, "원문 근거 검증에 실패하여 확정할 수 없습니다.")
            if field.get("previous"):
                check_field(field["previous"])
        for item in payload["items"]:
            for field in item["fields"].values():
                check_field(field)
            for event in item.get("timeline", []) + item.get("supporting_records", []):
                for field in event["fields"].values():
                    check_field(field)
                check_field({"evidence": event.get("metadata_evidence", [])})

    @app.get("/api/health")
    def health():
        return {"status": "ok", "version": "1.6.7"}

    @app.post("/api/login")
    async def login(request: Request):
        body = await request.json()
        if not access_token or not secrets.compare_digest(str(body.get("token", "")), access_token):
            raise HTTPException(401, "접속 코드를 확인해 주세요.")
        response = JSONResponse({"ok": True})
        response.set_cookie("handover_access", access_token, httponly=True, samesite="strict", secure=request.url.scheme == "https", max_age=86400)
        return response

    @app.get("/api/config")
    def config():
        return {"vision_available": vision.available, "llm_available": bool(model["key"]), "model": model["model"] if model["key"] else None, "search": "본문 키워드 검색", "role_mode": "demo", "supported": ["HWP", "HWPX", "PDF", "DOCX", "XLSX", "TXT", "MD"], "limits": {"upload_mb": 80, "file_mb": 20, "files": 100}, "access_protected": bool(access_token)}

    @app.get("/api/budget")
    def budget():
        result = meter.summary(dict(model))
        if result["available"] and not result.get('shared'):
            result["remaining_usd"] = result["budget_usd"] - result["used_usd"]
        return result

    @app.get("/api/budget/images")
    def image_budget():
        return vision.budget()

    @app.post("/api/model")
    def connect_model(body: ModelInput, x_role: str = Header(default="predecessor")):
        predecessor(x_role)
        if body.model not in {"solar-pro4", "solar-mini4"}:
            raise HTTPException(422, "지원하는 Solar 모델을 선택해 주세요.")
        candidate = {"url": "https://api.upstage.ai/v1", "key": body.key.strip(), "model": body.model, "_meter": meter}
        # Only a synthetic one-block probe is sent, never existing user documents.
        try:
            result = llm_discover({"id": "connection-test", "path": "합성 연결 시험.txt"}, [{"id": "probe", "doc_id": "connection-test", "parse_id": "probe", "text": "업무: 합성 연결 시험\n담당: 가상 담당팀\n기한: 2026-12-31\n다음 행동: 결과 확인"}], candidate)
            if not result["candidates"]:
                raise ValueError("연결 시험에서 업무를 추출하지 못했습니다.")
        except Exception as exc:
            message = str(exc) if isinstance(exc, ValueError) else "모델 연결 시험에 실패했습니다. 키와 네트워크를 확인하세요."
            raise HTTPException(422, message) from exc
        with store.connect(write=True) as db:
            if db.execute("SELECT id FROM jobs WHERE status IN ('RUNNING','QUEUED')").fetchone():
                raise HTTPException(409, "진행 중인 자료 처리가 끝난 뒤 연결해 주세요.")
            model.update(candidate)
        return {"ok": True, "model": model["model"], "usage": result["usage"], "note": "키는 현재 서버 프로세스 메모리에만 보관합니다. 재시작 시 다시 연결하거나 전용 .env를 설정하세요."}

    @app.post("/api/employee-demo")
    def employee_demo():
        from .employee_demo import seed
        return seed(store,runner,ROOT)

    @app.post("/api/inheritance-demo")
    def inheritance_demo():
        from .inheritance_demo import seed
        return seed(store,runner,ROOT)

    @app.get("/api/cases")
    def cases(request: Request, include_archived: bool=False):
        rows = store.rows("SELECT c.*,json_extract(r.payload,'$.mode') AS mode FROM cases c LEFT JOIN revisions r ON r.id=c.current ORDER BY c.created DESC,c.id DESC")
        employee = employee_from(request)
        for row in rows:
            row.update(memberships(store,row["id"]))
            row["delivery"] = store.one("SELECT revision_id,sent_at FROM handover_deliveries WHERE case_id=? ORDER BY sent_at DESC LIMIT 1",(row["id"],))
            row["my_role"] = member_role(store,row["id"],employee) if employee else None
        return [r for r in rows if not employee or (r["my_role"] and (include_archived or not r["archived"]))]

    @app.post("/api/cases", status_code=201)
    def create_case(body: CaseInput, request: Request, x_role: str = Header(default="predecessor")):
        predecessor(x_role)
        owner = employee_from(request) or body.predecessor_id or "employee1"
        if owner not in EMPLOYEES:raise HTTPException(422,"직원 1~4 중 선택해 주세요.")
        recipient = body.successor_id or "employee" + str(int(owner[-1]) % 4 + 1)
        if owner not in EMPLOYEES or recipient not in EMPLOYEES or owner == recipient:
            raise HTTPException(422,"인계자와 인수자를 서로 다른 직원으로 선택하세요.")
        if body.predecessor_id and body.predecessor_id != owner:
            raise HTTPException(403,"자신의 인계함만 만들 수 있습니다.")
        case_id = uid()
        with store.connect(write=True) as db:
            db.execute("INSERT INTO cases VALUES (?,?,?,?,?,?,?,?)", (case_id, body.title.strip(), body.predecessor, body.successor, now(), None, None, None))
            db.execute("INSERT INTO case_members VALUES (?,?,?)",(case_id,owner,recipient))
        return case(case_id)

    @app.post("/api/demo-sets", status_code=201)
    def demo_set(body: DemoSetInput, request: Request):
        owner=employee_from(request) or body.predecessor_id
        if owner!=body.predecessor_id:raise HTTPException(403,"선택한 인계자 화면으로 전환한 뒤 실행하세요.")
        if owner not in EMPLOYEES or body.successor_id not in EMPLOYEES or owner==body.successor_id:
            raise HTTPException(422,"인계자와 인수자를 서로 다른 직원으로 선택하세요.")
        titles={"comprehensive":"종합 인수인계 실무 시연","practice":"4개 업무 복합 처리 시연","versions":"파일명, 버전 혼선 시연","inheritance":"업무연결 시연"}
        with store.connect(write=True) as db:
            db.execute("INSERT INTO demo_sequences VALUES (?,1) ON CONFLICT(kind) DO UPDATE SET number=number+1",(body.kind,))
            number=db.execute("SELECT number FROM demo_sequences WHERE kind=?",(body.kind,)).fetchone()[0]
        title=f"{titles[body.kind]} ({number})"
        if body.kind in {"inheritance","comprehensive"}:
            from .inheritance_demo import seed
            previous=next(i for i in range(1,5) if f"employee{i}" not in {owner,body.successor_id})
            options={"base_pack":"comprehensive-base.zip","target_packs":("comprehensive-current.zip","comprehensive-old.zip","comprehensive-draft.zip")} if body.kind=="comprehensive" else {}
            return seed(store,runner,ROOT,source_id=uid(),target_id=uid(),title=title,owner=int(owner[-1]),recipient=int(body.successor_id[-1]),previous=previous,**options)
        new=create_case(CaseInput(title=title,predecessor=EMPLOYEES[owner],successor=EMPLOYEES[body.successor_id],predecessor_id=owner,successor_id=body.successor_id),request,x_role="predecessor")
        filename="practice-samples.zip" if body.kind=="practice" else "version-samples.zip"
        with store.connect(write=True) as db:store.audit(db,new["id"],"DEMO_SET",{"kind":body.kind,"image_processing":"manual-only-poc7-priority"})
        ingest(new["id"],filename,(ROOT/"release/public"/filename).read_bytes())
        return {"target_case_id":new["id"],"employee":owner,"title":title}

    @app.get("/api/cases/{case_id}")
    def details(case_id: str, request: Request):
        row = case(case_id)
        row.update(memberships(store,case_id))
        with store.connect() as db:row["demo_image_manual_only"]=demo_policy.is_demo(db,case_id,ROOT)
        row["my_role"] = member_role(store,case_id,employee_from(request))
        documents = store.rows("SELECT d.*,p.id AS parse_id,p.status,p.warnings FROM documents d LEFT JOIN parses p ON p.id=(SELECT id FROM parses WHERE doc_id=d.id ORDER BY (parser=?) DESC,created DESC LIMIT 1) WHERE d.case_id=? ORDER BY d.created,d.path", (PARSER_VERSION, case_id))
        for doc in documents:
            doc["warnings"] = json.loads(doc["warnings"] or "[]")
            doc["status"] = doc["status"] or "PENDING"
            doc["block_count"] = store.one("SELECT count(*) AS n FROM blocks WHERE parse_id=?", (doc["parse_id"],))["n"]
        row["deliveries"] = store.rows("SELECT * FROM handover_deliveries WHERE case_id=? ORDER BY sent_at DESC",(case_id,))
        row["documents"] = documents
        row["jobs"] = store.rows("SELECT id,status,stage,progress,attempts,error,created,updated,result FROM jobs WHERE case_id=? ORDER BY created DESC", (case_id,))
        row["history"] = store.rows("SELECT r.id,r.parent,r.hash,r.created,r.actor,r.reason,c.created AS confirmed_at FROM revisions r LEFT JOIN confirmations c ON c.revision=r.id WHERE r.case_id=? ORDER BY r.created DESC", (case_id,))
        return row

    def ingest(case_id, name, data):
        case(case_id)
        idle(case_id)
        try:
            entries = unpack_upload(name, data)
        except InputError as exc:
            raise HTTPException(422, str(exc)) from exc
        return register_entries(case_id, entries)

    def register_entries(case_id, entries):
        case(case_id)
        registered = []
        with store.connect(write=True) as db:
            active = db.execute("SELECT id FROM jobs WHERE case_id=? AND status IN ('RUNNING','QUEUED')", (case_id,)).fetchone()
            if active:
                raise HTTPException(409, "처리 중에는 자료를 변경할 수 없습니다.")
            fresh = sum(not db.execute("SELECT id FROM documents WHERE case_id=? AND path=? AND sha=?", (case_id, path, digest(raw))).fetchone() for path, raw in entries)
            if db.execute("SELECT count(*) FROM documents WHERE case_id=?", (case_id,)).fetchone()[0] + fresh > 200:
                raise HTTPException(422, "인수인계함당 최대 200개 파일 판본을 보관할 수 있습니다.")
            for path, raw in entries:
                sha = digest(raw)
                old = db.execute("SELECT id FROM documents WHERE case_id=? AND path=? AND sha=?", (case_id, path, sha)).fetchone()
                if old:
                    registered.append({"id": old[0], "path": path, "duplicate": True})
                    continue
                doc_id = uid()
                target = store.root / "raw" / sha
                if not target.exists():
                    with target.open("xb") as f:
                        f.write(raw)
                db.execute("INSERT INTO documents VALUES (?,?,?,?,?,?)", (doc_id, case_id, path, sha, Path(path).suffix.lower(), now()))
                registered.append({"id": doc_id, "path": path, "duplicate": False})
            store.audit(db, case_id, "UPLOAD", registered)
        return {"documents": registered}

    @app.post("/api/cases/{case_id}/documents")
    async def upload(case_id: str, file: UploadFile = File(...), x_role: str = Header(default="predecessor")):
        predecessor(x_role)
        data = await file.read(MAX_TOTAL + 1)
        return ingest(case_id, file.filename or "upload", data)

    @app.post("/api/cases/{case_id}/documents/batch")
    async def upload_batch(case_id: str, files: list[UploadFile] = File(...), x_role: str = Header(default="predecessor")):
        predecessor(x_role)
        case(case_id)
        idle(case_id)
        if not 1 <= len(files) <= MAX_FILES:
            raise HTTPException(422, "한 번에 1~100개 파일을 등록할 수 있습니다.")
        entries, wire_size, expanded_size = [], 0, 0
        try:
            for file in files:
                data = await file.read(MAX_TOTAL + 1)
                wire_size += len(data)
                if wire_size > MAX_TOTAL:
                    raise InputError("전체 업로드는 80MB 이하만 가능합니다.")
                batch = unpack_upload(file.filename or "upload", data)
                expanded_size += sum(len(raw) for _, raw in batch)
                entries.extend(batch)
                if len(entries) > MAX_FILES or expanded_size > MAX_TOTAL:
                    raise InputError("압축 해제 후에도 총 100개 파일·80MB 이하만 가능합니다.")
            # Same path with distinct content is a version, not a filename error.
        except InputError as exc:
            raise HTTPException(422, str(exc)) from exc
        return register_entries(case_id, entries)

    @app.get("/api/demo.zip")
    def demo_zip(expanded: bool = False):
        return Response(expanded_archive() if expanded else demo_archive(), media_type="application/zip", headers={"Content-Disposition": 'attachment; filename="handover-synthetic.zip"'})

    @app.get("/samples/flow.zip")
    def flow_sample():
        frozen=Path(__file__).resolve().parents[1]/"release/public/flow-samples.zip"
        return Response(frozen.read_bytes() if frozen.exists() else flow_archive(),media_type="application/zip",headers={"Content-Disposition": 'attachment; filename="flow-samples.zip"'})

    @app.get("/samples/practice.zip")
    def practice_sample():
        frozen=ROOT/"release/public/practice-samples.zip"
        return Response(frozen.read_bytes() if frozen.exists() else practice_archive(),media_type="application/zip",headers={"Content-Disposition": 'attachment; filename="practice-samples.zip"'})

    @app.get("/samples/employee-kit.zip")
    def employee_kit():
        return FileResponse(ROOT/"release/public/employee-kit.zip",media_type="application/zip",filename="employee-kit.zip")

    @app.get("/api/cases/{case_id}/images/{image_sha}")
    def source_image(case_id: str,image_sha: str):
        case(case_id)
        # Authorization is membership-scoped by middleware, association is block-scoped here.
        if len(image_sha)!=64 or any(c not in "0123456789abcdef" for c in image_sha):raise HTTPException(404)
        rows=store.rows("SELECT payload FROM revisions WHERE case_id=?",(case_id,))
        if not any(v.get("image_sha")==image_sha for row in rows for i in json.loads(row["payload"])["items"] for v in i.get("image_reviews",[])):raise HTTPException(404)
        return FileResponse(store.root/"images"/image_sha,media_type="image/png")

    @app.get("/samples/versions.zip")
    def version_sample():
        return FileResponse(ROOT/"release/public/version-samples.zip",media_type="application/zip",filename="version-samples.zip")

    @app.post("/api/cases/{case_id}/versions-demo")
    def versions_demo(case_id: str, x_role: str = Header(default="predecessor")):
        predecessor(x_role)
        return ingest(case_id,"version-samples.zip",(ROOT/"release/public/version-samples.zip").read_bytes())

    @app.post("/api/cases/{case_id}/practice-demo")
    def practice_demo(case_id: str, x_role: str = Header(default="predecessor")):
        predecessor(x_role)
        return ingest(case_id,"practice-samples.zip",practice_sample().body)

    @app.post("/api/cases/{case_id}/flow-demo")
    def flow_demo(case_id: str, x_role: str = Header(default="predecessor")):
        predecessor(x_role)
        return ingest(case_id,"flow-samples.zip",flow_sample().body)

    @app.post("/api/cases/{case_id}/demo")
    def demo(case_id: str, x_role: str = Header(default="predecessor")):
        predecessor(x_role)
        return ingest(case_id, "demo.zip", demo_archive())

    @app.get("/api/cases/{case_id}/inheritance-options")
    def inheritance_options(case_id: str, x_role: str = Header(default="predecessor")):
        predecessor(x_role)
        case(case_id)
        with store.connect() as db:return inheritance.candidates(db,case_id)

    @app.post("/api/cases/{case_id}/generate", status_code=202)
    def generate(case_id: str, body: GenerateInput, x_role: str = Header(default="predecessor")):
        predecessor(x_role)
        case(case_id)
        if body.mode not in {"rules", "llm"}:
            raise HTTPException(422, "추출 모드를 확인해 주세요.")
        if body.mode == "llm" and (not model["key"] or not body.external_consent):
            raise HTTPException(422, "LLM 연결과 공개·합성 자료의 외부 전송 동의가 필요합니다.")
        if body.image_consent and not vision.available:
            raise HTTPException(422,"GPT 그림 판독 연결을 확인해 주세요.")
        with store.connect(write=True) as db:
            row = db.execute("SELECT * FROM cases WHERE id=?", (case_id,)).fetchone()
            active = db.execute("SELECT id FROM jobs WHERE case_id=? AND status IN ('QUEUED','RUNNING')", (case_id,)).fetchone()
            if active:return {"job_id":active[0],"reused":True}
            if bool(body.basis_case_id)!=bool(body.basis_revision_id):raise HTTPException(422,"이전 보고서와 확정 판본을 함께 선택하세요.")
            basis=inheritance.freeze(db,store,case_id,body.basis_case_id,body.basis_revision_id) if body.basis_case_id else None
            # Compare every immutable version by body metadata, never upload order.
            documents = db.execute("SELECT d.id FROM documents d WHERE d.case_id=? AND NOT EXISTS (SELECT 1 FROM inherited_documents i WHERE i.doc_id=d.id) ORDER BY d.path,d.sha", (case_id,)).fetchall()
            if not documents and not basis:
                raise HTTPException(422, "먼저 업무자료를 등록하거나 이전 보고서를 선택해 주세요.")
            cfg = {"document_ids": [d[0] for d in documents], "mode": body.mode, "model": model["model"] if body.mode == "llm" else "label-rules-v1", "model_url": model["url"] if body.mode == "llm" else None, "parent": row["current"], "parser": PARSER_VERSION, "external_consent": body.external_consent, "flow_version": "all-immutable-versions-v2", "image_consent": body.image_consent, "prompt_hash": digest(model.get("extraction_prompt") or EXTRACTION_PROMPT) if body.mode == "llm" else None}
            cfg["basis"]=basis
            cfg["registered_document_ids"]=[d[0] for d in db.execute("SELECT id FROM documents WHERE case_id=?",(case_id,))]
            input_hash = digest({k: v for k, v in cfg.items() if k != "parent"} | {"request_id": body.request_id}) if body.request_id else digest(cfg)
            active = db.execute("SELECT id FROM jobs WHERE case_id=? AND status IN ('QUEUED','RUNNING')", (case_id,)).fetchone()
            if active:
                return {"job_id": active[0], "reused": True}
            old = db.execute("SELECT id,status FROM jobs WHERE case_id=? AND input_hash=?", (case_id, input_hash)).fetchone()
            if old:
                return {"job_id": old[0], "reused": True}
            job_id = uid()
            db.execute("INSERT INTO jobs VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", (job_id, case_id, input_hash, "QUEUED", "QUEUE", 0, 1, "", now(), now(), None, dump(cfg)))
        runner.enqueue(job_id)
        return {"job_id": job_id, "reused": False}

    @app.post("/api/cases/{case_id}/jobs/{job_id}/retry")
    def retry(case_id: str, job_id: str, x_role: str = Header(default="predecessor")):
        predecessor(x_role)
        case(case_id)
        with store.connect(write=True) as db:
            job = db.execute("SELECT * FROM jobs WHERE id=? AND case_id=?", (job_id, case_id)).fetchone()
            if not job:
                raise HTTPException(404, "작업을 찾을 수 없습니다.")
            if job["status"] not in {"FAILED", "INTERRUPTED"}:
                raise HTTPException(409, "실패·중단된 작업만 재시도할 수 있습니다.")
            if db.execute("SELECT id FROM jobs WHERE case_id=? AND status IN ('QUEUED','RUNNING')", (case_id,)).fetchone():
                raise HTTPException(409, "다른 작업이 진행 중입니다.")
            retry_config=json.loads(job["config"])
            all_ids={r[0] for r in db.execute("SELECT id FROM documents WHERE case_id=?",(case_id,))}
            if set(retry_config.get("registered_document_ids",retry_config["document_ids"]))!=all_ids:
                raise HTTPException(409,"등록된 모든 판본을 비교하려면 새 초안을 생성해 주세요.")
            current = db.execute("SELECT current FROM cases WHERE id=?", (case_id,)).fetchone()[0]
            if json.loads(job["config"])["parent"] != current:
                raise HTTPException(409, "초안이 변경되었습니다. 새 초안 생성으로 진행하세요.")
            db.execute("UPDATE jobs SET status='QUEUED',attempts=attempts+1,error='',updated=? WHERE id=?", (now(), job_id))
        runner.enqueue(job_id)
        return {"job_id": job_id}

    @app.get("/api/cases/{case_id}/revisions/{revision_id}")
    def revision(case_id: str, revision_id: str, x_role: str = Header(default="predecessor")):
        row = case(case_id)
        revision_id = row["confirmed"] if revision_id == "confirmed" else row["current"] if revision_id == "current" else revision_id
        if not revision_id:
            return None
        result = get_revision(case_id, revision_id)
        if x_role == "successor" and not result["confirmation"]:
            raise HTTPException(403, "후임자는 확정된 판본만 열람할 수 있습니다.")
        return result

    @app.patch("/api/cases/{case_id}/revisions/{revision_id}/items/{item_id}")
    def edit(case_id: str, revision_id: str, item_id: str, body: EditInput, x_role: str = Header(default="predecessor")):
        predecessor(x_role)
        case(case_id)
        if not set(body.fields) <= set(FIELDS) or any(len(v) > 2000 for v in body.fields.values()):
            raise HTTPException(422, "허용되지 않은 필드 또는 너무 긴 값입니다.")
        with store.connect(write=True) as db:
            row = db.execute("SELECT * FROM revisions WHERE id=? AND case_id=?", (revision_id, case_id)).fetchone()
            current = db.execute("SELECT current FROM cases WHERE id=?", (case_id,)).fetchone()[0]
            if not row or current != revision_id or row["hash"] != body.expected_hash:
                raise HTTPException(409, "초안이 변경되었습니다. 새로 고친 후 수정해 주세요.")
            if db.execute("SELECT id FROM jobs WHERE case_id=? AND status IN ('QUEUED','RUNNING')", (case_id,)).fetchone():
                raise HTTPException(409, "자료 처리가 끝난 뒤 수정해 주세요.")
            payload = json.loads(row["payload"])
            item = next((i for i in payload["items"] if i["id"] == item_id), None)
            if item_id == "new" and not body.delete:
                item = {"id": uid(), "fields": {k: empty_field() for k in FIELDS}, "source_documents": [], "related_blocks": []}
                payload["items"].append(item)
            if not item:
                raise HTTPException(404, "업무 항목을 찾을 수 없습니다.")
            if body.delete:
                payload["items"].remove(item)
            else:
                for key, value in body.fields.items():
                    previous = copy.deepcopy(item["fields"].get(key, empty_field()))
                    item["fields"][key] = {"value": value.strip(), "provenance": "HUMAN_ENTERED", "review_status": "CONFIRMED" if value.strip() else "NEEDS_CONFIRMATION", "evidence": [], "observations": [], "previous": previous, "reason": body.reason, "actor": "PREDECESSOR", "changed_at": now()}
                if not item["fields"]["title"]["value"]:
                    raise HTTPException(422, "업무명은 비워 둘 수 없습니다.")
            annotate_items(payload["items"])
            new_id = store.revision(db, case_id, payload, revision_id, body.reason)
        return get_revision(case_id, new_id)

    @app.post("/api/cases/{case_id}/revisions/{revision_id}/groups")
    def group_work(case_id: str,revision_id: str,body: GroupInput,x_role: str=Header(default="predecessor")):
        from .grouping import regroup
        predecessor(x_role)
        case(case_id)
        with store.connect(write=True) as db:
            row=db.execute("SELECT * FROM revisions WHERE id=? AND case_id=?",(revision_id,case_id)).fetchone()
            current=db.execute("SELECT current FROM cases WHERE id=?",(case_id,)).fetchone()[0]
            if not row or current!=revision_id or row["hash"]!=body.expected_hash:raise HTTPException(409,"초안이 변경되었습니다. 묶음 창을 다시 열어 주세요.")
            if db.execute("SELECT id FROM jobs WHERE case_id=? AND status IN ('QUEUED','RUNNING')",(case_id,)).fetchone():raise HTTPException(409,"자료 처리가 끝난 뒤 묶어 주세요.")
            payload=json.loads(row["payload"])
            try:payload=regroup(payload,[g.model_dump() for g in body.groups],body.reason.strip())
            except ValueError as exc:raise HTTPException(422,str(exc)) from exc
            validate_evidence(db,case_id,payload)
            new_id=store.revision(db,case_id,payload,revision_id,"업무 묶음 확인: "+body.reason.strip())
        return get_revision(case_id,new_id)

    @app.post("/api/cases/{case_id}/revisions/{revision_id}/match")
    def match_work(case_id: str, revision_id: str, body: MatchInput, x_role: str = Header(default="predecessor")):
        predecessor(x_role)
        if body.source_id == body.target_id or not body.owner.strip() or not body.reason.strip():
            raise HTTPException(422, "서로 다른 업무와 확인한 담당·매칭 사유가 필요합니다.")
        with store.connect(write=True) as db:
            row=db.execute("SELECT * FROM revisions WHERE id=? AND case_id=?",(revision_id,case_id)).fetchone()
            current=db.execute("SELECT current FROM cases WHERE id=?",(case_id,)).fetchone()
            if not row or not current or current[0]!=revision_id or row["hash"]!=body.expected_hash:
                raise HTTPException(409,"초안이 변경되었습니다. 새로 고친 후 매칭해 주세요.")
            if db.execute("SELECT id FROM jobs WHERE case_id=? AND status IN ('QUEUED','RUNNING')",(case_id,)).fetchone():
                raise HTTPException(409,"자료 처리가 끝난 뒤 매칭해 주세요.")
            payload=json.loads(row["payload"])
            target=next((i for i in payload["items"] if i["id"]==body.target_id),None)
            source=next((i for i in payload["items"] if i["id"]==body.source_id),None)
            if not target or not source:raise HTTPException(404,"현재 초안의 업무 항목을 찾을 수 없습니다.")
            if not source.get("timeline") or not target.get("timeline"):
                raise HTTPException(422,"보고 흐름이 없는 구버전 초안입니다. 자료에서 새 초안을 만들어 주세요.")
            before=copy.deepcopy(target["fields"]["owner"])
            record={"source_id":source["id"],"source_title":source["fields"]["title"]["value"],"target_title":target["fields"]["title"]["value"],"reason":body.reason.strip(),"owner":body.owner.strip(),"actor":"PREDECESSOR","created":now()}
            target.setdefault("timeline",[]).extend(source["timeline"])
            target.setdefault("supporting_records",[]).extend(source.get("supporting_records",[]))
            target["source_documents"]=sorted(set(target["source_documents"]+source["source_documents"]))
            target["related_blocks"]=sorted(set(target.get("related_blocks",[])+source.get("related_blocks",[])))
            target.setdefault("match_history",[]).extend(source.get("match_history",[])+[record])
            project_latest(target)
            target["fields"]["owner"]={"value":body.owner.strip(),"provenance":"HUMAN_ENTERED","review_status":"CONFIRMED","evidence":[],"observations":[],"previous":before,"reason":body.reason.strip(),"actor":"PREDECESSOR","changed_at":now()}
            target["merge_note"]="담당자가 관련 문서를 같은 업무로 확인·매칭했습니다."
            payload["items"].remove(source);annotate_items(payload["items"])
            new_id=store.revision(db,case_id,payload,revision_id,"업무 매칭: "+body.reason.strip())
        return get_revision(case_id,new_id)

    @app.post("/api/cases/{case_id}/revisions/{revision_id}/confirm")
    def confirm(case_id: str, revision_id: str, body: ConfirmInput, x_role: str = Header(default="predecessor")):
        predecessor(x_role)
        case(case_id)
        with store.connect(write=True) as db:
            row = db.execute("SELECT * FROM revisions WHERE id=? AND case_id=?", (revision_id, case_id)).fetchone()
            current = db.execute("SELECT current FROM cases WHERE id=?", (case_id,)).fetchone()[0]
            if not row or current != revision_id or row["hash"] != body.expected_hash:
                raise HTTPException(409, "현재 초안과 확인한 판본이 다릅니다. 새로 고침이 필요합니다.")
            if db.execute("SELECT id FROM jobs WHERE case_id=? AND status IN ('RUNNING','QUEUED')", (case_id,)).fetchone():
                raise HTTPException(409, "진행 중인 자료 처리가 있습니다.")
            payload = json.loads(row["payload"])
            latest = [r[0] for r in db.execute("SELECT d.id FROM documents d WHERE d.case_id=?", (case_id,))]
            if set(latest) != set(payload["document_ids"]):
                raise HTTPException(409, "새 자료가 등록되었습니다. 새 초안을 생성한 뒤 확정해 주세요.")
            validate_evidence(db, case_id, payload)
            warnings = warnings_for(payload)
            if warnings and not body.acknowledge_warnings:
                raise HTTPException(422, "미확인·부분 추출 항목을 확인한 뒤 확정해 주세요.")
            if not payload["items"]:
                raise HTTPException(422, "업무가 없는 초안은 확정할 수 없습니다.")
            already = db.execute("SELECT confirmed FROM cases WHERE id=?", (case_id,)).fetchone()[0] == revision_id
            db.execute("INSERT OR IGNORE INTO confirmations VALUES (?,?,?,?,?)", (revision_id, case_id, row["hash"], now(), dump(warnings)))
            if not already:
                db.execute("UPDATE cases SET confirmed=?,accepted=NULL WHERE id=?", (revision_id, case_id))
                store.audit(db, case_id, "CONFIRM", {"revision": revision_id, "hash": row["hash"], "warnings": warnings})
        return get_revision(case_id, revision_id)

    @app.post("/api/cases/{case_id}/deliver")
    def deliver(case_id: str, body: DeliveryInput, x_role: str = Header(default="predecessor")):
        predecessor(x_role)
        info=case(case_id)
        message=body.message.strip()
        if not message:raise HTTPException(422,"전달 의견을 입력해 주세요.")
        with store.connect(write=True) as db:
            members=db.execute("SELECT * FROM case_members WHERE case_id=?",(case_id,)).fetchone()
            recipient=members["successor_id"] if members else "employee2"
            sender=members["predecessor_id"] if members else "employee1"
            if body.recipient_id!=recipient:raise HTTPException(409,"이 인수인계함의 인수자가 변경되었습니다. 다시 확인해 주세요.")
            info=db.execute("SELECT * FROM cases WHERE id=?",(case_id,)).fetchone()
            row=db.execute("SELECT * FROM revisions WHERE id=? AND case_id=?",(body.revision_id,case_id)).fetchone()
            if not row or info["confirmed"]!=body.revision_id or info["current"]!=body.revision_id or row["hash"]!=body.expected_hash:
                raise HTTPException(409,"최신 초안을 검토·확정한 뒤 인계해 주세요.")
            if db.execute("SELECT 1 FROM jobs WHERE case_id=? AND status IN ('RUNNING','QUEUED')",(case_id,)).fetchone():
                raise HTTPException(409,"자료 처리 완료 후 인계해 주세요.")
            payload=json.loads(row["payload"])
            docs={r[0] for r in db.execute("SELECT id FROM documents WHERE case_id=?",(case_id,))}
            if docs!=set(payload["document_ids"]):raise HTTPException(409,"새 자료가 등록되었습니다. 새 초안을 생성·확정한 뒤 인계해 주세요.")
            old=db.execute("SELECT * FROM handover_deliveries WHERE case_id=? AND revision_id=?",(case_id,body.revision_id)).fetchone()
            if old:
                if old["message"]!=message or old["recipient_id"]!=recipient:raise HTTPException(409,"이 판본은 이미 인계되었습니다. 전달 기록은 변경할 수 없습니다.")
                return dict(old)
            if info["accepted"]:raise HTTPException(409,"이미 인수 완료된 판본입니다. 새 내용을 반영한 판본으로 인계해 주세요.")
            ident=uid();stamp=now()
            db.execute("INSERT INTO handover_deliveries VALUES (?,?,?,?,?,?,?,?)",(ident,case_id,body.revision_id,row["hash"],sender,recipient,message,stamp))
            store.audit(db,case_id,"HANDOVER_DELIVER",{"delivery_id":ident,"revision":body.revision_id,"hash":row["hash"],"recipient_id":recipient})
            return {"id":ident,"case_id":case_id,"revision_id":body.revision_id,"revision_hash":row["hash"],"sender_id":sender,"recipient_id":recipient,"message":message,"sent_at":stamp}

    @app.post("/api/cases/{case_id}/accept")
    def accept(case_id: str, body: ConfirmInput, x_role: str = Header(default="predecessor")):
        if x_role != "successor":
            raise HTTPException(403, "후임자 역할에서 확인해 주세요.")
        with store.connect(write=True) as db:
            row = db.execute("SELECT r.* FROM cases c JOIN revisions r ON r.id=c.confirmed WHERE c.id=?", (case_id,)).fetchone()
            if not row or row["hash"] != body.expected_hash:
                raise HTTPException(409, "확정본이 변경되었거나 아직 없습니다.")
            accepted = db.execute("SELECT accepted FROM cases WHERE id=?", (case_id,)).fetchone()[0]
            if not accepted:
                db.execute("UPDATE cases SET accepted=? WHERE id=?", (now(), case_id))
                store.audit(db, case_id, "SUCCESSOR_ACCEPT", {"revision": row["id"]})
        return {"ok": True}

    @app.get("/api/cases/{case_id}/blocks/{block_id}")
    def block(case_id: str, block_id: str):
        case(case_id)
        result = store.one("SELECT b.*,d.path,d.sha AS source_sha FROM blocks b JOIN documents d ON b.doc_id=d.id WHERE b.id=? AND b.case_id=?", (block_id, case_id))
        if not result:
            raise HTTPException(404, "이 인수인계함에서 근거를 찾을 수 없습니다.")
        result["neighbors"] = store.rows("SELECT id,location,text FROM blocks WHERE parse_id=? AND ordinal BETWEEN ? AND ? ORDER BY ordinal", (result["parse_id"], result["ordinal"] - 2, result["ordinal"] + 2))
        return result

    @app.get("/api/cases/{case_id}/documents/{document_id}/blocks")
    def document_blocks(case_id: str, document_id: str):
        case(case_id)
        if not store.one("SELECT id FROM documents WHERE id=? AND case_id=?", (document_id, case_id)):
            raise HTTPException(404, "자료를 찾을 수 없습니다.")
        return store.rows("SELECT b.* FROM blocks b JOIN parses p ON p.id=b.parse_id WHERE b.doc_id=? AND b.case_id=? AND p.id=(SELECT id FROM parses WHERE doc_id=? ORDER BY (parser=?) DESC,created DESC LIMIT 1) ORDER BY b.ordinal", (document_id, case_id, document_id, PARSER_VERSION))

    @app.get("/api/cases/{case_id}/documents/{document_id}/raw")
    def raw_document(case_id: str, document_id: str):
        doc = store.one("SELECT * FROM documents WHERE id=? AND case_id=?", (document_id, case_id))
        if not doc:
            raise HTTPException(404, "자료를 찾을 수 없습니다.")
        return FileResponse(store.root / "raw" / doc["sha"], filename=Path(doc["path"]).name, media_type="application/octet-stream")

    @app.get("/api/cases/{case_id}/search")
    def search(case_id: str, q: str = "", x_role: str = Header(default="predecessor")):
        row = case(case_id)
        pointer = row["confirmed"] if x_role == "successor" else row["current"]
        if not pointer:
            return {"results": [], "revision": None, "mode": "본문 키워드 검색"}
        payload = get_revision(case_id, pointer)["payload"]
        blocks = store.rows("SELECT b.*,d.path FROM blocks b JOIN documents d ON b.doc_id=d.id WHERE b.case_id=?", (case_id,))
        blocks = [b for b in blocks if b["parse_id"] in payload["corpus"]]
        return {"results": search_blocks(blocks, q[:300], 5), "revision": pointer, "mode": "본문 키워드 검색"}

    @app.post("/api/cases/{case_id}/reindex")
    def reindex(case_id: str, x_role: str = Header(default="predecessor")):
        predecessor(x_role)
        case(case_id)
        with store.connect(write=True) as db:
            db.execute("REINDEX blocks_case")
            store.audit(db, case_id, "REINDEX", {"engine": "local-keyword-v1", "immutable_sources": True})
        return {"ok": True, "engine": "local-keyword-v1"}

    @app.get("/api/cases/{case_id}/briefing")
    def successor_briefing(case_id: str):
        info = case(case_id)
        if not info["confirmed"]:
            raise HTTPException(409, "먼저 인수인계 보고서를 확정해 주세요.")
        rev = get_revision(case_id, info["confirmed"])
        return briefing(rev, datetime.now(ZoneInfo("Asia/Seoul")).date())

    def prepare_question(case_id, body):
        info = case(case_id)
        if not info["confirmed"] or info["confirmed"] != body.expected_revision:
            raise HTTPException(409, "확정본이 없거나 변경되었습니다. 최신 보고서를 확인해 주세요.")
        if body.mode not in {"local", "llm"} or not body.question.strip():
            raise HTTPException(422, "질문과 조회 방식을 확인해 주세요.")
        if body.mode == "llm" and (not body.external_consent or not model["key"]):
            raise HTTPException(422, "AI 질의에는 모델 연결과 질문·확정본·관련 원문 외부 전송 동의가 필요합니다.")
        if any(not 1 <= len(q) <= 500 for q in body.previous_questions):
            raise HTTPException(422, "이전 질문은 1~500자로 입력해 주세요.")
        rev = get_revision(case_id, info["confirmed"])
        blocks = store.rows("SELECT b.*,d.path FROM blocks b JOIN documents d ON b.doc_id=d.id WHERE b.case_id=?", (case_id,))
        return rev, blocks, dict(model)

    def finish_question(case_id, rev, body, result):
        with store.connect(write=True) as db:
            if db.execute("SELECT confirmed FROM cases WHERE id=?", (case_id,)).fetchone()[0] != rev["id"]:
                raise HTTPException(409, "응답 중 확정본이 변경되었습니다. 최신 보고서에서 다시 질문하세요.")
            store.audit(db, case_id, "QUESTION", {"revision": rev["id"], "mode": body.mode, "status": result["status"], "model": result["model"], "usage": result["usage"]})
        return result

    @app.post("/api/cases/{case_id}/questions")
    def question(case_id: str, body: QuestionInput):
        rev, blocks, config = prepare_question(case_id, body)
        try:
            result = answer_question(rev, body.question.strip(), blocks, body.mode, config, include_sources=body.include_sources, previous_questions=body.previous_questions)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        return finish_question(case_id, rev, body, result)

    @app.post("/api/cases/{case_id}/questions/stream")
    async def question_stream(case_id: str, body: QuestionInput):
        rev, blocks, config = prepare_question(case_id, body)
        async def events():
            queue = asyncio.Queue()
            loop = asyncio.get_running_loop()
            cancelled = threading.Event()
            def emit(kind, value):
                if not cancelled.is_set():
                    loop.call_soon_threadsafe(queue.put_nowait, (kind, value))
            def run():
                try:
                    result = answer_question(rev, body.question.strip(), blocks, body.mode, config,
                        include_sources=body.include_sources, previous_questions=body.previous_questions,
                        on_delta=lambda text: emit('delta', {'text':text}), cancelled=cancelled)
                    if not cancelled.is_set():
                        result = finish_question(case_id, rev, body, result)
                        emit('done', result)
                except (ValueError, HTTPException) as exc:
                    emit('error', {'message':exc.detail if isinstance(exc, HTTPException) else str(exc)})
                except Exception:
                    emit('error', {'message':'답변 연결이 끊겼습니다. 잠시 후 다시 질문해 주세요.'})
            task = asyncio.create_task(asyncio.to_thread(run))
            try:
                yield 'event: start\ndata: '+dump({'revision_id':rev['id']})+'\n\n'
                while True:
                    try: kind, value = await asyncio.wait_for(queue.get(), timeout=10)
                    except asyncio.TimeoutError:
                        yield ': keep-alive\n\n'; continue
                    yield 'event: '+kind+'\ndata: '+dump(value)+'\n\n'
                    if kind in {'done','error'}: break
            finally:
                cancelled.set()
        return StreamingResponse(events(), media_type='text/event-stream',
            headers={'X-Accel-Buffering':'no','Cache-Control':'no-cache, no-transform'})

    def report_data(case_id, revision_id):
        info = case(case_id)
        if revision_id == "confirmed":
            revision_id = info["confirmed"]
        if not revision_id:
            raise HTTPException(404, "아직 확정된 인수인계 보고서가 없습니다.")
        rev = get_revision(case_id, revision_id)
        if not rev["confirmation"]:
            raise HTTPException(403, "확정본을 먼저 만들어 주세요.")
        return build_report(info, rev, lambda block_id: block(case_id, block_id))

    @app.get("/api/cases/{case_id}/reports/{revision_id}")
    def report(case_id: str, revision_id: str):
        return HTMLResponse(render_html(report_data(case_id, revision_id)), headers={"Cache-Control": "no-store", "Content-Security-Policy": report_interactions.csp()})

    @app.get("/api/cases/{case_id}/exports/{revision_id}.{format}")
    def export(case_id: str, revision_id: str, format: str):
        if format not in {"md", "html", "docx"}:
            raise HTTPException(404, "지원하지 않는 출력 형식입니다.")
        data = report_data(case_id, revision_id)
        if format == "docx":
            return Response(render_docx(data), media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document", headers={"Content-Disposition": f'attachment; filename="handover-{data["revision_id"][:8]}.docx"'})
        content = render_html(data) if format == "html" else render_markdown(data)
        return Response(content, media_type="text/html; charset=utf-8" if format == "html" else "text/markdown; charset=utf-8", headers={"Content-Disposition": f'attachment; filename="handover-{data["revision_id"][:8]}.{format}"'})

    @app.get("/guide")
    def guide():
        return FileResponse(ROOT / "app" / "web" / "guide.html")

    @app.get("/downloads/{filename}")
    def download_material(filename: str):
        # A closed manifest, never a path into workspace data or arbitrary repository files.
        directory = ROOT / "release" / "public"
        manifest_path = directory / "manifest.json"
        manifest = json.loads(manifest_path.read_text()) if manifest_path.is_file() else {"files": []}
        allowed = {row["file"] for row in manifest["files"]}
        if filename == "manifest.json" and manifest_path.is_file():
            return FileResponse(manifest_path, media_type="application/json")
        if filename not in allowed or Path(filename).name != filename:
            raise HTTPException(404, "배포 자료를 찾을 수 없습니다.")
        path = directory / filename
        if not path.is_file():
            raise HTTPException(404, "배포 자료를 찾을 수 없습니다.")
        return FileResponse(path, filename=filename, content_disposition_type="inline" if filename in {"flow-report.html", "practice-report.html", "version-report.html", "comprehensive-report.html"} else "attachment", headers={"Content-Security-Policy": report_interactions.csp()} if filename in {"flow-report.html", "practice-report.html", "version-report.html", "comprehensive-report.html"} else None)

    @app.get("/samples/submission.zip")
    def submission_sample():
        path = ROOT / "release" / "public" / "handover-samples.zip"
        if path.is_file():
            return FileResponse(path, filename="handover-samples.zip", media_type="application/zip")
        return Response(submission_archive(), media_type="application/zip", headers={"Content-Disposition": 'attachment; filename="handover-samples.zip"'})

    app.mount("/assets", StaticFiles(directory=ROOT / "app" / "web"), name="assets")

    @app.get("/")
    def index():
        return FileResponse(ROOT / "app" / "web" / "index.html")

    return app
