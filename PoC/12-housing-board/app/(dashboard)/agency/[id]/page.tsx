import type { Metadata } from 'next';
import { notFound } from 'next/navigation';
import Crumbs from '../../../../components/Crumbs';
import ProjectTable from '../../../../components/policy/ProjectTable';
import { Lede, Page, PageTitle } from '../../../../components/page';
import { Badge } from '../../../../components/ui/badge';
import { Basis } from '../../../../components/ui';
import { agencies, agencyId, policyProjects } from '../../../../lib/home10/policy-907';

type Props = { params: Promise<{ id: string }> };
export const dynamicParams = false;
export const generateStaticParams = () => agencies.map((item) => ({ id: item.id }));
export async function generateMetadata({ params }: Props): Promise<Metadata> { const { id } = await params; return { title: `${agencies.find((item) => item.id === id)?.name ?? '기관'} · 9·7 후보` }; }
export default async function AgencyDetail({ params }: Props) {
  const { id } = await params;
  const agency = agencies.find((item) => item.id === id);
  if (!agency) notFound();
  const rows = policyProjects.filter((item) => agencyId(item) === id);
  return <Page>
    <Crumbs items={[{ label: '9·7 상황판', href: '/' }, { label: '기관별', href: '/agency' }, { label: agency.name }]} />
    <PageTitle>{agency.name} 9·7 후보 <Badge variant="warn">{rows.length}건</Badge></PageTitle>
    <Lede>{agency.fullName}의 공개 자료에서 온 사업후보입니다. 정책 귀속과 동일 사업 여부는 검토 상태입니다.</Lede>
    <ProjectTable rows={rows} label={`${agency.name} 9·7 후보`} />
    <Basis>기관별 행 수는 원천 후보 수입니다. 준공 실적이나 확정 사업 수가 아닙니다.</Basis>
  </Page>;
}
