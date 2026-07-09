"""파일 기반 프로젝트 컬렉션 로더."""

from __future__ import annotations

import json
from pathlib import Path


BASE_DIR = Path(__file__).parent
PROJECTS_DIR = BASE_DIR / "projects"
POC_DIR = BASE_DIR / "PoC"


def _load_collection(root_dir: Path, label: str) -> list[dict]:
    """*/project.json을 읽어 화면에서 사용할 프로젝트 목록을 만든다."""
    projects = []

    if not root_dir.exists():
        return projects

    for metadata_path in sorted(root_dir.glob("*/project.json")):
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            project_dir = metadata_path.parent
            entry_file = metadata.get("entry_file", "main.py")
            source_path = project_dir / entry_file

            metadata.setdefault("id", project_dir.name)
            metadata.setdefault("title", project_dir.name)
            metadata.setdefault("date", "Practice")
            metadata.setdefault("summary", "")
            metadata.setdefault("description", "")
            metadata.setdefault("tags", [])
            metadata.setdefault("features", [])
            metadata.setdefault("usage", [])
            metadata.setdefault("note", "")
            metadata["file"] = entry_file
            metadata["code"] = (
                source_path.read_text(encoding="utf-8")
                if source_path.is_file()
                else "# 실행 파일을 찾을 수 없습니다."
            )
            projects.append(metadata)
        except (OSError, json.JSONDecodeError) as error:
            print(f"Skipping invalid {label} project {metadata_path}: {error}")

    projects.sort(key=lambda item: (item.get("order", 999), item["title"]))
    for index, project in enumerate(projects, start=1):
        project["no"] = str(project.get("display_no") or f"{index:02d}")
    return projects


def load_projects() -> list[dict]:
    """projects/*/project.json을 읽어 포트폴리오 목록을 만든다."""
    return _load_collection(PROJECTS_DIR, "portfolio")


def load_poc_projects() -> list[dict]:
    """PoC/*/project.json을 읽어 PoC 목록을 만든다."""
    return _load_collection(POC_DIR, "PoC")


def _as_json(projects: list[dict]) -> str:
    """HTML script 안에 안전하게 삽입할 JSON을 반환한다."""
    value = json.dumps(projects, ensure_ascii=False)
    return value.replace("</", "<\\/")


def projects_as_json() -> str:
    """HTML script 안에 안전하게 삽입할 JSON을 반환한다."""
    return _as_json(load_projects())


def poc_projects_as_json() -> str:
    """HTML script 안에 안전하게 삽입할 PoC JSON을 반환한다."""
    return _as_json(load_poc_projects())
