import type { Metadata } from 'next';
import Link from 'next/link';
import Crumbs from '../../../components/Crumbs';
import { Lede, Page, PageTitle, PanelTitle } from '../../../components/page';
import { Badge } from '../../../components/ui/badge';
import { Card } from '../../../components/ui/card';
import { DataGrid } from '../../../components/ui/data-grid';
import { Basis } from '../../../components/ui';
import { home10 } from '../../../lib/home10/data';
import { completionYears, policy, policyMonitor, policyProjects, policySources, policyStats } from '../../../lib/home10/policy-907';

export const metadata: Metadata = { title: '9·7 자료 보고' };
export default function ReportsPage() {
  const goals = [
    { name: '발표 목표', value: policy.targetUnits?.toLocaleString('ko-KR') ?? '미확인', basis: policy.metric ?? '지표 미확인' },
    { name: '정책 연결 검토 후보', value: String(policyStats.candidates), basis: '사업→프로그램 연결 전부 REVIEW' },
    { name: '모집공고 검토 물량', value: policyMonitor.current_notice_units?.toLocaleString('ko-KR') ?? '미확인', basis: `${policyMonitor.current_notice_count ?? 0}건 · 정책 귀속 검토 · 준공 실적 아님` },
  ];
  return <Page>
    <Crumbs items={[{ label: '9·7 상황판', href: '/' }, { label: '보고자료' }]} />
    <PageTitle>9·7 정책 자료 보고 <Badge variant="warn">검토 자료</Badge></PageTitle>
    <Lede>PoC 10의 9·7 정책과 연결 제안된 공개 원천만 정리했습니다. 정책 발표 목표와 개별 후보의 예정·공고 물량은 범위와 측정 단계가 달라 달성률로 계산하지 않습니다.</Lede>
    <Card render={<section aria-label="9·7 핵심 수치" />}><PanelTitle>정책과 후보</PanelTitle>
      <DataGrid label="정책과 후보 지표" cols={[{ key: 'name', label: '항목', kind: 'text' }, { key: 'value', label: '원천값', kind: 'text' }, { key: 'basis', label: '해석', kind: 'text' }]}
        rows={goals.map((item) => ({ id: item.name, c: item }))} />
      <Basis>정책 발표일 {policy.announcedAt ?? '미확인'} · 발표 범위 {policy.targetScope ?? '미확인'}. PoC 10 데이터 변환 {home10.readFinishedAt.slice(0, 10)}. {policy.evidenceUrl ? <a href={policy.evidenceUrl} target="_blank" rel="noopener noreferrer">정책 원문</a> : null}</Basis>
    </Card>
    <Card render={<section aria-label="연도별 준공 예정일" />}><PanelTitle>후보별 준공 예정일 확보</PanelTitle>
      <DataGrid label="준공 예정 연도" cols={[{ key: 'year', label: '예정 연도', kind: 'text' }, { key: 'count', label: '후보 건수' }]}
        rows={completionYears.map((item) => ({ id: item.year, c: { year: item.year, count: item.count } }))} />
      <Basis>원천 사업 기록의 준공 예정일이 있는 {policyStats.completionDate}건만 셉니다. 미확보 {policyStats.candidates - policyStats.completionDate}건. 실제 준공·입주 확인 호수는 {policyStats.actualDelivery}건이므로 완료 물량은 표시하지 않습니다.</Basis>
    </Card>
    <Card render={<section aria-label="원천별 후보" />}><PanelTitle>원천별 후보 기록</PanelTitle>
      <DataGrid label="9·7 원천별 후보" cols={[{ key: 'name', label: '원천', kind: 'text' }, { key: 'count', label: '후보 행' }, { key: 'progress', label: '공정률 확인' }, { key: 'location', label: '위치점 연결' }]}
        rows={policySources.map((source) => { const rows = policyProjects.filter((item) => item.sourceId === source.id); return { id: source.id, c: { name: source.name, count: rows.length, progress: rows.filter((item) => item.progressPct !== null).length, location: rows.filter((item) => item.locationRole).length } }; })} />
      <Basis>원천마다 같은 사업을 별도 기록했을 수 있습니다. 행 수와 계획호수를 정책 실적으로 더하지 않습니다.</Basis>
    </Card>
    <p className="mt-5 text-[15px]">개별 근거는 <Link href="/projects">사업후보 목록</Link>, 수집 범위는 <Link href="/sources">원천 화면</Link>에서 확인합니다.</p>
  </Page>;
}
