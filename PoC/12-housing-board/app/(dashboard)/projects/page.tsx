import type { Metadata } from 'next';
import Link from 'next/link';
import Crumbs from '../../../components/Crumbs';
import ProjectTable from '../../../components/policy/ProjectTable';
import StageLadder from '../../../components/StageLadder';
import { Lede, Page, PageTitle } from '../../../components/page';
import { Badge } from '../../../components/ui/badge';
import { Basis } from '../../../components/ui';
import { home10 } from '../../../lib/home10/data';
import { policy, policyPrograms, policyProjects, policyStats, stageCounts } from '../../../lib/home10/policy-907';

export const metadata: Metadata = { title: '9·7 사업후보' };

export default function ProjectsPage() {
  return <Page>
    <Crumbs items={[{ label: '9·7 상황판', href: '/' }, { label: '사업후보' }]} />
    <PageTitle>9·7 정책 관련 사업후보 <Badge variant="warn">연결 검토 중</Badge></PageTitle>
    <Lede>PoC 10 공개 원천에서 가져온 서울·경기 후보 {policyStats.candidates}건입니다. 개별 사업의 9·7 정책 귀속은 아직 확정되지 않았습니다.</Lede>
    <div className="mb-4 flex flex-wrap gap-3 text-[15px]"><a href="/poc/housing-board/map?region=home-907">3D 지도에서 보기</a><Link href="/stage">단계별 보기</Link><Link href="/sources">원천 보기</Link></div>
    <p className="mb-3 text-[15px]">정책 발표 목표: {policy.targetUnits?.toLocaleString('ko-KR') ?? '미확인'}호 · 지표: {policy.metric ?? '미확인'} · 사업후보 위치점 연결 {policyStats.located}건 · 미연결 {policyStats.candidates - policyStats.located}건</p>
    <StageLadder className="mb-5" counts={stageCounts} />
    <p className="mb-2 text-[15px]">전체 {policyStats.candidates}건입니다. 아래 표에서 사업명·시군구를 검색하거나 페이지를 내려 모든 후보를 볼 수 있습니다. 위치가 연결된 행의 ‘지도에서 위치 보기’를 누르면 해당 점으로 이동합니다.</p>
    <ProjectTable rows={policyProjects} />
    <Basis>PoC 10 변환 {home10.readFinishedAt.slice(0, 10)}. 원본 ID와 결측값을 유지합니다. 계획 규모는 실제 공급량이 아니며, 동일 사업으로 확인되지 않은 원천 후보의 규모를 합산하지 않습니다. 정책 연결은 {policyStats.review}건 모두 검토 상태입니다.</Basis>
    <h2 className="mt-8 text-[22px]">9·7 연결 제안 프로그램</h2>
    <ul className="pl-5 text-[15px] leading-8">{policyPrograms.map((item) => <li key={item.id}>{item.name} · 연결 후보 {policyProjects.filter((project) => project.programId === item.id).length}건 · {item.status}</li>)}</ul>
  </Page>;
}
