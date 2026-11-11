"""Derive audience-specific Markdown from README.md. No external calls."""
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'docs/readme-views'
MARKER = re.compile(r'^<!-- readme:section audiences="([a-z,]+)" -->\s*$', re.M)
ROLES = {'user': ('USER.md', '사용자'), 'maintainer': ('MAINTAINER.md', '유지보수'), 'developer': ('DEVELOPER.md', '재개발자')}


def relative_link(target):
    if target.startswith(('#', '/', '//')) or re.match(r'^[a-zA-Z][\w+.-]*:', target):
        return target
    path, separator, fragment = target.partition('#')
    return Path(os.path.relpath(ROOT / path, OUT)).as_posix() + (separator + fragment if separator else '')


def relocate(text):
    text = re.sub(r'(\]\()([^\s)]+)(\))', lambda m: m[1] + relative_link(m[2]) + m[3], text)
    return re.sub(r'\b(src|href|poster)="([^"]+)"', lambda m: m[1] + '="' + relative_link(m[2]) + '"', text)


def main():
    source = (ROOT / 'README.md').read_text()
    matches = list(MARKER.finditer(source))
    if not matches or source[:matches[0].start()].strip():
        raise ValueError('README must start with an audience section marker')
    sections = []
    for index, match in enumerate(matches):
        roles = set(match[1].split(','))
        if not roles <= set(ROLES) | {'all', 'master'}:
            raise ValueError('Unknown audience: ' + match[1])
        end = matches[index+1].start() if index+1 < len(matches) else len(source)
        sections.append((roles, source[match.end():end].strip()))
    OUT.mkdir(parents=True, exist_ok=True)
    for role, (filename, label) in ROLES.items():
        text = '\n\n'.join(body for roles, body in sections if role in roles or 'all' in roles)
        text = relocate(text)
        text = text.replace('# 업무바통 · PoC 13', '# 업무바통 · PoC 13 — ' + label + ' 버전', 1)
        note = '\n\n> [공통 마스터 README](../../README.md)에서 자동 생성한 문서입니다. 수정은 마스터에서 수행한 뒤 `python3 scripts/build_readme_views.py`로 다시 생성하세요.'
        title_end = text.index('\n', text.index('# 업무바통 · PoC 13'))
        text = text[:title_end] + note + text[title_end:]
        (OUT / filename).write_text(text + '\n')
        print('Generated ' + str((OUT / filename).relative_to(ROOT)))


if __name__ == '__main__':
    main()
