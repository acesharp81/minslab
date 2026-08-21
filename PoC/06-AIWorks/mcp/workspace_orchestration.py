"""Generic workspace request profiling for the AIWorks feedback slice.

The core classifies only interaction/output shapes. Domain behavior stays in MCP
capabilities so examples such as budget or settlement do not become platform
workflow types.
"""

from __future__ import annotations

from pathlib import Path
import re


MANIFEST = {
    "id": "core.workspace-orchestration",
    "name": "범용 작업공간 오케스트레이션 MCP",
    "version": "0.1.0",
    "runtime": "local",
    "description": "파일·선택 영역·요청 산출물을 기준으로 필요한 MCP Capability를 조합합니다.",
    "inputs": {"intent": {"type": "string"}, "context": {"type": "object"}},
    "outputs": {"workflow": {"type": "object"}},
    "permissions": [],
}


MCP_LABELS = {
    "core.intent-analysis@0.1.0": "의도 분석 MCP",
    "output.text@1.0.0": "텍스트 표출 MCP",
    "data.budget@0.1.0": "예산 MCP",
    "document.report@1.0.0": "보고서 MCP",
    "template.settlement@0.1.0": "결산 양식 MCP",
    "knowledge.legal@0.1.0": "법률 MCP",
    "document.report-hwpx@0.1.0": "보고서 HWPX 산출 MCP",
    "document.report-structure@0.1.0": "보고서 구조화 MCP",
    "document.markdown@1.0.0": "프로젝트 Markdown 문서 MCP",
    "template.report-style@0.1.0": "보고서 양식 적용 MCP v2",
    "document.rhwp@1.0.0": "RHWP 보고서 편집기 MCP",
    "template.mois-report@0.1.0": "행안부 보고서 양식 MCP",
}


def _contains(text: str, words: tuple[str, ...]) -> bool:
    return any(word in text for word in words)


def _step(step_id: str, mcp: str, action: str, permissions: list[str], model: str | None, depends_on: list[str]) -> dict:
    return {
        "id": step_id,
        "mcp": mcp,
        "action": action,
        "model": model,
        "permissions": permissions,
        "dependsOn": depends_on,
    }


def build_workflow(intent: str, context: dict, route: dict) -> dict:
    normalized = " ".join(str(intent or "").lower().split())
    filename = str(context.get("filename") or "").strip()
    has_attachment = bool(context.get("has_attachment")) or bool(
        Path(filename).suffix.lower() in {".hwp", ".hwpx", ".hwt", ".hml", ".pdf", ".md", ".txt"}
        and str(context.get("document_id") or "").startswith("docsession_")
    )
    has_selection = bool(context.get("has_selection") or context.get("selection_text"))
    has_previous_answer = bool(str(context.get("previous_answer") or "").strip())
    has_current_document = bool(
        str(context.get("document_id") or "").startswith("docsession_")
        and (str(context.get("document_excerpt") or "").strip() or str(context.get("filename") or "").strip())
    )
    asks_legal = _contains(normalized, ("법률", "법령", "법조항", "법 조항", "관련 법", "근거 조항"))
    asks_editable_document = _contains(
        normalized,
        (
            "문서를 편집",
            "문서 편집",
            "편집 가능한 문서",
            "편집할 수 있는 문서",
            "문서를 수정",
            "문서 수정",
            "수정 가능한 문서",
            "문서로 열",
            "편집기로",
            "rhwp",
        ),
    ) or (
        has_previous_answer
        and _contains(
            normalized,
            ("편집하자", "편집하고 싶어", "편집할 수 있도록", "수정하고 싶어", "수정할 수 있도록"),
        )
    )
    asks_report = asks_editable_document or _contains(
        normalized, ("보고서", "작성해", "작성 해", "문서로", "양식으로", "초안")
    )
    asks_settlement = _contains(normalized, ("결산", "회계연도", "집행 실적"))
    asks_budget = _contains(normalized, ("예산", "세출", "세입", "재정", "집행액"))
    asks_mois_template = _contains(normalized, ("행안부", "행정안전부")) and _contains(
        normalized, ("양식", "서식", "형식", "포맷")
    )
    asks_fresh_research = asks_report and (asks_budget or asks_settlement or asks_legal) and _contains(
        normalized, ("확인", "조회", "검색", "찾아", "조사", "분석")
    )
    asks_outline = _contains(normalized, ("개조식", "항목식", "불릿", "bullet"))
    references_previous = has_previous_answer and _contains(
        normalized,
        ("이 내용", "이 내용을", "이를 바탕", "이걸 바탕", "위 내용", "앞의 내용", "분석 내용", "분석 결과"),
    )
    previous_answer_is_primary = references_previous and asks_report
    asks_document_transform = has_current_document and not previous_answer_is_primary and (
        asks_outline
        or (
            _contains(normalized, ("전체 내용", "전체 문서", "문서 전체", "보고서 전체", "전체를", "전체적으로"))
            and _contains(normalized, ("다듬", "수정", "바꿔", "변경", "정리", "재작성"))
        )
    )

    model_id = str((route.get("model") or {}).get("id") or "upstage/solar-pro-3")
    steps = [_step("understand", "core.intent-analysis@0.1.0", "classify-request", [], None, [])]
    loaded = ["core.intent-analysis@0.1.0"]

    if asks_mois_template and has_current_document and not previous_answer_is_primary and not asks_fresh_research:
        response_type = "template-transform"
        loaded.extend(["document.rhwp@1.0.0", "template.mois-report@0.1.0"])
        steps.extend([
            _step("read-current-document", "document.rhwp@1.0.0", "read-current-hwpx", ["document.read"], None, ["understand"]),
            _step("load-template", "template.mois-report@0.1.0", "load-template-contract", ["document.read"], None, ["read-current-document"]),
            _step("apply-template", "template.mois-report@0.1.0", "apply-preserving-content", ["document.write"], None, ["load-template"]),
            _step("save-revision", "document.rhwp@1.0.0", "replace-current-artifact", ["document.write"], None, ["apply-template"]),
        ])
        title = "행안부 내부보고 양식 적용"
    elif has_selection and asks_legal:
        response_type = "context-answer"
        loaded.extend(["document.rhwp@1.0.0", "knowledge.legal@0.1.0", "output.text@1.0.0"])
        steps.extend([
            _step("read-selection", "document.rhwp@1.0.0", "read-selection", ["document.read"], None, ["understand"]),
            _step("search-law", "knowledge.legal@0.1.0", "find-relevant-provisions", ["document.read", "model.invoke", "network.send"], model_id, ["read-selection"]),
            _step("show-answer", "output.text@1.0.0", "render-grounded-answer", [], None, ["search-law"]),
        ])
        title = "선택 문구 관련 법률 검토"
    elif has_selection:
        response_type = "selection-edit"
        loaded.extend(["document.report@1.0.0", "document.rhwp@1.0.0"])
        steps.extend([
            _step("read-selection", "document.rhwp@1.0.0", "read-selection", ["document.read"], None, ["understand"]),
            _step("rewrite", "document.report@1.0.0", "rewrite-selection", ["document.read", "model.invoke", "network.send"], model_id, ["read-selection"]),
            _step("validate-patch", "document.rhwp@1.0.0", "validate-selection-patch", ["document.write"], None, ["rewrite"]),
        ])
        title = "선택 문구 변경 제안"
    elif asks_document_transform:
        response_type = "document-transform"
        loaded.extend(["document.rhwp@1.0.0", "document.report@1.0.0", "document.report-hwpx@0.1.0"])
        steps.extend([
            _step("read-current-document", "document.rhwp@1.0.0", "read-current-hwpx", ["document.read"], None, ["understand"]),
            _step("rewrite-document", "document.report@1.0.0", "rewrite-full-document-locally", ["document.read"], None, ["read-current-document"]),
            _step("package-hwpx", "document.report-hwpx@0.1.0", "package-editable-hwpx", ["document.write"], None, ["rewrite-document"]),
            _step("save-revision", "document.rhwp@1.0.0", "replace-current-artifact", ["document.write"], None, ["package-hwpx"]),
        ])
        title = "현재 보고서 전체 개조식 변환" if asks_outline else "현재 보고서 전체 문구 변환"
    elif asks_report:
        response_type = "report-artifact"
        if has_attachment and not previous_answer_is_primary and not asks_fresh_research:
            loaded.append("document.rhwp@1.0.0")
            steps.append(_step("read-attachment", "document.rhwp@1.0.0", "read-source-artifact", ["document.read"], None, ["understand"]))
            previous = ["read-attachment"]
        else:
            previous = ["understand"]
        if asks_settlement:
            loaded.append("template.settlement@0.1.0")
            steps.append(_step("load-template", "template.settlement@0.1.0", "load-current-settlement-template", ["document.read"], None, previous))
            previous = ["load-template"]
        loaded.extend(["document.report@1.0.0", "document.markdown@1.0.0", "document.report-structure@0.1.0", "document.quality-harness@0.1.0", "template.report-style@0.1.0", "document.report-hwpx@0.1.0", "document.rhwp@1.0.0"])
        report_steps = [
            _step("generate-report", "document.report@1.0.0", "generate-markdown-report", ["document.read", "document.write", "model.invoke", "network.send"], model_id, previous),
            _step("structure-report", "document.report-structure@0.1.0", "parse-semantic-blocks", ["document.read"], None, ["generate-report"]),
            _step("review-draft", "document.quality-harness@0.1.0", "compare-request-evidence-draft", ["document.read"], None, ["structure-report"]),
            _step("save-markdown", "document.markdown@1.0.0", "save-project-source-revision", ["document.write"], None, ["review-draft"]),
            _step("apply-template", "template.report-style@0.1.0", "bind-project-facts-and-style", ["document.read"], None, ["save-markdown"]),
            _step("package-hwpx", "document.report-hwpx@0.1.0", "render-editable-hwpx", ["document.write"], None, ["apply-template"]),
        ]
        if asks_mois_template:
            loaded.append("template.mois-report@0.1.0")
            report_steps.append(_step("apply-mois-template", "template.mois-report@0.1.0", "apply-to-new-report", ["document.read", "document.write"], None, ["package-hwpx"]))
            open_dependency = ["apply-mois-template"]
        else:
            open_dependency = ["package-hwpx"]
        report_steps.append(_step("open-editor", "document.rhwp@1.0.0", "open-generated-artifact", ["document.write"], None, open_dependency))
        steps.extend(report_steps)
        if _contains(normalized, ("지적사항", "지적 사항")) and _contains(normalized, ("대안", "개선", "향후 계획")):
            title = "지적사항별 개선대안 보고"
        else:
            title = "올해 결산 보고서" if asks_settlement else "분석 및 시사점 보고서"
    else:
        response_type = "text-answer"
        if asks_budget:
            loaded.append("data.budget@0.1.0")
            steps.append(_step("query-data", "data.budget@0.1.0", "query-current-budget-summary", ["common-data.read"], None, ["understand"]))
            previous = ["query-data"]
        else:
            previous = ["understand"]
        loaded.append("output.text@1.0.0")
        steps.extend([
            _step("compose-answer", "output.text@1.0.0", "compose-grounded-answer", ["model.invoke", "network.send"], model_id, previous),
            _step("show-answer", "output.text@1.0.0", "render-chat-answer", [], None, ["compose-answer"]),
        ])
        title = "예산 현황 요약" if asks_budget else "업무 질의 답변"

    return {
        "id": response_type,
        "responseType": response_type,
        "title": title,
        "hasAttachment": has_attachment,
        "hasSelection": has_selection,
        "loadedMcps": list(dict.fromkeys(loaded)),
        "steps": steps,
        "signals": {
            "budget": asks_budget,
            "report": asks_report,
            "editableDocument": asks_editable_document,
            "settlement": asks_settlement,
            "legal": asks_legal,
            "moisTemplate": asks_mois_template,
            "documentTransform": asks_document_transform,
            "outline": asks_outline,
            "previousAnswerPrimary": previous_answer_is_primary,
            "freshResearch": asks_fresh_research,
        },
        "contextPriority": "previous-answer" if previous_answer_is_primary else ("data-source" if asks_fresh_research else ("current-document" if has_current_document else "project")),
    }


def _outline_markdown(source: str, title: str) -> str:
    output = []
    for raw in str(source or "").splitlines():
        line = raw.strip()
        if not line:
            if output and output[-1] != "":
                output.append("")
            continue
        if line.startswith("#"):
            output.append(line)
            continue
        line = re.sub(r"^(?:[-*•○□▪◦]+|\d+[.)])\s*", "", line).strip()
        if not line:
            continue
        sentences = [item.strip() for item in re.split(r"(?<=[.!?다함됨임])\s+", line) if item.strip()]
        output.extend("- " + item for item in (sentences or [line]))
    if not output or not output[0].startswith("# "):
        output.insert(0, "# " + title)
        output.insert(1, "")
    return "\n".join(output).strip()


def _issue_alternative_markdown(source: str) -> str:
    candidates = []
    priority_terms = (
        "인공지능 공통기반", "정보화전략계획", "실집행", "집행률", "이월",
        "지연", "완료", "성과지표", "지적", "미흡", "문제",
    )
    for raw in str(source or "").splitlines():
        line = re.sub(r"^\s*(?:[-*]|\d+[.)])\s*", "", raw).strip()
        if not line or line.startswith("#") or line.startswith("※") or line.startswith("["):
            continue
        if any(term in line for term in priority_terms):
            clean = re.sub(r"\s+", " ", line)[:420].strip()
            if clean and clean not in candidates:
                candidates.append(clean)
    sections = []
    for index, issue in enumerate(candidates[:4], start=1):
        if any(term in issue for term in ("정보화전략계획", "사전", "예산 편성")):
            alternative = "예산 편성 전에 정보화전략계획 등 선행절차를 완료하고, 단계별 사전검토 통과 여부를 다음 단계 착수 조건으로 관리함."
            plan = "차기 사업부터 선행계획·예산요구·계약 일정을 연계한 점검표를 적용하고 분기별로 준수 여부를 보고함."
        elif any(term in issue for term in ("실집행", "집행률", "이월", "불용")):
            alternative = "교부액과 실집행액을 분리 관리하고 월별 집행률·이월 예상액을 조기에 점검하여 지연 공정을 즉시 조정함."
            plan = "집행 부진 기준과 시정 기한을 설정하고, NIA 등 수행기관의 월별 실집행 실적과 잔액 처리계획을 정례 점검함."
        elif any(term in issue for term in ("지연", "완료", "일정")):
            alternative = "착수·구축·검수 단계별 핵심 일정을 재설계하고 지연 위험 발생 시 대체 일정과 책임 주체를 즉시 확정함."
            plan = "주요 마일스톤별 진척률과 위험요인을 월 단위로 점검하고 차년도 이월 가능성을 사전에 관리함."
        elif any(term in issue for term in ("성과", "효과", "실효성")):
            alternative = "사업 산출물 중심 지표를 이용기관 활용도와 업무개선 효과 중심의 성과지표로 보완함."
            plan = "기관별 활용실적과 이용자 체감효과를 반기별 측정하여 다음 연도 예산과 기능개선 계획에 반영함."
        else:
            alternative = "지적 원인을 절차·집행·성과관리로 구분하고 원인별 책임부서와 개선기한을 명확히 설정함."
            plan = "개선과제별 이행지표를 마련하여 분기별 추진실적을 점검하고 미이행 과제는 보완계획을 수립함."
        sections.extend([
            f"### {index}. 지적사항",
            f"- {issue}",
            "- 개선대안",
            f"  - {alternative}",
            "- 향후계획",
            f"  - {plan}",
            "",
        ])
    if not sections:
        sections = [
            "### 1. 지적사항",
            "- 직전 분석에서 확인된 지적사항의 원문·연도·근거 위치를 재확인할 필요가 있음.",
            "- 개선대안",
            "  - 지적 원인을 절차·집행·성과관리로 구분하고 책임부서와 개선기한을 설정함.",
            "- 향후계획",
            "  - 근거 확인 후 과제별 이행지표를 확정하고 분기별 추진실적을 관리함.",
            "",
        ]
    return "\n".join(sections).strip()


def local_result(intent: str, context: dict, workflow: dict) -> dict:
    response_type = workflow["responseType"]
    selection = str(context.get("selection") or context.get("selection_text") or "").strip()
    previous = str(context.get("previous_answer") or "").strip()
    source_name = str(context.get("filename") or "첨부 자료")

    if response_type == "template-transform":
        return {
            "template": {
                "id": "mois.internal-report.v1",
                "name": "행정안전부 내부보고형",
                "officialSourceConnected": False,
                "contentPolicy": "preserve-text",
            }
        }

    if response_type == "selection-edit":
        before = selection or "선택 문구"
        after = (
            "해당 과제는 정책 목표의 적기 달성과 국민 체감 효과 확보를 위해 반드시 추진할 필요가 있으며, "
            "업무 연속성과 책임성 있는 성과 관리를 위해 실행 기반을 조속히 마련해야 한다."
        )
        return {"patches": [{"op": "replace", "target": context.get("selection_id") or "document.selection", "before": before, "after": after}]}

    if response_type == "document-transform":
        filename = str(context.get("filename") or "AIWorks_보고서.hwpx")
        title = Path(filename).stem
        for suffix in ("_KODAK", "_AIWorks"):
            if title.endswith(suffix):
                title = title[: -len(suffix)]
        source = str(context.get("document_excerpt") or context.get("previous_answer") or "").strip()
        content = _outline_markdown(source, title) if workflow["signals"]["outline"] else source
        return {"artifact": {"title": title, "filename": title + ".hwpx", "content": content, "editorMcp": "document.rhwp@1.0.0", "applyMode": "replace-current-session"}}

    if response_type == "context-answer":
        return {
            "answer": (
                "법률 MCP가 선택 문구를 검색 질의로 변환했습니다. 현재 체험 환경에는 국가법령정보센터 같은 "
                "권위 있는 법령 원문 연결이 설정되지 않아 특정 법률·조항을 확정해서 제시하지 않았습니다. "
                "법률 데이터 커넥터를 연결하면 법령명, 조문, 시행일과 원문 링크를 함께 표시합니다."
            )
        }

    if response_type == "report-artifact":
        basis = previous or str(context.get("document_excerpt") or "프로젝트에 연결된 자료")
        if workflow["signals"]["settlement"]:
            body = (
                f"# {workflow['title']}\n\n"
                "## 1. 작성 기준\n"
                f"{source_name}의 내용을 기준으로 올해 결산 보고서 항목에 맞춰 재구성했습니다.\n\n"
                "## 2. 사업 개요\n"
                f"{basis[:700]}\n\n"
                "## 3. 추진 실적 및 집행 결과\n"
                "첨부 자료에서 확인 가능한 실적과 집행 내용을 항목별로 정리하고, 확인되지 않은 값은 검토 필요로 표시합니다.\n\n"
                "## 4. 성과와 시사점\n"
                "성과의 지속 가능성과 다음 연도 개선 과제를 중심으로 후속 관리가 필요합니다.\n\n"
                "## 5. 확인 필요 사항\n"
                "실제 결산 양식 원본과 확정 수치가 연결되면 필수 항목과 합계 검증을 자동 수행합니다."
            )
        else:
            issue_alternatives = ""
            if _contains(intent, ("지적사항", "지적 사항")) and _contains(intent, ("대안", "개선", "향후 계획")):
                issue_alternatives = (
                    "\n\n## 3. 지적사항별 개선대안 및 향후계획\n"
                    + _issue_alternative_markdown(basis)
                    + "\n"
                )
            body = "".join([
                f"# {workflow['title']}\n\n",
                "## 1. 보고 목적\n",
                "현재까지 확인된 자료를 간부 검토가 가능한 수준으로 요약하고, 주요 판단사항과 후속 조치 방향을 보고드리고자 합니다.\n\n",
                "## 2. 주요 현황\n",
                f"{basis[:900]}\n\n",
                issue_alternatives,
                "## 4. 검토 결과\n" if issue_alternatives else "## 3. 검토 결과\n",
                "- 현재 연결된 근거를 기준으로 핵심 수치와 추진 상황을 구분해 정리했습니다.\n",
                "- 기준일, 담당부서 및 확정 여부가 연결되지 않은 항목은 확인 필요 사항으로 관리해야 합니다.\n\n",
                "## 5. 정책적 시사점\n" if issue_alternatives else "## 4. 정책적 시사점\n",
                "핵심 지표의 변화가 정책 목표와 국민 체감 성과로 이어지는지 정기적으로 점검하고, 근거 데이터 변경 시 관련 파생 보고서를 함께 갱신할 필요가 있습니다.\n\n",
                "## 6. 종합 향후 조치 계획\n" if issue_alternatives else "## 5. 향후 조치 계획\n",
                "- 담당부서 검토를 거쳐 기준일과 확정 수치를 보완합니다.\n",
                "- 프로젝트 공통 메타정보와 보고서 간 불일치 여부를 확인합니다.\n",
                "- 확인 결과를 반영한 최종 보고본을 새 revision으로 확정합니다.",
            ])
        return {"artifact": {"title": workflow["title"], "filename": workflow["title"] + ".hwpx", "content": body, "editorMcp": "document.rhwp@1.0.0"}}

    if workflow["signals"]["budget"]:
        return {
            "answer": (
                "현재 AIWorks 체험용 예산 MCP에 연결된 프로젝트 데이터 기준 요약입니다.\n\n"
                "- 총사업비: 1,284백만원\n"
                "- SW 개발비: 856백만원\n"
                "- 인프라 구축: 318백만원\n"
                "- 교육·초기 운영: 110백만원\n\n"
                "기관 전체 예산 현황을 조회하려면 실제 행안부 예산 DB 또는 내부 재정시스템 MCP 연결이 필요합니다."
            )
        }
    return {"answer": "요청을 분석했지만 연결된 업무 데이터 MCP가 없습니다. 필요한 데이터 소스나 자료를 지정해 주세요."}


def live_messages(intent: str, context: dict, workflow: dict) -> list[dict]:
    response_type = workflow["responseType"]
    previous = str(context.get("previous_answer") or "")[:20_000]
    excerpt = str(context.get("document_excerpt") or "")[:8_000]
    selection = str(context.get("selection") or context.get("selection_text") or "")[:4_000]
    facts = ((context.get("project_fact_snapshot") or {}).get("facts") or {})
    fact_context = "\n".join(
        f"- [FACT {key}] {item.get('label')}: {item.get('value')} {item.get('unit') or ''}".rstrip()
        for key, item in list(facts.items())[:30]
    )
    markdown_documents = context.get("project_markdown_context") or []
    markdown_context = ""
    if context.get("project_markdown_prompt_allowed") is True:
        markdown_context = "\n\n".join(
            "[MD " + str(item.get("versionId") or "") + "] " + str(item.get("title") or "프로젝트 문서") + "\n" + str(item.get("markdown") or "")
            for item in markdown_documents[:6]
        )[:24_000]
    mcp_context = ""
    if workflow["signals"]["budget"]:
        mcp_context = (
            "체험용 예산 MCP 데이터: 총사업비 1,284백만원, SW 개발비 856백만원, "
            "인프라 318백만원, 교육·초기 운영 110백만원. 기관 전체 실제 데이터는 미연결."
        )
    if workflow["signals"]["legal"]:
        mcp_context = "권위 있는 법령 원문 데이터 커넥터가 아직 미연결. 정확한 법률명이나 조항을 추측하지 말 것."

    if response_type == "selection-edit":
        system = (
            "당신은 AIWorks 보고서 MCP입니다. 사용자 지시를 반영한 최종 대체 문구만 한국어로 출력하세요. "
            "설명·머리말·따옴표·마크다운은 넣지 말고 원문을 그대로 반복하지 마세요."
        )
        user = f"요청: {intent[:1000]}\n선택 문구: {selection}"
    elif response_type == "document-transform":
        system = (
            "당신은 AIWorks 보고서 MCP입니다. 현재 보고서의 사실·수치·제목·절 구조를 보존하면서 사용자 지시에 맞게 전체 문서를 다시 쓰세요. "
            "개조식 요청은 각 절의 핵심 내용을 간결한 항목으로 바꾸고 새로운 사실을 추가하거나 기존 내용을 누락하지 마세요. "
            "최종 편집 가능한 Markdown 본문만 출력하세요."
        )
        user = f"요청: {intent[:1000]}\n현재 보고서 전체 내용:\n{excerpt or previous}"
    elif response_type == "report-artifact":
        system = (
            "당신은 AIWorks 보고서 MCP입니다. 제공된 자료만 근거로 편집 가능한 한국어 보고서를 Markdown으로 작성하세요. "
            "사용자의 요청 문장 전체를 제목으로 복사하지 마세요. 문서 내용을 대표하는 간결한 제목을 정하고, "
            "장 번호가 없는 '# 제목'을 정확히 한 번만 출력한 뒤 본문 장은 '## I. 장 제목', '## II. 장 제목' 순서로 작성하세요. "
            "3개 이상의 ## 절을 포함하고, 확인되지 않은 값은 추측하지 말고 '확인 필요'로 표시하세요. "
            "목록은 Markdown '- '만 사용하며 목록 본문에 ·, •, ○ 같은 글머리표 문자를 넣지 마세요. "
            "[FACT 키] 값은 프로젝트 확정값이므로 같은 의미의 수치를 임의로 바꾸지 마세요. "
            "사용자가 지적사항별 대안을 요구하면 각 지적사항마다 '지적사항-원인-개선대안-향후계획'이 대응되도록 작성하세요. "
            "직전 분석이 1차 원본으로 지정된 경우 요청 주제와 무관한 과거 사례나 다른 사업 내용은 제외하세요."
        )
        user = f"요청: {intent[:1000]}\n프로젝트 확정 메타정보:\n{fact_context or '없음'}\n프로젝트 Markdown 원본:\n{markdown_context or '없음'}\n이전 분석: {previous}\n첨부 자료 발췌: {excerpt}\nMCP 문맥: {mcp_context}"
    else:
        system = (
            "당신은 AIWorks 텍스트 표출 MCP입니다. 연결된 MCP 문맥과 프로젝트 자료만 사용해 빠르고 명확하게 한국어로 답하세요. "
            "근거가 연결되지 않은 값이나 법조항은 추측하지 말고 연결 필요 상태를 명시하세요."
        )
        user = f"요청: {intent[:1000]}\n선택 문구: {selection}\n이전 분석: {previous}\n첨부 자료 발췌: {excerpt}\nMCP 문맥: {mcp_context}"
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]
