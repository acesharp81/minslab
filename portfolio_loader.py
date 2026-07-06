"""파일 기반 포트폴리오 프로젝트 로더."""

from __future__ import annotations

import json
from pathlib import Path


PROJECTS_DIR = Path(__file__).parent / "projects"


def load_projects() -> list[dict]:
    """projects/*/project.json을 읽어 화면에서 사용할 프로젝트 목록을 만든다."""
    projects = []

    if not PROJECTS_DIR.exists():
        return projects

    for metadata_path in sorted(PROJECTS_DIR.glob("*/project.json")):
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
            print(f"Skipping invalid portfolio project {metadata_path}: {error}")

    projects.sort(key=lambda item: (item.get("order", 999), item["title"]))
    for index, project in enumerate(projects, start=1):
        project["no"] = str(project.get("display_no") or f"{index:02d}")
    return projects


def projects_as_json() -> str:
    """HTML script 안에 안전하게 삽입할 JSON을 반환한다."""
    value = json.dumps(load_projects(), ensure_ascii=False)
    return value.replace("</", "<\\/")
