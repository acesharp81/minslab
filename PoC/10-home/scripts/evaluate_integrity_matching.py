"""Replay pre/post automatic matching on a fixed, source-backed purpose sample.

This measures eligibility to transfer a full-cohort ACTUAL fact, not population
coverage, truth of every field, or pre-announcement detection performance.
Labels below were assigned from the explicit source identity and quantity
statements. No reviewed officer decision is overwritten by this evaluation.
"""
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tarfile
from datetime import date

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from backend import evidence_bridge as current
from backend.data_integrity import classification_metrics

PAIRS=[
 ('PRO_c96377d9ec7e60cf32e1ccdb','DOC_95c94530881ed671d1e20223',True,'마곡17단지 원문이 토지임대부 모집 381호를 직접 특정 · 단지 전체 577호와 구분'),
 ('PRO_c96377d9ec7e60cf32e1ccdb','DOC_888be48e854c94dac1771fa7',True,'마곡17단지 사용검사 원문에 해당 분양 381호 범위 명시'),
 ('PRO_12d91632b8ca640e1505869f','DOC_96131d25e28a18b567965e4c',True,'계양 A17 원문 구성 309+154=463 중 공공분양 309호 모집'),
 ('PRO_f25c0c21ce607faf686e73a5','DOC_40568394acf657168283f458',True,'고양창릉 S1 동일 블록 · 본 모집 494호와 사업 494호 일치'),
 ('PRO_8c391ca1a19b12b73f9bd9bd','DOC_892db81b5fa983eb924c4ffb',True,'파주운정3 A20 동일 블록 · 본 모집 612호 일치'),
 ('PRO_120626d9ffa1c95cd3e9a326','DOC_ca9e3a703ac46be570fdc1e6',True,'남양주진접2 A1 동일 블록 · 본 모집 920호 일치'),
 ('PRO_1f4c8795c658a64e348d64d0','DOC_fedfc4a83f56740572c06f2f',True,'남양주진접2 B1 동일 블록 · 본 모집 260호 일치'),
 ('PRO_8ccbf751972faf82dc5b094d','DOC_adb04e782bf332dd7a47a3f7',True,'검단 AA19 국민임대 991호의 해당 유형 본 모집'),
 ('PRO_3cb5f412f922f460f58516ca','DOC_5be4f81c5f3a090babe74259',True,'검단 AA19 영구임대 332호의 해당 유형 본 모집'),
 ('PRO_1a98096fd39a060c2144684a','DOC_d196e107a1ab4461bccf4973',False,'사업 850호와 금회 610호 부분 모집은 전체 실적으로 전파 불가'),
 ('PRO_a7012ddbc7d3e06fb0580569','DOC_64018500ec307ebf7a6bd073',False,'사업 378호와 금회 377호의 부분 범위'),
 ('PRO_3e4fe820f1cb21379bbbe611','DOC_ecb6331144d4737782f010fd',False,'사업 227호와 금회 116호의 부분 범위'),
 ('PRO_7b3aa15241d24df4972a9f95','DOC_2da3962f3268eb50502ae54c',False,'사업 710호와 금회 405호의 부분 범위'),
 ('PRO_e79e6d9e96f006b1537e24f4','DOC_4cdbbeb8354709b48ee0dc47',False,'사업 561호와 공공분양 금회 251호의 부분 범위'),
 ('PRO_5c41696f54ce584f4f9b324c','DOC_5d7f5935a1f89bcfd63e888a',False,'추가 모집 41호는 사업 350호의 신규 전체 실적 아님'),
 ('PRO_12d91632b8ca640e1505869f','DOC_40568394acf657168283f458',False,'계양과 창릉은 지역·지구·블록이 다른 사업'),
 ('PRO_120626d9ffa1c95cd3e9a326','DOC_2da3962f3268eb50502ae54c',False,'같은 진접2 지구여도 A1과 A7은 다른 블록'),
 ('PRO_8ccbf751972faf82dc5b094d','DOC_5be4f81c5f3a090babe74259',False,'검단 AA19라도 국민임대 991호와 영구임대 332호는 다른 구획'),
 ('PRO_1fbf5c7629634fa05be7652a','DOC_88ac39d7d4dd5104250c7612',False,'사전예약 500호와 향후 본청약 계획은 현재 전체 실적 아님'),
 ('PRO_1fbf5c7629634fa05be7652a','DOC_8c86c11eadbca18ae914485e',False,'사진 등록일은 세대수가 확인된 착공·준공 사건이 아님'),
]


def predict(module, project, source, witnesses):
    pk,sk=module.match_key(project),module.match_key(source)
    if not pk or pk!=sk:return False
    target,total=project.get('planned_units'),source.get('planned_units')
    scoped=module.contained_facts(project,source,witnesses,date(2026,10,16))
    if target!=total and not scoped:return False
    facts=scoped or module.facts(source,date(2026,10,16))
    return any(f.get('kind')=='ACTUAL' and f.get('date') and not f.get('scope_partial')
               and f.get('units',f.get('scope_units',target))==target
               and f.get('notice_round',source.get('notice_round','MAIN'))=='MAIN' for f in facts)


def main():
    folder=ROOT/'data/remediation/r01'
    raw=(folder/'matching-input-before.json').read_bytes();data=json.loads(raw)
    lookup={r['id']:r for r in data['project']+data['document_evidence']}
    with tarfile.open(folder/'source-before.tar.gz') as archive:
        member=next(m for m in archive.getmembers() if m.name.endswith('backend/evidence_bridge.py'))
        code=archive.extractfile(member).read()
    path=Path('/tmp/home-baseline-evidence-bridge.py');path.write_bytes(code)
    spec=importlib.util.spec_from_file_location('backend._baseline_evidence_bridge',path)
    baseline=importlib.util.module_from_spec(spec);spec.loader.exec_module(baseline)
    cases=[]
    for index,(pid,sid,label,basis) in enumerate(PAIRS,1):
        p,s=lookup[pid],lookup[sid]
        witnesses=[r for r in lookup.values() if current.match_key(r)==current.match_key(p)]
        cases.append(dict(id=f'G{index:02}',project_id=pid,source_entity_id=sid,name=p['name'],source_name=s['name'],
                          label=label,label_basis=basis,evidence_url=s.get('evidence_url'),
                          project_revision_no=p['revision_no'],source_revision_no=s['revision_no'],
                          before_prediction=predict(baseline,p,s,witnesses),after_prediction=predict(current,p,s,witnesses)))
    result=dict(dataset_id='HOME-MATCHING-GOLD-20261016-v1',sample_method='PURPOSIVE_REMEDIATION_ACCEPTANCE',
                scope='원문 사건을 해당 사업 전체 구획의 실제 근거로 자동 전파할 수 있는지 이진 판정',
                note='보완 대상과 반례를 의도적으로 선정한 20쌍. 독립적인 무작위·블라인드 평가가 아니며 전체 플랫폼 정확도로 일반화할 수 없습니다. 처음 지표는 변경 전 코드를 동일 동결 입력에 소급 실행한 값이며 당시 측정 기록이나 발표 선행 포착을 뜻하지 않습니다. 수동 확정 연결 성능과 별도입니다.',
                labeler='Codex 원천 내용 대조 · 담당자 독립 재검토 대기',source_input_sha256=hashlib.sha256(raw).hexdigest(),
                baseline_algorithm_sha256=hashlib.sha256(code).hexdigest(),current_algorithm_sha256=hashlib.sha256((ROOT/'backend/evidence_bridge.py').read_bytes()).hexdigest(),
                cases=cases)
    for version in ('before','after'):
        result[version]=classification_metrics([dict(label=c['label'],prediction=c[version+'_prediction']) for c in cases])
    (folder/'matching-evaluation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:result[k] for k in ('before','after')},ensure_ascii=False))


if __name__=='__main__':main()
