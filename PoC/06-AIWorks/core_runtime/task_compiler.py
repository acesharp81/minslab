"""Compile a workflow into an explicit, inspectable task contract."""

from __future__ import annotations


def compile_tasks(*, workflow: dict, steps: list[dict], context_contract: dict) -> dict:
    bindings = {
        str(item.get("packageRef") or ""): item
        for item in workflow.get("capabilityBindings") or []
        if isinstance(item, dict)
    }
    tasks = []
    for index, step in enumerate(steps or [], 1):
        package_ref = str(step.get("mcp") or "")
        binding = bindings.get(package_ref, {})
        io_contract = (
            step.get("ioContract")
            if isinstance(step.get("ioContract"), dict)
            else binding.get("ioContract")
            if isinstance(binding.get("ioContract"), dict)
            else {}
        )
        tasks.append({
            "id": str(step.get("id") or f"task-{index}"),
            "order": index,
            "action": str(step.get("action") or ""),
            "capabilityId": str(step.get("capability") or binding.get("capabilityId") or step.get("action") or ""),
            "packageRef": package_ref,
            "runtime": str(step.get("runtime") or "local"),
            "permissions": sorted(set(str(item) for item in step.get("permissions") or [] if str(item))),
            "dependsOn": list(step.get("dependsOn") or ([tasks[-1]["id"]] if tasks else [])),
            "inputArtifactTypes": list(step.get("inputArtifactTypes") or io_contract.get("inputArtifactTypes") or []),
            "optionalInputArtifactTypes": list(step.get("optionalInputArtifactTypes") or io_contract.get("optionalInputArtifactTypes") or []),
            "outputArtifactTypes": list(step.get("outputArtifactTypes") or io_contract.get("outputArtifactTypes") or []),
            "status": str(step.get("status") or "planned"),
        })
    return {
        "contractVersion": "task-compiler/1.0",
        "workflowId": str(workflow.get("id") or ""),
        "responseType": str(workflow.get("responseType") or "text-answer"),
        "projectId": context_contract.get("projectId"),
        "tasks": tasks,
        "requiredCapabilities": list(dict.fromkeys(task["capabilityId"] for task in tasks if task["capabilityId"])),
        "valid": all(task["action"] and task["capabilityId"] and task["packageRef"] and "@" in task["packageRef"] for task in tasks),
    }
