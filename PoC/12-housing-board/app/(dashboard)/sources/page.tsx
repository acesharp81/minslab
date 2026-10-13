import type { Metadata } from 'next';
import Crumbs from '../../../components/Crumbs';
import { Lede, Page, PageTitle, PanelTitle } from '../../../components/page';
import { Badge } from '../../../components/ui/badge';
import { Card } from '../../../components/ui/card';
import { DataGrid } from '../../../components/ui/data-grid';
import { Basis } from '../../../components/ui';
import { home10 } from '../../../lib/home10/data';
import { policy, policyCoverage, policyProjects, policySources } from '../../../lib/home10/policy-907';

export const metadata: Metadata = { title: '9·7 데이터 원천' };
export default function SourcesPage() { return <Page>
  <Crumbs items={[{ label: '9·7 상황판', href: '/' }, { label: '데이터 원본' }]} />
  <PageTitle>9·7 데이터 원본 <Badge variant="ok">PoC 10 공개 원천</Badge></PageTitle>
  <Lede>현재 9·7 연결 검토 후보에 실제 사용된 원천 {policySources.length}종만 표시합니다. 수집 성공은 조회 조건의 응답을 확보했다는 뜻이며 정책 귀속 승인이나 모집단 완결을 뜻하지 않습니다.</Lede>
  <Card render={<section id="home10-sources" aria-label="9·7 사업후보 원천" />}><PanelTitle>사업후보 원천</PanelTitle>
    <DataGrid label="9·7 후보 원천" cols={[{ key: 'name', label: '원천', kind: 'text' }, { key: 'org', label: '제공 기관', kind: 'text' }, { key: 'count', label: '9·7 후보 행' }, { key: 'status', label: '수집 상태', kind: 'text' }, { key: 'last', label: '마지막 수집', kind: 'text' }]}
      rows={policySources.map((source) => ({ id: source.id, c: { name: source.url ? { text: source.name, href: source.url } : source.name, org: source.org ?? '미확인', count: policyProjects.filter((item) => item.sourceId === source.id).length, status: source.status ?? '미확인', last: source.lastSuccess?.slice(0, 10) ?? { na: '미확인' } } }))} />
    <Basis>정책 원문: {policy.evidenceUrl ? <a href={policy.evidenceUrl} target="_blank" rel="noopener noreferrer">9·7 주택공급 확대방안</a> : '원문 미확보'} · PoC 10 변환 {home10.readFinishedAt.slice(0, 10)}. 각 후보 상세에서 원문 링크와 기준일을 볼 수 있습니다.</Basis>
  </Card>
  <Card render={<section aria-label="수집 범위" />}><PanelTitle>원천 조회 범위</PanelTitle>
    {policyCoverage.length ? <DataGrid label="9·7 관련 원천 조회 범위" maxHeight={500} cols={[{ key: 'source', label: '원천 ID', kind: 'text' }, { key: 'region', label: '조회 지역', kind: 'text' }, { key: 'period', label: '기간', kind: 'text' }, { key: 'fetched', label: '가져온 행' }, { key: 'population', label: '모집단 상태', kind: 'text' }]}
      rows={policyCoverage.map((item, index) => ({ id: `${item.sourceId}-${index}`, c: { source: item.sourceId ?? '미확인', region: item.region ?? '미확인', period: item.sourcePeriod ?? { na: '미확인' }, fetched: item.fetchedCount ?? { na: '미확인' }, population: item.populationStatus ?? { na: '미확인' } } }))} />
      : <p>이번 6종 원천과 직접 연결된 조회 범위 기록은 PoC 10에 없습니다. 수집 성공 상태만으로 전체 사업을 빠짐없이 확보했다고 판정하지 않습니다.</p>}
    <Basis>인천 9·7 후보가 없는 상태에서 서울·경기 후보만 표시합니다. 좌표는 LH 블록 이름이 유일하게 맞는 경우의 탐색용 라벨점입니다.</Basis>
  </Card>
</Page>; }
