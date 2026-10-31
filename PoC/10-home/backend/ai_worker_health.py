"""Health checks read one heartbeat, never initialize schema or load run history."""
from pathlib import Path
import sqlite3
import time

def online(data_dir):
    path=Path(data_dir)/'runtime'/'ai-collection.sqlite3'
    try:
        with sqlite3.connect(path.as_uri()+'?mode=ro',uri=True,timeout=2) as db:
            row=db.execute('SELECT checked FROM worker WHERE id=1').fetchone()
            return bool(row and time.time()-row[0]<90)
    except (OSError,sqlite3.Error,ValueError):return False
