"""Small authenticated official probes; never persist keys or credential fields."""
import json,os,urllib.request,urllib.parse
from pathlib import Path
OUT=Path('/app/data/official-followup-sources-20261021');OUT.mkdir(exist_ok=True)

def clean(value):
    if isinstance(value,dict):return {k:clean(v) for k,v in value.items() if k.lower() not in ('cert_id','key','apikey','servicekey','access_token')}
    if isinstance(value,list):return [clean(v) for v in value]
    return value

def fetch(name,url,params):
    safe={k:v for k,v in params.items() if k.lower() not in ('key','apikey')}
    try:
        with urllib.request.urlopen(url+'?'+urllib.parse.urlencode(params),timeout=30) as r:data=json.load(r)
        data=clean(data);(OUT/(name+'.json')).write_text(json.dumps(data,ensure_ascii=False,indent=2))
        rows=data if isinstance(data,list) else data.get('result_data',{}).get('formList',[])
        result=dict(name=name,url=url,params=safe,rows=len(rows),status=data.get('result_status') if isinstance(data,dict) else 'LIST',
            error_code=data.get('err') if isinstance(data,dict) else None,columns=list(rows[0]) if rows else [])
    except Exception as exc:result=dict(name=name,url=url,params=safe,error=type(exc).__name__)
    return result

if __name__=='__main__':
    import sys
    if '--kosis-metadata' in sys.argv:
        k=os.environ.get('POC10_KOSIS_API_KEY','');assert k
        results=[fetch('kosis_starts_items','https://kosis.kr/openapi/statisticsItem.do',
            dict(apiKey=k,method='getList',orgId='116',tblId='DT_MLTM_5387',format='json',type='OBJ')),
            fetch('kosis_molit_table_catalog','https://kosis.kr/openapi/statisticsList.do',
            dict(apiKey=k,method='getList',vwCd='MT_OTITLE',parentListId='116',format='json'))]
        (OUT/'kosis_metadata_manifest.json').write_text(json.dumps(results,ensure_ascii=False,indent=2));print(json.dumps(results,ensure_ascii=False));raise SystemExit(0)
    if '--full-starts' in sys.argv:
        k=os.environ.get('POC10_MOLIT_STAT_API_KEY','');assert k
        manifest=[];all_rows=[]
        for year in (2025,2026):
            for month in (3,5,7):
                name=f'molit_5387_{year}{month:02d}_{month+1:02d}'
                result=fetch(name,'https://stat.molit.go.kr/portal/openapi/service/rest/getList.do',dict(key=k,
                    form_id='5387',style_num='1',start_dt=f'{year}{month:02d}',end_dt=f'{year}{month+1:02d}'))
                assert result.get('status',{}).get('status_code')=='INFO-000',name
                data=json.loads((OUT/(name+'.json')).read_text());assert data['result_data']['unitName']=='호'
                for r in data['result_data']['formList']:
                    if r.get('구  분')=='서울':all_rows.append(r)
                manifest.append(result)
        (OUT/'molit_5387_seoul_2025_2026.json').write_text(json.dumps(all_rows,ensure_ascii=False,indent=2))
        (OUT/'molit_5387_full_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
        print(json.dumps(dict(rows=len(all_rows),periods=sorted({r['date'] for r in all_rows})),ensure_ascii=False))
        raise SystemExit(0)
    results=[]
    k=os.environ.get('POC10_MOLIT_STAT_API_KEY','')
    if k:results.append(fetch('molit_5387_202608','https://stat.molit.go.kr/portal/openapi/service/rest/getList.do',
        dict(key=k,form_id='5387',style_num='1',start_dt='202608',end_dt='202608')))
    k=os.environ.get('POC10_KOSIS_API_KEY','')
    if k:results.append(fetch('kosis_5387_202608','https://kosis.kr/openapi/Param/statisticsParameterData.do',
        dict(apiKey=k,method='getList',orgId='116',tblId='DT_MLTM_5387',objL1='ALL',objL2='ALL',objL3='ALL',itmId='ALL',prdSe='M',startPrdDe='202608',endPrdDe='202608',format='json',jsonVD='Y')))
    (OUT/'statistics_probe_manifest.json').write_text(json.dumps(results,ensure_ascii=False,indent=2));print(json.dumps(results,ensure_ascii=False))
