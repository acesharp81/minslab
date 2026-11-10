import json
from concurrent.futures import ThreadPoolExecutor

from .engine import annotate_items, llm_discover, merge_candidates, rules_discover, structured_profile, search_blocks
from .parsers import PARSER_VERSION, parse
from .prompts import EXTRACTION_PROMPT
from .timeline import attach_timeline, project_latest
from .practice_fields import document_role
from .store import digest, dump, now, uid
from .vision import postprocess
from . import inheritance


class JobRunner:
    def __init__(self, store, model_config, vision=None):
        self.vision = vision
        self.store = store
        self.model_config = model_config
        self.pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="handover")
        with store.connect(write=True) as db:
            db.execute("UPDATE jobs SET status='INTERRUPTED',error='서버가 재시작되었습니다. 완료 단계는 보존되어 있습니다.',updated=? WHERE status IN ('RUNNING','QUEUED')", (now(),))

    def close(self):
        self.pool.shutdown(wait=True)

    def enqueue(self, job_id):
        self.pool.submit(self.run, job_id)

    def update(self, job_id, **fields):
        fields["updated"] = now()
        with self.store.connect(write=True) as db:
            db.execute("UPDATE jobs SET " + ",".join(k + "=?" for k in fields) + " WHERE id=?", (*fields.values(), job_id))

    def run(self, job_id):
        store = self.store
        job = store.one("SELECT * FROM jobs WHERE id=?", (job_id,))
        config = json.loads(job["config"])
        case_id = job["case_id"]
        active_doc = None
        try:
            if config["mode"] == "llm" and (not self.model_config["key"] or config["model"] != self.model_config["model"] or config.get("model_url") != self.model_config["url"]):
                raise ValueError("작업 생성 시점의 모델 연결이 달라졌습니다. 같은 설정을 복원하거나 새 초안을 생성하세요.")
            if config["mode"] == "llm" and config.get("prompt_hash") != digest(self.model_config.get("extraction_prompt") or EXTRACTION_PROMPT):
                raise ValueError("분석 프롬프트가 변경되었습니다. 기존 문서 단계와 혼합하지 않도록 새 초안을 생성해 주세요.")
            self.update(job_id, status="RUNNING", stage="PARSE", progress=5, error="")
            documents = [store.one("SELECT * FROM documents WHERE id=? AND case_id=?", (doc_id, case_id)) for doc_id in config["document_ids"]]
            results, coverage, snapshots = [], [], []
            for n, doc in enumerate(documents):
                active_doc = doc
                parsed = store.one("SELECT * FROM parses WHERE doc_id=? AND parser=?", (doc["id"], PARSER_VERSION))
                if not parsed:
                    status, warnings, blocks = parse(store.root / "raw" / doc["sha"], doc["format"])
                    parse_id = digest([doc["id"], PARSER_VERSION])
                    with store.connect(write=True) as db:
                        db.execute("INSERT INTO parses VALUES (?,?,?,?,?,?)", (parse_id, doc["id"], PARSER_VERSION, status, dump(warnings), now()))
                        for ordinal, block in enumerate(blocks):
                            block_id = digest([parse_id, ordinal, block["text"]])
                            db.execute("INSERT INTO blocks VALUES (?,?,?,?,?,?,?,?,?)", (block_id, case_id, parse_id, doc["id"], ordinal, block["location"], block["kind"], block["text"], digest(block["text"])))
                    parsed = store.one("SELECT * FROM parses WHERE id=?", (parse_id,))
                snapshots.append(parsed["id"])
                blocks = store.rows("SELECT * FROM blocks WHERE parse_id=? ORDER BY ordinal", (parsed["id"],))
                cached = store.one("SELECT payload FROM discovery WHERE job_id=? AND doc_id=?", (job_id, doc["id"]))
                self.update(job_id, stage="DISCOVER", progress=10 + int(65 * n / len(documents)))
                if cached:
                    result = json.loads(cached["payload"])
                else:
                    if document_role(blocks)=='증빙대장':
                        result={"candidates":[],"status":"REFERENCE_ONLY","scanned_blocks":len(blocks),"reviewed_blocks":0,"unreviewed_block_ids":[b['id'] for b in blocks],"note":"증빙대장: 원문 검색·열람용으로 보존하며 독립 업무나 완료 사실을 자동 생성하지 않습니다.","usage":{}}
                    elif not blocks:
                        result = {"candidates": [], "status": "FAILED", "scanned_blocks": 0, "reviewed_blocks": 0, "unreviewed_block_ids": [], "note": "원문 추출 불가", "usage": {}}
                    else:
                        result = structured_profile(doc, blocks)
                        if result is None:result = llm_discover(doc, blocks, self.model_config) if config["mode"] == "llm" else rules_discover(doc, blocks)
                    attach_timeline(result, doc, blocks)
                    with store.connect(write=True) as db:
                        db.execute("INSERT INTO discovery VALUES (?,?,?)", (job_id, doc["id"], dump(result)))
                results.append(result)
                coverage.append({"document_id": doc["id"], "path": doc["path"], "parse_status": parsed["status"], **{k: v for k, v in result.items() if k != "candidates"}})
            self.update(job_id, stage="MERGE", progress=85)
            items = annotate_items([project_latest(i) for i in merge_candidates(results)])
            basis=config.get("basis")
            inherited_summary=None
            if basis:
                items,counts=inheritance.combine(basis,items)
                inherited_summary={"source":basis["source"],"counts":counts}
                snapshots=list(dict.fromkeys(basis["payload"]["corpus"]+snapshots))
                coverage=basis["payload"].get("coverage",[])+coverage
            image_notes=[]
            if config.get("image_consent"):
                self.update(job_id,stage="IMAGES",progress=88)
                image_snapshots,image_notes=postprocess(store,self.vision,items,documents,case_id)
                snapshots.extend(image_snapshots)
            # Supplemental search results are background references, not newly asserted facts.
            corpus = store.rows("SELECT b.*,d.path FROM blocks b JOIN documents d ON b.doc_id=d.id WHERE b.case_id=?", (case_id,))
            corpus = [b for b in corpus if b["parse_id"] in snapshots]
            for item in items:
                item["related_blocks"] = [b["id"] for b in search_blocks(corpus, item["fields"]["title"]["value"], 5)]
            payload = {"items": items, "coverage": coverage, "corpus": snapshots, "document_ids": config.get("registered_document_ids",config["document_ids"]), "mode": config["mode"], "model": config["model"], "parser": PARSER_VERSION, "search": "local-keyword-v1", "report_schema":"practice-v1", "generated_at": now(), "image_notes": image_notes, "image_policy":"latest-selected-only-v1" if config.get("image_consent") else "disabled"}
            if basis:
                payload["inheritance"]=inherited_summary
                payload["handover_chain"]=basis["chain"]
            with store.connect(write=True) as db:
                current = db.execute("SELECT current FROM cases WHERE id=?", (case_id,)).fetchone()[0]
                if current != config["parent"]:
                    raise ValueError("처리 중 초안이 변경되어 자동 교체하지 않았습니다. 새 초안 생성을 다시 실행해 주세요.")
                revision = store.revision(db, case_id, payload, current, "문서별 초안 생성", "SYSTEM")
                db.execute("UPDATE jobs SET status='SUCCEEDED',stage='DONE',progress=100,result=?,updated=? WHERE id=?", (revision, now(), job_id))
        except Exception as exc:
            if hasattr(exc, "diagnostic"):
                with store.connect(write=True) as db:
                    store.audit(db, case_id, "MODEL_FAILURE", {"job_id": job_id, "document_id": active_doc["id"] if active_doc else None, "document_path": active_doc["path"] if active_doc else None, **exc.diagnostic})
            error = str(exc) if isinstance(exc, ValueError) else f"처리 오류 ({type(exc).__name__}). 완료된 문서 단계는 보존했습니다."
            if active_doc and hasattr(exc, "diagnostic"):
                error = active_doc["path"] + ": " + error
            self.update(job_id, status="FAILED", error=error, stage="ERROR")
