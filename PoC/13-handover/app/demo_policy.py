"""Identify demo workloads for explicit, manual-only GPT image analysis."""
from functools import lru_cache
from pathlib import Path
import hashlib,zipfile

@lru_cache(maxsize=4)
def sample_hashes(root):
    result=set()
    for name in ['comprehensive-base.zip','comprehensive-current.zip','comprehensive-old.zip','comprehensive-draft.zip','practice-samples.zip','version-samples.zip','version-samples-shuffled.zip','flow-samples.zip','01_최신본_먼저등록.zip','02_구판_나중등록.zip','03_미승인초안_마지막등록.zip','01_이전인계_원본.zip','02_현행화_신규업무.zip','grouping-samples.zip']:
        path=Path(root)/'release/public'/name
        if not path.exists():continue
        with zipfile.ZipFile(path) as z:
            result.update(hashlib.sha256(z.read(n)).hexdigest() for n in z.namelist() if not n.endswith('/'))
    return result

def is_demo(db,case_id,root):
    if db.execute("SELECT 1 FROM audit WHERE case_id=? AND action IN ('DEMO_SEED','CONTINUATION_DEMO','DEMO_SET') LIMIT 1",(case_id,)).fetchone():return True
    known=sample_hashes(str(root))
    return any(row[0] in known for row in db.execute('SELECT sha FROM documents WHERE case_id=?',(case_id,)))
