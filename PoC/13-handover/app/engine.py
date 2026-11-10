"""Document-wise discovery, validated evidence, conservative merging and search."""
import json
import os
import re
import time
import unicodedata
from collections import defaultdict
from datetime import date

import httpx
from .billing import completion_request

from .store import digest, uid
from .prompts import EXTRACTION_PROMPT
from .practice_fields import PRACTICE_FIELDS, PROFILE_FIELDS, document_role

FIELDS = {"title": "업무명", "status": "현재 상태", "due_date": "기한", "owner": "담당", "next_action": "다음 행동", "notes": "참고 사항", "completed_work": "완료한 일", "remaining_work": "남은 업무", "issues": "현안·장애 사항", "collaborators": "협의·협업 부서", "contacts": "연락처"}
LABELS = {"업무": "title", "업무명": "title", "사업명": "title", "상태": "status", "현재 상태": "status", "진행상태": "status", "기한": "due_date", "마감": "due_date", "제출기한": "due_date", "담당": "owner", "담당자": "owner", "다음 행동": "next_action", "후속조치": "next_action", "다음행동": "next_action", "비고": "notes", "참고": "notes"}
LABELS.update({"완료한 일": "completed_work", "추진 실적": "completed_work", "완료 사항": "completed_work", "남은 업무": "remaining_work", "향후 계획": "remaining_work", "현안": "issues", "장애 사항": "issues", "현안·장애 사항": "issues"})
LABELS.update({"협의 부서": "collaborators", "협업 부서": "collaborators", "연락처": "contacts", "연락망": "contacts"})
FIELDS.update(PRACTICE_FIELDS)
LABELS.update({v:k for k,v in FIELDS.items()})
LABELS.update({v:k for k,v in PRACTICE_FIELDS.items()})
LABEL_RE = re.compile(r"(?:^|[|\n])\s*(?:[A-Z]+\d*:\s*|C\d+:\s*)?(?:[○□-]\s*)?\(?(" + "|".join(sorted(map(re.escape, LABELS), key=len, reverse=True)) + r")(?:\)\s*[:：]?\s*|\s*[:：]\s*)")


def empty_field():
    return {"value": "", "provenance": "AI_PROPOSED", "review_status": "NEEDS_CONFIRMATION", "evidence": [], "observations": []}


def evidence(block, quote):
    if not quote or quote not in block["text"]:
        raise ValueError("원문에 존재하지 않는 인용입니다.")
    return {"id": digest([block["id"], quote])[:32], "block_id": block["id"], "document_revision_id": block["doc_id"], "parse_id": block["parse_id"], "quote": quote, "quote_hash": digest(quote), "verified": True}


def fact(value, block, quote=None):
    return {"value": value, "provenance": "SOURCE_DERIVED", "review_status": "UNREVIEWED", "evidence": [evidence(block, quote or value)], "observations": []}


def rules_discover(document, blocks):
    candidates, current, recognized = [], None, set()
    for block in blocks:
        matches = list(LABEL_RE.finditer(block["text"]))
        if matches and LABELS[matches[0].group(1)] in PROFILE_FIELDS:
            matches=matches[:1] # A labelled multiline brief is one field; nested table labels are data.
        for i, match in enumerate(matches):
            field = LABELS[match.group(1)]
            value = block["text"][match.end():matches[i + 1].start() if i + 1 < len(matches) else None].strip(" |\t\r\n")
            if not value:
                continue
            if field == "title":
                current = {"id": uid(), "fields": {key: empty_field() for key in FIELDS}, "source_documents": [document["id"]]}
                candidates.append(current)
            if current is not None:
                incoming = fact(value, block)
                old = current["fields"][field]
                current["fields"][field] = merge_field(field, old, incoming) if old["value"] else incoming
                recognized.add(block["id"])
    # Unlabelled prose is not falsely claimed to be semantically reviewed.
    unreviewed = [b["id"] for b in blocks if b["id"] not in recognized]
    return {"candidates": candidates, "scanned_blocks": len(blocks), "reviewed_blocks": len(recognized), "unreviewed_block_ids": unreviewed,
            "status": "PARTIALLY_REVIEWED" if unreviewed or not candidates else "EXTRACTED", "mode": "rules", "model": "label-rules-v1", "seconds": 0, "usage": {},
            "note": "모든 블록을 조사하고 명시적 업무·기한·담당 라벨을 추출했습니다. 비정형 서술은 사람 또는 LLM의 추가 검토가 필요합니다."}


def structured_profile(document, blocks):
    """Exact labels in a declared work brief are data, not generated prose.
    Return None if non-metadata prose requires semantic model review.
    """
    if document_role(blocks)!='업무기준정보':return None
    result=rules_discover(document,blocks)
    if not result['candidates']:return None
    ignored=[]
    for b in blocks:
        if b['id'] not in result['unreviewed_block_ids']:continue
        if re.match(r'^(?:[A-Z]+\d+:\s*)?(?:문서역할\s*[:：]|보고일\s*[:：]|합성자료(?:\s|$))',b['text'].strip()):ignored.append(b['id'])
        else:return None
    return {**result,'mode':'structured','model':'source-labels-v1','status':'EXTRACTED',
            'unreviewed_block_ids':[], 'context_only_block_ids':ignored,
            'note':'업무기준정보의 명시적 항목을 원문 그대로 읽었습니다. 문서역할·보고일·합성자료 표시는 맥락으로 구분하며 모델이 다시 작성하지 않습니다.'}


def validate_model_result(data, document, blocks):
    if not isinstance(data, dict) or set(data) != {"items"} or not isinstance(data["items"], list) or len(data["items"]) > 100:
        raise ValueError("LLM 응답 스키마가 유효하지 않습니다.")
    lookup = {b["id"]: b for b in blocks}
    candidates = []
    for item in data["items"]:
        if not isinstance(item, dict) or set(item) != {"fields"} or not isinstance(item["fields"], dict) or "title" not in item["fields"] or not set(item["fields"]) <= set(FIELDS):
            raise ValueError("LLM 업무 필드가 유효하지 않습니다.")
        fields = {key: empty_field() for key in FIELDS}
        for key, value in item["fields"].items():
            if value is None and key != "title":
                continue
            if isinstance(value, dict) and set(value) == {"block_id", "quote"}:
                value = {**value, "value": value["quote"]}
            if not isinstance(value, dict) or set(value) != {"value", "block_id", "quote"} or not all(isinstance(v, str) for v in value.values()):
                raise ValueError(f"{key}: 필드 근거 스키마가 유효하지 않습니다.")
            block = lookup.get(value["block_id"])
            if not block or not value["value"] or len(value["value"]) > 2000 or value["value"] not in value["quote"]:
                raise ValueError(f"{key}: 값은 실제 원문 인용의 부분 문자열이어야 하고 블록 ID가 존재해야 합니다.")
            recovered = False
            if value["quote"] not in block["text"] and document.get("format") == ".pdf":
                from .citations import exact_pdf_span
                quote = exact_pdf_span(block["text"], value["quote"])
                raw_value = exact_pdf_span(quote, value["value"])
                value = {**value, "quote": quote, "value": raw_value}
                recovered = True
            fields[key] = fact(value["value"], block, value["quote"])
            if recovered:
                fields[key]["citation_recovery"] = "pdf-visual-line-wrap-to-original"
        candidates.append({"id": uid(), "fields": fields, "source_documents": [document["id"]]})
    return candidates


class ModelFailure(ValueError):
    def __init__(self, message, diagnostic):
        super().__init__(message)
        self.diagnostic = diagnostic


def extraction_schema():
    ref = {"type": "object", "properties": {"block_id": {"type": "string"}, "quote": {"type": "string"}}, "required": ["block_id", "quote"], "additionalProperties": False}
    fields = {"type": "object", "properties": {key: ref if key == "title" else {"anyOf": [ref, {"type": "null"}]} for key in FIELDS}, "required": list(FIELDS), "additionalProperties": False}
    item = {"type": "object", "properties": {"fields": fields}, "required": ["fields"], "additionalProperties": False}
    return {"type": "object", "properties": {"items": {"type": "array", "items": item}}, "required": ["items"], "additionalProperties": False}


def llm_discover(document, blocks, config):
    # A workbook may hold several complete work briefs. Keep worksheet context
    # intact and avoid truncating a multi-work response at the model output limit.
    if document_role(blocks)=='업무기준정보' and document.get('format')=='.xlsx':
        groups={}
        for b in blocks:groups.setdefault(b['location'].rsplit('!',1)[0],[]).append(b)
        if len(groups)>1:
            parts=[llm_discover({**document,'format':'sheet'},group,config) for group in groups.values()]
            return {**parts[0], 'candidates':[c for p in parts for c in p['candidates']],
                    'scanned_blocks':sum(p['scanned_blocks'] for p in parts),
                    'reviewed_blocks':sum(p['reviewed_blocks'] for p in parts),
                    'unreviewed_block_ids':[b for p in parts for b in p['unreviewed_block_ids']],
                    'status':'PARTIALLY_REVIEWED' if any(p['unreviewed_block_ids'] for p in parts) else 'EXTRACTED',
                    'usage':{k:sum(p['usage'].get(k,0) for p in parts) for k in ['prompt_tokens','completion_tokens','total_tokens']},
                    'calls':[c for p in parts for c in p['calls']], 'seconds':sum(p['seconds'] for p in parts)}
    start = time.monotonic()
    selected, size = [], 0
    for block in blocks:
        if size + len(block["text"]) > 60000:
            break
        selected.append(block)
        size += len(block["text"])
    system = config.get("extraction_prompt") or EXTRACTION_PROMPT
    aliases = {f"B{i + 1}": b["id"] for i, b in enumerate(selected)}
    messages = [{"role": "system", "content": system}, {"role": "user", "content": json.dumps({"document": "현재 문서 본문 (파일명은 해석에서 제외)", "blocks": [{"block_id": f"B{i + 1}", "text": b["text"]} for i, b in enumerate(selected)]}, ensure_ascii=False)}]
    calls, usage = [], {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    for attempt in range(2):
        call = {"attempt": attempt + 1}
        try:
            response = completion_request(config, {"model": config["model"], "messages": messages, "temperature": 0, "max_tokens": 8000, "response_format": {"type": "json_schema", "json_schema": {"name": "handover_evidence", "strict": True, "schema": extraction_schema()}}}, 150, 'extraction')
            call["http_status"] = response.status_code
            if response.status_code != 200:
                message = f"모델 API 오류 HTTP {response.status_code}. 설정·사용량을 확인하세요."
                if response.status_code not in {429, 500, 502, 503, 504}:
                    raise ModelFailure(message, {"model": config["model"], "calls": calls + [call], "usage": usage})
                raise ValueError(message)
            result = response.json()
            call["usage"] = result.get("usage", {})
            for key in usage:
                usage[key] += int(call["usage"].get(key, 0) or 0)
            content = result["choices"][0]
            if content.get("finish_reason") == "length":
                raise ValueError("모델 출력이 잘렸습니다. 문서를 나누어 등록하세요.")
            raw = content["message"]["content"]
            data = json.loads(raw)
            if isinstance(data, dict) and isinstance(data.get("items"), list):
                for item in data["items"]:
                    if isinstance(item, dict) and isinstance(item.get("fields"), dict):
                        for value in item["fields"].values():
                            if isinstance(value, dict) and isinstance(value.get("block_id"), str):
                                value["block_id"] = aliases.get(value["block_id"], value["block_id"])
            candidates = validate_model_result(data, document, selected)
            call["valid"] = True
            calls.append(call)
            break
        except ModelFailure:
            raise
        except (ValueError, KeyError, IndexError, TypeError, httpx.HTTPError) as exc:
            error = str(exc) if isinstance(exc, ValueError) and not isinstance(exc, json.JSONDecodeError) else f"모델 응답 계약/연결 오류 ({type(exc).__name__})"
            call.update(valid=False, error=error)
            calls.append(call)
            if attempt == 1:
                raise ModelFailure(error + " 자동 재시도 후에도 실패하여 초안을 저장하지 않았습니다.", {"model": config["model"], "calls": calls, "usage": usage, "seconds": round(time.monotonic() - start, 2)}) from exc
            # Retry original source with targeted validation feedback, never weaken citation checks.
            messages.append({"role": "user", "content": "직전 출력 검증 실패: " + error + ". 원문에서 정확히 일치하는 구간만 복사하고 확인되지 않은 필드는 null로 반환하세요. JSON 전체를 다시 작성하세요."})
            time.sleep(1)
    unreviewed = [b["id"] for b in blocks[len(selected):]]
    return {"candidates": candidates, "scanned_blocks": len(blocks), "reviewed_blocks": len(selected), "unreviewed_block_ids": unreviewed,
            "status": "PARTIALLY_REVIEWED" if unreviewed else ("EXTRACTED" if candidates else "NO_WORK_FOUND"), "mode": "llm", "prompt_hash": digest(system), "model": config["model"], "resolved_model": result.get("model", config["model"]), "seconds": round(time.monotonic() - start, 2), "usage": usage, "calls": calls, "note": "원문 인용을 기계 검증했습니다. 의미·누락 여부는 전임자가 검토해야 합니다."}


def normalize(text):
    return re.sub(r"[^가-힣a-z0-9]", "", unicodedata.normalize("NFKC", text).lower())


def merge_field(key, old, new):
    if not old["value"]:
        return new
    if not new["value"]:
        return old
    if normalize(old["value"]) == normalize(new["value"]):
        seen = {e["id"] for e in old["evidence"]}
        old["evidence"] += [e for e in new["evidence"] if e["id"] not in seen]
        return old
    if not old["observations"]:
        old["observations"] = [{"value": old["value"], "evidence": list(old["evidence"])}]
    old["observations"].append({"value": new["value"], "evidence": new["evidence"]})
    old["evidence"] += new["evidence"]
    # Status variations may be progress over time; don't call them a contradiction.
    old["review_status"] = "CONFLICT" if key in {"due_date", "owner"} else "NEEDS_CONFIRMATION"
    old["value"] = " / ".join(dict.fromkeys(o["value"] for o in old["observations"]))
    return old


def merge_candidates(results):
    items, groups = [], {}
    owner_groups=defaultdict(list)
    for result in results:
        for candidate in result["candidates"]:
            fields = candidate["fields"]
            for name in FIELDS:
                fields.setdefault(name, empty_field())
            # Exact body title plus explicit project code, or unambiguous owner identity.
            events=candidate.get('timeline',[])+candidate.get('supporting_records',[])
            codes={e.get('work_code') for e in events if e.get('work_code')}
            code=next(iter(codes)) if len(codes)==1 else None
            key = (normalize(fields["title"]["value"]), ('사업번호:'+code) if code else normalize(fields["owner"]["value"]))
            owner_key=(key[0],normalize(fields['owner']['value']))
            existing = groups.get(key) if key[1] else None
            if existing is None and owner_key[1] and len(owner_groups[owner_key])==1:
                prior=owner_groups[owner_key][0]
                prior_codes={e.get('work_code') for e in prior.get('timeline',[])+prior.get('supporting_records',[]) if e.get('work_code')}
                if not code or not prior_codes or prior_codes=={code}:existing=prior
            if existing:
                groups[key]=existing
                for name in FIELDS:
                    existing["fields"][name] = merge_field(name, existing["fields"][name], fields[name])
                existing["source_documents"] = sorted(set(existing["source_documents"] + candidate["source_documents"]))
                existing.setdefault("timeline", []).extend(candidate.get("timeline", []))
                existing.setdefault("supporting_records", []).extend(candidate.get("supporting_records", []))
                existing["merge_note"] = "본문의 동일 업무명과 사업관리번호로 연결했습니다." if code else "동일 업무명·담당 표현의 후보를 묶었습니다. 연도·대상·범위가 같은 업무인지 확인해 주세요."
            else:
                items.append(candidate)
                groups[key] = candidate
                owner_groups[owner_key].append(candidate)
    return items


def annotate_items(items):
    """Derived display metadata never replaces the quoted original values."""
    for item in items:
        for key in ["owner", "due_date"]:
            if key not in item["fields"]:
                continue
            field = item["fields"][key]
            if field["provenance"] != "HUMAN_ENTERED" and re.search(r"미정|미확정|정하지 않|아직 정|확정되지 않", field["value"]):
                field["review_status"] = "NEEDS_CONFIRMATION"
        due = item["fields"]["due_date"]
        value = due["value"].strip()
        precision, normalized = "UNKNOWN", None
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            try:
                normalized = date.fromisoformat(value).isoformat()
                precision = "DAY"
            except ValueError:
                pass
        elif "매월" in value or "매주" in value:
            precision = "RECURRING"
        elif re.fullmatch(r"(?:\d{4}년\s*)?\d{1,2}월(?:\s*(?:말|초|중순))?", value):
            precision = "MONTH"
        due["normalized_date"] = normalized
        due["precision"] = precision
        original = item["fields"]["status"]["value"].strip()
        states = {"완료": "COMPLETED", "업무 완료": "COMPLETED", "사업 완료": "COMPLETED", "진행 중": "IN_PROGRESS", "계획": "PLANNED", "예정": "PLANNED", "보류": "ON_HOLD", "요청": "REQUESTED"}
        item["business_status"] = states.get(original, "IN_PROGRESS" if original.endswith(" 중") and "/" not in original else "UNKNOWN")
    return items


def warnings_for(payload):
    warnings = list(payload.get("image_notes",[]))
    for item in payload["items"]:
        title = item["fields"]["title"]["value"]
        if "확인 필요" in item.get("inheritance_status",""):warnings.append(title+": 이전 보고서와 새 자료의 연결·현행화 확인 필요")
        if item.get("version_policy") and item.get("timeline") and not item.get("latest_document_id"):
            warnings.append(title+": 최신 기준본 확인 필요 — "+item.get("chronology_note",""))
        for key, field in item["fields"].items():
            if key in {"due_date", "owner", "next_action"} and not field["value"]:
                warnings.append(f"{title}: {FIELDS[key]} 미확인")
            if field["review_status"] in {"CONFLICT", "NEEDS_CONFIRMATION"} and field["value"]:
                warnings.append(f"{title}: {FIELDS[key]} 대조·확인 필요")
    for coverage in payload.get("coverage", []):
        if coverage["status"] not in {"EXTRACTED", "NO_WORK_FOUND", "REFERENCE_ONLY"}:
            warnings.append(f"{coverage['path']}: 문서 검토 {coverage['status']}")
        if coverage.get("parse_status") != "SUCCESS":
            warnings.append(f"{coverage['path']}: 원문 추출 {coverage.get('parse_status')}")
    if not payload["items"]:
        warnings.append("추출된 업무가 없습니다. 직접 추가하거나 다른 추출 모드로 검토하세요.")
    return warnings


def search_blocks(blocks, query, limit=5):
    tokens = [normalize(t) for t in re.findall(r"[가-힣a-zA-Z0-9]+", query) if len(normalize(t)) > 1]
    if not tokens:
        return []
    scored = []
    for block in blocks:
        text = normalize(block["text"])
        score = sum(5 + min(text.count(t), 3) for t in tokens if t in text)
        # Korean character bigrams supplement lexical variants, never advertised as embeddings.
        grams = {t[i:i + 2] for t in tokens for i in range(len(t) - 1)}
        score += sum(0.15 for gram in grams if gram in text)
        if score >= 1:
            scored.append({**block, "score": round(score, 2)})
    return sorted(scored, key=lambda b: (-b["score"], b["doc_id"], b["ordinal"]))[:limit]
