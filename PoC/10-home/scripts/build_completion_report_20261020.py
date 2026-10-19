"""Build a shareable report from the frozen completion audit, without DB writes."""
import csv
import hashlib
import json
import shutil
import zipfile
from pathlib import Path
from scripts.register_completion_evidence_20261020 import CASES
from scripts.build_continuation_review_20261020 import table

ROOT=Path(__file__).resolve().parents[1]
WORK=ROOT/'data/completion-20261020'
OUT=ROOT/'docs/analysis/completion_20261020'
REPORT=ROOT/'docs/analysis/HOME_REMAINING_WORK_REVIEW_20261020.md'
NAMES={'building_general_permit':'일반 건축인허가','building_register':'건축물대장 표제부',
       'building_register_recap':'건축물대장 총괄표제부','building_hub_details':'주택인허가 동·대지 상세'}

def read(name):return json.loads((WORK/name).read_text())
def csvfile(name,rows):
    with (OUT/name).open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    v=read('final-validation.json');before=read('scope-before.json');reg=read('registration-idempotence.json')
    assert not v['changed_existing_keys'] and not v['manual_schedule_changes']
    assert v['contributing_source_ids']==v['unique_source_ids']
    assert reg['action_counts']=={'unchanged':26}
    after=v['metrics_after'];old=v['metrics_before']
    f=lambda x:'미확인' if x is None else f'{x:,}'
    scopes=[]
    for sid,state in v['scopes'].items():
        scopes.append(dict(자료=NAMES[sid],시작_조회완료=before[sid]['scope_completed_dongs'],
            최종_조회완료=state['scope_completed_dongs'],전체_법정동=state['scope_total_dongs'],
            미조회=state['scope_remaining_dongs'],현재_원천행=v['raw_current_counts'].get(sid,0),
            검증기간_신규행=v['raw_new_records_in_review_window'].get(sid,0)))
    csvfile('collection_scope.csv',scopes)
    held=[('평택고덕','A72',773),('평택고덕','A73',522),('평택고덕','A69',1162),('평택고덕','A71',833),('평택고덕','A70',1225),
          ('인천검단','AA30',444),('성남복정1','B2',735),('양주고읍','A12',138),('화성동탄','A1',464)]
    reasons={
        '평택고덕':'개별 공모·사업자 선정·12월 착공 계획 확인. 2025-537호의 기존 구획과 신규 A69~73의 전환 관계를 확보한 자료로 확정할 수 없어 9·7 세부 프로그램 귀속은 유보.',
        '인천검단':'AA30 면적 20,876㎡는 일치. 과거 지구계획은 임대 464호, 후속 공모는 분양전환 공공임대 444호. 임대의 분양전환과 민간매각 택지의 LH 직접시행 전환은 다른 개념이므로 전용하지 않음.',
        '성남복정1':'공모 735호·38,510㎡·210% 및 사업자 선정 확인. 4월 정부 발표도 성남복정 735호를 공공주택 착공 계획에 명시. 다만 최근 6·7차 지구계획 첨부는 서버에서 파일 없음 응답. 공공사업 존재와 9·7 세부 프로그램 귀속을 구분해 보존.',
        '양주고읍':'공모 125+13=138호·16,751㎡·100%와 사업자 선정 확인. 기존 민간매각 계획의 전환 또는 9·7 개별 귀속을 확인할 추가 공식 근거 미확보.',
        '화성동탄':'공모 464호·33,852㎡·160% 및 사업자 선정 확인. 확보한 동탄 지구 변경 고시만으로 A1의 정책 전환 관계 확정 불가. 동탄2의 다른 블록과 혼합하지 않음.'}
    decisions=[dict(지구='서울도봉01',블록='1',원문_호수=2100,결정='기존 사업에 연결·중복 신규등록 방지',
        근거='성균관대 야구장·도봉동 628·48,055㎡. 기존 승인 1,800호 보존, 새 공모 2,100호는 참조값.',착공_계획='2027-06')]
    for c in CASES:
        decisions.append(dict(지구=c['district'],블록=c['block'],원문_호수=c['units'],결정='담당자 대행 정책 연결 확정',근거=c['basis'],착공_계획='2026-12'))
    for d,b,u in held:decisions.append(dict(지구=d,블록=b,원문_호수=u,결정='원문 확보·정책 세부 귀속 유보',근거=reasons[d],착공_계획='2026-12'))
    assert len(decisions)==14 and sum(r['원문_호수'] for r in decisions)==11554
    assert sum(u for _,_,u in held)==6296
    csvfile('remaining_14_case_decisions.csv',decisions)
    manifests=[]
    for name in ('lh-documents-manifest.json','lh-extra-manifest.json','land-documents-manifest.json','land-extra-manifest.json'):
        manifests.extend(read(name))
    manifests.append(read('public-start-source.json'))
    sources=[];files=set()
    for m in manifests:
        status=m.get('status','SAVED');path=m.get('file') or m.get('response_file')
        sha=m.get('sha256') or m.get('response_sha256')
        if path:
            assert hashlib.sha256((WORK/path).read_bytes()).hexdigest()==sha
            if not path.endswith('.zip'):files.add(path)
        if m.get('text_file'):files.add(m['text_file'])
        # Keep extracted schedules from large, nested originals; retain the ZIP
        # checksum and official URL in the manifest instead of duplicating 400MB.
        for child in m.get('children',[]):
            if child.get('text_file'):files.add(child['text_file'])
        sources.append(dict(자료=m.get('name') or m.get('id') or '4월 공공주택 공급점검',날짜=m.get('date') or '',
            상태=status,공식URL=m.get('landing_url') or m.get('listing') or m['url'],첨부URL=m['url'],
            원본파일=path or '',SHA256=sha or '',비고=m.get('reason','')))
    csvfile('official_source_urls_and_hashes.csv',sources)
    core=('scope-before.json','final-validation.json','registration-applied.json','registration-refinement.json','registration-idempotence.json',
          'target-source-recheck.json','deployment-verification.json','lh-documents-manifest.json','lh-extra-manifest.json',
          'land-documents-manifest.json','land-extra-manifest.json','public-start-source.json','drain-result.json','independent-verification.json','source-summary-current.json','loading-verification.json')
    for name in core:
        if (WORK/name).exists():files.add(name)
    files.update(p.name for p in WORK.glob('registration-refinement*.json'))
    for name in files:
        dest=OUT/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(WORK/name,dest)
    for name in ('notice-636471.pdf','notice-636471.txt','notice-636472.pdf','notice-636472.txt'):
        shutil.copyfile(ROOT/'data/continuation-20261020'/name,OUT/name)
    stage_names={'BUSINESS':'사업화','APPROVAL':'인허가','CONSTRUCTION':'착공','SUPPLY':'공급','COMPLETION':'준공','MOVE_IN':'입주'}
    metric_table=table(['단계','현재 누적 측정량','종전 연말 계획','정비 후 연말 계획'],[
        [stage_names[k],f(after[k]['actual']),f(old[k]['year_end']),f(after[k]['year_end'])] for k in stage_names])
    scope_table=table(['API','시작 조회','최종 조회 / 2,907','미조회','현재 원천 행'],[
        [r['자료'],f(r['시작_조회완료']),f(r['최종_조회완료']),f(r['미조회']),f(r['현재_원천행'])] for r in scopes])
    case_table=table(['사업','호수','최종 처리','판정 근거'],[
        [r['지구']+' '+r['블록'],f(r['원문_호수']),r['결정'],r['근거']] for r in decisions])
    remaining=sum(r['미조회'] for r in scopes)
    collection_conclusion=('네 가지 보완 API 모두 수도권 법정동 2,907개 조회를 완료했다.' if not remaining else
        f'표제부·총괄표제부 등 완료 범위와 미조회 범위를 분리했다. API별 미조회 합계는 {remaining:,}개이며 같은 법정동이 API별로 중복되므로 지역 수로 해석하지 않는다. 전체 조회 완료라고 표시하지 않는다.')
    summary=read('source-summary-current.json') if (WORK/'source-summary-current.json').exists() else None
    summary_text=('집계 완료 시각 '+summary['generated_at']+' 기준, 등록 출처 중 데이터가 있는 출처 **'+f(summary['current']['sources'])+'개**, 추출 데이터 **'+f(summary['current']['extracted_cells'])+'개 셀**, 사업으로 정리되거나 근거로 연결된 원천 **'+f(summary['current']['linked_records'])+'건**이다. 추출 데이터는 출처·유형별 **현행 행 수 × 고유 컬럼 수**이며 빈칸을 포함한다. 연결 건수는 주택 호수·실사업 수가 아니다. [전체 출처·유형별 집계 근거](completion_20261020/source-summary-current.json).') if summary else '출처·유형별 전체 집계는 서비스의 집계 완료 시각과 함께 확인한다.'
    text=f'''# 잔여 수집·정책 연결 및 10월 공식 발표 차이 검증 보고서

작성일: 2026-10-20 · 비교 기준: 2026-10-20 · 단위: 별도 표기가 없으면 호

> **공개자료를 더 확인해 실제로 보완할 사업과 계획을 찾았다.** 사업 4개·3,158호를 담당자 대행 검토로 정책에 연결했고, 기존 C5의 착공 계획 490호를 추가했다. 연말 착공 계획은 **{f(old['CONSTRUCTION']['year_end'])} → {f(after['CONSTRUCTION']['year_end'])}호**, 현재 누적 착공 측정량은 **{f(after['CONSTRUCTION']['actual'])}호**다. 공모·선정 자료를 실제 착공으로 바꾸지 않았다. **10월 정부 총계와 우리 관리 원장이 사실상 일치하며 차이는 모두 비공개 때문이라는 결론은 근거가 부족하다.**

## 독자를 위한 비교 기준

**판단의 핵심은 “자료가 얼마나 같은가”보다 “무엇을 같은 기준으로 비교했는가”다.** 공식 발표는 수도권 전체 공급 부문의 당해 연도 실적·목표이고, HOME 화면은 개별 정책 연결 사업의 과거 포함 단계 도달량과 저장된 계획 누계다. 두 총량의 비율을 정확도라고 계산하면 관리 원장에 이미 있는 과거 착공과 이번 연도 계획이 잘못 섞인다.

| 질문 | 이 보고서의 답 | 증거 |
| --- | --- | --- |
| 수집·연결 보완이 실제 있었는가 | 신규 정책 연결 4개 3,158호, 기존 C5 착공 계획 490호 추가 | 3·4장 개별 부지 대조, 공식 URL·원문 해시 |
| 승인된 관리값이 바뀌었는가 | 기존 보호 기록 3,033건 및 승인 일정 변경 0건 | 전후 해시, final-validation.json |
| 더한 물량이 중복 또는 실제 착공으로 과대 표시됐는가 | 관리 묶음 기여 ID 215개 모두 고유. 새 공모 물량은 계획에만 반영 | 원장·중복 검사, 독립 사건 구획 대조 |
| 공식 발표와의 차이가 전부 수집 시차인가 | 아니다. 기간·모집단·물량 범위·계획/실적 차이와 실제 미조회가 함께 존재 | 5~7장 |
| 남은 차이가 비공개 자료 때문인가 | 현재 근거만으로 단정할 수 없다 | 미조회 2,183개 법정동, 귀속 유보 9개 사업, 첨부 제공 장애 기록 |
| 지금 배포 가능한 결론인가 | 승인값과 공식 원문을 추적할 수 있는 관리 기준본으로 배포 가능. 정부 전체 실적의 전수 재현이라고 표현하지 않음 | 보고서와 증거 ZIP을 함께 제공 |

## 1. 이번에 끝낸 판단과 반영

| 조치 | 결과 | 집계 처리 |
| --- | --- | --- |
| 미연결 14개 블록·11,554호 전건 재심사 | 1개·2,100호는 기존 성대야구장과 동일, 4개·3,158호 신규 정책 연결, 9개·6,296호 세부 귀속 유보 | 14건 모두 판정 이유 기록. 11,554호 전부를 새 사업으로 추가하지 않음 |
| 수원당수 C5 ↔ 공모 B4 | 면적 35,553㎡, 170+320=490호, 용적률 140% 일치 | 기존 사업을 유지하고 2026년 12월 착공 계획만 추가 |
| 새 사업 착공 계획 | 수원당수2 B5 364, B7 880, 안산장상 A10 320, 고양창릉 B1 1,594 | 2026년 12월 계획 3,158호. 실제 착공은 추가하지 않음 |
| 새 사업 인허가 계획 | 안산장상 A10·고양창릉 B1 공모에 2026년 12월 승인 명시 | 인허가 계획 1,914호 반영 |
| 사업화 단계 도달 확인 | 새 사업 4개와 기존 C5의 공식 우선협상대상자 선정 결과 | 사업화 확인량 3,648호 보완. 선정 확인일까지 단계에 도달했다는 기록이며 최초 사업화일·착공일로 전용하지 않음 |
| 서울도봉01·위례 업무용지 | 9·7 후속이라는 LH 명시 자료와 개별 부지 대조 | 승인 관리량 1,800·1,000호 및 기존 수동 일정 보존. 원문 2,100·999호는 참조 연결 |
| 원천 적재·조회 성능 | 원천 행 일괄 적재, 현행 원천 수 인덱스, 실제착공 후보 인덱스 | 원문 해시·이력·중복 처리·트랜잭션 검증 유지 |
| 수집 중 화면 오류 | 배치 상태 조회 사이 완료된 레코드가 이전 RUNNING 객체로 남던 경쟁 조건 수정 | 최신 성공 배치의 완료 시각을 다시 읽도록 반영 |
| 외부 API 장애 대응 | HTTP 429·503 구분, 요청 간격 제어, Retry-After 대기, 동일 페이지 재시도 | 실패·빈 응답을 0건이나 조회 완료로 바꾸지 않음 |

기존 보호 대상 **{v['protected_existing_records']:,}건 변경 0건**, 수동 승인 일정 변경 0건이다. 반복 등록에서 26개 근거 레코드는 모두 동일하여 추가 생성하지 않았다. 원천 사업은 **{v['project_records']}건**, 9·7 확정 연결은 **{v['confirmed_907']}건**, 관리 묶음은 **{v['portfolio_cohorts']}개**다. 관리 묶음에 기여하는 원천 사업 ID **{v['contributing_source_ids']}개**가 중복 없이 들어가는 것을 확인했다. 이 수치들은 서로 다른 단위다.

## 2. 현재 화면에 반영되는 값

{metric_table}

현재 누적은 과거부터 해당 기준일까지 확인된 관리 사업의 단계 도달량이다. 연말 예상은 12월 말까지의 **저장된 계획 누계**이며 실제 착공 전망에 대한 통계 예측값이 아니다. 정부의 올해 착공 목표와 비교할 때는 연도·대상 사업·사업 유형을 먼저 맞춰야 한다.

## 3. 어떤 항목이 일치해서 정책·프로그램으로 연결했는가

공통 경로는 **9·7 정책 → LH 직접시행 전환·토지이용 효율화 → 개별 블록**이다. 단순한 지구명 유사도나 “공공주택이므로 해당”이라는 규칙을 쓰지 않았다. 공식 지구계획의 기존 민간분양 구조와 후속 LH 공공주택 공모의 블록·면적·호수·용적률을 함께 확인했다. 정책 프로그램 귀속은 사용자 위임에 따른 담당자 대행 판단이며, 정부가 네 블록을 9·7 대상으로 각각 명시했다는 뜻은 아니다.

| 사업 | 이전 공식 기록 | 후속 공모의 일치 항목 | 관리 기준과 구분 |
| --- | --- | --- | --- |
| 수원당수2 B5 | 제2025-807호 C1 민간분양 | 23,922㎡·364호·170%, 239+125호 | C1/B5를 같은 부지로 연결. 기존 다른 B1·A1·A3와 별개 |
| 수원당수2 B7 | 제2025-807호 C4 민간분양, 과거 C4·C5 통합 | 42,841㎡·880호·230% | 통합 전 두 블록을 별도로 더하지 않음 |
| 안산장상 A10 | 제2025-665호에서 민간분양→공공분양 명시 | A10·12,989㎡·200% | 지구계획 325호와 후속 개별 공모 320호 차이를 보존하고 공모 320호 채택 |
| 고양창릉 B1 | 제2025-813호에서 민간분양 1,059호→공공분양, 통합공공임대 317호 | B1·79,119㎡·200% | 지구계획 1,376호와 공모 1,594호의 범위를 구분. 전체 사업 1,594호를 정책 순증으로 해석하지 않음 |

근거: [LH 3차 재공고](https://www.lh.or.kr/board.es?mid=a10604010000&bid=0034&act=view&list_no=732709), [수원당수2 변경 고시](https://www.eum.go.kr/web/gs/gv/gvGosiDet.jsp?seq=636471), [안산장상 변경 고시 4쪽](https://www.eum.go.kr/web/gs/gv/gvGosiDet.jsp?seq=623464), [고양창릉 변경 고시 7·12쪽](https://www.eum.go.kr/web/gs/gv/gvGosiDet.jsp?seq=628391). 원문 해시와 보관 파일은 별도 목록에 있다.

## 4. 남았던 14개 블록의 최종 판정

{case_table}

유보 9개는 사업이 없거나 계획이 허위라는 뜻이 아니다. LH 공모와 선정 기록까지 확보했지만, 9·7 세부 프로그램으로 귀속시킬 개별 근거가 충분하지 않은 경우다. 공공사업 후보 데이터는 보존하고 정책 집계에 임의로 더하지 않았다. 성남복정 735호는 [4월 15일 정부 공공주택 점검 발표](https://www.korea.kr/news/policyNewsView.do?newsId=148962743)에도 등장한다. **공공주택 6.2만호 계획에 포함된다는 사실과 특정 정책 프로그램 배정은 서로 다른 확인 사항**이다.

## 5. 실제 착공 여부는 무엇을 확인했는가

LH 공모는 승인·착공 **예정 시기**, 우선협상대상자 선정은 **사업자 선정 단계**의 근거다. 7월 선정 결과가 있어도 실제착공일을 만들지 않았다. 개별 블록의 주택인허가·일반 건축인허가·건축물대장 후보를 명칭과 블록으로 다시 대조했고, 결과는 [착공·인허가 원천 재대조표](completion_20261020/target-source-recheck.json)에 보존했다. 이름이 맞아도 호수·변경승인·실제 날짜가 없으면 실적을 확대하지 않는다.

| 공식 선정일 | 대상 블록 | 우선협상대상자 | 확인 가능한 단계 |
| --- | --- | --- | --- |
| 2026-07-08 | 평택고덕 A72·A73 | 금호건설 컨소시엄 | 사업자 선정 |
| 2026-07-10 | 평택고덕 A70 | 디엘건설 컨소시엄 | 사업자 선정 |
| 2026-07-15 | 평택고덕 A69·A71 | 극동건설 컨소시엄 | 사업자 선정 |
| 2026-07-16 | 인천검단 AA30 | 금강주택 컨소시엄 | 사업자 선정 |
| 2026-07-23 | 고양창릉 B1·양주고읍 A12 | 동부건설 컨소시엄 | B1 사업화 확인 반영, A12 정책 귀속은 유보 |
| 2026-07-23 | 화성동탄 A1 | 남광토건 컨소시엄 | 사업자 선정 |
| 2026-07-29 | 안산장상 A10·성남복정1 B2 | 한신공영 컨소시엄 | A10 사업화 확인 반영, B2 정책 세부 귀속은 유보 |
| 2026-07-30 | 수원당수2 B5·B7, 수원당수 B4 | 계룡건설산업 컨소시엄 | 동일 블록 3건의 사업화 확인 반영 |

6월 재공고·일정 지연을 다룬 뉴스는 탐색 단서로만 참고했다. 이후의 공식 선정 결과를 확보했으므로 과거 재공고 보도만으로 현재도 사업자가 없다고 판단하지 않는다. 반대로 선정 결과만으로 착공 완료를 주장하지 않는다. 공식 선정 공고의 개별 URL·HWP 원문은 출처 목록에 포함했다.

고양창릉 A4·S5·S6은 LH 10월 보도자료의 2,089호 및 2024년 10월 착공 언급을 기존 900+759+430호와 대조했다. 이는 기존 사업을 뒷받침하는 자료이며 2026년 신규 착공 2,089호가 아니다. 부천대장 A9의 568→574호는 앞선 검증에서 확보한 변경승인 근거를 유지했다. 신규 사업을 더하거나 같은 승인 물량을 반복 가산하지 않았다.

### 독립 집계의 중복·날짜 해석 보정

인천검단 AA19는 국민임대 991호와 영구임대 332호로 나뉜 동일 단지다. 공식 원문의 구성표로 두 물량이 겹치지 않음을 확인해 합계 1,323호로 처리하고, 991호 정정공고는 중복 가산하지 않았다. 독립 검증의 미해결 충돌은 1건에서 0건으로 해소됐다. 또한 단계 도달을 확인한 날짜를 최초 사업화·인허가 발생일로 해석하지 않도록 보정했다. 화면의 승인 관리량과 누적 착공량은 유지했다. [검증 근거와 제외 사유](completion_20261020/independent-verification.json).

## 6. API 수집 범위와 장애 처리 결과

{summary_text}

{collection_conclusion}

{scope_table}

**수집 작업 종료 상태:** 표제부·총괄표제부·주택인허가 상세는 각각 2,907개 전체 조회를 마쳤다. 일반 건축인허가는 HTTP 429 요청 제한이 반복되어 724개 조회 후 보충 작업이 중단됐다. 미조회 2,183개는 남은 수집 범위이며, 이 보고서 시점에 해당 보충 작업이 실행 중이라고 표시하지 않는다. 외부 제한 해소 후 정상 수집 절차에서 이어받아야 한다. 새로운 수동 검증 범위를 늘리는 대신 이 제한을 명시해 현재 기준본을 확정한다.

검증 기간 DB에 처음 등록된 네 경로의 원천 기록은 **{sum(v['raw_new_records_in_review_window'].values()):,}행**이다. 집계 창은 `{v['review_window_start']}`부터 `{v['review_window_end']}`까지이며 정례 수집이 같은 기간 추가한 행도 포함한다. 원천 행 수는 주택 호수·사업 수·컬럼 셀 수가 아니다. API별 동일 현상을 담은 기록도 있을 수 있어 서로 더해 주택 공급량으로 표시하지 않는다.

기존 주택인허가 기본 API의 서울·경기 2,629개 및 인천 278개 법정동 조회와 별도로, 이번 표는 일반허가·대장·상세 경로의 보완 범위를 보여준다. 법정동 전체 조회가 완료되더라도 원천 기관의 지연 신고, 누락 입력, 정책 귀속, 실제 착공 사건의 완전성이 자동으로 증명되지는 않는다.

재시도는 동일 페이지를 다시 받아 총건수·페이지 크기·관리번호 중복·지역 코드를 검증한다. 성공한 법정동만 완료 목록에 저장하고 7일 지난 지역은 재방문한다. 원문 해시가 같으면 기존 레코드를 유지하고, 달라지면 이전 판본을 보존한다. 요청 제한 중 전체 페이지가 완료되지 않으면 해당 배치를 실패로 남겨 마지막 정상 자료를 유지한다. 변경된 공식 자료를 처리하는 과정에서도 기존 승인 사업량·일정은 자동 덮어쓰기하지 않는다.

## 7. 10월 정부 발표와 차이가 나는 이유

| 비교 대상 | 공식 값·범위 | 우리 데이터와 다른 점 | 가능한 결론 |
| --- | --- | --- | --- |
| 1~8월 수도권 착공 통계 | 86,739호 = 서울 20,679 + 인천 17,515 + 경기 48,545 | 연간 특정 기간·전체 민간/공공 모집단. 우리 화면은 연결된 관리 사업의 과거 포함 누적 | 두 값을 직접 빼서 미수집량이나 정확도로 해석할 수 없음 |
| 10월 공급점검 연말 목표 | 268,000호 | 9·7 외 1·29·8·13 등, 공공·정비·민간·매입약정 등 여러 부문 포함 | 관리 사업 일부의 계획 누계와 같은 분모가 아님 |
| 10월 부문별 실적 | 공공 16,200 / 매입 13,000 / 정비 17,000 / 기타 47,000 / 공공지원민간임대 5,600 | 표시 수치 합계 98,800호, 본문 약 9.9만호. 정비는 9월, 기타는 8월 등 혼합 기준 | 반올림·기준일 차이를 확인할 수 있지만 전체 격차를 시차 하나로 설명할 수 없음 |
| 공공주택 착공 목표 | 62,000호 | 공공사업 전체의 연간 계획. 개별 공모 블록·담당자 승인 관리량과 단계가 다름 | 실제 착공 확인과 계획 호수를 분리해서 비교해야 함 |
| 새로 찾아 연결한 자료 | 4개·3,158호 + 기존 490호 착공 계획 | 이미 공개된 개별 공모·지구계획에 연결 근거가 있었음 | 종전 차이 중 공개자료 수집·연결 보완 여지가 실제로 존재했음 |
| 공식 첨부가 내려받아지지 않는 사례 | 성남복정1 6·7차 고시 목록은 존재, 다운로드는 파일 없음 | 목록 발견과 본문 확보는 다름 | 공식 첨부 제공 장애로 기록. 비공개 자료라고 단정하지 않음 |

공식 비교 원문: [10월 공급점검 자료](https://www.fsc.go.kr/comm/getFile?srvcId=BBSTY1&upperNo=87948&fileTy=ATTACH&fileNo=3), [국가 지표 주택건설실적 자료](https://www.index.go.kr/unity/potal/FileDown.do?seq=17704&id=1229&div=1). 직전 보고서의 동일 기준 비교표와 함께 사용한다. 이번에 원천 문서를 추가했다고 기존 공식 대조표의 분모를 늘려 정확도 비율을 높이지 않았다.

## 8. 설명자료에 사용할 결론과 이후 관리 기준

**지금 사용할 결론:** “우리 데이터는 개별 사업의 공식 원천과 담당자 승인값을 연결한 사업관리 데이터셋이다. 중복 사업·블록 별칭·전체/부분 물량·계획/실적을 구분하여 정비했고, 공개된 지구계획과 공모를 추가 대조해 누락된 연결을 보완했다. 정부 전체 통계와는 대상·기간·사업 유형이 달라 동일 총량이라고 주장하지 않는다.”

**지금 필요한 조치:** 이 보고서의 관리 기준본을 공유하고, 유보 사업은 근거가 확보될 때만 정책 귀속을 갱신한다. 원천 첨부 제공 장애와 API 미조회가 남은 경우 해당 범위를 수집 화면과 보고서에 그대로 표시한다. 이미 확인된 담당자 승인값을 반복해서 불확실한 값으로 서술할 필요는 없다.

**장기적으로 중점 관리할 항목:** 월별 공식 총계를 동일 기간·부문으로 비교하는 표, 공모→선정→주택사업 승인→실제 착공의 사건 연결, 블록명 변경·합필/분필 이력, 원천 계획과 승인 관리일정의 판본 차이, 수집 실패 후 재개 및 오래된 지역 재방문이다. 정부 부문별 총계의 개별 사업 명세를 확보하면 그때 동일 모집단 비교를 확장한다. 현재 명세를 확보하지 못했다는 사실만으로 비공개라고 단정하지 않는다.

## 9. 화면 로딩과 통계 표시 개선

출처 통계의 미표시는 공식 문서 본문에 포함된 제어문자를 PostgreSQL의 JSON 키 추출 함수가 처리하지 못한 오류였다. 원문·해시를 수정하지 않고 해당 출처의 컬럼 키를 안전하게 집계하도록 보정했다. 대량 집계는 백그라운드에서 한 번 수행하고, 마지막 완료 집계와 집계 시각을 표시한다. 갱신 중인 이전 값을 최신 완료값으로 표현하지 않는다.

사업별 수집연계는 변경 확인 시 여러 유형의 원천 이력을 광범위하게 읽던 쿼리를 유형별 인덱스 조회로 바꾸고, 한 화면 계산 안에서 반복되는 읽기를 재사용했다. 지역 여건은 정책 연결·지역 통계가 바뀔 때 갱신하되 아직 연결되지 않은 대량 건축 원천 적재만으로 캐시가 무효화되지 않게 했다. 승인·정책 연결 변경에 대한 무효화는 유지한다. 원천 통계 집계용 인덱스와 DB 통계도 갱신했다.

API 메모리 한도는 768MiB에서 1,536MiB로, DB 한도는 1GiB에서 2GiB로 조정했다. 변경 파일과 실행 결과, 첫 계산/재조회 시간 및 실제 화면 검수 결과는 [로딩 검증 기록](completion_20261020/loading-verification.json)에 보존한다. 응답 시간은 당시 서버 상태의 측정값이며 모든 기기·네트워크의 속도를 보장하는 값은 아니다.

## 10. 다운로드 및 재현 자료

- [14개 사업 판정 CSV](completion_20261020/remaining_14_case_decisions.csv)
- [API 범위·원천 행 수 CSV](completion_20261020/collection_scope.csv)
- [공식 출처 URL·첨부 URL·SHA-256 목록](completion_20261020/official_source_urls_and_hashes.csv)
- [최종 집계·승인값·중복 검증 JSON](completion_20261020/final-validation.json)
- [핵심 원문·대조표 ZIP](HOME_REMAINING_WORK_REVIEW_20261020.zip)

자료 묶음은 핵심 원문과 추출 텍스트를 제공한다. 용량이 큰 중첩 공모 ZIP은 원본 해시와 공식 다운로드 URL을 목록에 남기고, 관련 추출 텍스트를 포함했다. 전체 원본은 작업 폴더 `data/completion-20261020/documents`에 보존되어 있다. 조회·적재·연결 검사 코드는 `scripts/complete_collection_review_20261020.py`, `scripts/register_completion_evidence_20261020.py`, `scripts/finalize_completion_review_20261020.py`에 있다.
'''
    REPORT.write_text(text)
    archive=REPORT.with_suffix('.zip')
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
        z.write(REPORT,REPORT.name)
        for path in sorted(OUT.rglob('*')):
            if path.is_file():z.write(path,str(path.relative_to(REPORT.parent)))
    with zipfile.ZipFile(archive) as z:assert z.testzip() is None
    print(json.dumps(dict(report=str(REPORT),archive=str(archive),archive_bytes=archive.stat().st_size,remaining_api_dongs=remaining),ensure_ascii=False))

if __name__=='__main__':main()
