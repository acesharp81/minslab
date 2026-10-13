import type { Metadata } from 'next';
import { notFound } from 'next/navigation';
import Crumbs from '../../../../components/Crumbs';
import ProjectTable from '../../../../components/policy/ProjectTable';
import StageLadder from '../../../../components/StageLadder';
import { Lede, Page, PageTitle } from '../../../../components/page';
import { Badge } from '../../../../components/ui/badge';
import { Basis } from '../../../../components/ui';
import { STAGES } from '../../../../lib/board/stages';
import { policyProjects, stageCounts } from '../../../../lib/home10/policy-907';

type Props = { params: Promise<{ id: string }> };
export const dynamicParams = false;
export const generateStaticParams = () => STAGES.map((stage) => ({ id: stage.code }));
export async function generateMetadata({ params }: Props): Promise<Metadata> { const { id } = await params; return { title: `${id} 단계 · 9·7 후보` }; }
export default async function StageDetail({ params }: Props) {
  const { id } = await params;
  const stage = STAGES.find((item) => item.code === id);
  if (!stage) notFound();
  const rows = policyProjects.filter((item) => item.stageCode === id);
  return <Page>
    <Crumbs items={[{ label: '9·7 상황판', href: '/' }, { label: '단계별', href: '/stage' }, { label: `${id} ${stage.name}` }]} />
    <PageTitle>{id} {stage.name} <Badge variant="warn">{rows.length}건 후보</Badge></PageTitle>
    <Lede>9·7 정책 관련 원천 후보 중 이 탐색 단계에 해당하는 자료입니다. 정책 귀속과 개별 사업 상태는 검토 중입니다.</Lede>
    <StageLadder className="mb-5" current={id} counts={stageCounts} />
    {rows.length ? <ProjectTable rows={rows} label={`${stage.name} 사업후보`} /> : <p className="rounded-[10px] border border-border bg-card p-4">PoC 10 원천에서 이 단계로 확인된 9·7 후보가 없습니다. 0건을 임의로 실적으로 대체하지 않습니다.</p>}
    <Basis>실제 준공·입주 호수는 미확보입니다. 단계별 지연률과 달성률은 산출하지 않습니다.</Basis>
  </Page>;
}
