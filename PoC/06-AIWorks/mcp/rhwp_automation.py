"""RHWP Automation MCP contract and authenticated native-bridge client."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import shlex
import subprocess
import time
from typing import Callable


MANIFEST = {
    "id": "document.rhwp",
    "name": "RHWP 전체 기능 자동화",
    "version": "1.0.0",
    "runtime": "hybrid",
    "description": "Windows 한글 자동화 객체를 고수준 문서 도구와 HAction/HParameterSet 실행기로 제공합니다.",
    "inputs": {"tool": {"type": "string"}, "arguments": {"type": "object"}},
    "outputs": {"result": {"type": "object"}},
    "permissions": [
        {"scope": "document.read", "reason": "열린 한글 문서와 선택 영역 읽기", "required": True},
        {"scope": "document.write", "reason": "승인된 편집·저장·출력 실행", "required": True},
    ],
    "supports": [".hwp", ".hwpx", ".hwt", ".hml", ".pdf", "HAction", "HParameterSet"],
    "dependencies": [],
    "visibility": "organization",
    "sourceIncluded": False,
}


READ_TOOLS = {
    "rhwp.capabilities",
    "rhwp.session.status",
    "rhwp.document.inspect",
    "rhwp.document.read",
    "rhwp.document.fields",
    "rhwp.document.position",
}
WRITE_TOOLS = {
    "rhwp.session.new",
    "rhwp.session.open",
    "rhwp.session.close",
    "rhwp.document.insert",
    "rhwp.document.replace",
    "rhwp.document.set_fields",
    "rhwp.document.action",
    "rhwp.document.method",
    "rhwp.document.save",
    "rhwp.document.save_as",
    "rhwp.document.export_pdf",
    "rhwp.document.print",
    "rhwp.document.undo",
    "rhwp.document.redo",
    "rhwp.document.transform",
}
TOOLS = {
    "rhwp.capabilities": ("런타임·한글 버전·지원 기능 확인", {}),
    "rhwp.session.status": ("현재 문서와 선택 상태 확인", {}),
    "rhwp.session.new": ("새 한글 문서 생성", {}),
    "rhwp.session.open": ("HWP/HWPX/HWT/HML 문서 열기", {"path": "string"}),
    "rhwp.session.close": ("현재 문서 닫기", {"save": "boolean"}),
    "rhwp.document.inspect": ("문서 속성·필드·본문 구조 읽기", {}),
    "rhwp.document.read": ("전체/선택 영역 텍스트 읽기", {"scope": "all|selection"}),
    "rhwp.document.fields": ("누름틀·필드 목록과 값 읽기", {}),
    "rhwp.document.position": ("캐럿 위치 읽기", {}),
    "rhwp.document.insert": ("현재 위치에 텍스트 삽입", {"text": "string"}),
    "rhwp.document.replace": ("찾기/바꾸기", {"find": "string", "replace": "string", "all": "boolean"}),
    "rhwp.document.set_fields": ("필드 값 일괄 입력", {"values": "object"}),
    "rhwp.document.action": ("HAction/HParameterSet 실행", {"action": "string", "parameterSet": "string?", "parameters": "object"}),
    "rhwp.document.method": ("허용된 RHWP 메서드 호출", {"method": "string", "arguments": "array"}),
    "rhwp.document.save": ("현재 문서 저장", {}),
    "rhwp.document.save_as": ("새 경로/형식으로 저장", {"path": "string", "format": "string?"}),
    "rhwp.document.export_pdf": ("PDF로 내보내기", {"path": "string"}),
    "rhwp.document.print": ("인쇄 대화상자 또는 승인된 출력 실행", {"parameters": "object"}),
    "rhwp.document.undo": ("실행 취소", {}),
    "rhwp.document.redo": ("다시 실행", {}),
    "rhwp.document.transform": ("문서 바이트를 RHWP로 열어 명령 실행·저장·PDF 스냅샷 생성", {"filename": "string", "contentBase64": "string", "operations": "array"}),
}


class RhwpMcpError(RuntimeError):
    pass


def _secret() -> bytes:
    value = os.getenv("AIWORKS_RHWP_BRIDGE_SECRET", "").strip()
    if not value:
        raise RhwpMcpError("AIWORKS_RHWP_BRIDGE_SECRET이 설정되지 않았습니다.")
    return value.encode("utf-8")


def _canonical(value: dict) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def tool_catalog() -> list[dict]:
    return [
        {
            "name": name,
            "description": detail[0],
            "input": detail[1],
            "permission": "document.read" if name in READ_TOOLS else "document.write",
        }
        for name, detail in TOOLS.items()
    ]


def runtime_status() -> dict:
    command = os.getenv("AIWORKS_RHWP_BRIDGE_COMMAND", "").strip()
    return {
        "configured": bool(command),
        "available": bool(command and os.getenv("AIWORKS_RHWP_BRIDGE_SECRET", "").strip()),
        "transport": "authenticated-stdio",
        "runtime": "windows-native-bridge",
        "tools": len(TOOLS),
        "restrictions": ["same-user child process", "HMAC request signing", "no bridge network", "macro and shell calls blocked"],
    }


def _validate(tool: str, arguments: dict, approved_permissions: list[str], confirmed: bool) -> None:
    if tool not in TOOLS:
        raise RhwpMcpError("등록되지 않은 RHWP 도구입니다.")
    if not isinstance(arguments, dict):
        raise RhwpMcpError("arguments는 객체여야 합니다.")
    required = "document.read" if tool in READ_TOOLS else "document.write"
    if required not in approved_permissions:
        raise RhwpMcpError(f"{required} 권한 승인이 필요합니다.")
    if tool in WRITE_TOOLS and not confirmed:
        raise RhwpMcpError("문서 변경 작업은 사용자의 명시적 확인이 필요합니다.")
    encoded = _canonical(arguments)
    limit = 20_000_000 if tool == "rhwp.document.transform" else 1_000_000
    if len(encoded) > limit:
        raise RhwpMcpError(f"RHWP 요청은 {limit:,}바이트를 넘을 수 없습니다.")


def _envelope(tool: str, arguments: dict) -> dict:
    body = {
        "protocol": "aiworks.rhwp-bridge/1",
        "id": "rhwp_" + secrets.token_hex(16),
        "timestamp": int(time.time()),
        "nonce": secrets.token_hex(16),
        "tool": tool,
        "arguments": arguments,
    }
    body["signature"] = hmac.new(_secret(), _canonical(body), hashlib.sha256).hexdigest()
    return body


def _subprocess_transport(envelope: dict) -> dict:
    command = os.getenv("AIWORKS_RHWP_BRIDGE_COMMAND", "").strip()
    if not command:
        raise RhwpMcpError("Windows RHWP 브리지 명령이 설정되지 않았습니다.")
    timeout = max(2, min(120, int(os.getenv("AIWORKS_RHWP_BRIDGE_TIMEOUT", "30"))))
    try:
        completed = subprocess.run(
            shlex.split(command),
            input=json.dumps(envelope, ensure_ascii=False) + "\n",
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
            env={**os.environ, "NO_PROXY": "*", "no_proxy": "*"},
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise RhwpMcpError(f"RHWP 브리지 실행 실패: {error}") from error
    if completed.returncode != 0:
        detail = completed.stderr.strip()[:500] or f"exit {completed.returncode}"
        raise RhwpMcpError(f"RHWP 브리지 오류: {detail}")
    try:
        response = json.loads(completed.stdout.strip().splitlines()[-1])
    except (json.JSONDecodeError, IndexError) as error:
        raise RhwpMcpError("RHWP 브리지 응답이 올바른 JSON이 아닙니다.") from error
    return response


def invoke(
    tool: str,
    arguments: dict,
    approved_permissions: list[str],
    confirmed: bool,
    *,
    transport: Callable[[dict], dict] | None = None,
) -> dict:
    _validate(tool, arguments, approved_permissions, confirmed)
    envelope = _envelope(tool, arguments)
    response = (transport or _subprocess_transport)(envelope)
    if not isinstance(response, dict) or response.get("id") != envelope["id"]:
        raise RhwpMcpError("RHWP 브리지 응답 ID가 일치하지 않습니다.")
    if not response.get("ok"):
        raise RhwpMcpError(str(response.get("error") or "RHWP 도구 실행에 실패했습니다."))
    return {
        "tool": tool,
        "requestId": envelope["id"],
        "result": response.get("result") or {},
        "runtime": "windows-native-bridge",
        "externalTransfer": False,
    }
