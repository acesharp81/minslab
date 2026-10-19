"""Conservative physical keys; numeric SH complexes are not LH block codes."""
import re


def numeric_complex_key(row):
    region = row.get('region')
    if not region:
        return None
    text = str(row.get('name') or '').replace(' ', '')
    hits = re.findall(r'([가-힣]+?)(?:지구)?(\d+)단지', text)
    if len(set(hits)) != 1:
        return None
    district, number = hits[0]
    district = district.removesuffix('지구')
    if not district or len(district) < 2:
        return None
    return region, district, 'COMPLEX_' + str(int(number))


def normalized_tenure(row):
    text = ' '.join(str(row.get(key) or '') for key in ('tenure', 'program', 'name'))
    for kind in ('국민임대', '영구임대', '행복주택', '통합공공임대', '공공분양'):
        if kind in text:
            return kind
    return '공공분양' if '토지임대부' in text else None


def taxonomy(row):
    text = ' '.join(str(row.get(k) or '') for k in ('name', 'program', 'tenure', 'source_id'))
    mode = ('NEW_PURCHASE_AGREEMENT' if '약정' in text else 'EXISTING_PURCHASE' if '매입' in text else
            'LEASE_SUPPORT' if '전세임대' in text else 'REDEVELOPMENT' if any(w in text for w in ('재개발', '재건축', '재정비')) else 'NEW_BUILD')
    tenure = normalized_tenure(row)
    supply = 'SALE' if tenure == '공공분양' or '분양' in text else 'RENT' if tenure or '임대' in text else 'UNKNOWN'
    target = 'YOUTH' if '청년' in text else 'NEWLYWED' if '신혼' in text else 'ELDERLY' if '고령' in text else 'UNSPECIFIED'
    return dict(acquisition_mode=mode, supply_mode=supply, target_group=target,
                construction_applicable=mode not in ('LEASE_SUPPORT', 'EXISTING_PURCHASE'),
                classification_basis='원천 명시 용어 · 미표기 속성은 미확정')
