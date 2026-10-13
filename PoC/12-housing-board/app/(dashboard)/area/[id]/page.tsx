import type { Metadata } from 'next';
import { notFound } from 'next/navigation';
import Crumbs from '../../../../components/Crumbs';
import ProjectTable from '../../../../components/policy/ProjectTable';
import { Lede, Page, PageTitle } from '../../../../components/page';
import { Badge } from '../../../../components/ui/badge';
import { Basis } from '../../../../components/ui';
import { located, policyProjects, regions } from '../../../../lib/home10/policy-907';

type Props = { params: Promise<{ id: string }> };
export const dynamicParams = false;
export const generateStaticParams = () => regions.map((item) => ({ id: item.id }));
export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { id } = await params;
  return { title: `${regions.find((item) => item.id === id)?.name ?? '지역'} · 9·7 후보` };
}
export default async function AreaDetail({ params }: Props) {
  const { id } = await params;
  const region = regions.find((item) => item.id === id);
  if (!region) notFound();
  const rows = policyProjects.filter((item) => item.region === region.name);
  return <Page>
    <Crumbs items={[{ label: '9·7 상황판', href: '/' }, { label: '지역별', href: '/area' }, { label: region.name }]} />
    <PageTitle>{region.name} 9·7 사업후보 <Badge variant="warn">검토 중</Badge></PageTitle>
    <Lede>원천 후보 {rows.length}건 · LH 블록 라벨점 연결 {rows.filter(located).length}건 · 위치점 미연결 {rows.length - rows.filter(located).length}건.</Lede>
    <p className="mb-4 text-[15px]"><a href={`/poc/housing-board/map?region=${region.map}`}>3D 지도에서 보기</a></p>
    <ProjectTable rows={rows} label={`${region.name} 9·7 사업후보`} />
    <Basis>정책 귀속과 LH 위치점 연결은 검토 중입니다. 시군구가 비어 있는 후보는 해당 시도 목록에 남기고 지도 위치점은 만들지 않았습니다.</Basis>
  </Page>;
}
