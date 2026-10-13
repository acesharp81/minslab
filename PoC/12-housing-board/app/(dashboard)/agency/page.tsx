import type { Metadata } from 'next';
import Link from 'next/link';
import Crumbs from '../../../components/Crumbs';
import { Lede, Page, PageTitle, cardsGrid } from '../../../components/page';
import { Badge } from '../../../components/ui/badge';
import { cardVariants } from '../../../components/ui/card';
import { DataGrid } from '../../../components/ui/data-grid';
import { Basis } from '../../../components/ui';
import { agencies, agencyId, policyProjects, policySources } from '../../../lib/home10/policy-907';

export const metadata: Metadata = { title: '9·7 기관별 원천' };
export default function AgencyPage() { return <Page>
  <Crumbs items={[{ label: '9·7 상황판', href: '/' }, { label: '기관별' }]} />
  <PageTitle>9·7 기관별 원천 <Badge variant="warn">후보 자료</Badge></PageTitle>
  <Lede>LH·GH·SH 공개 원천에서 수집한 후보 행을 기관별로 구분합니다. 같은 사업이 여러 원천에 있을 수 있어 기관별 호수는 합산하지 않습니다.</Lede>
  <div className={`${cardsGrid} mt-3`}>{agencies.map((agency) => <Link key={agency.id} className={cardVariants({ variant: 'link' })} href={`/agency/${agency.id}`}><b>{agency.name}</b><span>후보 {policyProjects.filter((item) => agencyId(item) === agency.id).length}건</span></Link>)}</div>
  <h2 className="mt-7 text-[22px]">사용한 원천</h2>
  <DataGrid label="기관별 원천" cols={[{ key: 'name', label: '원천', kind: 'text' }, { key: 'org', label: '기관', kind: 'text' }, { key: 'count', label: '9·7 후보 행' }, { key: 'type', label: '자료 유형', kind: 'text' }]}
    rows={policySources.map((source) => ({ id: source.id, c: { name: source.name, org: source.org ?? '미확인', count: policyProjects.filter((item) => item.sourceId === source.id).length, type: source.type ?? '미확인' } }))} />
  <Basis>원천에 실제로 기록된 공정률은 각 사업 상세에서 볼 수 있습니다. 기관별 정상·주의·지연 판정은 비교 가능한 일정 이력이 없어 제공하지 않습니다.</Basis>
</Page>; }
