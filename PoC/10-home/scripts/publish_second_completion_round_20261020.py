"""Append R02 using the existing 40-item rubric and reproducible measurements."""
from copy import deepcopy
from datetime import datetime, timezone
from html import escape
import hashlib,json
from pathlib import Path
from sqlalchemy import select
from backend.db import engine_for, IntegrityRound
from backend.service import HomeService
from backend.data_integrity import save_round

ID='HOME-INTEGRITY-R02-20261020'

def main():
    s=HomeService(engine_for());w=s.data_dir/'completion-20261020'
    with s.sessions() as db:
        parent=db.scalar(select(IntegrityRound).where(IntegrityRound.sequence==1).order_by(IntegrityRound.created_at.desc()))
        prior=deepcopy(parent.result);parent_id=parent.id
    v=json.loads((w/'final-validation.json').read_text())
    q=json.loads((w/'requirements-current.json').read_text())
    sources=json.loads((w/'sources-current.json').read_text())['items']
    r=deepcopy(prior)
    r['prior_reference_only']={k:r.pop(k) for k in ('metrics','evidence','source_snapshot_at','tests','technical_score_assessed_at','additional_collection_paths','replaced_rounds') if k in r}
    r['tests']={'runs':[{'suite':'loading/source statistics/cache/policy/evidence','passed':37},
        {'suite':'independent integrity/project collection/regional indicators/outlook','passed':63},
        {'suite':'light regional input equivalence and housing indicators','passed':26}],
        'note':'실행 묶음 간 중복이 있어 합산하지 않음. 고정 회귀검증 결과이며 전체 데이터 정확도가 아님.'}
    for key in ('api_collection_update','report_reproducibility','assessment_addendum','diagnostics','matching_corrections','notice_classification_update','management_connection_update','official_report_reviews'):
        r.pop(key,None)
    stamp=datetime.now(timezone.utc).isoformat()
    comments={
        'A3':'추가 API의 법정동·전체 페이지 검증과 실패 재시도를 확인. 일반 건축인허가 724/2,907개 이후 HTTP 429로 중단, 실패를 완료로 처리하지 않음.',
        'A4':'공식 고시·HWP 공모·사업자 선정 문서의 블록·면적·호수·일정을 대조. 원문 제어문자로 인한 통계 집계 실패를 원문 수정 없이 처리.',
        'B1':'정부 전체 착공 모집단의 개별 사업 명세는 미확보. 관리 원장과 공식 전체 총량을 동일 분모로 간주하지 않음.',
        'B2':'보완 API 4개 중 3개는 수도권 2,907개 법정동 전체 조회 완료. 일반 건축인허가 미조회 2,183개는 명시. 지역 사업 전수 확보 점수로 전환하지 않음.',
        'B4':'API별 조회 완료·미조회·원천 행 수를 고정하고 CSV로 보존. 조회 완료와 전수 사업 확보는 구분.',
        'C1':'블록 별칭 C1/B5·C4/B7·C5/B4를 면적·호수·용적률로 대조하고 근거 판본을 연결.',
        'C2':'미연결 14개 블록을 전건 재심사: 기존 중복 1개, 신규 정책 연결 4개 3,158호, 세부 귀속 유보 9개 6,296호.',
        'C4':'서울도봉01은 기존 성균관대 야구장과 같은 부지로 연결. 관리 묶음 기여 ID 215개 중복 0개.',
        'E1':'사업자 선정과 실제 착공을 구분. OBSERVED_BY 확인일은 최초 사건일로 전용하지 않도록 수정하고 회귀검증.',
        'E2':'검단 AA19의 국민임대 991호·영구임대 332호는 공식 구성표를 근거로 1,323호로 구분 합산. 같은 유형 정정공고는 중복 가산하지 않음.',
        'E3':'독립 사건 충돌 1건을 원문 구성표로 해결해 현재 미해결 충돌 0건. 모든 모집단의 무오류를 의미하지 않음.',
        'F1':'공식 원문 URL·첨부 URL·SHA-256 목록과 핵심 원문·추출 텍스트 ZIP을 제공.',
        'F3':'기존 보호 기록 3,033건의 전후 해시 동일, 승인 수동 일정 변경 0건. 새 연결은 사용자 위임에 따른 담당자 대행 판단으로 기록.',
        'F4':'독립 사건 기준본을 원천 판본·인지시각과 함께 동결. 확인시점과 최초 발생시점의 차이를 반영.',
        'H1':'반복 읽기 격리·캐시 무효화·계획/실적·공급 구획·수집 통계 관련 회귀검증 수행. 테스트 성공률은 데이터 정확도가 아님.',
        'H2':'HTTP 429·503 재시도 및 기존 정상본 유지 확인. 요청 제한으로 멈춘 수집 범위는 그대로 공개.',
        'H3':'이번 보완을 MD 보고서·원문 ZIP·검증 JSON·새 성적표 회차에 연결. 종전 회차는 덮어쓰지 않음.',
        'J1':'현재 누적 착공 76,936호와 연말 계획 92,479호를 구분. 1~8월 전체 착공 86,739호와 직접 뺄셈해 누락으로 판정하지 않음.',
        'J3':'수집 현황·정책 연결·공식 격차의 기준본과 CSV·해시·검증 결과를 공유용으로 고정.',
        'J4':'1차 성적표를 부모로 참조하는 2차 성적표를 별도 발행. 공식 총량과 일치한다는 가정을 사용하지 않음.'}
    mapping={'D1':'F-03','D2':'F-02','D3':'F-05','D4':'F-06','I3':'F-08'}
    for cat in r['categories']:
        for item in cat['items']:
            key=item['id'];item['previous_score']=item['score'];item['previous_reason']=item['reason']
            comment=comments.get(key,'이번 범위에서 기존 등급을 변경할 신규 정량 근거가 없어 이전 평가를 유지. '+item.get('next_step',''))
            if key in ('A1','A2'):
                count=sum(x['status']=='SUCCESS' for x in sources) if key=='A1' else sum(not x.get('manual_only',False) for x in sources)
                total=len(sources);item.update(numerator=count,denominator=total,fraction=count/total)
                comment=f'같은 정의로 현재 비율 재산정: {count}/{total}. 최근 상태/자동 대상 비율이며 장기 성공률·전체 수집률이 아님.'
            elif key in mapping:
                m=q['metrics'][mapping[key]]['without_estimates'];item.update(numerator=m['count'],denominator=m['total'],fraction=m['count']/m['total'] if m['total'] else 0)
                comment=f"같은 기존 지표 정의로 재산정: {m['count']}/{m['total']}. {m['note']} 관리 대상 증가로 분모가 달라졌으며 점수 하락이 기존 승인값 오류를 뜻하지 않음."
            item['score']=item['weight']*item['fraction'];item['score_delta']=item['score']-item['previous_score'];item['change_comment']=comment;item['reason']=comment
        cat['score']=sum(i['score'] for i in cat['items'])
    total=sum(c['score'] for c in r['categories'])
    r.update(title='2차 보완 성적표 · 수집 범위·정책 연결·공식 발표 대조',round_id=ID,parent_id=parent_id,sequence=2,
        as_of_date='2026-10-20',assessed_at=stamp,generated_at=stamp,previous_total_score=prior['total_score'],
        comparison_base_label='1차 보완',total_score=total,display_score=round(total,1),
        actor='담당자 대행',reason='잔여 수집·정책 연결·중복 및 공식 발표 대조 검증',
        snapshot_id=v['independent_snapshot_id'],independent_snapshot_counts=v['independent_counts'],
        classification_note='4대 지표는 이전 고정 표본의 보존 결과이며, 이번 추가 사업 전체의 재평가 결과나 플랫폼 전체 정확도가 아닙니다.',
        agreement_note='기존 53개 주장 대조의 보존값. 이번 회차에서 전체 정부 통계 일치율로 재평가하지 않았습니다.',
        completion_review=v,report_markdown=(w/'final-report.md').read_text(),score_scope='기존 40개 항목 기술·데이터 구축 준비도. 데이터 정확도나 공식 총량 일치율이 아님.')
    for group in r['groups']:
        group['score']=sum(c['score'] for c in r['categories'] if c['group']==group['id']);group['percent']=group['score']/group['weight']*100
    r['round_evidence']={name:dict(path='data/completion-20261020/'+name,sha256=hashlib.sha256((w/name).read_bytes()).hexdigest()) for name in ['final-validation.json','independent-verification.json','requirements-current.json','sources-current.json','final-report.md']}
    esc=lambda x:escape(str(x))
    rows=''.join('<tr><td>'+esc(i['id']+' '+i['name'])+'</td><td>'+f"{i['previous_score']:.2f} → {i['score']:.2f} / {i['weight']}"+'</td><td>'+esc(i['change_comment'])+'</td></tr>' for c in r['categories'] for i in c['items'])
    html='<!doctype html><html lang="ko"><meta charset="utf-8"><title>2차 보완 성적표</title><style>body{font:15px/1.7 sans-serif;max-width:1100px;margin:40px auto;color:#18394c}table{border-collapse:collapse;width:100%}th,td{border:1px solid #cbd5df;padding:12px;text-align:left;vertical-align:top}th{background:#eef4f8}@media print{body{margin:0}thead{display:table-header-group}tr{break-inside:avoid}}</style><h1>2차 보완 성적표</h1><p>'+esc(stamp)+' · 담당자 대행</p><h2>'+f"{prior['display_score']:.1f} → {r['display_score']:.1f} / 100점"+'</h2><p>기존 40개 항목과 배점을 유지했습니다. 정량 항목은 현재 분모로 재계산하고, 새 검증 근거가 없는 등급 항목은 유지했습니다. 이 점수는 기술·데이터 구축 준비도이며 전체 데이터 정확도가 아닙니다.</p><p>4개 사업 3,158호 추가 연결 · 착공 누적 76,936호 · 연말 계획 92,479호 · 보호 기록 3,033건 변경 0건 · 중복 기여 ID 0건 · 독립 집계 미해결 충돌 0건.</p><p>보완 API 4개 중 3개 전체 조회. 일반 건축인허가 2,183개 법정동 미조회, 정책 세부 귀속 9개 사업 6,296호 유보. 전체 전수 수집·정부 총량 일치로 해석하지 않습니다.</p><table><thead><tr><th>평가 항목</th><th>1차 → 2차 / 배점</th><th>근거 및 남은 범위</th></tr></thead><tbody>'+rows+'</tbody></table></html>'
    folder=w/'scorecard';folder.mkdir(exist_ok=True)
    (folder/'round.json').write_text(json.dumps(r,ensure_ascii=False,indent=2));(folder/'report.html').write_text(html)
    identity=save_round(s,ID,2,r,html,r['actor'],r['reason'],snapshot_id=r['snapshot_id'],parent_id=parent_id)
    print(json.dumps(dict(id=identity,previous=prior['display_score'],current=r['display_score'],items=40),ensure_ascii=False))

if __name__=='__main__':main()
