import json
from unittest.mock import MagicMock,patch
from backend.policy_geo import _region_outline


def test_unchanged_boundary_survives_restart_and_changed_or_corrupt_cache_rebuilds(tmp_path):
    engine=MagicMock();query=engine.connect.return_value.__enter__.return_value.execute
    query.return_value.mappings.return_value.one.return_value=dict(shape=json.dumps(dict(type='Polygon',coordinates=[[[0,0],[1,0],[1,1],[0,0]]])),anchor=json.dumps(dict(type='Point',coordinates=[.5,.5])))
    with patch.dict('os.environ',{'POC10_DATA_DIR':str(tmp_path)}):
        _region_outline.cache_clear()
        before=_region_outline(engine,'boundary-one')
        assert query.call_count==1
        _region_outline.cache_clear()  # A new API process has no in-memory cache.
        assert _region_outline(engine,'boundary-one')==before
        assert query.call_count==1
        _region_outline(engine,'boundary-two')
        assert query.call_count==2
        for p in (tmp_path/'runtime/region-outlines').glob('*.json'):p.write_text('{invalid')
        _region_outline.cache_clear()
        assert _region_outline(engine,'boundary-one')==before
        assert query.call_count==3
    _region_outline.cache_clear()
