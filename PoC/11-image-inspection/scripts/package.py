"""Portable source archive. Explicit allowlist excludes secrets, uploads and runtime data."""
from pathlib import Path
import zipfile
root=Path(__file__).resolve().parents[1];out=root/'data'/'chekmi-poc11-source.zip';out.parent.mkdir(exist_ok=True)
files=['README.md','.env.example','.gitignore','.dockerignore','requirements.txt','requirements-dev.txt','requirements.lock','requirements-ocr.txt','requirements-ocr.lock','pytest.ini','Dockerfile','compose.yaml','project.json']
for folder in ('app','web','rules','scripts','docs','tests','samples','deploy'):
    files += [str(p.relative_to(root)) for p in (root/folder).rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix not in ('.pyc','.zip')]
with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
    for f in files:
        p=root/f
        if p.exists():z.write(p,'11-image-inspection/'+f)
    assert not any(n.endswith('/.env') or '/data/' in n or '/.venv/' in n for n in z.namelist())
print(out)
