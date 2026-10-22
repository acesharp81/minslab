"""Refresh R02 and add a separately scored official-comparison rubric v1.
Run inside API container with inputs in data/remediation/r02-current-20261022.
The original 40-item/100-point longitudinal scale is deliberately unchanged.
"""
from copy import deepcopy
from datetime import date,datetime
from zoneinfo import ZoneInfo
from pathlib import Path
from html import escape
import csv,hashlib,json
from backend.db import engine_for
from backend.service import HomeService
from backend.data_integrity import get_round,amend_round,rounds
from backend.independent_metrics import freeze
from backend.policy_delivery import build_delivery,comparison_index
from scripts.complete_collection_review_20261020 import slim,IDS
from scripts.review_policy_readmission_20261019 import protected,digest

ID='HOME-INTEGRITY-R02-20261020'
REASON='사용자 요청: 10월22일 현재 기준 보완2 갱신 및 공식자료 비교 지표 별도 채점'

def main():
 s=HomeService(engine_for());w=s.data_dir/'remediation/r02-current-20261022'
 def read(n):return json.loads((w/n).read_text())
 def save(n,x):(w/n).write_text(json.dumps(x,ensure_ascii=False,indent=2,default=str)+'\n')
 old=get_round(s,ID);save('round-before.json',old)
 original={x['id']:x['digest'] for x in rounds(s)['items']};protected_before=protected(s)
 model=build_delivery(s,date(2026,10,22),include_portfolio_comparisons=False);save('model.json',model)
 cohorts=model['portfolio_cohorts'];byid={x['id']:x for x in cohorts}
 ids=[pid for c in cohorts for pid in c['source_ids']];assert len(ids)==len(set(ids))
 reference=read('reference-model.json')
 def canonical(x):
  if isinstance(x,dict):return {k:canonical(v) for k,v in x.items()}
  if isinstance(x,list):return sorted([canonical(v) for v in x],key=lambda v:json.dumps(v,sort_keys=True,default=str))
  return x
 assert digest(canonical(cohorts))==digest(canonical(reference['portfolio_cohorts'])), '최신 관리사업 내용 재검토 필요'
 comparison=comparison_index(dict(model['plan'],period_start='1900-01-01',portfolio=True),cohorts,model['settings'],[],date(2026,10,22))['policy']['metrics']
 metrics={stage:{name:next((p['units'] for p in reversed(v['tracking'][field]) if p['date']<=end),None) for name,field,end in [('actual','actual_points','2026-10-22'),('year_end','forecast_points','2026-12-31')]} for stage,v in comparison.items()}
 expected={x['stage']:{'actual':x['current_units'],'year_end':x['year_end_units']} for x in read('cumulative-audit.json')['summary']}
 assert metrics==expected,(metrics,expected)
 snap=freeze(s,'담당자 대행',REASON);save('independent.json',snap)
 rows=list(csv.DictReader((w/'official-32.csv').open(encoding='utf-8-sig')))
 for x in rows:assert byid[x['home_cohort_id']]['units']==int(x['home_quantity']),x['official_name']
 grouped={x['home_cohort_id']:x for x in rows};equal=[x for x in grouped.values() if int(x['group_difference'])==0]
 different=[x for x in grouped.values() if int(x['group_difference'])!=0]
 assert len(rows)==32 and len(grouped)==31 and len(different)==5
 official=sum(int(x['official_value']) for x in rows);housing=sum(int(x['count_once_units']) for x in rows)
 sources=read('sources.json')['items'];q=read('requirements.json')
 success=sum(x['status']=='SUCCESS' for x in sources);automatic=sum(not x.get('manual_only',False) for x in sources)
 r=deepcopy(old['result']);parent=get_round(s,old['parent_id'])['result'];prior={i['id']:i for c in parent['categories'] for i in c['items']}
 comments={
 'B1':'정책 전체 사업 명부와 분모는 미확정. 공식 4분기 발표32개는 전수 대응했으나 전체 정책 모집단으로 확대하지 않음.',
 'C1':'공식32행을31관리 묶음에 대응. 신길A1/A3 합산은1회만 기여하고 연남8호를 별도 식별.',
 'C2':'공식 후속 근거63개와 정책 관련관계를 보강. 원135만호의 추가 정량 귀속은 유보하며 새 착공 실적으로 가산하지 않음.',
 'C4':f'관리 묶음{len(cohorts)}개·원천ID{len(ids)}개. 기여ID 중복0개. 물리적 현장 전수 동일성 검증과 구분.',
 'E1':'과거 착공을 포함하는 정책 누적, 당해연도 공식실적, 미래 계획을 분리. 연말 예상은 사업·단계별 현재 누적과 연말까지 계획의 큰 값을 합산.',
 'E2':'검단AA19 국민991+영구332=1323호. 병점726주택+54오피스텔을 분리. 공식32행의 주택 부분합14753호, 공식14731호와+22호.',
 'E4':'CSV의76개/화면177개 범위 차이를 수정. 371범위×6단계=2226개 검증, 과거 착공101개도 누적에 포함. 전체 플랫폼 무오류를 뜻하지 않음.',
 'F3':'기존R02 JSON·HTML·해시를 보존하고 같은 회차 갱신. 최초 및1차 평가 원본 보존. 공식 비교는 별도20점 신규 척도로 기록.',
 'H1':'누적·예상·내보내기 관련 Python36개 및JS19개 검증 통과(10월22일 기존 실행). 데이터 전수 정확도와 구분.',
 'H3':'기존 공식 비교185항목의 판정과 최신 관리사업32행 수량 불변을 점검. 원문 기준과 자체 계산 근거 고정.',
 'H4':'DB 복원 검증과 DB·외부 원문 동시 복구 실증은 별개. 후자 미완료로 기존 등급 유지.',
 'J1':f"현재 정책 누적 착공{metrics['CONSTRUCTION']['actual']:,}호, 연말 예상{metrics['CONSTRUCTION']['year_end']:,}호. 담당자 확인·추정·선행 단계 도달값 포함이며 정부 연간 실제착공 총계와 다름.",
 'J3':'공식32행 대조·185항목 판정·223후보 상태·누적 검증 결과와 발표용MD를 판본별 제공.',
 'J4':'기존40항목100점과 새 공식비교20점을 분리. 서로 다른 척도 합산이나 이전 성적 대비 상승률을 산출하지 않음.'}
 mapping={'D1':'F-03','D2':'F-02','D3':'F-05','D4':'F-06','I3':'F-08'}
 changes=[]
 for c in r['categories']:
  for i in c['items']:
   key=i['id'];previous=i['score'];i.update(previous_score=prior[key]['score'],previous_reason=prior[key]['reason'])
   comment=comments.get(key,'이번 범위에서 추가 등급 변경 근거가 없어 기존 등급 유지. '+i.get('next_step',''))
   if key in ('A1','A2'):
    num=success if key=='A1' else automatic;den=len(sources);i.update(numerator=num,denominator=den,fraction=num/den)
    comment=f'현재 동일 정의 재산정 {num}/{den}. '+('최근 상태 성공 비율이며 장기 성공률이 아님. iH 실패도 분모에 유지.' if key=='A1' else '자동 순회 설정 비율. 실제 정시 성공률·업무 담당자의 연결 작업과 구분.')
   elif key in mapping:
    m=q['metrics'][mapping[key]]['without_estimates'];num=m['count'];den=m['total'];i.update(numerator=num,denominator=den,fraction=num/den if den else 0)
    comment=f"추정 제외 같은 정의로 재산정: {num}/{den}. {m['note']}"
   i.update(score=i['weight']*i['fraction'],reason=comment,change_comment=comment,amendment_previous_score=previous)
   i.update(score_delta=i['score']-i['previous_score'],amendment_score_delta=i['score']-previous)
   if abs(i['score']-previous)>1e-9:changes.append(dict(id=key,before=previous,after=i['score']))
  c['score']=sum(i['score'] for i in c['items'])
 assessed=datetime.now(ZoneInfo('Asia/Seoul')).isoformat();total=sum(c['score'] for c in r['categories'])
 r.update(total_score=total,display_score=round(total,1),previous_total_score=parent['total_score'],assessed_at=assessed,generated_at=assessed,snapshot_id=snap['id'],independent_snapshot_counts=snap['result']['counts'],actor='담당자 대행',reason=REASON,title='2차 보완 성적표 · 공식자료 비교 지표 추가',tests=dict(passed=55,note='2026-10-22 누적 집계 관련 Python36·JS19개 기존 실행 결과'))
 for g in r['groups']:
  g['score']=sum(c['score'] for c in r['categories'] if c['group']==g['id']);g['percent']=100*g['score']/g['weight']
 oitems=[]
 def add(key,name,weight,num,den,reason,evidence):
  oitems.append(dict(id=key,name=name,weight=weight,numerator=num,denominator=den,score=weight*num/den,reason=reason,evidence=evidence))
 add('O1','4분기 발표 사업의 관리사업 대응',3,32,32,'32행 모두 대응. A1/A3는 하나의 관리 묶음이라 수량 비교는31개 단위. 실제 공급 완료나 전체 정책 수집률이 아님.','official-32.csv')
 add('O2','4분기 사업별 원수량 직접 대조',4,len(equal),len(grouped),'같은 비교 단위의 원수량이 같은26/31. 주택·오피스텔 범위 조정이나 반올림으로 설명되는 항목은 O4에서 별도 평가; 해당 항목이 잘못된 데이터라는 뜻은 아님.','official-32.csv')
 add('O3','4분기 비교의 원문·사업ID·판본 추적',2,sum(bool(x['source_url'] and x['source_revision'] and x['home_project_id']) for x in rows),32,'32행 모두 원문 URL·사업 ID·원천 판본 보유. URL 전수 재접속 성공률을 뜻하지 않음.','official-32.csv')
 add('O4','수량 차이가 나는 비교 단위의 원인 확정',3,1,len(different),'병점54실은 오피스텔 범위 차이 확인. 대장A2 +50, 신길B1 +5·A6 -1·A1/A3 +22는 원수량 차이 확인만 완료, 발생 원인은 미확정.','official-32.csv')
 add('O5','착공5개 공급유형의 전체 원장 재현',2,0,5,'공공주택·신축매입·민간정비·기타 일반민간·공공지원민간임대의 정부 동일범위 전체명세 재현 미완료. 0점은 검증완료 기준 미충족이며 실적0호가 아님.','HOME_SUPPLY_TYPE_VERIFICATION_20261021.md')
 add('O6','1~3분기 분양·임대 모집 총계 재현',2,0,2,'분양 후보14451호, 임대 상세부분합4461호. 공식14800·14700호의 같은 범위 전량 대사는 미완료. 0점은 데이터 없음 또는 오류 판정이 아님.','HOME_ADDITIONAL_MAPPING_REVIEW_20261021.md')
 add('O7','정책 누적과 연말 예상의 범위 일관성',2,2226,2226,'371범위×6단계 검증. 과거 착공 포함·예상>=현재·계획 원장 보존. 공식 연간 통계와의 수치 일치 점수가 아닌 집계 검증 점수.','cumulative-audit.json')
 summary=read('comparison-summary.json');assert summary['indicators']==185
 add('O8','공식 비교 항목의 판정·유보 분류 기록',2,sum(summary['status_counts'].values()),185,'185항목 전부 판정 상태 기록. 41부합·1계획부합 외 범위 차이와 유보 등을 구분. 185개를 독립적인 수치 일치로 계산하지 않음.','comparison-summary.json')
 oscore=sum(x['score'] for x in oitems)
 rubric=dict(version='OFFICIAL-COMPARISON-V1-20261022',assessed_at=assessed,items=oitems,total_score=oscore,display_score=round(oscore,2),max_score=20,previous_score=None,note='신규 공식 비교 검증 준비도 척도. 가중치는 내부 평가 설계이며 통계적 정확도·수집률·정부 인증점수가 아니다. 기존40항목100점과 중복되는 과정 지표가 있어 두 점수를 합산하지 않는다. 원수량 동등성과 설명 가능성, 총계 재현을 각각 채점한다.',status_counts=summary['status_counts'])
 r['official_comparison_scorecard']=rubric
 v=dict(assessed_at=assessed,previous_score=old['result']['display_score'],previous_total_score=old['result']['total_score'],previous_digest=old['digest'],metrics=metrics,portfolio_cohorts=len(cohorts),contributing_source_ids=len(ids),unique_source_ids=len(set(ids)),scopes={sid:slim(s.latest_collection_stats(sid)) for sid in IDS},snapshot_id=snap['id'],independent_counts=snap['result']['counts'],source_count=len(sources),successful_sources=success,automatic_sources=automatic,score_changes=changes,official=dict(official_rows=32,official_units=official,matched_rows=32,matched_official_units=official,matched_weight_percent=100,matched_quantity_rows=len(equal),comparison_groups=31,matched_quantity_units=sum(int(x['group_home_units']) for x in equal),home_housing_units=housing,note='32행 사업 대응과31개 비교 단위 중26개 원수량 동등을 분리. 전체 정확도·전체 정책 수집률 아님.'),policy_review=dict(projects_confirmed=63,project_units=None,quantity_added=0,scope_only_records=16,scope_only_units=29699),note='63개는 공식 후속 근거 보강이며 9·7 신규 정량 편입0개. 223후보 상태를 별도 제공. 4대 분류·53개 주장 검증은 과거 고정 표본 결과이며 최신 전수 정확도로 주장하지 않음.')
 r['current_reassessment']=v;save('current-validation.json',v)
 r['classification_note']='기존 고정 표본 결과 유지. 이번 185항목·32행·177관리사업의 전수 분류 정확도 아님.'
 r['agreement_note']='이전 고정53개 주장 기준 확인율. 신규 공식 비교 점수는 별도 표 참조. 현재 전체 일치율로 사용하지 않음.'
 for name in ('sources.json','requirements.json','current-validation.json','independent.json','official-32.csv','comparison-summary.json','cumulative-audit.json'):
  r['round_evidence'][name]=dict(path=str((w/name).relative_to(s.data_dir)),sha256=hashlib.sha256((w/name).read_bytes()).hexdigest())
 text=['# the주택 2차 보완 성적표 · 2026-10-22','',f'평가 시각: {assessed}','',f'**기존 구축 준비도 {old["result"]["display_score"]:.1f} → {r["display_score"]:.1f}/100점. 공식자료 비교 평가 {oscore:.2f}/20점 신규 추가.**','',rubric['note'],'','## 공식자료 비교 점수 항목','', '| 항목 | 근거 충족 / 평가 분모 | 취득 / 배점 | 판정 근거 |','|---|---:|---:|---|']
 text += [f'| {i["id"]} {i["name"]} | {i["numerator"]}/{i["denominator"]} | {i["score"]:.2f}/{i["weight"]} | {i["reason"]} |' for i in oitems]
 text += ['','배점: 사업 대응3·원수량4·출처2·차이원인3·부문총계2·모집총계2·집계일관성2·판정기록2=20점. 공식자료 대비 숫자가 크다는 이유로 가점하지 않는다. O1/O3/O7/O8은 과정·추적 품질, O2/O4/O5/O6은 수량 대조 및 재현 여부를 평가한다.','','## 현재 수집·관리 범위','',f'- 등록 출처 {len(sources)}개, 최근 성공 {success}개, 자동 순회 대상 {automatic}개. 장기 성공률과 구분.',f'- 관리사업 {len(cohorts)}개, 기여 원천 {len(ids)}개, 기여 ID 중복0개.',f'- 공식32행 계획14731호 ↔ 관리 주택14753호(+22). 오피스텔54실 별도, 발표와 혼합 범위로 재구성하면14807(+76).',f'- 정책 누적 착공{metrics["CONSTRUCTION"]["actual"]:,}호, 연말 예상{metrics["CONSTRUCTION"]["year_end"]:,}호. 과거 착공 포함; 추정·담당자 채택이 포함된 관리값. 정부 연간 실적 아님.','- 63개 공식 후속 근거 보강은 신규 착공 증가0호. 관계 연결과 정량 산입을 분리.','- 최초·1차 평가 원본 및 수정 전2차 성적표를 해시와 함께 보존.','','## 기존40개 항목 · 같은 기준 재산정','', '| 항목 | 갱신 전 → 후 / 배점 | 근거 |','|---|---:|---|']
 text += [f'| {i["id"]} {i["name"]} | {i["amendment_previous_score"]:.3f} → {i["score"]:.3f}/{i["weight"]} | {i["reason"]} |' for c in r['categories'] for i in c['items']]
 text += ['','## 근거 파일','', '- [공식32행 비교 CSV](reliability_update_20261022/official-32.csv)','- [185항목 판정 분포](reliability_update_20261022/comparison-summary.json)','- [전체 평가 JSON](reliability_update_20261022/round.json)','- [정책 누적 검증](THE_JUTAEK_CUMULATIVE_FORECAST_REVIEW_20261022.md)','- [공공분양·임대 부분합 원장과 한계](HOME_OFFICIAL_FOLLOWUP_COLLECTION_20261021.md)','- [5개 공급유형 분류·전체실적 재현 한계](HOME_SUPPLY_TYPE_VERIFICATION_20261021.md)']
 md='\n'.join(text)+'\n';r['report_markdown']=md
 html='<!doctype html><html lang="ko"><meta charset="utf-8"><title>the주택 2차 보완 성적표</title><style>body{font:15px/1.8 sans-serif;max-width:1200px;margin:32px auto;padding:20px}pre{white-space:pre-wrap;overflow-wrap:anywhere}</style><h1>the주택 2차 보완 성적표</h1><pre>'+escape(md)+'</pre></html>'
 save('round.json',r);(w/'report.md').write_text(md);(w/'report.html').write_text(html);save('official-scorecard.json',rubric)
 assert protected_before==protected(s),'보호 원장 변경'
 amend_round(s,ID,old['digest'],r,html,'담당자 대행',REASON)
 after={x['id']:x['digest'] for x in rounds(s)['items']}
 assert original.keys()==after.keys() and all(after[k]==v for k,v in original.items() if k!=ID)
 assert protected_before==protected(s)
 final=get_round(s,ID);receipt=dict(id=ID,score=final['result']['display_score'],official_score=round(oscore,2),digest=final['digest'],other_rounds_unchanged=True,protected_unchanged=True,source_ids=len(ids),projects=len(cohorts))
 save('published.json',receipt);print(json.dumps(receipt,ensure_ascii=False),flush=True)
if __name__=='__main__':main()
