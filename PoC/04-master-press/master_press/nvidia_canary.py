"""Synthetic case-batch evaluation; never reads or writes the operational DB.

All articles and case definitions below are invented evaluation fixtures.
Only these fixtures and the existing public application prompt go to the provider.
"""
from __future__ import annotations
import argparse
from collections import Counter
import json
from pathlib import Path
import time
from .config import Settings
from .scoring import RelevanceEngine


def fixtures(batch_size=5):
    definitions = [
        ('digital', '디지털 행정', '행정안전부가 핵심 주체인 디지털 행정 서비스 도입 또는 개선 정책을 찾습니다.', ['디지털', '행정']),
        ('finance', '지방재정', '행정안전부가 핵심 주체인 지방재정 또는 지방교부세 정책을 찾습니다.', ['지방재정', '지방교부세']),
        ('disaster', '재난안전', '행정안전부가 핵심 주체인 재난안전 대책이나 재난 대응 활동을 찾습니다.', ['재난', '안전']),
        ('criticism', '기관 직접 비판', '행정안전부의 정책이나 행정에 대한 직접적인 비판과 책임 추궁 보도를 찾습니다. 단순 운영 사실은 제외합니다.', ['행정안전부', '비판']),
        ('personnel', '공무원 교육', '행정안전부가 핵심 주체인 공무원 교육 및 인재 양성 정책을 찾습니다.', ['공무원', '교육']),
    ]
    if batch_size == 10:
        definitions.extend([
            ('privacy', '개인정보 보호', '행정안전부가 핵심 주체인 개인정보 보호 정책과 개인정보 유출 예방 대책을 찾습니다.', ['개인정보', '보호']),
            ('registry', '주민등록 제도', '행정안전부가 핵심 주체인 주민등록 주소 변경 및 전입신고 제도 개선을 찾습니다.', ['주민등록', '전입신고']),
            ('population', '지방소멸 대응', '행정안전부가 핵심 주체인 지방소멸 및 지역 인구 감소 대응 정책을 찾습니다.', ['지방소멸', '인구']),
            ('election', '지방선거 지원', '행정안전부가 핵심 주체인 지방선거 행정 지원과 공정한 선거 관리를 찾습니다.', ['지방선거', '선거']),
            ('fire', '화재 예방', '행정안전부가 핵심 주체인 화재 예방과 소방 안전 대책을 찾습니다.', ['화재', '소방']),
        ])
    cases = [dict(id=key, name=name, topic_description=prompt, topic_search_prompt=prompt,
                  include_terms=terms, required_terms=[], exclude_terms=[], synonym_terms={},
                  organization_terms=['행정안전부','행안부'], relevance_threshold=70,
                  keyword_weight=0, semantic_weight=0, llm_weight=1,
                  _semantic_raw=0, _semantic_score=0) for key,name,prompt,terms in definitions]
    rows = [
        ('디지털 민원 서비스 개편', '행정안전부는 디지털 행정 서비스 개선 계획을 발표했다. 온라인 민원 신청 절차를 줄이고 모바일 신분증을 활용해 주민의 방문 부담을 낮추기로 했다.', ['digital'], '사실전달'),
        ('지방교부세 배분 기준 개편', '행정안전부는 지방재정 확충을 위해 지방교부세 배분 기준을 개편했다. 재정 여건이 열악한 지방자치단체에 지원을 늘리는 것이 핵심이다.', ['finance'], '사실전달'),
        ('호우 대응 점검회의', '행정안전부는 집중호우에 대비한 재난안전 점검회의를 개최했다. 행정안전부는 침수 위험 지역을 점검하고 주민 대피 계획을 확인했다.', ['disaster'], '사실전달'),
        ('교육과정 확대', '행정안전부는 지방공무원의 역량 강화를 위한 공무원 교육 계획을 발표했다. 신규 공무원 교육과 관리자의 인재 양성 과정을 확대한다.', ['personnel'], '사실전달'),
        ('디지털 민원 장애에 책임 추궁', '국회는 행정안전부의 디지털 행정 서비스 관리 부실을 비판했다. 온라인 민원 시스템 장애가 반복되는데도 행정안전부가 개선을 미뤄 주민 피해가 커졌다는 지적이다.', ['digital','criticism'], '부정적'),
        ('교부세 배분 기준 비판', '지방자치단체들은 행정안전부의 지방교부세 배분 기준이 불공정하다고 비판했다. 행정안전부가 지역의 지방재정 현실을 외면했다며 시정을 요구했다.', ['finance','criticism'], '부정적'),
        ('재난 대응 지연 논란', '국회는 행정안전부가 재난 대응 지휘를 지연해 피해를 키웠다고 비판했다. 행정안전부의 재난안전 보고 체계가 제대로 작동하지 않은 책임을 물었다.', ['disaster','criticism'], '부정적'),
        ('행안부 모바일 민원 확대', '행안부는 디지털 행정 서비스를 확대한다. 행안부는 주민이 모바일로 민원을 신청할 수 있도록 디지털 민원 플랫폼을 개선했다고 밝혔다.', ['digital'], '사실전달'),
        ('민간 게임 회사 신규 서비스', '가상게임사는 디지털 게임 서비스를 출시했다. 민간 게임 이용자를 위한 새 상품으로 정부의 행정 서비스와는 관계가 없다.', [], '사실전달'),
        ('교육부 학교 수업 지원', '교육부는 학교 교사의 수업 역량을 높이는 연수 계획을 발표했다. 대상은 초등학교 교사이며 교육부가 직접 운영한다.', [], '사실전달'),
        ('시청 예산 부실 비판, 행안부는 배경 설명', '가상시의회는 가상시청의 축제 예산 낭비를 비판했다. 비판 대상은 가상시청이다. 행정안전부는 전국 지방재정 통계를 제공하는 기관으로 배경에만 언급됐다.', [], '부정적'),
        ('가상시 공무원 교육', '가상시청은 자체 공무원 교육 과정을 열었다. 가상시청 인사과가 교육 계획과 예산을 전담한다. 행정안전부 관계자는 참석자 명단에만 포함됐다.', [], '사실전달'),
    ]
    if batch_size == 10:
        rows.extend([
            ('개인정보 보호 강화', '행정안전부는 공공기관 개인정보 보호 계획을 발표했다. 개인정보 유출 예방을 위해 문서 접근 권한과 보관 절차를 점검한다.', ['privacy'], '사실전달'),
            ('전입신고 제도 개선', '행정안전부는 주민등록 주소 변경과 전입신고 제도 개선안을 발표했다. 서류 제출 절차를 간소화하고 주민센터의 전입신고 접수 방식을 통일한다.', ['registry'], '사실전달'),
            ('인구 감소 지역 지원', '행정안전부는 지방소멸 및 인구 감소 대응 계획을 발표했다. 지역의 정주 여건을 개선하고 청년의 지역 정착을 지원한다.', ['population'], '사실전달'),
            ('공정한 지방선거 지원', '행정안전부는 공정한 지방선거를 위한 행정 지원 계획을 발표했다. 지방선거의 선거인명부 작성과 투표소 접근 편의 지원이 핵심이다.', ['election'], '사실전달'),
            ('화재 예방 대책', '행정안전부는 재난안전 정책의 일환으로 화재 예방과 소방 안전 대책을 발표했다. 화재 위험 시설을 점검하고 소방 대응 체계를 강화한다.', ['disaster','fire'], '사실전달'),
            ('통합 정책 점검과 비판', '행정안전부는 디지털 행정 서비스 개선, 지방재정 확충과 지방교부세 배분, 재난안전 대책, 공무원 교육 계획을 함께 발표했다. 행정안전부는 개인정보 보호 및 유출 예방, 주민등록 주소 변경과 전입신고 절차 개선도 추진한다. 행정안전부는 지방소멸과 인구 감소 대응, 공정한 지방선거 행정 지원, 화재 예방과 소방 안전 대책도 주요 과제로 제시했다. 국회는 행정안전부가 이들 정책의 집행을 미뤄 주민 피해를 키웠다고 직접 비판하고 행정안전부에 시정을 요구했다.', [case['id'] for case in cases], '부정적'),
        ])
    return cases, rows


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--provider', default='nvidia', choices=['nvidia','openai'])
    parser.add_argument('--model', default='nvidia/nemotron-3-super-120b-a12b')
    parser.add_argument('--batch-size', type=int, choices=[5,10], default=5)
    parser.add_argument('--output', type=Path, required=True)
    args=parser.parse_args()
    engine=RelevanceEngine(Settings.from_env())  # No Store, service, or DB access.
    cases,rows=fixtures(args.batch_size)
    report={'model':args.model,'provider':args.provider,'dataset':f'{len(rows)} invented articles x {len(cases)} invented cases; no operational data', 'batches':[]}
    matrix=Counter()
    for i,(title,body,positive,tone) in enumerate(rows):
        article={'id':f'synthetic-{i}', 'title':title,'snippet':body,'body':body}
        common={'summary':body,'tone':tone,'article_type':'정책','evidence':[body]}
        entry={'article':article,'positive':positive,'results':{},'error':''}
        start=time.monotonic()
        try:
            results=engine.evaluate_cases_with_common_provider(args.provider,cases,article,common,args.model)
            first=next(iter(results.values()), {}).get('analysis_report', {})
            entry['raw_response']=first.get('raw_response', '')
            raw_ids=[item.get('case_id') for item in json.loads(entry['raw_response']).get('results', [])]
            entry['exact_case_ids']=sorted(raw_ids)==sorted(case['id'] for case in cases)
            entry['results']={key: {field:value.get(field) for field in
                ('decision','llm_score','evidence_status','reasons')} for key,value in results.items()}
        except Exception as error:
            entry['error']=f'{type(error).__name__}: {str(error)[:500]}'
        entry['seconds']=round(time.monotonic()-start,3)
        for case in cases:
            expected='send' if case['id'] in positive else 'low'
            actual=entry['results'].get(case['id'],{}).get('decision','missing')
            matrix[f'{expected}->{actual}']+=1
        report['batches'].append(entry)
        args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2))
        print(json.dumps({'batch':i+1,'returned':len(entry['results']),'seconds':entry['seconds'],'error':entry['error']},ensure_ascii=False),flush=True)
        time.sleep(2)
    report['summary']={'batches':len(rows),'cases':len(rows)*len(cases),
        'complete_batches':sum(len(b['results'])==len(cases) and b.get('exact_case_ids',False) and not b['error'] for b in report['batches']),
        'decision_matrix':dict(matrix),'accuracy':(matrix['send->send']+matrix['low->low'])/(len(rows)*len(cases)),
        'unverified_sends':sum(r['decision']=='send' and r['evidence_status']!='verified' for b in report['batches'] for r in b['results'].values()),
        'average_seconds':sum(b['seconds'] for b in report['batches'])/len(rows)}
    args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print(json.dumps(report['summary'],ensure_ascii=False),flush=True)

if __name__=='__main__':
    main()
