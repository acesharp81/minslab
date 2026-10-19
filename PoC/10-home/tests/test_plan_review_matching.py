from backend.plan_review_matching import scope_key

def test_partition_blocks_are_never_collapsed():
    base={'region':'인천광역시'}
    assert scope_key(dict(base,name='인천검단 AA13-1BL 아파트'))==('인천광역시','인천검단','AA13-1')
    assert scope_key(dict(base,name='인천검단 AA13-2BL 아파트'))!=scope_key(dict(base,name='인천검단 AA13-1BL 아파트'))
    assert scope_key(dict(base,name='인천검단 AA1,AA2')) is None

def test_official_scope_names_and_numeric_complexes():
    assert scope_key(dict(region='인천광역시',name='인천계양(공공주택) A-2'))==scope_key(dict(region='인천광역시',name='인천계양 A2BL 아파트 건설공사'))
    assert scope_key(dict(region='서울특별시',name='고덕강일지구 3단지'))==scope_key(dict(region='서울특별시',name='고덕강일 3단지'))
    assert scope_key(dict(region='경기도',name='구리갈매 A1'))!=scope_key(dict(region='경기도',name='구리갈매역세권 A1'))
    assert scope_key(dict(region='경기도',name='테스트 아파트')) is None
