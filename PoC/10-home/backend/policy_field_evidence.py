"""Field citations from the locally verified 9·7 original PDF, never invented page numbers."""
import re
from .policy_907_sources import PDF_URL

OBJECTIVE = '선호 입지에 내집 마련의 기회를 대폭 늘리고, 위축된 주택공급 여건을 개선하여 주택시장 안정 및 국민 주거안정 도모'
SHA256 = '6a72c5e14edcc3705043dfd58ac7aad2b0167fb343270d47ecd80522eeb0c5e6'


def extract_evidence(pages, sha256):
    """Called only at collection, not when opening the management screen."""
    result = dict(document_name='주택공급 확대방안.pdf', sha256=sha256, sections={})
    for i, raw in enumerate(pages):
        text = re.sub(r'\s+', ' ', raw).strip()
        printed = re.search(r'-\s*(\d+)\s*-', raw)
        page = int(printed[1]) if printed else None
        objective = re.search(r'선호\s*입지에.*?주거안정\s*도모', text)
        if objective:
            result['sections']['overview'] = dict(excerpt=objective[0], pdf_page=i+1, printed_page=page)
        goal = re.search(r'｢주택공급.*?착공\s*추진(?:\(.*?\))?', text)
        if goal and '135만호' in text:
            result['sections']['target_units'] = dict(excerpt=goal[0], pdf_page=i+1, printed_page=page)
        if '134.9' in text and '26.9' in text and '33.5' in text:
            result['sections']['table'] = dict(excerpt='수도권 공급 현황 및 계획(착공기준)', pdf_page=i+1, printed_page=page)
    return result


def evidence_for(plan, key, value):
    bundle = plan.get('field_evidence')
    if not bundle and plan.get('evidence_url') == PDF_URL and plan.get('base_date') == '2025-09-07':
        # This immutable source was verified against data/raw/policy_907_plan/<sha>.pdf.
        bundle = dict(document_name='주택공급 확대방안.pdf', sha256=SHA256, sections={
            'overview':dict(excerpt=OBJECTIVE, printed_page=4, pdf_page=7),
            'target_units':dict(excerpt='｢주택공급 확대방안｣을 통해 ’30년까지 수도권에서 매년 27만호, 총 135만호 규모의 신규주택 착공 추진(매년 11만호 순증)', printed_page=43, pdf_page=46),
            'table':dict(excerpt='수도권 공급 현황 및 계획(착공기준)', printed_page=43, pdf_page=46)})
    if not bundle or key == 'advice':
        return dict(excerpt=str(value) if value is not None else '해당 항목의 수집된 값이 없습니다.', excerpt_type='VALUE')
    sections = bundle.get('sections', {})
    metadata = dict(document_name=bundle['document_name'], document_sha256=bundle.get('sha256'))
    if key == 'overview' and sections.get('overview'):
        return dict(metadata, **sections['overview'], excerpt_type='QUOTE')
    if key == 'target_units' and sections.get('target_units'):
        return dict(metadata, **sections['target_units'], excerpt_type='QUOTE')
    if key == 'name':
        return dict(metadata, excerpt='주택공급 확대방안 · 2025.9.7.', pdf_page=1, printed_page=None, excerpt_type='QUOTE')
    table = sections.get('table', {})
    if key in ('period_start','period_end'):
        excerpt='수도권 공급 현황 및 계획(착공기준) · 향후 5년, ’26~’30. 관리 기간: 2026-01-01~2030-12-31.'
    elif key.startswith('region:'):
        region=key.split(':')[1]
        excerpt=f'수도권 공급 현황 및 계획(착공기준) · {region} 합계 {value:,}호.' if value is not None else f'원문 목표표에는 수도권·서울만 구분됩니다. {region} 개별 목표는 분리 공표되지 않았습니다.'
    elif key.startswith('annual:'):
        _, scope, year = key.split(':')
        excerpt=f'수도권 공급 현황 및 계획(착공기준) · {scope} {year}년 {value:,}호. 원문 표 단위 만호를 호로 환산.' if value is not None else f'{scope} {year}년 개별 목표 미확보. 원문 목표표의 개별 값이 없습니다.'
    else: excerpt=str(value) if value is not None else '수집된 값이 없습니다.'
    return dict(metadata, excerpt=excerpt, printed_page=table.get('printed_page'), pdf_page=table.get('pdf_page'), excerpt_type='TABLE_VALUE')
