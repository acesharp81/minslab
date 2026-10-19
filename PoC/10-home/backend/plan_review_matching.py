"""Exact physical scope keys for delegated plan review; no fuzzy policy inference."""
import re
from .subject_identity import numeric_complex_key

BLOCK=re.compile(r'(?<![A-Za-z])([A-Za-z]{1,3})\s*[-－]?\s*(\d+)(?:\s*[-－]\s*(\d+))?(?:BL|블록)?',re.I)

def scope_key(row):
    region=row.get('region');name=str(row.get('name') or row.get('district_name') or '')
    if not region:return None
    numeric=numeric_complex_key(row)
    if numeric:return numeric
    # Ignore descriptive parentheses, but retain partition suffixes AA13-1/AA13-2.
    label=re.sub(r'\([^)]*\)','',name)
    hits=list(BLOCK.finditer(label));codes={(m[1].upper()+str(int(m[2]))+('-'+str(int(m[3])) if m[3] else '')) for m in hits}
    explicit=str(row.get('block') or '')
    block=BLOCK.fullmatch(explicit)
    if not hits and block:
        code=block[1].upper()+str(int(block[2]))+('-'+str(int(block[3])) if block[3] else '')
        district=row.get('district') or row.get('district_name')
    elif len(codes)==1:
        code=next(iter(codes));district=row.get('district') or row.get('district_name') or label[:hits[0].start()]
    else:return None
    if not district:return None
    district=re.sub(r'\([^)]*(?:\)|$)','',district)
    district=re.sub(r'^(?:조달청|민간참여)\)\s*','',district)
    district=re.sub(r'\s+','',district).replace('국제화계획','')
    district=re.sub(r'(?:공공주택지구|공공주택|택지개발사업|택지개발지구|지구)+$','',district)
    if not district or re.search(r'[,/·]',district):return None
    return region,district,code
