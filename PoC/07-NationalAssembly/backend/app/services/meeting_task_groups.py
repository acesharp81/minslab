"""Derived follow-up task groups; source tasks and evidence stay intact."""

from __future__ import annotations

import re
from typing import Any


_DOCUMENT_REQUEST = re.compile(
    r"(?:자료|서류|문서|보고서|내역|현황|직위표|영수증|지급결의서)"
    r".{0,24}(?:제출|송부|제공)"
    r"|(?:자료|서류)제출"
    r"|자료.{0,12}수신.{0,8}요구"
)
_OTHER_ACTION = re.compile(
    r"(?:제도|정책|운영).{0,8}(?:개선|정비|마련)"
    r"|실태\s*점검|계획\s*확정|심사\s*확인|의결\s*완료"
    r"|방식\s*검토|추가\s*검증"
    r"|출석|협조|투명성\s*확보|검증\s*절차|절차\s*확립"
    r"|자료\s*공개|공개\s*요구|의무\s*이행.{0,6}확인"
)


def _unique_values(tasks: list[dict[str, Any]], field: str) -> list[str]:
    return list(dict.fromkeys(
        str(value)
        for task in tasks
        for value in task.get(field) or []
        if value
    ))


def is_document_submission_task(task: dict[str, Any]) -> bool:
    return task.get("task_kind") == "DOCUMENT_SUBMISSION" or bool(
        _DOCUMENT_REQUEST.search(str(task.get("title") or ""))
        and not _OTHER_ACTION.search(str(task.get("title") or "")))


def group_document_submission_tasks(brief: dict[str, Any]) -> list[dict[str, Any]]:
    """Optional within-topic metadata only; never merge requests across subjects."""
    by_topic: dict[str, list[dict[str, Any]]] = {}
    for task in brief.get("tasks") or []:
        if not isinstance(task, dict) or not task.get("id") or task.get("status") == "RESOLVED":
            continue
        ids = task.get("related_topic_ids") or ([task["topic_id"]] if task.get("topic_id") else [])
        if len(ids) == 1 and is_document_submission_task(task):
            by_topic.setdefault(str(ids[0]), []).append(task)
    return [{
        "id": "task-group-document-submission-" + topic_id,
        "kind": "DOCUMENT_SUBMISSION", "scope": "TOPIC",
        "title": "자료 제출 요구", "task_count": len(tasks),
        "task_ids": [str(t["id"]) for t in tasks], "topic_ids": [topic_id],
        "ministries": _unique_values(tasks, "ministries"),
        "evidence_ids": _unique_values(tasks, "evidence_ids"),
        "official_evidence_ids": _unique_values(tasks, "official_evidence_ids"),
    } for topic_id, tasks in by_topic.items() if len(tasks) > 1]
