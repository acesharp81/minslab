"""Windows same-user RHWP automation bridge.

Requires Windows, Hancom Office and pywin32:
    py -m pip install pywin32
    set AIWORKS_RHWP_BRIDGE_SECRET=<random secret>
    py rhwp_windows_agent.py
"""

from __future__ import annotations

import hashlib
import hmac
import base64
import json
import os
import sys
import tempfile
import time
from pathlib import Path


PROTOCOL = "aiworks.rhwp-bridge/1"
ALLOWED_EXTENSIONS = {".hwp", ".hwpx", ".hwt", ".hml"}
SAFE_METHODS = {
    "GetFieldList", "GetFieldText", "PutFieldText", "MoveToField", "CreateField",
    "GetPos", "SetPos", "MovePos", "GetTextFile", "SetTextFile", "SelectText",
}
BLOCKED_ACTION_TOKENS = {"script", "macro", "shell", "internet", "hyperlinkopen", "ole"}
SEEN_NONCES: dict[str, int] = {}


def canonical(value: dict) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def verify(envelope: dict) -> None:
    secret = os.getenv("AIWORKS_RHWP_BRIDGE_SECRET", "").encode()
    if len(secret) < 16:
        raise RuntimeError("브리지 비밀키는 16자 이상이어야 합니다.")
    signature = str(envelope.pop("signature", ""))
    expected = hmac.new(secret, canonical(envelope), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected):
        raise RuntimeError("요청 서명이 올바르지 않습니다.")
    now = int(time.time())
    if abs(now - int(envelope.get("timestamp", 0))) > 30:
        raise RuntimeError("만료된 RHWP 요청입니다.")
    nonce = str(envelope.get("nonce", ""))
    if not nonce or not all(character in "0123456789abcdef" for character in nonce) or len(nonce) != 32 or nonce in SEEN_NONCES:
        raise RuntimeError("재사용된 RHWP 요청입니다.")
    nonce_root = Path(os.getenv("LOCALAPPDATA", tempfile.gettempdir())) / "AIWorks" / "rhwp-nonces"
    nonce_root.mkdir(parents=True, exist_ok=True)
    marker = nonce_root / nonce
    try:
        marker.touch(exist_ok=False)
    except FileExistsError as error:
        raise RuntimeError("재사용된 RHWP 요청입니다.") from error
    SEEN_NONCES[nonce] = now
    for old_marker in nonce_root.iterdir():
        try:
            if now - int(old_marker.stat().st_mtime) > 60:
                old_marker.unlink()
        except (OSError, ValueError):
            pass


class RhwpRuntime:
    def __init__(self) -> None:
        try:
            import win32com.client  # type: ignore
        except ImportError as error:
            raise RuntimeError("pywin32가 설치되지 않았습니다.") from error
        self.win32 = win32com.client
        self.hwp = None

    def ensure(self):
        if self.hwp is None:
            self.hwp = self.win32.gencache.EnsureDispatch("HWPFrame.HwpObject")
            try:
                self.hwp.RegisterModule("FilePathCheckDLL", "FilePathCheckerModuleExample")
            except Exception:
                pass
        return self.hwp

    @staticmethod
    def safe_path(value: str, *, output: bool = False) -> str:
        path = Path(value).expanduser().resolve()
        roots = [Path(item).expanduser().resolve() for item in os.getenv("AIWORKS_RHWP_ALLOWED_ROOTS", str(Path.home() / "Documents")).split(os.pathsep) if item]
        if not any(path == root or root in path.parents for root in roots):
            raise RuntimeError("허용된 문서 폴더 밖의 경로입니다.")
        if not output and path.suffix.lower() not in ALLOWED_EXTENSIONS:
            raise RuntimeError("지원하지 않는 한글 문서 형식입니다.")
        return str(path)

    def action(self, name: str, parameter_set: str | None, parameters: dict):
        lowered = name.lower()
        if not name or any(token in lowered for token in BLOCKED_ACTION_TOKENS):
            raise RuntimeError("보안 정책상 차단된 HAction입니다.")
        hwp = self.ensure()
        if not parameter_set:
            return {"executed": bool(hwp.HAction.Run(name)), "action": name}
        params = getattr(hwp.HParameterSet, parameter_set)
        hwp.HAction.GetDefault(name, params.HSet)
        for key, value in parameters.items():
            if key.startswith("_"):
                raise RuntimeError("허용되지 않은 파라미터 이름입니다.")
            setattr(params, key, value)
        return {"executed": bool(hwp.HAction.Execute(name, params.HSet)), "action": name, "parameterSet": parameter_set}

    def invoke(self, tool: str, args: dict) -> dict:
        hwp = self.ensure()
        if tool == "rhwp.capabilities":
            return {"application": "Hancom HWP", "version": str(getattr(hwp, "Version", "")), "hAction": True, "hParameterSet": True}
        if tool == "rhwp.session.status":
            return {"open": self.hwp is not None, "position": list(hwp.GetPos())}
        if tool == "rhwp.session.new":
            hwp.XHwpDocuments.Add()
            return {"created": True}
        if tool == "rhwp.session.open":
            path = self.safe_path(str(args.get("path", "")))
            return {"opened": bool(hwp.Open(path, "", "forceopen:true")), "path": path}
        if tool == "rhwp.session.close":
            hwp.XHwpDocuments.Close(bool(args.get("save", False)))
            return {"closed": True}
        if tool == "rhwp.document.read":
            option = "saveblock:true" if args.get("scope") == "selection" else ""
            return {"text": str(hwp.GetTextFile("UNICODE", option))}
        if tool == "rhwp.document.fields":
            names = [item for item in str(hwp.GetFieldList(0, 0)).split("\x02") if item]
            return {"fields": [{"name": name, "value": str(hwp.GetFieldText(name))} for name in names]}
        if tool == "rhwp.document.position":
            return {"position": list(hwp.GetPos())}
        if tool == "rhwp.document.inspect":
            text = str(hwp.GetTextFile("UNICODE", ""))
            names = [item for item in str(hwp.GetFieldList(0, 0)).split("\x02") if item]
            return {"characters": len(text), "fields": names, "position": list(hwp.GetPos())}
        if tool == "rhwp.document.insert":
            hwp.HAction.GetDefault("InsertText", hwp.HParameterSet.HInsertText.HSet)
            hwp.HParameterSet.HInsertText.Text = str(args.get("text", ""))
            return {"inserted": bool(hwp.HAction.Execute("InsertText", hwp.HParameterSet.HInsertText.HSet))}
        if tool == "rhwp.document.replace":
            parameters = {"FindString": str(args.get("find", "")), "ReplaceString": str(args.get("replace", "")), "IgnoreMessage": 1}
            return self.action("AllReplace" if args.get("all", True) else "ExecReplace", "HFindReplace", parameters)
        if tool == "rhwp.document.set_fields":
            values = args.get("values") or {}
            for name, value in values.items():
                hwp.PutFieldText(str(name), str(value))
            return {"updated": len(values)}
        if tool == "rhwp.document.action":
            return self.action(str(args.get("action", "")), args.get("parameterSet"), args.get("parameters") or {})
        if tool == "rhwp.document.method":
            method = str(args.get("method", ""))
            if method not in SAFE_METHODS:
                raise RuntimeError("허용되지 않은 RHWP 메서드입니다.")
            value = getattr(hwp, method)(*(args.get("arguments") or []))
            return {"method": method, "value": value}
        if tool == "rhwp.document.save":
            return {"saved": bool(hwp.Save())}
        if tool == "rhwp.document.save_as":
            path = self.safe_path(str(args.get("path", "")), output=True)
            return {"saved": bool(hwp.SaveAs(path, str(args.get("format") or ""), "")), "path": path}
        if tool == "rhwp.document.export_pdf":
            path = self.safe_path(str(args.get("path", "")), output=True)
            if Path(path).suffix.lower() != ".pdf":
                raise RuntimeError("PDF 출력 경로가 필요합니다.")
            return {"saved": bool(hwp.SaveAs(path, "PDF", "")), "path": path}
        if tool == "rhwp.document.print":
            return self.action("Print", "HPrint", args.get("parameters") or {})
        if tool == "rhwp.document.undo":
            return {"executed": bool(hwp.HAction.Run("Undo"))}
        if tool == "rhwp.document.redo":
            return {"executed": bool(hwp.HAction.Run("Redo"))}
        if tool == "rhwp.document.transform":
            filename = Path(str(args.get("filename") or "document.hwpx")).name
            if Path(filename).suffix.lower() not in ALLOWED_EXTENSIONS:
                raise RuntimeError("지원하지 않는 한글 문서 형식입니다.")
            try:
                source = base64.b64decode(str(args.get("contentBase64") or ""), validate=True)
            except (ValueError, TypeError) as error:
                raise RuntimeError("문서 바이트가 올바르지 않습니다.") from error
            if not source or len(source) > 15_000_000:
                raise RuntimeError("문서 크기가 허용 범위를 벗어났습니다.")
            root = Path(os.getenv("AIWORKS_RHWP_ALLOWED_ROOTS", str(Path.home() / "Documents")).split(os.pathsep)[0]).expanduser().resolve()
            workspace = root / ".aiworks-rhwp"
            workspace.mkdir(parents=True, exist_ok=True)
            request_id = hashlib.sha256(source + str(time.time_ns()).encode()).hexdigest()[:20]
            source_path = workspace / f"{request_id}-{filename}"
            artifact_path = workspace / f"{request_id}-artifact{Path(filename).suffix}"
            preview_path = workspace / f"{request_id}-preview.pdf"
            source_path.write_bytes(source)
            try:
                if not hwp.Open(str(source_path), "", "forceopen:true"):
                    raise RuntimeError("RHWP가 문서를 열지 못했습니다.")
                results = []
                for operation in args.get("operations") or []:
                    if not isinstance(operation, dict):
                        raise RuntimeError("RHWP operation은 객체여야 합니다.")
                    operation_tool = str(operation.get("tool") or "")
                    if operation_tool == "rhwp.document.transform":
                        raise RuntimeError("중첩 transform은 허용되지 않습니다.")
                    results.append(self.invoke(operation_tool, operation.get("arguments") or {}))
                if not hwp.SaveAs(str(artifact_path), "", ""):
                    raise RuntimeError("RHWP 산출물 저장에 실패했습니다.")
                if not hwp.SaveAs(str(preview_path), "PDF", ""):
                    raise RuntimeError("RHWP PDF 미리보기 생성에 실패했습니다.")
                return {
                    "filename": filename,
                    "contentBase64": base64.b64encode(artifact_path.read_bytes()).decode("ascii"),
                    "previewPdfBase64": base64.b64encode(preview_path.read_bytes()).decode("ascii"),
                    "operations": results,
                }
            finally:
                try:
                    hwp.XHwpDocuments.Close(False)
                except Exception:
                    pass
                for path in (source_path, artifact_path, preview_path):
                    try:
                        path.unlink()
                    except OSError:
                        pass
        raise RuntimeError("지원하지 않는 RHWP 도구입니다.")


def main() -> None:
    runtime = RhwpRuntime()
    for line in sys.stdin:
        request_id = ""
        try:
            envelope = json.loads(line)
            request_id = str(envelope.get("id", ""))
            verify(envelope)
            if envelope.get("protocol") != PROTOCOL:
                raise RuntimeError("지원하지 않는 브리지 프로토콜입니다.")
            result = runtime.invoke(str(envelope.get("tool", "")), envelope.get("arguments") or {})
            response = {"id": request_id, "ok": True, "result": result}
        except Exception as error:
            response = {"id": request_id, "ok": False, "error": str(error)}
        print(json.dumps(response, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
