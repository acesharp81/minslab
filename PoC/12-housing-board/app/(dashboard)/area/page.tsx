import type { Metadata } from 'next';
import Link from 'next/link';
import Crumbs from '../../../components/Crumbs';
import { Lede, Page, PageTitle, cardsGrid } from '../../../components/page';
import { Badge } from '../../../components/ui/badge';
import { cardVariants } from '../../../components/ui/card';
import { DataGrid } from '../../../components/ui/data-grid';
import { Basis } from '../../../components/ui';
import { located, policyProjects, regions } from '../../../lib/home10/policy-907';

export const metadata: Metadata = { title: '9·7 지역별 후보' };

export default function AreaPage() {
  const names = [...new Set(policyProjects.map((item) => `${item.region}|${item.municipality ?? ''}`))].sort();
  return <Page>
    <Crumbs items={[{ label: '9·7 상황판', href: '/' }, { label: '지역별' }]} />
    <PageTitle>9·7 지역별 후보 <Badge variant="warn">정책 연결 검토 중</Badge></PageTitle>
    <Lede>PoC 10에서 확인한 서울·경기 사업후보만 표시합니다. 9·7 발표 목표의 수도권 범위에는 인천도 포함되지만 이 후보 자료에는 인천 사업이 없습니다.</Lede>
    <div className={`${cardsGrid} mt-3`}>{regions.map((region) => {
      const rows = policyProjects.filter((item) => item.region === region.name);
      return <Link key={region.id} className={cardVariants({ variant: 'link' })} href={`/area/${region.id}`}><b>{region.name}</b><span>후보 {rows.length}건 · 위치점 연결 {rows.filter(located).length}건</span></Link>;
    })}</div>
    <h2 className="mt-7 text-[22px]">원천 시군구별 후보</h2>
    <DataGrid label="9·7 시군구 후보" cols={[{ key: 'place', label: '시도 · 시군구', kind: 'text' }, { key: 'count', label: '후보 건수' }, { key: 'located', label: '위치점 연결' }]}
      rows={names.map((key) => { const [region, municipality] = key.split('|'); const rows = policyProjects.filter((item) => item.region === region && (item.municipality ?? '') === municipality); return { id: key, c: { place: { text: `${region} · ${municipality || '미확보'}`, href: `/area/${region === '서울특별시' ? '11' : '41'}` }, count: rows.length, located: rows.filter(located).length } }; })} />
    <Basis>시군구 이름은 PoC 10 원천값을 유지했습니다. 미확보 후보 12건은 임의 지역으로 배치하지 않았습니다.</Basis>
  </Page>;
}
