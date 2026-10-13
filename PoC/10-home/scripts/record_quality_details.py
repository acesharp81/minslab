"""Attach checked quality findings to existing repair revisions; never reset officer decisions."""
import argparse,json,hashlib
from pathlib import Path
from backend.service import HomeService
from backend.db import engine_for
from backend.collection_repairs import patch_details

DAY='2026-10-12'
def check(identifier,title,kind,layer,result,rule,evidence,repair,completion,scope,metrics=None):
    return dict(id=identifier,title=title,kind=kind,layer=layer,result=result,rule=rule,evidence=evidence,repair=repair,
                completion_criteria=completion,checked_at=DAY,checked_scope=scope,metrics=metrics or [])
def m(label,value,total=None,unit='개'):
    return dict(label=label,value=value,total=total,unit=unit)

DETAILS={
 'a31-alias-and-documents':dict(related_keys=['block','project','actual','due'],quality_checks=[
  check('block-alias','동일 블록의 별칭·수량 정합성','CONSISTENCY','LINKAGE','PARTIAL','지역·지구·단일 블록·총호수가 함께 대응돼야 동일 사업 후보로 연결합니다.',
   '공급·건설 원천에서 A31 / Ab31 표기가 다르고 두 기록의 690호는 일치합니다. 별칭 후보와 원천 판본은 DB에 저장됐습니다.',
   '사업명에 명시된 블록과 공식 문서를 대조한 후보를 검토합니다. 이름만 비슷한 다른 A12·A65 단지는 제외합니다.',
   '담당자가 두 기록의 동일 사업 여부와 적용 범위를 확정하고 별칭 변환의 근거를 보존합니다.','평택고덕 A31 공급·건설 기록'),
  check('approval-draft','미완성 고시의 사건일 유효성','VALIDITY','SOURCE_LIMIT','PENDING','정식 고시번호와 유효한 실제 날짜가 없으면 승인 실적으로 쓰지 않습니다.',
   '확보된 인허가 문서는 2025-000·빈 일자를 가진 초안이며 실제 승인일이 확정되지 않았습니다.',
   '정식 승인 고시 원문을 확보해 번호·날짜·대상 블록을 대조합니다. 초안은 문서 확보 사실로 보존합니다.',
   '정식 고시의 발령일·번호·사업 범위를 확인하고 실제 사건 근거로 담당자가 연결합니다.','평택고덕 A31 승인 문서')]),
 'cross-source-bridges':dict(related_keys=['block','project','target'],quality_checks=[
  check('stored-scope','원천 간 동일성·연결 지속성','CONSISTENCY','LINKAGE','PARTIAL','연결 후보를 DB에 보존하고 확정·해제를 재수집으로 변경하지 않습니다.',
   '최초 정비에서 98개 사업 기록에 131개 후보를 저장했고 원천 판본·적용 범위·검토 상태를 보존했습니다. 보류 110건은 확정된 연결이 아닙니다.',
   '동일 블록·호수·복합 계약을 원문으로 확인하고 일부 범위 관계는 별도 확정합니다.',
   '확정·해제된 후보가 재실행 후 유지되고 중복 후보가 추가되지 않으며 전체/일부 사업의 중복 합산을 방지합니다.','최초 원천 간 연결 정비 스냅샷')]),
 'geumto-a2-split-tenure':dict(related_keys=['block','project','target','move_plan','move_actual'],quality_checks=[
  check('tenure-amount','단지·유형·금회 모집량 정합성','CONSISTENCY','LINKAGE','PARTIAL','단지 총량, 유형별 총량, 금회 모집량을 각각 관리합니다.',
   '공식 문서의 국민임대 438 + 영구임대 195 = 단지 633호를 확인했습니다. 금회 국민임대 모집은 219호이며 전체 438호와 다릅니다.',
   '438/633 및 195/633의 부분 범위로 연결하고 정정공고·복합 계약 범위를 확인합니다.',
   '유형별 합계 633호가 보존되고 금회 모집 219호나 계약 내 비주택 시설을 단지 총량으로 합산하지 않도록 검토합니다.','성남금토 A-2 원문 대조'),
  check('move-plan-not-actual','예정월과 실제 입주 유효성','VALIDITY','DISPLAY','PENDING','입주 예정월은 실제 입주 시작일 근거로 쓰지 않습니다.',
   '국민·영구임대 공고의 2027-01은 예정월입니다. 공고 상세를 연결해도 실제 입주 시작일은 별도 확인이 필요합니다.',
   '유형별 예정월을 보존하고 최초 실제 입주 시작일은 별도 공식 근거로 연결합니다.',
   '실제 시작 확인 자료의 사건일을 확보하고 예정과 실제 필드를 별도 표시합니다.','성남금토 A-2 입주 일정')]),
 'lh-notice-detail-gap':dict(related_keys=['notice','block','move_plan','due'],quality_checks=[
  check('detail-coverage','목록과 상세 일정의 수집 정합성','COVERAGE','COLLECTION','PARTIAL','목록 수집만으로 상세 일정·유형 정보를 확보했다고 판정하지 않습니다.',
   '1차 상세 53건과 후속 상세 115건에서 예정월·단지 총량·금회 모집량을 분리했습니다. 첨부에만 있는 일정은 HTML 상세만으로 확보되지 않습니다.',
   'PDF/HWP 첨부·정정·취소·복수 단지 공고를 추가 수집하고 원문 판본별 정보를 보존합니다.',
   '대상 공고의 HTML·첨부 범위를 구분하고 예정월·유형·총량의 원문 대조 결과와 취소/정정 관계를 남깁니다.','LH 공고 상세 정비 두 차수 스냅샷')]),
 'juam-c2-approval':dict(related_keys=['block','project','permit','actual','target'],quality_checks=[
  check('approval-scope','전체 승인과 일부 사업의 물량 정합성','CONSISTENCY','LINKAGE','PARTIAL','전체 승인 범위와 일부 주택유형의 적용 호수를 별도 관리합니다.',
   '건축HUB C2 승인 원천은 1,030호·2020-12-29이고 별도 행복주택 사업 기록은 344호입니다. C1 1,338호는 별도 허가 2020-12-31입니다.',
   'C2 일부 사업 344호/승인 원천 1,030호를 구분하고 C1/C2를 블록별로 검토합니다.',
   '원문으로 전체/부분 관계와 블록을 확인해 담당자가 확정하고 344호를 1,030호와 중복 합산하지 않습니다.','과천주암 C1·C2 공식 원천 대조'),
  check('gazette-proof','허가일과 승인 고시의 증빙 구분','VALIDITY','SOURCE_LIMIT','PENDING','모집공고는 승인 고시 원문을 대신하지 않습니다.',
   '건축HUB 허가일은 확보했으나 승인권자·고시번호·최초/변경승인 관계의 고시 원문 대조는 남아 있습니다.',
   '국토부·관보 고시를 찾아 사업 범위와 최초/변경 관계를 대조합니다.',
   '고시번호·발령일·승인권자·사업 범위의 근거 원문과 검토 결과를 저장합니다.','과천주암 승인 증빙 점검')]),
 'approval-global-normalization':dict(related_keys=['block','project','permit','actual'],quality_checks=[
  check('event-vs-inference','정규화·실제 사건일·선행 추정의 정합성','CONSISTENCY','LINKAGE','PARTIAL','동일 지역·블록의 공식 사건을 선행 추정보다 우선하되 담당자 판정은 보존합니다.',
   '292개 사업 점검에서 인허가 미연결 148→147개, 날짜 근거 신규·보강 7개(선행 추정 보강 6개)를 확인했고 재실행 새 판본 0건을 확인했습니다.',
   '남은 미연결을 주소/필지, 복수 블록, 원천 사업명, 고시 미수집으로 분류합니다.',
   '추정과 실제 사건이 구분되고 미연결을 미허가로 해석하지 않으며 담당자 확인과 해제가 보존됩니다.','전체 인허가 정비 적용 시점')]),
 'lh-notice-category-region-schedule':dict(related_keys=['region','notice','project'],quality_checks=[
  check('category-and-pages','지역·유형·페이지 범위의 완전성','COVERAGE','COLLECTION','PARTIAL','각 지역·유형의 API 총건수와 페이지 수를 검증하고 비주택·지역 혼합 공고를 분리합니다.',
   '분양 05·임대 06 외 신혼희망타운 39와 인천 28을 추가했습니다. 공고 3,050→4,018건, 신규 968건을 확인했습니다. 어린이집 239건·지역 혼합 2건은 임의 주택 배분에서 제외했습니다.',
   '정기 수집의 페이지 검증과 상세 연계를 유지하고 취소·정정 이력까지 보완합니다.',
   '조회 범위와 제외 규칙이 배치 이력에 남고 공고 건수를 주택 호수로 집계하지 않습니다.','LH 지역·유형 확대 수집 당시')]),
 'completion-stage-semantics':dict(related_keys=['start','progress','completion','supply','due','move_actual'],quality_checks=[
  check('completion-stage','예상 준공일의 단계 유효성','VALIDITY','DISPLAY','PASS','준공 예정일은 건설 계획에 포함하고 공급일·입주일과 구분합니다.',
   '예상 준공이 공급 칸에 중복 표시되던 분류를 정비해 건설 단계에만 배치했습니다. 원천 공정률과 기간 비례 계획을 분리했습니다.',
   '공급은 모집공고·분양 계획, 입주는 별도 시작일 근거로 관리하고 공식 공정표 확보 시 추정 계획을 보완합니다.',
   '준공일이 공급·입주 목표로 중복 생성되지 않고 0~100% 추정 계획은 공식 실적으로 표기되지 않습니다.','건설 일정 분류 구현·검증 결과')]),
 'schedule-unknown-semantics':dict(related_keys=['due','move_plan','supply'],quality_checks=[
  check('null-vs-tbd','미정·공란·항목 미제공의 유효성','VALIDITY','COLLECTION','PARTIAL','빈 날짜만으로 원문 미정이나 미계획을 판정하지 않습니다.',
   '원문 미정, 공란, 해당 항목 미제공, 원문 확인 전을 별도 상태로 관리합니다. 반기·예정월은 원래 정밀도로 보존합니다.',
   '고양창릉 S-02 등 일정 상태를 원문 항목의 존재 여부와 함께 확인하고 실제 입주 근거를 별도 수집합니다.',
   '각 상태에 원문 판본·항목명이 남고 공란이 0일·임의 날짜·실제 입주로 변환되지 않습니다.','사업별 공급·입주 일정 상태 정비')]),
 'missing-data-classification':dict(related_keys=['project','target','due','actual'],quality_checks=[
  check('missing-vs-zero','미확보와 0·미계획의 구분','VALIDITY','DISPLAY','PARTIAL','근거가 없는 실적은 0이 아니며 미계획 판정은 확인 근거가 필요합니다.',
   '사업×단계에 원천·목표·확보 근거와 담당자 원인 판정을 분리했습니다. 동일 기관·단계·사유의 수집 과제를 묶었습니다.',
   '제공처·수집 범위·연결 실패·미계획을 근거별로 조사하고 새 근거와 충돌하는 과거 판정을 재검토합니다.',
   '미확보 셀에 0 실적을 생성하지 않으며 담당자 판정 근거와 계획/실적 구분을 보존합니다.','사업별 수집 상태 관리 구현 점검')]),
}


def pnu_details(audit):
    counts=audit['counts'];total=audit['total'];scope='9·7 정책 조회 '+str(total)+'개 사업 기록 · 점검 시점';raw_scope='광주역세권 청년혁신타운 보관 원문 대조'
    return {
     'pnu-assembly-and-field-loss':dict(related_keys=['pnu','legal_dong','permit','block','project'],quality_checks=[
      check('pnu-components','PNU 구성값의 완전성','VALIDITY','COLLECTION','PARTIAL','법정동 10자리 + 일반/산 1자리 + 본번 4자리 + 부번 4자리가 필요합니다.',
       '법정동 확보 '+str(counts['projects_with_legal_code'])+'개. 연결 허가 기본개요에 본번·부번이 저장된 기록은 2개이나 1개는 블록·0000-0000이고 유효 지번은 1개입니다.',
       '기본개요와 대지위치의 대지구분·본번·부번을 모두 보존하고 공란과 실제 부번 0000을 구분합니다.',
       '원천 판본에 법정동·대지구분·유효 본번·부번이 있고 누락 상태를 별도 기록합니다.',scope,[m('법정동 확보',counts['projects_with_legal_code'],total,'사업 기록'),m('현재 PNU 확보',counts['projects_with_pnu'],total,'사업 기록')]),
      check('pnu-land-code','대지구분 코드 변환·저장 누락','PROCESSING','COLLECTION','FAIL','건축HUB 대지구분 0/1은 PNU 필지구분 1/2로 변환하고 블록 2는 필지로 조합하지 않습니다.',
       '기본 인허가·건축물대장 수집기는 platGbCd를 저장하지 않습니다. 광주역세권 청년혁신타운의 보관 원문에는 0·0417·0002가 있습니다.',
       '수집기에서 원래 코드를 저장하고 별도 변환값으로 PNU를 구성합니다. 보관 원문 재처리 시 기존 실제 사건 연결을 덮어쓰지 않습니다.',
       '대지/산 변환 검증이 통과하고 원천 코드와 변환 근거·판본이 보존됩니다.',raw_scope),
      check('pnu-join-path','필지와 사업 연결 경로 누락','CONSISTENCY','LINKAGE','FAIL','허가 원천 PK로 대지위치 상세를 결합한 뒤 저장된 사업–허가 관계를 따라 사업에 연결합니다.',
       '다이어그램은 완성된 pnu 값만 세며 구성 처리가 없습니다. 같은 허가 PK의 대지위치가 별도 저장돼도 사업 필지 연결로 전달하지 않습니다.',
       '사업↔허가↔필지 관계를 판본·적용 범위·검토 상태와 함께 저장하고 여러 필지를 목록으로 유지합니다.',
       '실제 연결된 유효 필지만 확보 건수에 포함하고 대표 필지 확보와 전체 필지 확인을 구분합니다.',scope),
      check('pnu-recoverable-example','보관 원문으로 구성 가능한 실제 사례','VALIDITY','COLLECTION','PARTIAL','19자리 문자열 구성 후 법정동과 지번을 원문으로 역검증합니다.',
       '광주역세권 청년혁신타운: 41610 + 11200 + 대지 0 + 0417 + 0002. 변환 후 후보 4161011200104170002입니다. 아직 DB 사업 필지로 적용하지 않았습니다.',
       '보관 원문 해시와 생성 근거를 저장하고 지적 원천의 동일 지번과 대조한 뒤 후보 연결을 검토합니다.',
       'PNU를 역분해하면 법정동 4161011200·일반토지·417-2와 일치하고 사업 범위 대조 기록이 남습니다.',raw_scope)]),
     'pnu-targeted-parcel-coverage':dict(related_keys=['pnu','legal_dong','permit','block'],quality_checks=[
      check('pnu-target-coverage','연결 사업 법정동의 수집 범위 부족','COVERAGE','COLLECTION','FAIL','연결된 허가가 속한 법정동부터 상세 대지위치를 조회하고 조회 완료와 전체 모집단 확보를 구분합니다.',
       '허가 '+str(audit['linked_unique_permits'])+'건은 26개 법정동에 걸쳐 있으며 점검 시 대지위치 조회 완료는 1개 법정동입니다.',
       '미조회 25개 법정동을 우선 수집하고 페이지 누락·중복을 검증한 후 원천 PK로 결합합니다.',
       '대상 26개 법정동의 조회 결과·총건수·일시·원문 판본을 보존하고 주소가 블록인 경우 별도 보완 과제로 남깁니다.',scope,[m('대상 법정동 조회 완료',1,26,'법정동')]),
      check('pnu-block-placeholder','블록 주소·0000-0000의 유효성 한계','VALIDITY','SOURCE_LIMIT','NOT_APPLICABLE','블록 식별자나 본번 0000은 실제 지번 PNU로 변환하지 않습니다.',
       '동일 허가 PK로 저장된 당수동 대지위치 2행은 대지구분 2(블록), 본번·부번 0000입니다. 3개 사업 기록에 대응하지만 유효 필지값이 아닙니다.',
       '승인 도서·기관 블록별 지번·건축물대장 부속지번에서 실제 지번을 확보합니다. 공간 경계 교차는 후보로 저장하고 담당자가 확인합니다.',
       '실제 일반/산 지번이 확인되거나 블록-only 상태와 보완 제공처가 명시돼 허위 PNU가 생성되지 않습니다.','수원 당수동 관련 대지위치 2행',[m('연결 대지위치 상세',2,None,'원천 행'),m('관련 사업 기록',3,None,'사업 기록')]),
      check('pnu-many-parcels','다중 필지·합필·기준일 정합성','CONSISTENCY','LINKAGE','PENDING','대표 필지 하나와 전체 사업 대지를 구분하고 여러 필지·분할·합필 관계를 원천 기준일과 함께 보존합니다.',
       '현재 연결된 상세는 블록 주소로 전체 필지·합필 관계를 확인할 수 없습니다. 법정동 또는 19자리 형식만으로 경계 일치를 확정할 수 없습니다.',
       '총괄표제부·부속지번과 승인 도서의 필지 목록을 대조합니다. 법정동·필지 변경 전후를 기록하고 정확한 도로명주소는 지번 후보 보완에 사용합니다.',
       '사업의 전체 필지 목록 또는 일부 확보 상태, 원천 기준일, 분할/합필 관계, 담당자 확인 상태가 남습니다.',scope)])}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--pnu-audit');args=p.parse_args()
    details=dict(DETAILS)
    if args.pnu_audit:
        artifact=Path(args.pnu_audit);pnu=pnu_details(json.loads(artifact.read_text()))
        for entry in pnu.values():
            for c in entry['quality_checks']:c['evidence_refs']=[dict(kind='DB_CODE_RAW_AUDIT',name=artifact.name,sha256=hashlib.sha256(artifact.read_bytes()).hexdigest())]
        details.update(pnu)
    s=HomeService(engine_for(),'/app/data')
    print(json.dumps([patch_details(s,k,v) for k,v in details.items()],ensure_ascii=False))
