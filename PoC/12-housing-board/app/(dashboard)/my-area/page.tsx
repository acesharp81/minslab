import type { Metadata } from 'next';
import Link from 'next/link';
import Crumbs from '../../../components/Crumbs';
import { Lede, Page, PageTitle, cardsGrid } from '../../../components/page';
import { Badge } from '../../../components/ui/badge';
import { cardVariants } from '../../../components/ui/card';
import { Basis } from '../../../components/ui';
import { located, policyProjects, regions } from '../../../lib/home10/policy-907';

export const metadata: Metadata = { title: '우리 동네 · 9·7' };
export default function MyAreaPage() { return <Page>
  <Crumbs items={[{ label: '9·7 상황판', href: '/' }, { label: '우리 동네' }]} />
  <PageTitle>우리 동네 9·7 후보 <Badge variant="warn">검토 자료</Badge></PageTitle>
  <Lede>PoC 10 원천에서 지역이 확인된 후보를 서울·경기에서 찾을 수 있습니다. 확인되지 않은 입주 예정이나 청약 자격은 표시하지 않습니다.</Lede>
  <div className={`${cardsGrid} mt-3`}>{regions.map((region) => { const rows = policyProjects.filter((item) => item.region === region.name); return <Link key={region.id} className={cardVariants({ variant: 'link' })} href={`/my-area/${region.id}`}><b>{region.name}</b><span>후보 {rows.length}건 · 위치점 연결 {rows.filter(located).length}건</span></Link>; })}</div>
  <Basis>정책 연결과 개별 사업 위치는 검토 상태입니다. 이 목록은 실제 입주 가능 단지 목록이 아닙니다.</Basis>
</Page>; }
