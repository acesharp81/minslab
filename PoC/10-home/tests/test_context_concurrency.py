from concurrent.futures import ThreadPoolExecutor
from threading import Event
from time import monotonic
from types import SimpleNamespace
from unittest.mock import MagicMock,patch
import pytest


@pytest.mark.parametrize('module_name,class_name,with_label',[
    ('infrastructure','InfrastructureContext',True),('building_context','BuildingContext',False)])
def test_cached_location_is_not_blocked_by_another_locations_network_request(tmp_path,module_name,class_name,with_label):
    import importlib
    mod=importlib.import_module('backend.'+module_name);context=getattr(mod,class_name)()
    started=Event();release=Event();anchor=dict(latitude=37.5,longitude=127.1,coordinate_basis='APPROXIMATE_ADDRESS',label='대표 위치')
    key=('ready',37.5,127.1,'APPROXIMATE_ADDRESS')+(('대표 위치',) if with_label else ())
    context._cache[key]=(monotonic(),{'ready':True})
    fetcher=MagicMock();fetcher.manifest=[]
    def fetch(*args,**kwargs):
        started.set()
        if not release.wait(3):raise RuntimeError('test timed out')
        return b'{"response":{"status":"NOT_FOUND"}}'
    fetcher.get.side_effect=fetch
    with patch.object(mod,'Fetcher',return_value=fetcher),patch.object(mod,'key_for',return_value='test'):
        with ThreadPoolExecutor(max_workers=2) as pool:
            slow=pool.submit(context.get,'slow',SimpleNamespace(data_dir=tmp_path,rows=lambda kind:[]),anchor)
            try:
                assert started.wait(1)
                hit=pool.submit(context.get,'ready',SimpleNamespace(data_dir=tmp_path),anchor)
                assert hit.result(timeout=.5)=={'ready':True}
            finally:release.set()
            assert slow.result(timeout=2)['block_id']=='slow'
