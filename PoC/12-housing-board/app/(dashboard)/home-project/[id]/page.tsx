import type { Metadata } from 'next';
import { notFound } from 'next/navigation';
import Link from 'next/link';
import Crumbs from '../../../../components/Crumbs';
import StageLadder from '../../../../components/StageLadder';
import { Dl, Lede, Page, PageTitle, PanelTitle } from '../../../../components/page';
import { Badge } from '../../../../components/ui/badge';
import { Card } from '../../../../components/ui/card';
import { Basis } from '../../../../components/ui';
import { home10 } from '../../../../lib/home10/data';
import { policy, policyProjectById, policyProjects } from '../../../../lib/home10/policy-907';
import { stageName } from '../../../../lib/board/stages';

type Props = { params: Promise<{ id: string }> };
export const dynamicParams = false;
export const generateStaticParams = () => policyProjects.map((project) => ({ id: project.id }));

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { id } = await params;
  return { title: `${policyProjectById.get(id)?.name ?? id} · HOME 자료` };
}

const show = (value: string | number | null | undefined) => value === null || value === undefined || value === '' ? '미확보' : String(value);
const units = (value: number | null | undefined) => value === null || value === undefined ? '미확보' : `${value.toLocaleString('ko-KR')}호`;

export default async function HomeProjectPage({ params }: Props) {
  const { id } = await params;
  const p = policyProjectById.get(id);
  if (!p) notFound();
  return (
    <Page>
      <Crumbs items={[{ label: '종합상황판', href: '/' }, { label: '9·7 사업후보', href: '/projects' }, { label: p.name }]} />
      <PageTitle>{p.name} <Badge variant="warn">PoC 10 검토 후보</Badge></PageTitle>
      <Lede>{p.region} · {p.municipality ?? '시군구 미확보'} · {p.district && p.block ? `${p.district} ${p.block}` : '지구·블록 미확보'} · <code>{p.id}</code></Lede>
      {p.stageCode ? <StageLadder current={p.stageCode} /> : <p>PoC 12 단계로 옮길 원천 상태가 확인되지 않았습니다.</p>}
      <p className="mt-3 text-[15px] text-muted-foreground">원천 상태: {show(p.stageLabel)}{p.stageCode ? ` · 탐색 단계 ${p.stageCode} ${stageName(p.stageCode)}` : ''}. 단계 변환은 화면 탐색용이며 공식 사업 상태 승인으로 간주하지 않습니다.</p>

      <Card render={<section aria-label="HOME 사업후보 자료" />}>
        <PanelTitle>사업후보 자료</PanelTitle>
        <Dl>
          <dt>계획호수</dt><dd>{units(p.plannedUnits)} · {show(p.unitBasis)}</dd>
          <dt>공급계획호수</dt><dd>{units(p.supplyUnits)} <span className="text-muted-foreground">(실제 공급·입주 실적이 아님)</span></dd>
          <dt>원천 공정률</dt><dd>{p.progressPct === null ? '미확보' : `${p.progressPct}%`}{p.progressDate ? ` · 측정일 ${p.progressDate}` : ' · 측정일 미확보 또는 별도 확인 필요'}{p.progressEvidenceUrl ? <> · <a href={p.progressEvidenceUrl} target="_blank" rel="noopener noreferrer">공정 근거</a></> : null}</dd>
          <dt>일정</dt><dd>{show(p.scheduleMonth)} · {show(p.scheduleBasis)}</dd>
          <dt>공사 시작 실적일</dt><dd>{show(p.startActualDate)}</dd>
          <dt>준공 예정일</dt><dd>{show(p.completionPlanDate)} <span className="text-muted-foreground">(실제 준공·입주일이 아님)</span></dd>
          <dt>입주 시작 예정일</dt><dd>{show(p.moveInStartDate)}{p.moveInStartDate ? ` · ${show(p.moveInStartBasis)} · ${show(p.moveInStartStatus)}` : ''}</dd>
          <dt>실제 준공·입주 호수</dt><dd>{units(p.actualDeliveryUnits)} <span className="text-muted-foreground">(검증된 실적만 표시)</span></dd>
          <dt>시행·시공</dt><dd>{show(p.developer)} · {show(p.contractor)}</dd>
          <dt>위치 수준</dt><dd>{p.locationLevel === 'BLOCK' ? '지구·블록 이름' : p.locationLevel === 'ADDRESS' ? '주소' : p.locationLevel === 'MUNICIPALITY' ? '시군구 이름' : '시도 이름'} · {p.locationRole ? 'LH 블록 라벨점 연결(이름 일치 검토)' : '좌표·공식 경계 미연결'}</dd>
          <dt>위치 근거</dt><dd>{p.locationRole && p.longitude !== null && p.latitude !== null ? <>LH 블록 라벨점 {p.latitude.toFixed(6)}, {p.longitude.toFixed(6)} · 사업 경계 아님 · <a href={`/poc/housing-board/map?region=home-907&homeProject=${p.id}`}>HOME 지도에서 보기</a> · {p.locationEvidenceUrl ? <a href={p.locationEvidenceUrl} target="_blank" rel="noopener noreferrer">LH 위치 원천</a> : '원천 URL 미확보'}</> : <>연결된 라벨점 없음 · <a href={`/poc/housing-board/map?region=home-907&homeProject=${p.id}`}>가상 3D 모형 보기 (실제 위치 아님)</a></>}</dd>
        </Dl>
      </Card>

      <Card render={<section aria-label="정책 연결과 근거" />}>
        <PanelTitle>정책 연결과 원천</PanelTitle>
        <Dl>
          <dt>프로그램</dt><dd>{show(p.programName)} <code>{show(p.programId)}</code></dd>
          <dt>정책 제안</dt><dd>{policy?.name ?? show(p.policyId)} · {show(p.policyId)}</dd>
          <dt>연결 상태</dt><dd>사업→프로그램 {show(p.projectProgramStatus)} · 프로그램→정책 {show(p.programPolicyStatus)}</dd>
          <dt>정체성 검토</dt><dd>{show(p.identityStatus)} · LH 준공예정 연결 제안 {p.forecastLinkCount}건{p.forecastLinkCount ? ` · 호수 비교 ${show(p.forecastUnitComparison)}` : ''}</dd>
          <dt>연결 근거</dt><dd>{show(p.mappingBasis)}</dd>
          <dt>원천</dt><dd>{p.sourceName} <code>{p.sourceId}</code></dd>
          <dt>원천 기준일</dt><dd>{show(p.baseDate)} · 저장 판본 {show(p.revisionNo)} · 최신 수집본 포함 {p.inLatestSource === null ? '미확인' : p.inLatestSource ? '예' : '아니오'}</dd>
          <dt>원문</dt><dd>{p.evidenceUrl ? <a href={p.evidenceUrl} target="_blank" rel="noopener noreferrer">원문 열기</a> : '미확보'}</dd>
        </Dl>
        <Basis>PoC 10 HOME API를 {home10.readFinishedAt.slice(0, 10)}에 변환했습니다. 원본 ID와 결측값을 보존했으며 PoC 12의 PRJ 사업과 자동으로 합치지 않았습니다. 일부 LH 블록 라벨점은 이름이 유일하게 일치할 때만 탐색용으로 연결했고 공식 사업 경계로 사용하지 않았습니다. <Link href="/projects">9·7 사업후보 목록</Link></Basis>
      </Card>
    </Page>
  );
}
