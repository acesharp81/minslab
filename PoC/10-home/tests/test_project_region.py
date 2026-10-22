from datetime import date
from backend.project_region import incheon_municipality, normalize_project_region


def row(name, municipality='지역 상세 확인 필요', **extra):
    return dict(region='인천광역시', name=name, municipality=municipality, **extra)


def test_dated_reorganization_does_not_map_all_legacy_districts_to_one_place():
    assert incheon_municipality(row('인천검단 AA19'), date(2026,10,20)) == '검단구'
    assert incheon_municipality(row('인천검단 AA19'), date(2026,6,30)) == '서구'
    assert incheon_municipality(row('인천영종 A62', '중구'), date(2026,10,20)) == '영종구'
    assert incheon_municipality(row('인천서구 1', '서구'), date(2026,10,20)) is None
    assert incheon_municipality(row('알 수 없는 현장', '중구'), date(2026,10,20)) is None


def test_project_nickname_never_overrides_valid_explicit_district():
    assert incheon_municipality(row('제물포 도심공공복합', '미추홀구')) == '미추홀구'
    assert incheon_municipality(row('남인천 우체국', '남동구')) == '남동구'
    assert incheon_municipality(row('인천계양 A17', '서울 (구 확인 필요)')) == '계양구'


def test_use_source_query_district_detail_without_changing_project_identity():
    source=row('인천서구 1', evidence_url='https://apply.lh.or.kr/x?seBzdtNm=인천서구(거북이기지)')
    assert incheon_municipality(source, date(2026,10,20)) == '서해구'
    result=normalize_project_region(source, date(2026,10,20))
    assert result['name']=='인천서구 1' and result['source_municipality']=='지역 상세 확인 필요'
    assert result['municipality_provenance']['evidence_url'].startswith('https://www.incheon.go.kr/')
    assert incheon_municipality(dict(region='서울특별시',name='검단')) is None


def test_remaining_incheon_projects_and_conflicting_multisite_names():
    for name, expected in [('도화 공공임대 주택건설사업(B3BL)','미추홀구'),('송도 주택건설사업(Rc5-1BL)','연수구'),('인천송림4 1','제물포구'),('인천검암','서해구')]:
        assert incheon_municipality(row(name), date(2026,10,20))==expected
    assert incheon_municipality(row('인천검단 및 인천계양 공동 사업'), date(2026,10,20)) is None
