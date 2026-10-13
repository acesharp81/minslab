"""Replay checked official snapshots through the normal collection batch and record link changes."""
import argparse,hashlib,json,io,shutil
from pathlib import Path
from unittest.mock import patch
from pypdf import PdfReader
from backend.db import engine_for,upsert_revision,Audit
from backend.service import HomeService
from backend.evidence_bridge import reconcile,by_project
from backend.api_samples import today
from backend.lh_notice_detail import parse_detail,candidates
from backend.project_collection import collection_matrix


def apply_snapshots(service,snapshot):
    root=Path(snapshot);snapshot_data=json.loads((root/'results.json').read_text())
    checked={m['url']:m for m in snapshot_data['manifest']}
    class SnapshotFetcher:
        def __init__(self,source_id,raw_dir):self.raw_dir=Path(raw_dir);self.manifest=[]
        def close(self):pass
        def get(self,url,suffix='html'):
            m=checked[url];data=(root/'raw'/m['file']).read_bytes()
            if hashlib.sha256(data).hexdigest()!=m['sha256']:raise ValueError('보관 원문 해시 불일치')
            path=self.raw_dir/m['file'];path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
            self.manifest.append(m);return data
    before={r['id'] for r in service.rows('evidence_bridge')}
    with patch('backend.service.Fetcher',SnapshotFetcher):result=service.collect_all('lh_notice_detail')
    if result['results'][0]['status']!='SUCCESS':raise ValueError(str(result))
    meta=json.loads((root/'molit-geumto.json').read_text());body=(root/'molit-geumto.pdf').read_bytes()
    if hashlib.sha256(body).hexdigest()!=meta['sha256'] or not meta['url'].startswith('https://molit.go.kr/LCMS/DWN.jsp?'):raise ValueError('고시 원문 검증 실패')
    text=''.join(p.extract_text() or '' for p in PdfReader(io.BytesIO(body)).pages)
    if not all(t in text for t in ('2023-583','2023년10월23일','438','195','2021.12.31')):raise ValueError('성남금토 고시 본문 검증 실패')
    path=service.data_dir/'raw'/'official_document'/(meta['sha256']+'.pdf');path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(body)
    payload=dict(name='성남금토 A-2BL · 국토부 사업계획 변경승인 제2023-583호',region='경기도',municipality='성남시',district='성남금토',block='A2',
        planned_units=633,tenure='국민·영구',unit_basis='고시의 국민 438호 + 영구 195호; 별도 물량 합산 금지',
        sample_kind='document_evidence',base_date='2023-10-23',date_precision='DAY',original_sha256=meta['sha256'],original_file=str(path.relative_to(service.data_dir)),evidence_url=meta['url'],
        facts=[dict(stage='APPROVAL',kind='ACTUAL',date='2023-10-23',milestone='CHANGE_APPROVAL',basis='국토부 고시 제2023-583호 사업계획 변경승인 · 최초 승인일과 구분; PDF 본문 기준')],
        verification_status='SOURCE_CONTENT_CHECKED',original_approval_date='2021-12-31',scope_breakdown={'국민임대':438,'영구임대':195},
        source_note='원문 머리말 관보 날짜는 서식 자리표시자. 본문 고시번호·2023-10-23 날짜 확인. 이후 변경 여부는 별도 확인 필요.')
    with service.sessions.begin() as db:
        row,outcome=upsert_revision(db,'document_evidence','official_document','molit-geumto-a2-change-2023-583',payload,'official_document_capture')
        if outcome!='unchanged':db.add(Audit(entity_id=row.entity_id,action='OFFICIAL_DOCUMENT_CAPTURE',before={},after=payload))
    final=reconcile(service,apply=True)
    bridges=[r for rows in by_project(service,today()).values() for r in rows]
    return dict(collection=result,new_links=[r for r in bridges if r['id'] not in before],held=final['held'],
        details=[r for r in service.rows('document_evidence') if r['source_id']=='lh_notice_detail'],
        approval_document=payload,matrix=collection_matrix(service))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--snapshot-dir',required=True);p.add_argument('--output',required=True);a=p.parse_args()
    result=apply_snapshots(HomeService(engine_for(),'/app/data'),a.snapshot_dir)
    Path(a.output).write_text(json.dumps(result,ensure_ascii=False,indent=2))
    print(json.dumps(dict(new_links=len(result['new_links']),details=len(result['details']),held=len(result['held'])),ensure_ascii=False))
