"""Serve the last dated statistic while one background refresh runs."""
from concurrent.futures import ThreadPoolExecutor
from .api_samples import today
import json
import os
from pathlib import Path
from threading import Lock
from time import monotonic

class SourceSummaryCache:
    def __init__(self, path, build, version):
        self.path=Path(path);self.build=build;self.version=version
        self.lock=Lock();self.pool=ThreadPoolExecutor(max_workers=1,thread_name_prefix='source-summary')
        self.future=None;self.data=None;self.stamp=None;self.checked=0;self.failed=False
        try:
            saved=json.loads(self.path.read_text());self.data=saved['data'];self.stamp=saved['version']
        except (OSError,ValueError,KeyError): pass

    def get(self):
        with self.lock:
            if self.future and self.future.done():
                try: self.data,self.stamp=self.future.result();self.failed=False
                except Exception: self.failed=True
                self.future=None;self.checked=monotonic()
            # Version checks are bounded to avoid contention while a bulk import
            # finishes. Displayed generated_at remains the true snapshot time.
            if not self.future and (self.checked==0 or monotonic()-self.checked>=30):
                self.checked=monotonic()
                self.future=self.pool.submit(self._refresh)
            if self.data is None:
                return dict(status='RETRYING' if self.failed else 'BUILDING',refreshing=bool(self.future))
            return dict(self.data,status='READY',refreshing=bool(self.future),refresh_failed=self.failed,
                        snapshot_notice='마지막 완료 집계 · 최신 변경은 백그라운드에서 반영')

    def _refresh(self):
        stamp=repr((today().isoformat(),self.version()))
        if self.data is not None and self.stamp==stamp: return self.data,self.stamp
        data=self.build()
        self.path.parent.mkdir(parents=True,exist_ok=True)
        temp=self.path.with_suffix('.tmp')
        try:
            temp.write_text(json.dumps(dict(data=data,version=stamp),ensure_ascii=False))
            os.replace(temp,self.path)
        except OSError: pass
        return data,stamp
