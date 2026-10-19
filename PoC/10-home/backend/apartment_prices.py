"""Public R-ONE apartment index observations; one source vintage, no key required."""
import hashlib
import json
import re
from urllib.parse import urlparse
from .api_samples import today
from .area_stats import GYEONGGI
from .collectors import ALLOWED_HOSTS

BASE='https://www.reb.or.kr/r-one/portal/stat/'
TABLE='A_2024_00045'
PAGE=BASE+'easyStatPage/'+TABLE+'.do'
REGIONS={'서울':'서울특별시','경기':'경기도','인천':'인천광역시'}
ALLOWED_HOSTS.add('www.reb.or.kr')


def public_post(fetcher,path,params):
    # These three public statistics endpoints only retrieve published data.
    if path not in {'selectEasyStatDtl.do','statEasyItmJson.do','sttsDataPreviewList.do'}:raise ValueError('공개 통계 조회 경로 확인 필요')
    response=fetcher.client.post(BASE+path,data=params,headers={'Referer':PAGE})
    response.raise_for_status();body=response.content
    value=json.loads(body)
    digest=hashlib.sha256(body).hexdigest();file=fetcher.raw_dir/fetcher.source_id/(digest+'.json');file.parent.mkdir(parents=True,exist_ok=True);file.write_bytes(body)
    fetcher.manifest.append(dict(url=str(response.url),request_parameters=params,sha256=digest,bytes=len(body),file=fetcher.source_id+'/'+file.name))
    return value


def place_for_path(parts):
    parts=list(dict.fromkeys(parts));region=REGIONS.get(parts[0]) if parts else None
    if not region:return None
    if len(parts)==1:return region,None
    name=parts[-1]
    if region=='경기도':return (region,name) if name in GYEONGGI else None
    return (region,name) if name.endswith(('구','군')) else None


def parse_prices(data,source,basis):
    if data.get('RESULT',{}).get('CODE')!=0 or not isinstance(data.get('DATA'),list):raise ValueError('가격지수 원천 응답 확인 필요')
    records=[];seen=set()
    for row in data['DATA']:
        parts=[row[k] for k in sorted(row) if re.fullmatch(r'CATE\d+',k)]
        place=place_for_path(parts)
        if not place:continue
        for key,value in row.items():
            match=re.fullmatch(r'COL_(\d{6})100001OD',key)
            if not match or str(value).strip() in ('','-','…'):continue
            index=float(value)
            if not 0<index<10000:raise ValueError('가격지수 값 확인 필요')
            period=match[1]
            if not 1<=int(period[4:])<=12 or period>today().strftime('%Y%m'):continue
            identity='|'.join([place[0],place[1] or 'ALL',period])
            if identity in seen:raise ValueError('동일 지역·월 가격지수 중복')
            seen.add(identity)
            records.append(('market_price',identity,dict(name=place[1] or place[0],region=place[0],municipality=place[1],period=period[:4]+'-'+period[4:],
                index=index,index_basis=basis,source_id=source['id'],source_table=TABLE,base_date=period[:4]+'-'+period[4:]+'-01',date_precision='MONTH',
                collected_at=today().isoformat(),source_vintage=today().isoformat(),evidence_url=PAGE,
                definition='월간 아파트 매매가격지수. 월 변동률은 동일 조회 판본의 연속된 두 달 게시지수로 산출. 주간 변동률·실거래 평균가격과 구분')))
    if not records:raise ValueError('수도권 가격지수 미확보')
    return records


def collect_prices(source,fetcher):
    metadata=public_post(fetcher,'selectEasyStatDtl.do',dict(statblId=TABLE,metaCallYn='N'))['data']['DATA']
    if metadata.get('statblNm')!='(월) 매매가격지수_아파트':raise ValueError('아파트 가격지수 통계표 변경')
    classes=public_post(fetcher,'statEasyItmJson.do',dict(statblId=TABLE,itmTag='C'))['data']
    selected=[r for r in classes if place_for_path(str(r.get('viewItmFullnm') or '').split('>'))]
    if not selected:raise ValueError('가격지수 지역 분류 미확보')
    params=dict(statblId=TABLE,viewLocOpt='B',wrttimeType='L',dtadvsVal='OD',wrttimeLastestVal='10',wrttimeOrder='A',dtacycleCd='MM',
        wrttimeMinYear='2003',wrttimeMaxYear=str(today().year),wrttimeStartQt='01',wrttimeEndQt='12',wrttimeMinQt='01',wrttimeMaxQt='12',
        optDivVal='00',isRegionData='Y',chkItms='100001',chkClss=','.join(str(r['datano']) for r in selected),searchType='S')
    records=parse_prices(public_post(fetcher,'sttsDataPreviewList.do',params),source,metadata['rpstuiNm'])
    return records,dict(record_count=len(records),latest_period=max(r[2]['period'] for r in records),regions=list(REGIONS.values()),
        source_vintage=today().isoformat(),index_basis=metadata['rpstuiNm'],complete_population=False,
        scope_note='한국부동산원 공개 통계의 수도권 시도·공표 시군구 아파트 지수. 공개 미리보기 최근 10개월, 원문·지수 기준시점 보존. 통계 미공표 지역이나 12개월 비교는 임의 보간하지 않음')
