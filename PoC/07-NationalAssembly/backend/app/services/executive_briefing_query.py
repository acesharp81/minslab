from __future__ import annotations

import re
from copy import deepcopy
from difflib import SequenceMatcher
from typing import Any

_TOKEN_PATTERN = re.compile(r"[가-힣a-zA-Z0-9]{2,}")
_GENERIC_TOKENS = {
    "관련", "대한", "보고", "계획", "전략", "정부", "국무회의", "년도",
    "의의", "성과", "현황", "추진", "마련", "지원", "정책",
}
_DIRECTIVE_SIGNAL = re.compile(
    r"당부|지시|주문|요청|(?:해|해줄|해\s*주기)\s*바란|"
    r"(?:해|해\s*주면)\s*좋겠|검토해\s*달라|마련해\s*달라|"
    r"개발해\s*달라|성과를\s*내\s*달라|보강해\s*달라|"
    r"속도를\s*내\s*달라|점검해\s*달라|보고해\s*달라|"
    r"고민(?:을\s*많이)?\s*해\s*달라|찾아보라"
)
_BRIEFING_META_SENTENCE = re.compile(
    r"안녕하십니까|말씀드리겠습니다|브리핑을\s*시작|"
    r"지금부터.+(?:보고|설명)드리겠습니다|"
    r"국무회의에서\s*보고한.+(?:설명|말씀)|"
    r"(?:실장|장관|차관|대변인|본부장)\s*[가-힣]{2,4}입니다"
)
_POLICY_ACTION_SENTENCE = re.compile(
    r"추진|확대|강화|개선|완화|도입|설치|구축|지원|공급|운영|"
    r"마련|시행|정립|재설계|통합|점검|정원|인력|청사|시스템|"
    r"하겠습니다|할\s*계획|할\s*예정"
)
_POLICY_SEQUENCE_SENTENCE = re.compile(
    r"^(?:첫째|둘째|셋째|넷째|다섯째|여섯째|마지막으로|먼저|또한|아울러)"
)
_REPORT_CONFIRMATION_TEXT = re.compile(
    r"보고\s*사실이?.*(?:확인됐|확인되었)|"
    r"공식\s*결과문.*(?:보고\s*(?:제목|주제)|담당\s*부처).*(?:확인됐|확인되었|표기|확인\s*중)"
)
_OFFICIAL_POLICY_FACT = re.compile(
    r"통합|인하|확대|축소|개편|시행|추진|구축|공급|지원|개발|"
    r"점검|공개|운영|설치|도입|강화|완화|개선|현황|\d"
)
_PRESIDENTIAL_META_PARAGRAPH = re.compile(
    r"국무회의를\s*주재|오늘\s*회의에서는|"
    r"(?:비공개\s*회의|의안\s*심의)에서는.*(?:심의|의결)|"
    r"국정과제.*법령은\s*총|법률안\s*심의\s*과정.*설명|"
    r"그\s*외\s*자세한\s*내용|청와대\s*수석대변인|^\d{4}년\s*\d{1,2}월"
)
_DIRECTIVE_CONTINUATION = re.compile(r"^(?:이어|다만|이에)\b")
_PRESIDENTIAL_TOPIC_TITLE = re.compile(r"[「『<]([^」』>]{3,100})[」』>]")
_DIRECTIVE_TOPIC_RULES = (
    (re.compile(r"세종.*집무실|집무실.*세종"), "세종집무실·세종의사당 건립"),
    (re.compile(r"경찰.*(?:수사|치안)|(?:수사|치안).*경찰"), "경찰 수사 책임·조직 개혁"),
    (re.compile(r"국세청.*체납관리"), "국세청 체납관리·생산적 일자리"),
    (re.compile(r"노란봉투법"), "노란봉투법 하위법령 정비"),
    (re.compile(r"전시작전권|국군사관학교|핵잠수함"), "국방역량·전시작전권"),
    (re.compile(r"큰비|기후\s*재난"), "기후재난 대응 인프라"),
    (re.compile(r"혐오\s*표현"), "혐오표현 제재방안"),
    (re.compile(r"정책.*(?:홍보|공보)|(?:홍보|공보).*정책"), "정책 홍보·공보 대응"),
)
_TOKEN_SUFFIXES = (
    "으로", "에서", "에게", "까지", "부터", "관련", "대한",
    "에는", "하고", "하며", "과", "와", "을", "를", "이", "가", "은", "는",
)


def _normalize_topic_token(value: str) -> str:
    token = value.casefold()
    for suffix in _TOKEN_SUFFIXES:
        if len(token) >= len(suffix) + 2 and token.endswith(suffix):
            return token[:-len(suffix)]
    return token


def _topic_tokens(value: object) -> set[str]:
    return {
        normalized
        for token in _TOKEN_PATTERN.findall(str(value or ""))
        if (normalized := _normalize_topic_token(token)) not in _GENERIC_TOKENS
        and not token.isdigit()
    }


def _compact(value: object) -> str:
    return re.sub(r"[^0-9a-z가-힣]+", "", str(value or "").casefold())


def _briefing_excerpt_text(
    briefing: dict[str, Any], *, max_sentences: int = 4, max_chars: int = 650,
) -> str:
    relation = briefing.get("relation") or {}
    verified = (
        relation.get("authority_status") == "VERIFIED"
        or briefing.get("authority_status") == "OFFICIAL"
    )
    summary = re.sub(r"<[^>]+>", " ", str(briefing.get("summary") or ""))
    if not verified or not summary.strip():
        return ""
    sentences = [
        " ".join(sentence.split())
        for sentence in re.split(r"(?<=[.!?])\s+", summary)
        if sentence.strip() and not _BRIEFING_META_SENTENCE.search(sentence)
    ]
    candidates: list[tuple[int, int, str]] = []
    for index, sentence in enumerate(sentences):
        if len(sentence) < 20 or sentence.startswith(("<질문>", "<답변>")):
            continue
        score = 0
        if _POLICY_ACTION_SENTENCE.search(sentence):
            score += 4
        if _POLICY_SEQUENCE_SENTENCE.search(sentence):
            score += 2
        if re.search(r"^(?:최근|이는|이로\s*인해)|기인한 것으로", sentence):
            score -= 2
        candidates.append((score, index, sentence))
    ranked = sorted(candidates, key=lambda item: (-item[0], item[1]))
    chosen = sorted(ranked[:max_sentences], key=lambda item: item[1])
    selected: list[str] = []
    for _, _, sentence in chosen:
        if len(" ".join(selected + [sentence])) > max_chars and selected:
            continue
        selected.append(sentence)
    return " ".join(selected)


def _official_briefing_excerpt(report: dict[str, Any]) -> dict[str, Any] | None:
    briefings = list(report.get("related_ministry_briefings") or [])
    briefings.sort(
        key=lambda briefing: (
            "SAME_DAY" in str((briefing.get("relation") or {}).get("relation_type") or ""),
            briefing.get("source_kind") == "POLICY_BRIEFING",
            bool(briefing.get("summary")),
        ),
        reverse=True,
    )
    for briefing in briefings:
        excerpt = _briefing_excerpt_text(briefing)
        if not excerpt:
            continue
        return {
            "label": "부처 보고 내용",
            "text": excerpt,
            "source_label": (
                "공식 부처 보도자료 기반"
                if briefing.get("source_kind") == "PRESS_RELEASE"
                else "공식 부처 브리핑 기반"
            ),
            "authority_status": "OFFICIAL_BRIEFING_DERIVED",
            "source_topic_title": str(briefing.get("title") or ""),
            "source_url": briefing.get("source_url"),
            "broadcast_id": None,
        }
    return None


def _stored_report_summary(report: dict[str, Any]) -> str:
    summary = " ".join(str(report.get("summary") or "").split())
    discussion = " ".join(str(report.get("discussion_summary") or "").split())
    if (
        not summary
        or _REPORT_CONFIRMATION_TEXT.search(summary)
        or (discussion and _compact(summary) == _compact(discussion))
    ):
        return ""
    return summary


def _official_discussion_excerpt(report: dict[str, Any]) -> str:
    discussion = " ".join(str(report.get("discussion_summary") or "").split())
    if not discussion or _REPORT_CONFIRMATION_TEXT.search(discussion):
        return ""
    sentences = [
        sentence.strip()
        for sentence in re.split(r"(?<=[.!?다])\s+", discussion)
        if sentence.strip()
    ]
    facts = [
        sentence for sentence in sentences
        if _OFFICIAL_POLICY_FACT.search(sentence)
        and not _DIRECTIVE_SIGNAL.search(sentence)
    ][:2]
    if not facts:
        return ""
    return " ".join(facts)[:520]


def _best_live_topic(
    report: dict[str, Any], live_brief: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if not live_brief:
        return None
    report_title = str(report.get("topic") or "")
    report_tokens = _topic_tokens(report_title)
    report_compact = _compact(report_title)
    candidates: list[tuple[float, int, dict[str, Any]]] = []
    for index, topic in enumerate(live_brief.get("topics") or []):
        title = str(topic.get("title") or "")
        summary = " ".join(str(topic.get("summary") or "").split())
        if not title or not summary:
            continue
        tokens = _topic_tokens(title)
        shared = report_tokens & tokens
        long_anchor = any(len(token) >= 3 for token in shared)
        compact_title = _compact(title)
        containment = bool(
            min(len(report_compact), len(compact_title)) >= 8
            and (report_compact in compact_title or compact_title in report_compact)
        )
        if not containment and not (
            len(shared) >= 2 or (len(shared) == 1 and long_anchor)
        ):
            continue
        coverage = len(shared) / max(1, min(len(report_tokens), len(tokens)))
        policy_bonus = 0.0
        if (
            "국가재정운용" in report_compact
            and ("예산안편성" in compact_title or "재정운용" in compact_title)
        ):
            policy_bonus = 0.45
        score = coverage + (0.7 if containment else 0.0) + policy_bonus
        candidates.append((score, -index, topic))
    if not candidates:
        return None
    ranked = sorted(candidates, reverse=True, key=lambda item: (item[0], item[1]))
    if len(ranked) > 1 and ranked[0][0] - ranked[1][0] < 0.12:
        return None
    return dict(ranked[0][2])


def _report_content(
    report: dict[str, Any], live_source: dict[str, Any] | None,
) -> dict[str, Any]:
    live_topic = _best_live_topic(
        report, (live_source or {}).get("brief") if live_source else None,
    )
    if live_topic:
        return {
            "label": "부처 보고 내용",
            "text": " ".join(str(live_topic.get("summary") or "").split()),
            "source_label": "LIVE 저장본 요약",
            "authority_status": "PROVISIONAL",
            "source_topic_title": str(live_topic.get("title") or ""),
            "broadcast_id": (live_source or {}).get("broadcast_id"),
        }
    if official_excerpt := _official_briefing_excerpt(report):
        return official_excerpt
    if discussion_excerpt := _official_discussion_excerpt(report):
        return {
            "label": "부처 보고 내용",
            "text": discussion_excerpt,
            "source_label": "공식 대통령실 브리핑 기반",
            "authority_status": "OFFICIAL_DISCUSSION_DERIVED",
            "source_topic_title": str(report.get("topic") or ""),
            "broadcast_id": None,
        }
    if stored_summary := _stored_report_summary(report):
        return {
            "label": "부처 보고 내용",
            "text": stored_summary,
            "source_label": "공식 결과문 요약",
            "authority_status": "OFFICIAL",
            "source_topic_title": None,
            "broadcast_id": None,
        }
    return {
        "label": "부처 보고 내용",
        "text": "공식 결과문에는 세부 보고 내용이 공개되지 않아 확인 가능한 보고 제목·소관 부처·대통령 지시만 제공합니다.",
        "source_label": "공식자료만 반영 · 상세내용 미공개",
        "authority_status": "OFFICIAL_LIMITED",
        "source_topic_title": None,
        "broadcast_id": None,
    }


def _present_agenda(
    agenda: dict[str, Any], live_source: dict[str, Any] | None,
) -> dict[str, Any]:
    item = deepcopy(agenda)
    if item.get("agenda_type") == "REPORT":
        for briefing in item.get("related_ministry_briefings") or []:
            briefing["display_summary"] = _briefing_excerpt_text(
                briefing, max_sentences=3, max_chars=440,
            )
        for guidance in item.get("presidential_guidance") or []:
            # Older snapshots used several labels for the same presentation
            # layer. Keep the source payload intact in storage, but expose one
            # stable label to the web client.
            guidance["label"] = "대통령 지시"
        item["report_content"] = _report_content(item, live_source)
        report_text = _compact(item["report_content"].get("text"))
        duplicate_guidance = any(
            SequenceMatcher(
                None, report_text, _compact(guidance.get("text")),
                autojunk=False,
            ).ratio() >= 0.72
            for guidance in item.get("presidential_guidance") or []
            if report_text and guidance.get("text")
        )
        if duplicate_guidance:
            fallback_item = deepcopy(item)
            fallback_item["related_ministry_briefings"] = []
            item["report_content"] = _report_content(fallback_item, None)
            item["report_content"]["separation_reason"] = (
                "PRESIDENTIAL_GUIDANCE_DUPLICATE_SUPPRESSED"
            )
    return item


def _is_presidential_topic_start(text: str) -> bool:
    stripped = text.strip()
    return bool(
        _PRESIDENTIAL_TOPIC_TITLE.search(stripped)
        or re.search(r".{2,70}(?:와|과)?\s*관련(?:해서는|해서|해|하여)", stripped)
        or "보고받은 후" in stripped
        or re.match(
            r"^(?:비공개\s*회의에서\s*)?(?:끝으로\s*)?(?:이\s*)?대통령은\b",
            stripped,
        )
    )


def _directive_topic_label(text: str) -> str:
    for pattern, label in _DIRECTIVE_TOPIC_RULES:
        if pattern.search(text):
            return label
    if title := _PRESIDENTIAL_TOPIC_TITLE.search(text):
        return " ".join(title.group(1).split())[:70]
    cleaned = re.sub(
        r"^(?:비공개\s*회의에서\s*)?(?:끝으로\s*)?(?:이\s*)?대통령은?\s*",
        "", text,
    )
    cleaned = re.sub(r"^(?:이어|또한|아울러|다만|이에|특히|한편)\s*", "", cleaned)
    related = re.match(
        r"(.{2,70}?)(?:와|과)?\s*관련(?:해서는|해서|해|하여)", cleaned,
    )
    if related:
        return " ".join(related.group(1).strip(" ,·").split())[:70]
    quoted = re.search(r"[‘“]([^’”]{3,44})[’”]", cleaned)
    if quoted:
        candidate = re.split(r"(?:이라는|라는|은|는)\b", quoted.group(1), maxsplit=1)[0]
        if len(candidate.strip()) >= 3:
            return " ".join(candidate.split())[:70]
    candidate = re.split(
        r"(?:라면서|이라면서|하면서|하며|에\s*대해|에게|을\s*향해|를\s*향해)",
        cleaned,
        maxsplit=1,
    )[0]
    candidate = " ".join(candidate.strip(" ,·\"'“”‘’").split())
    if len(candidate) > 52:
        candidate = candidate[:52].rsplit(" ", 1)[0]
    return candidate or "국정 현안 후속조치"


def _directive_summary(texts: list[str]) -> str:
    summaries: list[str] = []
    for text in texts:
        summary = _concise_directive_text(text)
        if not summary or any(
            SequenceMatcher(None, _compact(summary), _compact(existing), autojunk=False).ratio()
            >= 0.86
            for existing in summaries
        ):
            continue
        summaries.append(summary)
    combined = " ".join(summaries)
    if len(combined) <= 560:
        return combined
    shortened = combined[:560]
    boundary = max(shortened.rfind("."), shortened.rfind("다."))
    return shortened[:boundary + 1] if boundary >= 180 else shortened.rstrip() + "…"


def _report_index_for_block(
    text: str,
    reports: list[dict[str, Any]],
    linked_by_source: dict[str, int],
    source_ids: list[str],
) -> int | None:
    linked = {linked_by_source[source_id] for source_id in source_ids if source_id in linked_by_source}
    if len(linked) == 1:
        return next(iter(linked))
    compact_text = _compact(text)
    block_tokens = _topic_tokens(text)
    candidates: list[tuple[float, int]] = []
    for index, report in enumerate(reports):
        title = str(report.get("topic") or "")
        compact_title = _compact(title)
        report_tokens = _topic_tokens(title)
        exact = bool(
            min(len(compact_title), len(compact_text)) >= 8
            and compact_title in compact_text
        )
        shared = report_tokens & block_tokens
        coverage = len(shared) / max(1, len(report_tokens))
        semantic_prefix = len(shared) >= 3 and any(len(token) >= 3 for token in shared)
        if not exact and not (
            (coverage >= 0.5 and any(len(token) >= 4 for token in shared))
            or semantic_prefix
        ):
            continue
        candidates.append((coverage + (1.0 if exact else 0.0), index))
    if not candidates:
        return None
    ranked = sorted(candidates, reverse=True)
    if len(ranked) > 1 and ranked[0][0] - ranked[1][0] < 0.2:
        return None
    return ranked[0][1]


def _presidential_directive_blocks(
    meeting: dict[str, Any], reports: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    paragraphs = []
    for position, paragraph in enumerate(
        (meeting.get("presidential_briefing") or {}).get("paragraphs") or []
    ):
        text = " ".join(str(paragraph.get("text") or "").split())
        paragraphs.append({
            "position": position,
            "source_span_id": str(paragraph.get("source_span_id") or ""),
            "text": text,
            "is_meta": bool(_PRESIDENTIAL_META_PARAGRAPH.search(text)),
        })

    linked_by_source: dict[str, int] = {}
    for report_index, report in enumerate(reports):
        for guidance in report.get("presidential_guidance") or []:
            for source_id in guidance.get("source_span_ids") or []:
                if source_id:
                    linked_by_source[str(source_id)] = report_index

    directives = [
        row for row in paragraphs
        if row["text"] and not row["is_meta"] and _DIRECTIVE_SIGNAL.search(row["text"])
    ]
    blocks: list[dict[str, Any]] = []
    for row in directives:
        merge = False
        if blocks and _DIRECTIVE_CONTINUATION.match(row["text"]):
            previous = blocks[-1]
            between = paragraphs[previous["last_position"] + 1:row["position"]]
            boundary = any(
                item["is_meta"] or _is_presidential_topic_start(item["text"])
                for item in between
            )
            explicit_new_title = bool(_PRESIDENTIAL_TOPIC_TITLE.search(row["text"]))
            merge = not boundary and not explicit_new_title
        if merge:
            blocks[-1]["directives"].append(row)
            blocks[-1]["last_position"] = row["position"]
        else:
            blocks.append({
                "directives": [row],
                "first_position": row["position"],
                "last_position": row["position"],
            })

    assigned: dict[int, list[dict[str, Any]]] = {}
    unlinked: list[dict[str, Any]] = []
    for block in blocks:
        first = block["directives"][0]
        start = block["first_position"]
        if _DIRECTIVE_CONTINUATION.match(first["text"]) and start > 0:
            previous = paragraphs[start - 1]
            if not previous["is_meta"] and _is_presidential_topic_start(previous["text"]):
                start -= 1
        source_rows = [
            row for row in paragraphs[start:block["last_position"] + 1]
            if row["text"] and not row["is_meta"]
        ]
        directive_rows = list(block["directives"])
        source_ids = [row["source_span_id"] for row in directive_rows if row["source_span_id"]]
        context_text = " ".join(row["text"] for row in source_rows)
        report_index = _report_index_for_block(
            context_text, reports, linked_by_source, source_ids,
        )
        item = {
            "content_type": "PRESIDENTIAL_DIRECTIVE",
            "label": "대통령 지시",
            "topic": (
                str(reports[report_index].get("topic") or "")
                if report_index is not None else _directive_topic_label(context_text)
            ),
            "text": " ".join(row["text"] for row in directive_rows),
            "display_text": _directive_summary([row["text"] for row in directive_rows]),
            "target_ministries": (
                list(reports[report_index].get("ministries") or ["관계부처"])
                if report_index is not None else ["관계부처"]
            ),
            "source_span_ids": source_ids,
            "source_paragraphs": [
                {"source_span_id": row["source_span_id"], "text": row["text"]}
                for row in source_rows
            ],
            "authority_status": "OFFICIAL",
        }
        if report_index is None:
            unlinked.append(item)
        else:
            assigned.setdefault(report_index, []).append(item)

    for report_index, items in assigned.items():
        report = reports[report_index]
        report["presidential_guidance"] = [{
            **items[0],
            "topic": str(report.get("topic") or items[0]["topic"]),
            "text": " ".join(item["text"] for item in items),
            "display_text": _directive_summary([item["text"] for item in items]),
            "source_span_ids": [
                source_id for item in items for source_id in item["source_span_ids"]
            ],
            "source_paragraphs": [
                paragraph for item in items for paragraph in item["source_paragraphs"]
            ],
        }]
    return unlinked


def _concise_directive_text(value: object) -> str:
    text = " ".join(str(value or "").split())
    continuation_parts = re.split(r"(?:^|\s)이어\s+", text)
    if len(continuation_parts) > 1:
        actionable_tail = next((
            part for part in reversed(continuation_parts[1:])
            if _DIRECTIVE_SIGNAL.search(part)
        ), "")
        if actionable_tail:
            text = actionable_tail
    quoted = [
        " ".join(item.split())
        for item in re.findall(r"[“\"]([^”\"]{8,})[”\"]", text)
    ]
    actionable = [
        item for item in quoted
        if _DIRECTIVE_SIGNAL.search(item)
        and not re.match(r"^고\s*(?:주문|지시|당부|강조)", item)
    ]
    if actionable:
        text = " ".join(actionable)
    elif len(quoted) == 1 and _DIRECTIVE_SIGNAL.search(quoted[0]):
        text = quoted[0]
    text = re.sub(r"^(?:특히|이어|아울러|또한|끝으로)\s*", "", text)
    text = re.sub(r"^(?:이\s*)?대통령(?:은|이)\s*", "", text)
    text = re.sub(
        r"\s+(?:당부|지시|주문|요청)(?:했|하였)습니다\.?$",
        "",
        text,
    )
    text = re.sub(r"달라고$", "달라", text)
    text = re.sub(r"하라고$", "하라", text)
    text = re.sub(r"바란다고$", "바란다", text)
    text = re.sub(r"바란다면서", "바라며", text)
    text = re.sub(r"(해|내|보강해|점검해|보고해)달라", r"\1 달라", text)
    text = re.sub(r"각별한\s+주의를\s+당부했습니다\.?$", "각별히 주의하도록 했습니다", text)
    text = re.sub(r"각별한\s+주의를\.?$", "각별히 주의하도록 했습니다", text)
    text = text.strip(" .")
    if not text:
        return "공식 지시 내용을 확인할 수 없습니다."
    return text + "."


def build_executive_content_groups(
    meeting: dict[str, Any], agendas: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    selected = agendas if agendas is not None else list(meeting.get("agendas") or [])
    reports = [
        agenda for agenda in selected if agenda.get("agenda_type") == "REPORT"
    ]
    deliberations = [
        agenda for agenda in selected if agenda.get("agenda_type") != "REPORT"
    ]
    unlinked_directives = _presidential_directive_blocks(meeting, reports)
    groups = [
        {
            "key": "ministry_reports",
            "label": "부처 보고 내용",
            "description": "국무회의에서 관계 부처가 보고한 정책·현안",
            "count": len(reports),
            "items": reports,
        },
        {
            "key": "presidential_directives",
            "label": "그 밖의 대통령 지시",
            "description": "특정 부처보고 카드에 연결되지 않은 공식 지시·당부",
            "count": len(unlinked_directives),
            "items": unlinked_directives,
        },
        {
            "key": "deliberated_agendas",
            "label": "심의안건",
            "description": "국무회의가 심의·의결한 법률안·대통령령안 등",
            "count": len(deliberations),
            "items": deliberations,
        },
    ]
    return groups


def build_government_source_flow(
    meeting: dict[str, Any], agendas: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Expose verified government-source relationships without inventing docs."""
    selected_agendas = agendas if agendas is not None else list(meeting.get("agendas") or [])
    meeting_id = str(meeting.get("news_id") or meeting.get("meeting_number") or "meeting")
    council_id = f"state-council:{meeting_id}"
    nodes: list[dict[str, Any]] = [{
        "id": council_id,
        "source_type": "STATE_COUNCIL",
        "institution_label": "국무회의",
        "title": meeting.get("title") or "국무회의 공식 결과",
        "source_url": meeting.get("source_url"),
        "authority_status": "OFFICIAL",
    }]
    links: list[dict[str, Any]] = []

    presidential = meeting.get("presidential_briefing") or {}
    if presidential:
        presidential_id = f"presidential:{presidential.get('briefing_id') or meeting_id}"
        nodes.append({
            "id": presidential_id,
            "source_type": "PRESIDENTIAL_OFFICE",
            "institution_label": "대통령실",
            "title": presidential.get("title") or "대통령실 공식 브리핑",
            "source_url": presidential.get("source_url"),
            "authority_status": "OFFICIAL",
        })
        links.append({
            "from": council_id,
            "to": presidential_id,
            "relation_type": "SAME_MEETING_NUMBER_AND_DATE",
            "label": "같은 회차·날짜의 후속 설명",
            "authority_status": "OFFICIAL_MATCH",
        })

    ministry_agendas: dict[str, dict[str, list[str]]] = {}
    for agenda in selected_agendas:
        for ministry in agenda.get("ministries") or []:
            grouped = ministry_agendas.setdefault(
                str(ministry), {"reports": [], "deliberations": []},
            )
            key = "reports" if agenda.get("agenda_type") == "REPORT" else "deliberations"
            grouped[key].append(str(agenda.get("topic") or "공식 안건"))
    for ministry in sorted(ministry_agendas):
        reports = ministry_agendas[ministry]["reports"]
        deliberations = ministry_agendas[ministry]["deliberations"]
        ministry_id = f"ministry:{ministry}"
        if reports and deliberations:
            ministry_title = f"보고 {len(reports)}건 · 심의안건 {len(deliberations)}건"
        elif reports:
            ministry_title = f"{len(reports)}개 보고 안건"
        else:
            ministry_title = f"{len(deliberations)}개 심의 안건 소관"
        relation_type = (
            "OFFICIAL_REPORTING_MINISTRY" if reports
            else "OFFICIAL_AGENDA_OWNER"
        )
        nodes.append({
            "id": ministry_id,
            "source_type": "MINISTRY",
            "institution_label": ministry,
            "title": ministry_title,
            "agenda_titles": reports + deliberations,
            "authority_status": relation_type,
        })
        links.append({
            "from": council_id,
            "to": ministry_id,
            "relation_type": relation_type,
            "label": (
                "국무회의 원문에 명시된 보고 부처" if reports
                else "공식 안건에 명시된 소관 부처"
            ),
            "authority_status": "OFFICIAL",
        })
    for agenda in selected_agendas:
        for briefing in agenda.get("related_ministry_briefings") or []:
            briefing_id = f"ministry-briefing:{briefing.get('briefing_id')}"
            nodes.append({
                "id": briefing_id,
                "source_type": "MINISTRY_BRIEFING",
                "institution_label": briefing.get("ministry") or "부처",
                "title": briefing.get("title") or "부처 공식 브리핑",
                "source_url": briefing.get("source_url"),
                "authority_status": "OFFICIAL",
            })
            relation = briefing.get("relation") or {}
            links.append({
                "from": council_id,
                "to": briefing_id,
                "relation_type": relation.get("relation_type")
                or "SAME_DAY_MINISTRY_REPORT_BRIEFING",
                "label": relation.get("label")
                or "같은 날·동일 부처·동일 주제의 공식 브리핑",
                "authority_status": relation.get("authority_status") or "VERIFIED",
                "evidence": relation.get("evidence"),
            })
    return {"nodes": nodes, "links": links, "node_count": len(nodes)}


def filter_executive_briefings(
    items: list[dict[str, Any]],
    *,
    ministry: str | None = None,
    query: str | None = None,
    live_briefs_by_official_id: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    ministry_filter = (ministry or "").strip()
    query_filter = (query or "").strip().casefold()
    ministry_counts: dict[str, int] = {}
    for meeting in items:
        for agenda in meeting.get("agendas", []):
            for label in agenda.get("ministries", []):
                ministry_counts[label] = ministry_counts.get(label, 0) + 1

    filtered = []
    for meeting in items:
        live_source = (live_briefs_by_official_id or {}).get(
            str(meeting.get("news_id") or ""),
        )
        agendas = []
        for agenda in meeting.get("agendas", []):
            if ministry_filter and ministry_filter not in agenda.get("ministries", []):
                continue
            related_titles = " ".join(
                str(row.get("title") or "")
                for row in agenda.get("related_ministry_briefings") or []
            )
            searchable = (
                f"{agenda.get('topic', '')} {agenda.get('summary', '')} {related_titles}"
            ).casefold()
            if query_filter and query_filter not in searchable:
                continue
            agendas.append(_present_agenda(agenda, live_source))
        if agendas:
            presented = {
                **meeting,
                "agendas": agendas,
                "agenda_count": len(agendas),
                "live_report_source": live_source,
            }
            reports = [row for row in agendas if row.get("agenda_type") == "REPORT"]
            linked_directives = sum(
                len(row.get("presidential_guidance") or []) for row in reports
            )
            additional = sum(
                len(row.get("related_ministry_briefings") or []) for row in reports
            )
            deliberations = len(agendas) - len(reports)
            presented["content_groups"] = build_executive_content_groups(
                presented, agendas,
            )
            unlinked_directives = next((
                int(group.get("count") or 0)
                for group in presented["content_groups"]
                if group.get("key") == "presidential_directives"
            ), 0)
            presented["presentation_summary"] = (
                f"부처 보고 {len(reports)}건 · "
                f"대통령 지시 {linked_directives + unlinked_directives}건 · "
                f"부처 추가 발표 {additional}건 · 심의안건 {deliberations}건"
            )
            presented["government_flow"] = build_government_source_flow(
                meeting, agendas,
            )
            filtered.append(presented)

    return {
        "items": filtered,
        "meeting_count": len(filtered),
        "agenda_count": sum(len(item["agendas"]) for item in filtered),
        "filters": {"ministry": ministry_filter or None, "q": query_filter or None},
        "facets": {
            "ministries": [
                {"label": label, "count": count}
                for label, count in sorted(
                    ministry_counts.items(), key=lambda item: (-item[1], item[0])
                )
            ],
        },
    }
