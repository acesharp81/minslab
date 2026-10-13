import Link from 'next/link';
import StageLadder from '../../components/StageLadder';
import { Card, cardVariants } from '../../components/ui/card';
import { Badge } from '../../components/ui/badge';
import { home10 } from '../../lib/home10/data';
import { agencies, agencyId, completionYears, policy, policyProjects, policySources, policyStats, regions, stageCounts } from '../../lib/home10/policy-907';

const n = (value: number) => value.toLocaleString('ko-KR');
const boardPanel = 'mt-3.5 grid grid-cols-[minmax(0,1fr)_400px] items-stretch gap-3.5 narrow:grid-cols-1';

export default function Home() {
  const cards = [
    { label: '정책 발표 목표', value: policy.targetUnits === null ? '미확인' : `${n(policy.targetUnits)}호`, note: policy.metric ?? '지표 미확인', href: '/reports' },
    { label: '연결 검토 후보', value: `${n(policyStats.candidates)}건`, note: '공식 정책 귀속 미확정', href: '/projects' },
    { label: '원천 공정률 확보', value: `${n(policyStats.progress)}건`, note: `미확보 ${n(policyStats.candidates - policyStats.progress)}건`, href: '/projects' },
    { label: '준공 예정일 확보', value: `${n(policyStats.completionDate)}건`, note: '예정일이며 준공 실적 아님', href: '/reports' },
    { label: '지도 위치 연결', value: `${n(policyStats.located)}건`, note: 'LH 블록 라벨점 검토', href: '/map' },
    { label: '사용 원천', value: `${policySources.length}종`, note: 'LH·GH·SH 공개 자료', href: '/sources' },
  ];
  return <div className="mx-auto max-w-[1440px] px-7 pb-9 mobile:px-4">
    <header className="flex flex-wrap items-center gap-5 pt-6 pb-4">
      <div><h1 className="m-0 text-[32px] leading-[1.35] font-bold tracking-[-0.035em]">9·7 주택공급 정책 상황판</h1>
        <span className="text-[14px] text-muted-foreground">PoC 10 원천 자료 · 서울·경기 사업후보 · 발표 목표와 사업후보는 별도 지표</span></div>
      <div className="ml-auto flex flex-wrap items-center gap-2.5"><Badge variant="warn">정책 귀속 검토 중</Badge><span className="text-[14px] text-muted-foreground">자료 변환 {home10.readFinishedAt.slice(0, 10)}</span></div>
    </header>
    <section aria-label="9·7 정책 주요 지표" className="grid grid-cols-[repeat(auto-fit,minmax(min(190px,100%),1fr))] gap-2">
      {cards.map((item) => <Link key={item.label} href={item.href} className={cardVariants({ variant: 'link' })}>
        <span>{item.label}</span><b className="font-display text-[27px] text-foreground">{item.value}</b><span>{item.note}</span>
      </Link>)}
    </section>
    <p className="mt-2 rounded-[10px] border border-border bg-card px-3.5 py-2 text-[15px] text-ink2">9·7 정책에 연결 제안된 후보 {policyStats.candidates}건은 모두 검토 상태입니다. 정책 목표 달성률과 실제 준공·입주 호수는 확인된 자료가 없어 계산하지 않습니다.</p>
    <div className={boardPanel}>
      <Card variant="board" render={<section aria-label="연도별 준공 예정 근거" />}>
        <div className="mb-3 flex flex-wrap justify-between gap-2"><h2 className="m-0 text-[22px]">연도별 준공 예정일 <Badge variant="warn">예정 자료</Badge></h2><Link href="/reports">근거 보기</Link></div>
        <p className="mt-0 text-[14px] text-muted-foreground">개별 사업후보의 원천 준공 예정일을 연도별로 센 건수입니다. 실제 준공·입주 물량이 아닙니다.</p>
        <div className="flex flex-col gap-3">{completionYears.map((item) => <div key={item.year} className="grid grid-cols-[60px_1fr_55px] items-center gap-3 text-[15px]"><b>{item.year}</b><div className="h-5 rounded bg-pn2"><div className="h-5 rounded bg-primary" style={{ width: `${item.count / Math.max(...completionYears.map((row) => row.count), 1) * 100}%` }} /></div><b className="text-right">{item.count}건</b></div>)}</div>
        <p className="mt-4 mb-0 text-[14px] text-muted-foreground">예정일 미확보 {policyStats.candidates - policyStats.completionDate}건 · 실제 준공·입주 확인 {policyStats.actualDelivery}건</p>
      </Card>
      <Card variant="board" render={<section aria-label="단계별 사업후보" />}>
        <div className="mb-3 flex flex-wrap justify-between gap-2"><h2 className="m-0 text-[22px]">단계별 후보</h2><Link href="/stage">단계 상세</Link></div>
        <StageLadder className="mt-1" counts={stageCounts} />
        <p className="mt-3 mb-0 text-[14px] text-muted-foreground">원천 상태를 탐색용 단계에 대응했습니다. 공급·입주 완료로 판정한 후보는 없습니다.</p>
      </Card>
    </div>
    <div className="mt-3.5 grid grid-cols-[repeat(auto-fit,minmax(min(300px,100%),1fr))] gap-3.5">
      <Card variant="board" render={<section aria-label="지역별 후보" />}>
        <h2 className="m-0 mb-3 text-[22px]">서울·경기 후보</h2>
        <div className="grid grid-cols-2 gap-2">{regions.map((region) => <Link key={region.id} href={`/area/${region.id}`} className={cardVariants({ variant: 'link' })}><b>{region.name}</b><span>{policyProjects.filter((item) => item.region === region.name).length}건 · 위치 연결 {policyProjects.filter((item) => item.region === region.name && item.locationRole).length}건</span></Link>)}</div>
        <p className="mt-3 mb-0 text-[14px] text-muted-foreground">9·7 발표 목표는 인천을 포함한 수도권입니다. 이 후보 자료는 서울·경기만 확보했습니다.</p>
      </Card>
      <Card variant="board" render={<section aria-label="기관별 후보" />}>
        <h2 className="m-0 mb-3 text-[22px]">기관별 원천</h2>
        <div className="flex flex-col gap-2">{agencies.map((agency) => <Link key={agency.id} href={`/agency/${agency.id}`} className={cardVariants({ variant: 'link' })}><b>{agency.name}</b><span>{policyProjects.filter((item) => agencyId(item) === agency.id).length}건 원천 후보</span></Link>)}</div>
      </Card>
      <Card variant="board" render={<section aria-label="자료 확보와 공백" />}>
        <h2 className="m-0 mb-3 text-[22px]">자료 확보와 공백</h2>
        <dl className="m-0 grid grid-cols-[1fr_auto] gap-2 text-[15px]"><dt>계획 규모 확인</dt><dd className="m-0">{policyStats.plannedUnits}/{policyStats.candidates}건</dd><dt>원천 공정률 확인</dt><dd className="m-0">{policyStats.progress}/{policyStats.candidates}건</dd><dt>지도 위치점 연결</dt><dd className="m-0">{policyStats.located}/{policyStats.candidates}건</dd><dt>실제 준공·입주 호수</dt><dd className="m-0">미확보</dd></dl>
        <div className="mt-4 flex flex-wrap gap-3 text-[15px]"><Link href="/projects">후보 목록</Link><Link href="/map">기존 3D 지도</Link><Link href="/sources">원천 확인</Link></div>
      </Card>
    </div>
  </div>;
}
