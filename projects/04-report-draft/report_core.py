"""홈페이지 04 프로젝트에서 재사용하는 민원자료 선택·프롬프트 처리 코어."""

import json
import os
import re
import xml.etree.ElementTree as ET
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "config" / "model_config.json"
XML_PATH = BASE_DIR / "data" / "civil_reply_context.xml"

DEFAULT_MODEL = "qwen2.5:1.5b"
SHARED_ENV_PATH = BASE_DIR.parents[1] / ".env"


def load_shared_env():
    """저장소 루트의 공용 .env를 읽되 기존 환경변수는 유지한다."""
    try:
        lines = SHARED_ENV_PATH.read_text(encoding="utf-8").splitlines()
    except OSError:
        return

    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip(chr(34)).strip(chr(39))
        if key and value and not value.startswith("YOUR_"):
            os.environ.setdefault(key, value)


load_shared_env()


def load_config():
    if not CONFIG_PATH.exists():
        return {
            "ollama_base_url": "http://localhost:11434",
            "temperature": 0.3,
            "num_predict": 500,
            "num_ctx": 2048,
        }

    with CONFIG_PATH.open("r", encoding="utf-8") as file:
        return json.load(file)


def text_of(element, path, default=""):
    found = element.find(path)
    return (found.text or "").strip() if found is not None else default


def list_texts(element, path):
    return [(item.text or "").strip() for item in element.findall(path) if (item.text or "").strip()]


def load_materials():
    tree = ET.parse(XML_PATH)
    root = tree.getroot()
    style = root.find("styleGuide")

    style_guide = {
        "tone": text_of(style, "tone") if style is not None else "",
        "length_rule": text_of(style, "lengthRule") if style is not None else "",
        "must_avoid": text_of(style, "mustAvoid") if style is not None else "",
        "review_notice": text_of(style, "reviewNotice") if style is not None else "",
    }

    cases = []
    for case in root.findall("case"):
        case_data = {
            "id": case.attrib.get("id", ""),
            "reply_type": text_of(case, "replyType"),
            "title": text_of(case, "title"),
            "department": text_of(case, "department"),
            "contact": text_of(case, "contact"),
            "received_issue": text_of(case, "receivedIssue"),
            "facts": list_texts(case, "facts/fact"),
            "action_plan": list_texts(case, "actionPlan/item"),
            "required_sections": text_of(case, "requiredSections"),
            "must_include": text_of(case, "mustInclude"),
            "review_note": text_of(case, "reviewNote"),
            "keywords": text_of(case, "keywords"),
        }
        case_data["search_text"] = " ".join(
            [
                case_data["reply_type"],
                case_data["title"],
                case_data["department"],
                case_data["received_issue"],
                " ".join(case_data["facts"]),
                " ".join(case_data["action_plan"]),
                case_data["required_sections"],
                case_data["must_include"],
                case_data["keywords"],
            ]
        ).lower()
        cases.append(case_data)

    return style_guide, cases


def tokenize(text):
    cleaned = re.sub(r"[^0-9A-Za-z가-힣]+", " ", text.lower())
    return [term for term in cleaned.split() if len(term) >= 2]


def score_case(request_text, case_data):
    request_lower = request_text.lower()
    score = 0

    for term in tokenize(request_text):
        if term in case_data["search_text"]:
            score += 1
        if term in case_data["title"].lower():
            score += 2
        if term in case_data["keywords"].lower():
            score += 3

    for keyword in [item.strip().lower() for item in case_data["keywords"].split(";") if item.strip()]:
        if keyword and keyword in request_lower:
            score += 6

    return score


def select_best_case(request_text, cases):
    if not cases:
        raise ValueError("민원자료 XML에서 case 항목을 찾을 수 없습니다.")

    return max(cases, key=lambda case_data: score_case(request_text, case_data))


def bullet_lines(items):
    return "\n".join(f"- {item}" for item in items)


def split_semicolon(text):
    return [item.strip() for item in text.split(";") if item.strip()]


def section_example(section, case_data):
    facts = " ".join(case_data["facts"])
    action_plan = " ".join(case_data["action_plan"])
    must_include = ", ".join(split_semicolon(case_data["must_include"]))

    if "문의처" in section:
        return f"{section}: {case_data['contact']}"
    if section in ("조치계획", "협조사항", "임시조치", "향후일정", "신고방법"):
        return f"{section}: {action_plan} 필수 반영: {must_include}"
    if section in ("검토결과", "현장검토", "현장확인", "단수일시", "대상지역", "선정방식"):
        return f"{section}: {facts}"
    return f"{section}: {case_data['received_issue']}"


def build_prompt(request_text, style_guide, case_data):
    sections = [section.strip() for section in case_data["required_sections"].split(";") if section.strip()]
    sections = sections[:5] or ["내용", "조치계획", "문의처"]
    json_lines = ",".join(json.dumps(section_example(section, case_data), ensure_ascii=False) for section in sections)

    return f"""아래 민원자료에 포함된 사실관계, 조치계획, 필수 포함문구만 근거로 사용해 한국어 초안을 작성하세요.

[사용자 요청]
{request_text}

[선택 민원자료]
- 자료 ID: {case_data["id"]}
- 초안 유형: {case_data["reply_type"]}
- 제목: {case_data["title"]}
- 담당부서: {case_data["department"]}
- 문의처: {case_data["contact"]}
- 접수/안내 배경: {case_data["received_issue"]}

[사실관계]
{bullet_lines(case_data["facts"])}

[조치계획]
{bullet_lines(case_data["action_plan"])}

[필수 섹션]
{case_data["required_sections"]}

[필수 포함문구]
{case_data["must_include"]}

[담당자 검토 메모]
{case_data["review_note"]}

[작성 규칙]
- 문체: {style_guide.get("tone", "정중하고 간결한 행정문체")}
- 길이: 4~5줄, 최대 8줄 이내
- 피해야 할 내용: {style_guide.get("must_avoid", "확정 보장, 법령 단정, 개인정보 직접 기재")}
- 자료에 없는 주소, 법령, 수치, 확정 일정을 새로 만들지 마세요.
- 담당자 검토 필요 안내는 앱 화면에 별도 표시되므로 본문에는 초안 내용만 작성하세요.
- 마크다운 제목, 표, 코드블록, 인사말 없이 본문만 작성하세요.
- 각 줄은 "섹션명: 내용" 형식의 한 문장으로 작성하세요.
- 사실관계, 조치계획, 필수 포함문구, 문의처가 모두 드러나야 합니다.
- 필수 포함문구의 각 항목을 빠뜨리지 말고 조치계획 또는 협조사항 줄에 반영하세요.

[출력 형식]
섹션명은 반드시 다음 순서와 이름을 사용하세요: {", ".join(sections)}
아래 형식의 JSON만 반환하세요.
{{"lines":[{json_lines}]}}
"""


def clean_line(line):
    cleaned = line.strip()
    if cleaned.startswith("```") or cleaned.lower() in ("json", "korean"):
        return ""
    cleaned = re.sub(r"^#+\s*", "", cleaned)
    cleaned = re.sub(r"^\d+[.)]\s*", "", cleaned)
    cleaned = re.sub(r"^[-*]\s*", "", cleaned)
    cleaned = re.sub(r"[:：]\s*[-*]\s*", ": ", cleaned)
    cleaned = cleaned.replace("**", "").replace("__", "").strip()
    if re.fullmatch(r"[^:：]{1,24}[:：]", cleaned):
        return ""
    return cleaned


def limit_to_eight_lines(text):
    cleaned = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    lines = [line.strip() for line in cleaned.split("\n") if line.strip()]

    if len(lines) <= 1 and "다." in cleaned:
        parts = [part.strip() for part in cleaned.split("다.") if part.strip()]
        lines = [f"{part}다." for part in parts]

    lines = [clean_line(line) for line in lines]
    lines = [line for line in lines if line]

    return "\n".join(lines[:8]).strip()


def extract_answer(raw_text):
    cleaned = raw_text.strip()
    candidates = [cleaned]

    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidates.append(cleaned[start : end + 1])

    for candidate in candidates:
        try:
            data = json.loads(candidate)
        except json.JSONDecodeError:
            continue

        if isinstance(data, dict):
            lines = data.get("lines")
            if isinstance(lines, list):
                return limit_to_eight_lines("\n".join(str(line) for line in lines))

            answer = data.get("answer") or data.get("response")
            if isinstance(answer, str):
                return limit_to_eight_lines(answer)

    return limit_to_eight_lines(cleaned)


def finalize_answer(answer, case_data):
    lines = [line for line in answer.split("\n") if line.strip()]
    contact = case_data.get("contact", "").strip()

    if contact and contact not in answer:
        contact_line = f"문의처: {contact}"
        replaced = False
        for index, line in enumerate(lines):
            if line.startswith("문의처:"):
                lines[index] = contact_line
                replaced = True
                break
        if not replaced:
            lines.append(contact_line)

    return "\n".join(lines[:8]).strip()
