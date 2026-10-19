"""Build the continuation report from frozen review artifacts, without DB writes."""
import csv
import hashlib
import json
import shutil
import zipfile
from collections import Counter
from datetime import date
from pathlib import Path

from backend.policy_delivery import comparison_index

ROOT=Path(__file__).resolve().parents[1]
WORK=ROOT/'data/continuation-20261020'
OUT=ROOT/'docs/analysis/continuation_20261020'
REPORT=ROOT/'docs/analysis/HOME_COLLECTION_CONTINUATION_20261020.md'


def read(name):return json.loads((WORK/name).read_text())


def metrics(model):
    values=comparison_index(dict(model['plan'],period_start='1900-01-01',portfolio=True),
        model['portfolio_cohorts'],model['settings'],[],date(2026,10,20))['policy']['metrics']
    return {stage:{label:next((p['units'] for p in reversed(v['tracking'][field]) if p['date']<=end),None)
        for label,field,end in [('actual','actual_points','2026-10-20'),('year_end','target_points','2026-12-31')]}
        for stage,v in values.items()}


def table(headers,rows):
    return '\n'.join(['| '+' | '.join(headers)+' |','| '+' | '.join(['---']*len(headers))+' |']+
        ['| '+' | '.join(str(x).replace('|',' / ').replace('\n',' ') for x in row)+' |' for row in rows])


def main():
    OUT.mkdir(exist_ok=True,parents=True)
    b,a=read('model-before.json'),read('model-after.json');before,after=metrics(b),metrics(a)
    reg=read('registration-idempotence.json');protected=read('final-protected-check.json')
    assert not protected['changed_existing_keys'] and protected['project_records']==444 and protected['confirmed_907']==223
    assert len(a['portfolio_cohorts'])==168 and len(b['portfolio_cohorts'])==167
    ids=[pid for c in a['portfolio_cohorts'] for pid in c['source_ids']]
    assert len(ids)==len(set(ids))==211
    assert all(before[s]==after[s] for s in ('CONSTRUCTION','SUPPLY','COMPLETION','MOVE_IN'))
    assert after['APPROVAL']['actual']-before['APPROVAL']['actual']==574
    assert after['BUSINESS']['actual']-before['BUSINESS']['actual']==574
    assert all(before[s]['year_end']==after[s]['year_end'] for s in before)
    old={c['id']:c for c in b['portfolio_cohorts']}
    for c in a['portfolio_cohorts']:
        if c['id'] not in old:continue
        manual=lambda x:sorted((s['stage'],s['due_date'],s.get('units')) for s in x['schedules'] if s.get('origin')=='MANUAL')
        assert manual(c)==manual(old[c['id']]),'승인 일정 변경'
    a9=next(c for c in a['portfolio_cohorts'] if c['id']=='PRO_91a176954d241b2aac791074')
    assert len(a9['events'])==1 and a9['events'][0]['date_basis']=='OBSERVED_BY'
    assert a9['events'][0]['stage']=='APPROVAL' and a9['events'][0]['units']==574
    assert not next(c for c in a['portfolio_cohorts'] if c['id']==reg['new_project_id'])['events']
    assert reg['action_counts']=={'unchanged':79},'반복 실행 중복 생성'
    latest={r['source_id']:r for r in read('retry-after-fix.json')}
    assert len(latest)==5 and all(r['result']['status']=='SUCCESS' for r in latest.values())
    counts={}
    for path in WORK.glob('*.jsonl'):
        for r in map(json.loads,path.read_text().splitlines()):
            c=counts.setdefault(r['source_id'],Counter());c[r['status']]+=1
            c.update({k:r['result'].get(k,0) for k in ('records','new','changed','unchanged')})
    for sid,r in latest.items():
        counts[sid][r['result']['status']]+=1
        counts[sid].update({k:r['result'].get(k,0) for k in ('records','new','changed','unchanged')})
    total_new=sum(c['new'] for c in counts.values())
    validation=dict(comparison_date='2026-10-20',before=before,after=after,protected=protected,
        portfolio_before=167,portfolio_after=168,unique_contributing_source_ids=211,
        manual_collection_counts=counts,new_raw_records=total_new,latest_retries=latest,
        registration_idempotent=True,approved_schedules_unchanged=True,construction_unchanged=True,
        measured_approval_delta=574,approval_date_basis='OBSERVED_BY')
    (OUT/'validation.json').write_text(json.dumps(validation,ensure_ascii=False,indent=2))
    names={'building_general_permit':'일반 건축인허가','building_hub_details':'주택인허가 동·대지 상세',
           'building_register':'건축물대장 표제부','building_register_recap':'건축물대장 총괄표제부','eum_housing_notices':'토지이음 고시 목록·첨부'}
    scopes=read('scope-before.json')
    scope_rows=[[names[sid],f"{scopes[sid]['scope_completed_dongs']:,}",f"{latest[sid]['scope']['scope_completed_dongs']:,}",
                 f"{latest[sid]['scope']['scope_remaining_dongs']:,}"] for sid in names if sid!='eum_housing_notices']
    collection_rows=[[names[sid],f"{counts[sid]['new']:,}",counts[sid]['SUCCESS'],counts[sid]['FAILED'],'성공'] for sid in names]
    stage_names={'BUSINESS':'사업화','APPROVAL':'인허가','CONSTRUCTION':'착공','SUPPLY':'공급','COMPLETION':'준공','MOVE_IN':'입주'}
    fmt=lambda n:'미확인' if n is None else f'{n:,}'
    metric_rows=[[stage_names[s],fmt(before[s]['actual']),fmt(after[s]['actual']),fmt(after[s]['year_end'])] for s in stage_names]
    image=read('official-0813-image-plans.json');links=[l for l in reg['links'] if l['kind']=='SUPPLY_PLAN']
    assert len(links)==12 and sum(l['units'] for l in links)==7508
    assert sum(l['reference_only'] for l in links)==2
    assert sum(l['units'] for l in links if not l['reference_only'])==5570
    matches=read('official-0813-image-plan-matches.json')['rows'];plan_rows=[]
    for r,m in zip(image['rows'],matches):
        pids=[p['id'] for p in m['project_matches']]
        if r['district']=='수원당수' and r['block']=='신설(전환)':pids=[reg['new_project_id']]
        found=[l for l in links if l['project_id'] in pids]
        label='승인 일정 보존·참조 연결' if found and found[0]['reference_only'] else '분양계획 연결' if found else '원천 보관·개별 귀속 검토'
        plan_rows.append(dict(지구=r['district'],블록=r['block'],공급계획호수=r['units'],시기='2027년 '+('상반기' if r['plan_half']=='H1' else '하반기'),
            처리=label,사업ID=' / '.join(l['project_id'] for l in found),원문=image['source_url']+'#page=15'))
    with (OUT/'official_0813_45_plans.csv').open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(plan_rows[0]));writer.writeheader();writer.writerows(plan_rows)
    manifest=read('followup-documents-manifest.json');assert len(manifest)==8
    files=['official-0813-0.pdf','official-0813-image-plans.json','registration-idempotence.json',
           'registration-applied.json','registration-refinement.json','followup-documents-manifest.json',
           'target-notice-catalogue.json','final-protected-check.json','scope-before.json','retry-after-fix.json',
           'permit-recheck.json','deployment-verification.json','post-restart-field-diff.json']
    for m in manifest:
        assert hashlib.sha256((WORK/m['file']).read_bytes()).hexdigest()==m['sha256']
        files.extend([m['file'],m['key']+'.txt'])
    for file in files:shutil.copyfile(WORK/file,OUT/file)
    shutil.copyfile(ROOT/'docs/analysis/closure_review_20261019/conversion-source.pdf',OUT/'conversion-source.pdf')
    shutil.copyfile(ROOT/'data/final-review-20261019/lh-12047.pdf',OUT/'lh-12047.pdf')
    source_rows=[[m['name'],m['source_date'],f"[원문]({m.get('landing_url') or m['url']})",f"[보관 파일](continuation_20261020/{m['file']})"] for m in manifest]
    plan_table=table(['지구','블록','계획 호수','시기','처리'],[[r[k] for k in ('지구','블록','공급계획호수','시기','처리')] for r in plan_rows])
    text=f'''# 수집 보완·정책 연결 및 공식 발표 차이 재진단 보고서

작성일: 2026년 10월 20일 · 이번 회차의 고정 비교 기준: 2026년 10월 20일

> **결론: 공개자료에서 추가로 보완할 내용이 실제로 확인됐다.** 수원당수 C5 490호를 9·7 정책에 연결했고, 부천대장 A9의 568↔574호 차이는 공식 변경승인으로 설명할 수 있게 됐다. 인허가 확인 총량은 574호 증가했다. **착공 76,936호와 연말 착공 예상 88,831호는 변하지 않았다.** 남은 공식 총계 차이를 전부 “비공개 자료”나 “수집 날짜 차이” 때문이라고 결론 내릴 단계는 아니다.

이 보고서는 [직전 종합 검증 보고서·근거 묶음](HOME_COLLECTION_OFFICIAL_GAP_CLOSURE_20261019.zip)의 후속 보고서다. 이전 수집 현황·유보 목록 중 이번에 해결된 항목은 아래 결과로 갱신한다. 담당자가 승인한 관리값은 기준값으로 존중하고, 새 공식 자료의 연결 근거와 수집 범위의 완결성을 별도로 점검했다.

## 1. 이번에 실제로 반영한 사항

| 항목 | 반영 결과 | 집계상 의미 |
| --- | --- | --- |
| 공개 API·고시 추가 수집 | 수동 보완 실행에서 신규 원천 레코드 **{total_new:,}건** 확보 | 호수·사업 수가 아닌 원천 레코드 수. 중복 재조회·변경·기존 행은 신규 수에서 제외 |
| 이미지로 들어 있던 공식 계획표 | 2027년 공공분양 **45개 블록, 26,695호** 구조화 | 원문의 약 2.7만호와 개별 행 합계를 구분. 2026년 착공으로 더하지 않음 |
| 개별 공급계획 연결 | **12개 사업·7,508호** 원문 연결 | 10개·5,570호는 계획 근거로 반영, 기존 승인 일정이 있는 2개·1,938호는 참조로만 연결 |
| 정책 귀속 유보 해소 | **수원당수 C5 490호** 추가 | 9·7 정책 → LH 직접시행 전환·토지이용 효율화 → C5 |
| 인허가 확인 보완 | **부천대장 A9 승인 총량 574호** 연결 | 변경승인 시점까지 승인된 재고. 올해 새로 승인된 574호라는 뜻이 아님 |
| 기타 공식 근거 보강 | 고시 PDF 6건·거래소 공시 2건 등록 | 계약·지구계획·사업계획 변경승인을 구분 |
| 기존 승인값 보존 | 연결 등록 직후 보호 기록 **3,031건 변경 0건** | 이후 자동 재수집에서 iH 원천 7건의 기준일 메타데이터만 변경. 수량·승인 연결·승인 일정 유지 |

원천 사업 레코드는 **443→444개**, 9·7 확정 연결은 **222→223개**, 중복·유형을 정리한 관리 묶음은 **167→168개**가 됐다. 관리 묶음에 기여하는 원천 사업 ID 211개에 중복 산입이 없는 것도 확인했다. 이 숫자들은 서로 다른 단위이므로 합산하지 않는다.

## 2. 화면 집계에 생긴 변화

단위: 호. 현재 값은 관리대상 사업의 과거부터 현재까지 누적 확인량이고, 연말 값은 2026년 12월 말까지의 계획 기준이다. 전국·수도권 연간 전체 통계와는 모집단이 다르다.

{table(['단계','반영 전 누적','반영 후 누적','2026년 말 계획 누적'],metric_rows)}

- 인허가 **+574호**: 이전에 착공 계획만 연결돼 있던 부천대장 A9에 공식 주택건설 사업계획 변경승인 근거를 연결했다.
- 사업화 **+574호**: 승인 단계가 확인된 사업의 선행 단계는 기존 선후관계 규칙에 따라 반영했다. 새 사업화 문서에서 별도 574호를 발견했다는 의미는 아니다.
- 착공 **변화 없음**: 변경승인·계약·분양계획은 실제 착공 증빙과 구분했다. 새로 확인된 실제 착공일은 없다.
- 수원당수 C5 **490호**: 사업과 2027년 하반기 공급계획을 추가했다. 2026년 착공 또는 공급 실적에 가산하지 않았다.

추가 수집 후 후속 연결 사업 **15개**를 보유 주택인허가·일반 건축인허가와 다시 대조했다. 지구명으로 찾은 58개 후보 중 지구·블록이 일치한 사업은 **부천대장 A9, 수원당수2 A3, 인천계양 A16의 3개**였고, 모두 실제 착공일은 공란이었다. 착공예정일은 실제 착공으로 사용하지 않았다. 이 검사는 현재 보유 자료의 지구·블록 기준이며, 미조회 지역이나 명칭이 없는 필지까지 전수 연결을 완료했다는 뜻은 아니다.

## 3. 수원당수 C5는 왜 정책에 연결했는가

**지구명만으로 공공주택에 배정한 것이 아니라, 정책의 전환 물량과 변경 고시의 블록 명세, LH 사업 공모를 연결했다.**

| 확인 자료 | 실제 확인한 항목 | 연결 판단 |
| --- | --- | --- |
| 9·7 이행실적·2026년 추진계획, PDF 6쪽 | 수원당수 **490호**, **단독→공동** 전환 | 정책 사업의 위치·방식·물량 식별 |
| 국토부 제2025-806호, 2025.12.24, PDF 7쪽 | 수원당수 **C-5**, 60㎡ 이하 **170호** + 60~85㎡ **320호** | 정책의 490호를 실제 블록에 대응 |
| 같은 변경 고시의 전후 표 | 공동주택 **7,634→8,124호**, 단독 등 **132→57호** | 공동주택 490호 증가와 기존 단독 등 75호 감소 확인 |
| LH 2026.05.29 공모계획, PDF 2쪽 | **수원당수 C-5 / 60이하·60~85 / 490호** | 지구·블록·면적 구성·호수 및 LH 공공주택 공모 일치 |
| 2026.08.13 공식 PDF 15쪽 이미지 표 | **수원당수 신설(전환) 490호 / 2027년 하반기** | 위 블록의 후속 공급계획에 연결 |

**490호는 해당 공동주택 블록의 규모, 415호는 지구 전체 계획의 순증이다.** 기존 단독 등 75호가 줄기 때문에 지구 전체는 7,766→8,181호, 즉 415호 증가한다. `490-75=415`를 구분해야 중복·과대 계산을 피할 수 있다. 이 숫자 차이는 수집 오류가 아니라 비교 대상의 차이다.

근거: [9·7 이행실적 원문](https://www.korea.kr/common/download.do?fileId=198344116#page=6), [C5 변경 고시](https://www.eum.go.kr/web/gs/gv/gvGosiDet.jsp?seq=636472), [LH 개별 공모](https://www.lh.or.kr/galleryDownload.es?bid=0003&list_no=12047&seq=2#page=2).

등록 사업 ID: `{reg['new_project_id']}`. 기존 전체 사업 원장에서 C5·B4·수원당수 490호의 중복 후보를 확인한 뒤 신규 등록했다. 7월 거래소 공시에 나오는 ‘수원당수 B4’는 별칭 변경을 직접 증명하는 자료가 부족하므로 새 별도 사업으로 만들지 않았다.

직전 보고서에서 LH 5월 공모의 후속 15개 블록 12,044호를 정책 귀속 유보로 남겼으나, 이번 C5 연결로 그 목록은 **14개 블록 11,554호**가 남는다. 이미 연결한 14개 블록 8,031호와 C5 490호를 합친 정책 연결 보강은 **15개 블록 8,521호**다. C5의 공급계획은 2027년이므로 이 합계를 2026년 착공계획으로 사용하지 않는다.

## 4. 부천대장 A9: 568호와 574호 차이의 원인을 확인했다

**이 사례는 수집일만 늦었던 문제가 아니라, API에 남은 이전 승인값을 변경 고시로 보완해야 하는 경우다.**

| 비교 항목 | 보유 주택인허가 API | 공식 변경승인 고시 |
| --- | --- | --- |
| 지구·블록 | 부천대장 A-9 | 부천대장 A-9 |
| 유형 | 공동주택 | 분양전환 공공임대 |
| 세대수 | **568호** | 기정 **568호 → 변경 574호**, 증 6세대 |
| 사업 규모 | 원천 기본개요 | 아파트 12개동, 대지 27,892㎡ |
| 날짜의 의미 | 최초 허가일 2023.12.29, 레코드 생성일 2024.05.09 | **변경승인 고시 2026.07.14** |
| 실제 착공일 | 공란 | 실제 착공일을 제시하지 않음 |

보유 API 값 568호가 고시의 ‘기정’ 값과 정확히 일치한다. 관리 기준 574호와 LH 공모 물량은 ‘변경’ 값과 일치한다. 따라서 이 사례의 **6호 차이는 공식 사업계획 변경으로 설명된다.** API 재수집 날짜가 최신이어도 원천 내용이 변경승인을 반영했다고 보장할 수 없음을 보여준다.

이번 연결은 **574호 승인 총량을 2026.07.14까지 확인했다는 관측**으로 저장했다. 최초 승인일을 2026년으로 바꾸거나 574호 모두를 2026년 신규 승인으로 취급하지 않는다. API의 568호를 원문에서 삭제하지 않고 고시와 함께 남겼다. 실제 착공일은 추가하지 않았다.

근거: [국토부 고시 제2026-364호](https://www.eum.go.kr/web/gs/gv/gvGosiDet.jsp?seq=643252), [고시 PDF 보관본](continuation_20261020/notice-643252.pdf). 원천 API ID: `PER_659498cd3ee4d1ca7910c9da`.

## 5. 수원당수2: 서로 다른 숫자를 공식 변경표로 대조했다

**C5와 별개인 수원당수2 3개 블록은 기존 관리 호수를 뒷받침하는 공식 근거를 확보했다.** 지구계획 변경표와 이후 공사 계약의 수량이 일치한다.

| 블록 | 지구계획 변경 전 | 변경 후 | 2026.03.25 거래소 계약 공시 | 기존 관리 호수 |
| --- | ---: | ---: | ---: | ---: |
| A1 | 624 | 693 | 693 | 693 |
| A3 | 585+132 = 717 | 794+117 = 911 | 911 | 911 |
| B1 | 480+203 = 683 | 495+210 = 705 | 705 | 705 |

국토부 제2025-807호의 변경표와 계약 공시에서 지구·블록·규모를 확인했다. A3의 API 717호는 변경 전 지구계획 총량과도 일치한다. 다만 지구계획 변경과 주택건설 사업계획 변경승인은 서로 다른 절차다. 이 자료만으로 모든 인허가 갱신이나 실제 착공을 확정하지 않는다. 계약일 **2026.03.24**도 실제 착공일로 전용하지 않았다.

근거: [제2025-807호 원문](https://www.eum.go.kr/web/gs/gv/gvGosiDet.jsp?seq=636471), [거래소 계약 공시](https://kind.krx.co.kr/external/2026/03/25/001247/20260323000081/91370.htm).

인천계양 A16 **434호**, A18 **782호**는 2026.09.09 지구계획 변경 고시에서도 유지되는 것을 확인했다. 반면 왕숙2의 지구계획 값과 개별 주택사업·분양계획 값은 차이가 남는다. 지구계획의 수용호수와 개별 건설·공급 호수를 섞어 관리값을 덮어쓰지 않았다.

## 6. 추가 수집의 범위와 남은 구간

아래는 **각 API별 법정동 조회 범위**다. 같은 동을 여러 API에서 조회하므로 행 간 완료 수를 더해 ‘서로 다른 지역 수’로 표현하면 안 된다. 전체 대상은 API별 2,907개 법정동이다.

{table(['수집 경로','반영 전 완료 동','이번 조회 후 완료 동','남은 동'],scope_rows)}

기존 주택인허가 기본개요는 서울·경기 2,629개 동, 인천 278개 동을 조회한 상태다. 위 표는 이를 보완하는 **일반 건축인허가·상세·대장 경로**이며, 기본개요 조회 완료가 모든 보완 경로의 완료를 뜻하지 않는다.

{table(['수집 경로','이번 실행 신규 레코드','성공 배치','도중 실패 배치','수정 후 마지막 실행'],collection_rows)}

신규 레코드 **{total_new:,}건**은 이번 수동 보완 실행 로그의 합계다. 원천 표의 레코드와 고시 목록·본문 레코드를 포함하며, 시스템 전체 데이터 셀 수(행×컬럼), 새 사업 수 또는 공급 호수와 다르다. 자동 수집이 별도로 진행한 행은 이 합계에 억지로 더하지 않았다.

토지이음은 새 목록을 더 발견하면서 주택 관련 상세 대기 건수가 **258→370건**으로 바뀌었다. 이는 확인 대상이 확대된 결과이며, 기존 자료를 잃었다는 의미가 아니다. 마지막 배치의 본문 추출 대기 첨부 **58개**는 **해당 배치만의 수치**다. 전체 누적 첨부 미처리량으로 사용하지 않는다. 지도 이미지 보관과 본문 수치 추출 완료도 구분한다.

## 7. 자동 수집에서 고친 부분

| 상황 | 기존 동작 | 이번 보완 |
| --- | --- | --- |
| HTTP 성공 응답인데 본문이 비어 있음 | 즉시 전체 배치 실패 | 같은 페이지를 최대 3회 재시도. 계속 비면 실패로 남기고 기존 정상 데이터 유지 |
| 수동 보완 중 같은 원천을 자동 작업자가 요청 | 잠금 경합을 실패 재시도로 소모할 수 있음 | `BUSY`는 60초 뒤 재대기. 실패 횟수 차감 복원, 같은 수집 단계 유지 |
| 고시의 오래된 미확인 상세가 많음 | 최근 변경승인도 오래된 고시 뒤에서 대기 | 배치 15건 중 최근 5건과 오래된 대기 10건을 함께 처리 |
| 본문 추출 대기 첨부 수 표시 | 배치 수치를 전체 대기로 오해할 여지 | 통계 범위를 `CURRENT_BATCH_ONLY`로 명시 |

빈 응답을 0건 자료로 적재하거나 페이지를 건너뛰지 않는다. 파일 해시·원천 ID·이전 개정 이력은 유지한다. 같은 작업을 다시 실행해도 새로운 사업을 중복 생성하지 않는다. 수집과 연결·스냅샷은 별도 단계로 이어지고, 원천 잠금과 작업 임대 토큰으로 다른 작업자의 결과를 덮어쓰지 않도록 했다.

반복 조회 자체는 자동으로 계속되지만, **이미지 표의 시각 검토, 블록 명칭 변경의 입증, 계획·계약·실제 착공의 의미 판정은 이번에 담당자 대행 검토를 거쳤다.** 이 작업까지 완전히 무인 자동화됐다고 설명하면 안 된다. 45개 이미지 표는 검토한 PDF의 해시와 함께 고정했으며 다른 판본을 같은 결과로 인정하지 않는다.

## 8. 10월 공식 발표와의 차이를 어떻게 설명할 것인가

**이번 결과는 “현재 데이터셋이 공식 총계와 사실상 일치한다”는 주장보다, 확인한 범위와 미확인 범위를 증거로 구분하는 설명을 뒷받침한다.**

| 차이의 유형 | 이번에 확보한 근거 | 설명 가능한 범위 |
| --- | --- | --- |
| 원천 판본 갱신 차이 | 부천대장 A9의 기정568→변경574 | 해당 사업의 6호 차이는 사업계획 변경으로 설명 가능 |
| 정책 연결의 유보 | 수원당수 C5 정책·고시·공모 교차 대조 | 기존 미연결 490호를 정책에 편입할 근거 확보 |
| 수집·추출의 누락 | 공식 PDF 이미지의 45개 블록 구조화 | 문서를 받았어도 표 안의 데이터셋이 완성된 것은 아님 |
| 수량 범위 차이 | C5 블록490호 vs 지구 순증415호 | 전체 블록과 전후 순증은 서로 다른 지표 |
| 사건 단계 차이 | 당수2 계약과 A9 변경승인 | 계약·승인 자료를 착공으로 합산하지 않음 |
| 지역·기간·정책 모집단 차이 | 우리 관리사업 누적 vs 공식 연간 수도권 부문 합계 | 숫자 차이를 그대로 미수집 호수나 오류율로 계산할 수 없음 |
| 공개 명세 미확보 | 공식 부문별 총계에 대응하는 전체 사업·블록 명세 미확보 | 비공개라고 확정한 것이 아니라 공개 자료의 존재·대응이 아직 확인되지 않은 상태 |

공식 1~8월 수도권 착공 **86,739호**, 10월 합동 점검에서 제시한 부문별 착공 실적, 우리 관리대상 누적 착공 **76,936호**는 집계 기간과 범위가 같지 않다. 86,739에서 76,936을 뺀 값을 곧바로 미수집 착공이라고 쓰면 안 된다. 반대로 과거 착공을 포함한 우리 누적 값이 존재한다는 이유로 공식 연간 총계를 모두 재현했다고 주장할 수도 없다.

10월 자료는 9·7뿐 아니라 후속 공급대책의 실행을 함께 다룬다. 신축매입·기타 민간·공공지원민간임대 등의 집계 명세가 우리 개별사업과 모두 대조되지 않았고, 일반 건축인허가 등 공개 API 조회도 끝나지 않았다. 따라서 **현재 잔여 차이를 전부 수집 시기나 비공개 탓으로 단정하지 않는다.**

근거: [10월 합동 발표 원문](https://www.fsc.go.kr/comm/getFile?srvcId=BBSTY1&upperNo=87948&fileTy=ATTACH&fileNo=3), [월별 공식 주택통계](https://www.index.go.kr/unity/potal/FileDown.do?seq=17704&id=1229&div=1). 세부 범위 분해는 [직전 종합 보고서·근거 ZIP](HOME_COLLECTION_OFFICIAL_GAP_CLOSURE_20261019.zip)을 함께 참조한다.

## 9. 즉시 조치와 장기 관리

| 우선순위 | 조치 | 완료·종료 판단 기준 |
| --- | --- | --- |
| 즉시 | 이번 C5 연결과 A9 변경승인을 기준 데이터에 반영 | 반영 완료. 보호 기록·집계 전후·반복 실행 검증 완료 |
| 계속 수집 | 일반 인허가·상세·대장 미조회 구간을 재개 가능한 배치로 소진 | API별 잔여 법정동 0, 실패 페이지 해소. 완료 뒤에도 변경 재조회 지속 |
| 우선 대조 | 8개 LH 블록의 실제 착공·개별 주택사업 변경승인 | 블록·호수·사건일이 확인되는 직접 자료. 계약일·분양예정일로 대체하지 않음 |
| 명칭 관리 | C5/B4, 당수2 B5/C1·B7/C4 등 표기 차이 | 공식 변경표·필지·면적·블록 도면으로 동일성 확정 후 하나의 사업에 연결 |
| 공식 총계 대사 | 신축매입·기타 민간·공공지원민간임대 명세 확보 및 대조 | 같은 기간·같은 지역·같은 사건 기준의 사업별 대사표 확보 |
| 장기 관리 | 원천 수집일과 원천 자료 기준일·변경일 분리 | ‘오늘 수집’만으로 ‘최신 승인값’ 판정하지 않도록 운영 |
| 장기 관리 | 원문 표의 세대수·공급량·순증·누적 범위 관리 | 수량 단위와 포함 범위를 함께 보존하고 사업 간 중복 합산 방지 |

## 10. 검증 결과와 재현 자료

- 연결 등록 직후 기존 보호 기록 3,031건의 전후 SHA-256: `{protected['protected_before']}`. 동일함을 확인했다.
- 사업·정책 연결 신규 키는 C5의 사업 레코드와 정책 매핑 2개다. 기존 승인 기록 변경은 없다.
- 데이터 등록을 다시 실행했을 때 **79개 대상 모두 unchanged**, 새 중복 레코드 0건이었다.
- API 응답의 관리 묶음 168개와 기여 원천 ID 211개를 대조했고, 중복 기여 ID는 없다.
- 기존 승인 일정, 현재 착공·공급·준공·입주, 2026년 연말 계획은 보존됐고, 인허가·사업화의 +574호만 확인했다.
- 관련 테스트는 네트워크 재시도·원천 잠금 경합·고시 선택·기존 연결/집계 검증을 포함해 실행했다. 실행 결과는 배포 검증 파일에 보관한다.

**자동 수집 재개 후 확인:** iH 원천 사업 7건은 `base_date`만 2026.10.19→2026.10.20으로 바뀌었다. 이는 해당 수집기의 조회 기준일 메타데이터 갱신이며, 공급 호수·정책 연결·승인 일정의 수정이나 새 착공이 아니다. 따라서 등록 직후의 전체 해시 일치를 영구적인 원천 불변으로 설명하지 않는다. [7건 필드별 전후 차이](continuation_20261020/post-restart-field-diff.json)를 보관했고, 재시작 후 API의 단계별 수치가 위 표와 같은 것도 확인했다.

다운로드: [공식 계획 45개 행 CSV](continuation_20261020/official_0813_45_plans.csv), [집계·보호 검증 JSON](continuation_20261020/validation.json), [등록·반복 실행 검증](continuation_20261020/registration-idempotence.json), [배포·자동 수집 확인](continuation_20261020/deployment-verification.json), [보유 인허가 지구·블록 재대조](continuation_20261020/permit-recheck.json).

재현 스크립트: `scripts/register_continuation_20261020.py`(기본값은 쓰기 없는 미리보기), `scripts/build_continuation_review_20261020.py`(고정 스냅샷으로 보고서 생성). ZIP에는 공개 원문과 요약 검증값을 포함한다. 보고서 생성 스크립트의 완전 재실행에는 내부 `data/continuation-20261020`의 전후 모델 스냅샷이 필요하다.

## 부록 A. 이번 추가 확인 원문

{table(['자료','발표·고시일','공식 출처','보관본'],source_rows)}

추가 참조: [8월 공식 공급계획 PDF](https://www.korea.kr/common/download.do?fileId=198524780&tblKey=GMN#page=15) · [보관본](continuation_20261020/official-0813-0.pdf), [9·7 이행실적 보관본](continuation_20261020/conversion-source.pdf), [LH 5월 공모 보관본](continuation_20261020/lh-12047.pdf).

## 부록 B. 이미지 표에서 구조화한 2027년 공급계획 45개 블록

상반기 8개 **4,436호**, 하반기 37개 **22,259호**, 합계 **26,695호**. ‘원천 보관·개별 귀속 검토’는 자료를 버렸다는 뜻이 아니라, 이 표만으로 기존 개별 사업·9·7 프로그램을 확정하지 않았다는 뜻이다. 위례·평택 등 블록의 숫자·영문 접두어도 원문 그대로 보존했다.

{plan_table}
'''
    REPORT.write_text(text)
    checksums={str(p.relative_to(OUT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in OUT.iterdir() if p.is_file() and p.name!='checksums.json'}
    (OUT/'checksums.json').write_text(json.dumps(checksums,ensure_ascii=False,indent=2))
    with zipfile.ZipFile(REPORT.with_suffix('.zip'),'w',zipfile.ZIP_DEFLATED) as z:
        z.write(REPORT,REPORT.name)
        # Include the complete prior bundle so its own relative links remain usable.
        previous=ROOT/'docs/analysis/HOME_COLLECTION_OFFICIAL_GAP_CLOSURE_20261019.zip'
        z.write(previous,previous.name)
        for p in sorted(OUT.iterdir()):
            if p.is_file():z.write(p,'continuation_20261020/'+p.name)
    print(json.dumps(dict(report=str(REPORT),new_raw_records=total_new,files=len(checksums),
        zip_bytes=REPORT.with_suffix('.zip').stat().st_size,metrics=after),ensure_ascii=False))


if __name__=='__main__':main()
