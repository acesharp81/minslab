"""Describe why fixed MCP package versions were selected for a task."""

from __future__ import annotations


def describe(*, workflow: dict, task_contract: dict) -> dict:
    bindings = {
        str(item.get("packageRef") or ""): item
        for item in workflow.get("capabilityBindings") or []
        if isinstance(item, dict)
    }
    decisions = []
    for task in task_contract.get("tasks") or []:
        package_ref = task.get("packageRef")
        binding = bindings.get(package_ref, {})
        decisions.append({
            "taskId": task.get("id"),
            "packageRef": package_ref,
            "packageId": str(binding.get("packageId") or str(package_ref).split("@", 1)[0]),
            "versionPinned": "@" in str(package_ref),
            "capabilityId": str(binding.get("capabilityId") or task.get("action") or ""),
            "executionAdapter": str(binding.get("executionAdapter") or task.get("runtime") or "local"),
            "rankScore": binding.get("rankScore"),
            "matchedBy": list(binding.get("matchedBy") or []),
            "ioContract": dict(binding.get("ioContract") or {
                "inputArtifactTypes": task.get("inputArtifactTypes") or [],
                "optionalInputArtifactTypes": task.get("optionalInputArtifactTypes") or [],
                "outputArtifactTypes": task.get("outputArtifactTypes") or [],
            }),
            "reason": str(
                binding.get("selectionReason")
                or binding.get("reason")
                or binding.get("description")
                or "컴파일된 작업의 입출력과 권한을 충족하는 설치 MCP를 선택했습니다."
            ),
        })
    return {
        "contractVersion": "capability-resolution/1.0",
        "workflowId": task_contract.get("workflowId"),
        "decisions": decisions,
        "valid": all(item["packageRef"] and item["versionPinned"] for item in decisions),
    }
