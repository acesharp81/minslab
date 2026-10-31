"""프로젝트 경로·고유 번호와 별개로 메뉴를 분류하는 파일 기반 카탈로그."""
from __future__ import annotations
import json
from pathlib import Path

BASE_DIR = Path(__file__).parent
PROJECTS_DIR = BASE_DIR / 'projects'
POC_DIR = BASE_DIR / 'PoC'


def _load_collection(root_dir: Path, label: str) -> list[dict]:
    projects = []
    if not root_dir.exists():
        return projects
    for metadata_path in sorted(root_dir.glob('*/project.json')):
        try:
            metadata = json.loads(metadata_path.read_text(encoding='utf-8'))
            if metadata.get('menu_group') == 'hidden':
                continue
            project_dir = metadata_path.parent
            entry_file = metadata.get('entry_file', 'main.py')
            source_path = project_dir / entry_file
            for key, default in {'id': project_dir.name, 'title': project_dir.name,
                                 'date': 'Practice', 'summary': '', 'description': '',
                                 'tags': [], 'features': [], 'usage': [], 'note': ''}.items():
                metadata.setdefault(key, default)
            metadata['file'] = entry_file
            metadata['code'] = ('' if metadata.get('app_path') and not metadata.get('definition_only') else
                                source_path.read_text(encoding='utf-8') if source_path.is_file() else '# 실행 파일을 보존하지 않는 프로젝트입니다.')
            # Folder prefix is an immutable original identifier, never list position.
            original_no = metadata.get('display_no') or project_dir.name.split('-', 1)[0]
            metadata['no'] = str(original_no)
            metadata.setdefault('menu_group', 'poc' if root_dir == POC_DIR else 'portfolio')
            projects.append(metadata)
        except (OSError, ValueError) as error:
            print(f'Skipping invalid {label} project {metadata_path}: {error}')
    return projects


def _catalog(group: str) -> list[dict]:
    projects = _load_collection(PROJECTS_DIR, 'portfolio') + _load_collection(POC_DIR, 'PoC')
    return sorted((p for p in projects if p['menu_group'] == group), key=lambda p: (p.get('order', 999), p['title']))


def load_projects() -> list[dict]:
    return _catalog('portfolio')


def load_poc_projects() -> list[dict]:
    return _catalog('poc')


def _as_json(projects: list[dict]) -> str:
    return json.dumps(projects, ensure_ascii=False).replace('</', '<\\/')


def projects_as_json() -> str:
    return _as_json(load_projects())


def poc_projects_as_json() -> str:
    return _as_json(load_poc_projects())
