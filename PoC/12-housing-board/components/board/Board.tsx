'use client';
/* 종합상황판(/) — 시안 이식. 시안의 동작(지시 6건 순환·월별 리본 차트·재생·시점 이동·범례 강조·시도)을 그대로 두고,
   수치는 시안의 SAMPLE 이다(위젯마다 SAMPLE 표지). 실데이터가 있는 위젯(향후 12개월 LH 준공 예정, 원천 수)은 실제 값이고 '실데이터' 표지가 붙는다.
   실데이터 위젯(월별 실적 흐름)은 서버 컴포넌트(RealPanels)를 middle 로 받아 '전국 17개 시도'와 같은 줄에 둔다. */
import { useEffect, useLayoutEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import {
  AD, AG, AW, C, CIR, K, LAST, NOW, PITCH, PW, PX0, RANGE, RCOL, RLAB, REG, VW,
  argmax, dStage, f, ip, kind, makeDir, ml, r10, rcls, sg, tot, txSnap, txTrend, vals, ymOf, yr,
} from '../../lib/board/sample';
import { cn } from 'cn';
import { sub } from '../page';
import { Badge } from '../ui/badge';
import { Card } from '../ui/card';
import { CUR, HOVER, RIBBON, chartStatic, ribbonDynamic } from './ribbon';
import { Real, Sample } from './tags';
import PanelLink from './PanelLink';
import { ag, agName, agVal, ags, bar3, btn, disp, pacts, phead, ptSmall, ptSmallBlock, ptitle, row2 } from './styles';

export type BoardReal = {
  sourceCount: number;                                              // 원천 카탈로그의 원천 수
  validMonths: string[];                                            // /month/{ym} 이 열리는 달
  lh: { ym: string; units: number; blocks: number }[];              // NOW(2026.10)부터 12개월 LH 준공 예정
  lhAsOf: string;                                                   // LH 파일 기준일
  lhAgeMonths: number;                                              // 기준일이 실적 마지막 달보다 몇 개월 묵었나
  actualMonth: string;                                              // 통계누리 실적의 마지막 달(YYYY-MM)
};

/* 문구가 바뀌어도 칸 높이가 변하지 않게 가장 긴 문구를 보이지 않게 겹쳐 둔다(시안 reserve) */
function Reserve({ live, list }: { live: ReactNode; list: string[] }) {
  const sizes = Array.from(new Set(list)).sort((a, b) => b.length - a.length).slice(0, 3);
  return <span className="grid [&>*]:min-w-0 [&>*]:[grid-area:1/1]"><span>{live}</span>{sizes.map((t, i) => <span key={i} className="pointer-events-none invisible select-none" aria-hidden="true">{t}</span>)}</span>;
}

/* 패널 겉모양(.pnl)과 지시가 가리킬 때 둘러지는 주색 고리(.ringable .ring) */
const ringable = (on: boolean) => cn('[transition:box-shadow_.25s]', on && 'is-ringed [box-shadow:0_0_0_1px_var(--primary)]');   // is-ringed: 호버 그림자가 고리를 덮지 않게(card-soft)
/* 선택된 칩·버튼의 공통 호버: 눌려 있지 않을 때만 배경이 밝아진다 */
const hoverBg = 'not-aria-pressed:hover:bg-pn2';
/* 툴팁 안의 한 줄(.tip .tr): 왼쪽 이름(작은 색 사각형 포함)과 오른쪽 값 */
const tipRow = 'flex items-center justify-between gap-1.5';
const tipRowKey = 'flex items-center gap-1.5';

export default function Board({ real, middle }: { real: BoardReal; middle: ReactNode }) {
  const [focus, setFocus] = useState(1);
  const [cursor, setCursor] = useState(NOW);
  const [tour, setTour] = useState(false);
  const [tick, setTick] = useState(0);
  const [hl, setHl] = useState(-1);
  const [region, setRegion] = useState('서울');
  const [tip, setTip] = useState<{ m: number; x: number; y: number } | null>(null);
  /* 리본 첫 화면 연출 단계(app/tailwind.css 의 [data-intro]): sweep 쓸기 → travel 기준 시점 2025.01→2026.10 → landed 착지 → '' 끝. 서버 렌더부터 sweep 이라 첫 화면부터 쓸린다 */
  const [intro, setIntro] = useState<'sweep' | 'travel' | 'landed' | ''>('sweep');
  const svgRef = useRef<SVGSVGElement>(null);
  const wrapRef = useRef<HTMLDivElement>(null);
  const tipRef = useRef<HTMLDivElement>(null);

  const DIR = useMemo(() => makeDir(real.sourceCount), [real.sourceCount]);
  const valid = useMemo(() => new Set(real.validMonths), [real.validMonths]);
  const staticSvg = useMemo(() => chartStatic(hl), [hl]);
  const dynSvg = useMemo(() => ribbonDynamic(cursor), [cursor]);

  useEffect(() => { setTour(!window.matchMedia('(prefers-reduced-motion: reduce)').matches); }, []);   // 시안: reduce 이면 순환 끔
  useEffect(() => {   // 리본 첫 화면 연출. 움직임 줄이기면 건너뛰고, 사용자가 누르거나 키·휠을 쓰면 바로 끝내고 기준 시점을 2026.10 으로 둔다(누른 곳의 동작은 그대로 이어진다)
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) { setIntro(''); return; }
    const EV = ['pointerdown', 'keydown', 'wheel'] as const, opt = { capture: true, passive: true };
    const timers: number[] = [];
    let raf = 0;
    const off = () => { for (const ev of EV) window.removeEventListener(ev, skip, opt); };
    const end = () => { timers.forEach(clearTimeout); cancelAnimationFrame(raf); off(); setIntro(''); };
    function skip() { end(); setCursor(NOW); }
    for (const ev of EV) window.addEventListener(ev, skip, opt);
    setIntro('sweep'); setCursor(0);
    timers.push(window.setTimeout(() => {   // ② 시간 여행: 한 달에 60ms. 경과 시간으로 달을 정해 타이머가 늦춰지는 탭에서도 같은 시간에 끝난다
      setIntro('travel');
      const t1 = performance.now();
      const step = (t: number) => {
        const m = Math.min(NOW, Math.floor((t - t1) / 60) + 1);
        setCursor(m);
        if (m >= NOW) { setIntro('landed'); timers.push(window.setTimeout(() => { off(); setIntro(''); }, 950)); return; }
        raf = requestAnimationFrame(step);
      };
      raf = requestAnimationFrame(step);
    }, 1100));
    return end;
  }, []);
  useEffect(() => {   // 지시 순환: 1 초 틱, 7 초마다 다음 지시
    const id = setInterval(() => setTick((t) => t + 1), 1000);
    return () => clearInterval(id);
  }, []);
  useEffect(() => { if (tour && tick > 0 && tick % 7 === 0) setFocus((x) => (x % 6) + 1); }, [tick, tour]);

  const goto = (m: number) => setCursor(Math.max(0, Math.min(LAST, m)));
  const monthAt = (clientX: number) => {
    const r = svgRef.current!.getBoundingClientRect();
    const m = Math.floor(((clientX - r.left) * (VW / r.width) - PX0) / PITCH);
    return m < 0 || m > LAST ? -1 : m;
  };
  useLayoutEffect(() => {   // 툴팁이 차트 밖으로 나가지 않게 자리를 잡는다(시안 showTip)
    if (!tip || !tipRef.current || !wrapRef.current) return;
    const wr = wrapRef.current.getBoundingClientRect(), t = tipRef.current;
    const tw = t.offsetWidth, th = t.offsetHeight;
    let x = tip.x + 14, y = tip.y + 14;
    if (x + tw > wr.width - 6) x = tip.x - tw - 14;
    if (y + th > wr.height - 6) y = wr.height - th - 6;
    t.style.left = `${Math.max(x, 6)}px`; t.style.top = `${Math.max(y, 6)}px`;
  }, [tip]);

  /* 선택 시점의 값 */
  const v = vals(cursor), nv = vals(NOW), past = cursor <= NOW, ds = dStage(cursor), bk = argmax(ds);
  const d = r10(ip(AD, cursor)), w = r10(ip(AW, cursor)), tt = tot(cursor), ok = tt - d - w, pct = (x: number) => (x / tt * 100).toFixed(1) + '%';
  const cc = Math.min(cursor, NOW), tx = (m: number) => (m * 560 / NOW).toFixed(1), ty = (val: number) => (190 - val / 20000 * 180).toFixed(1);
  const pts = (arr: [number, number][]) => RANGE.slice(0, NOW + 1).map((m) => tx(m) + ',' + ty(ip(arr, m))).join(' ');
  const fi = cursor - NOW, hasFut = fi >= 0 && fi < 12;
  const maxLh = Math.max(1, ...real.lh.map((m) => m.units));
  const cur = DIR[focus - 1];
  const curReg = REG.find((r) => r.n === region)!;
  const monthLink = valid.has(ymOf(cursor)) ? `/month/${ymOf(cursor)}` : null;
  const tipView = tip ? tipOf(tip.m) : null;
  const futRead = hasFut
    ? `${ml(cursor)} 예정 — LH 준공 ${f(real.lh[fi].units)}세대 · ${real.lh[fi].blocks}블록`
    : cursor < NOW ? `지난 시점(${ml(cursor)})의 준공 실적은 월 상세·지역별 화면에서 봅니다.` : '이 시점은 12개월 예정 범위(2026.10~2027.09) 밖입니다.';
  const futList = [`${ml(NOW)} 예정 — LH 준공 ${f(maxLh)}세대 · 99블록`, '지난 시점(2025.01)의 준공 실적은 월 상세·지역별 화면에서 봅니다.', '이 시점은 12개월 예정 범위(2026.10~2027.09) 밖입니다.'];

  function tipOf(m: number) {
    const vv = vals(m), dd = dStage(m), b = argmax(dd);
    return { m, vv, dd, b };
  }

  return (
    <div className="[&_:focus-visible]:[outline-offset:2px] [&_:focus-visible]:[outline:2px_solid_var(--primary)] motion-reduce:[&_*]:animate-none! motion-reduce:[&_*]:transition-none!">
      <div className="board-desktop mx-auto max-w-[1440px] px-7 pb-9">
        <header className="flex flex-wrap items-center gap-5 pt-6 pb-4">
          <div className="flex flex-wrap items-center gap-5 phone:gap-2"><div className="flex flex-col gap-[3px] phone:w-full"><h1 className="m-0 text-[32px] leading-[1.35] font-bold tracking-[-0.035em] text-foreground mobile:text-[13px]">주택공급 종합상황판</h1><span className="text-[14px] text-muted-foreground [word-break:keep-all]">계획에서 입주까지, 대한민국 주택공급의 흐름을 한눈에</span></div></div>
          <div className="ml-auto flex flex-wrap items-center gap-2.5">
            <Badge variant="solid" className="bg-[var(--sample-bg)] text-[var(--sample-ink)]" title="시안의 수치는 SAMPLE입니다. '실데이터' 표지가 붙은 위젯만 실제 자료이고, 각각 자료의 기준일을 함께 보입니다.">SAMPLE 시안 수치 · &lsquo;실데이터&rsquo; 표지만 실제 자료</Badge>
            <span className={sub}>시안 기준일 2026-10-07 · 실적 자료는 {real.actualMonth.replace('-', '.')}까지</span>
          </div>
        </header>

        <section aria-label="총리 지시 6건">
          <div className="grid grid-cols-[repeat(auto-fit,minmax(min(190px,100%),1fr))] gap-2">
            {DIR.map((x, i) => (
              <button key={i} type="button" data-slot="board-dir" style={{ ['--i' as string]: i }} className={cn(btn, 'q-rise card-lift group/dir relative flex min-w-0 flex-col gap-0.5 overflow-hidden rounded-[12px] border border-border bg-card px-3.5 pt-2.5 pb-3 aria-pressed:border-primary aria-pressed:bg-accent', hoverBg)} aria-pressed={i === focus - 1} onClick={() => { setFocus(i + 1); setTour(false); }}
                aria-label={x.dv !== undefined ? `${x.t} ${x.m}, 전월 대비 ${Math.abs(x.dv).toFixed(1)}%p ${x.dv >= 0 ? '상승' : '하락'}` : undefined}>
                <span className="text-[14px] text-muted-foreground">{x.date} · {x.t}</span>
                <span className="flex min-w-0 flex-wrap items-center gap-x-2"><span className={cn(disp, 'text-[28px] leading-[1.15] group-aria-pressed/dir:text-primary')}>{x.m}</span>
                  {x.dv !== undefined ? <span className={cn('flex flex-col text-[14px] leading-[1.15] font-bold whitespace-nowrap', x.dv >= 0 ? 'text-ok' : 'text-bad')}><span>{x.dv >= 0 ? '▲' : '▼'} {Math.abs(x.dv).toFixed(1)}%p</span><small className="text-[13px] font-normal text-muted-foreground">전월 대비</small></span> : null}
                </span>
                <span className="absolute bottom-0 left-0 h-[3px] w-0 bg-primary [transition:width_.9s_linear]" style={{ width: i === focus - 1 && tour ? `${(((tick % 7) + 1) / 7 * 100).toFixed(0)}%` : '0' }} />
              </button>
            ))}
          </div>
          <div className="mt-2 flex flex-wrap items-center gap-2.5 rounded-[10px] border border-border bg-card px-3.5 py-2 text-[15px] text-ink2"><Badge variant="solid" className="bg-secondary text-primary">지시 요지</Badge><Reserve live={cur.q} list={DIR.map((x) => x.q)} /></div>
        </section>

        <div className="mt-3.5 grid grid-cols-[minmax(0,1fr)_400px] items-stretch gap-3.5 narrow:grid-cols-1">
          <Card variant="board" className={ringable(cur.p.includes('p-chart'))} render={<section id="p-chart" aria-label="월별 공급 파동" />}>
            <div className="mb-2 flex flex-wrap items-center gap-3.5">
              <h2 className={ptitle}>월별 공급 파동 <Sample /> <small className={ptSmall}>· 연도별 총량에 따른 단계별 위치 · 2026.10까지 실적, 이후 예정(빗금)</small></h2>
              <div data-slot="board-legend" className="ml-auto flex flex-wrap gap-1" role="group" aria-label="단계 범례 (누르면 해당 단계를 강조)">
                {K.map((k, i) => <button key={k} type="button" className={cn(btn, 'flex items-center gap-1.5 rounded-full border border-transparent px-[9px] py-[3px] text-[14px] [transition:background_.15s,border-color_.15s] aria-pressed:border-primary aria-pressed:bg-accent', hoverBg)} aria-pressed={hl === i} onClick={() => setHl(hl === i ? -1 : i)}><i className="block size-[11px] flex-none rounded-[3px]" style={{ background: C[i] }} />{k}</button>)}
              </div>
            </div>
            {/* 좁은 화면에서만 가로로 민다. 세로는 숨긴다: overflow-x 가 auto 면 세로도 auto 가 되어, 툴팁·소수점 높이로 1px 만 넘쳐도 세로 스크롤바가 생기고 그 폭만큼 차트가 다시 줄어 그림이 흔들렸다 */}
            <div className="overflow-x-auto overflow-y-hidden rounded-[10px]">
            <div className="relative min-w-[900px] cursor-pointer rounded-[10px] border border-border bg-chartbg [touch-action:pan-y] mobile:min-w-0" ref={wrapRef} data-intro={intro || undefined}
              onPointerMove={(e) => { const m = monthAt(e.clientX); if (m < 0) setTip(null); else { const wr = wrapRef.current!.getBoundingClientRect(); setTip({ m, x: e.clientX - wr.left, y: e.clientY - wr.top }); } }}
              onPointerLeave={() => setTip(null)}
              onClick={(e) => { const m = monthAt(e.clientX); if (m >= 0) goto(m); }}>
              <svg id="chart" shapeRendering="geometricPrecision" ref={svgRef} className="block h-auto w-full [&_text]:[font-family:inherit]" viewBox="0 0 960 400" role="img" aria-label="2025년 1월부터 2028년 10월까지 단계별 호수를 쌓은 월별 리본. 연도별 총량에 따라 굵기가 달라지고, 층 안의 붉은 띠가 단계별 지연 호수이며 핀이 병목 단계를 가리킵니다. 차트를 누르면 그 달을 고릅니다.">
                <g dangerouslySetInnerHTML={{ __html: staticSvg }} />
                <rect x={(RIBBON.PX0 + (tip ? tip.m : 0) * RIBBON.PITCH).toFixed(1)} y={RIBBON.TOP - 4} width={RIBBON.PITCH.toFixed(1)} height={RIBBON.PH + 8} fill={HOVER.fill} fillOpacity={HOVER.opacity} visibility={tip ? 'visible' : 'hidden'} pointerEvents="none" />
                <rect x={(PX0 + cursor * PW / (LAST + 1)).toFixed(1)} y={RIBBON.TOP - 4} width={RIBBON.PITCH.toFixed(1)} height={RIBBON.PH + 8} rx="3" fill={CUR.fill} className="rb-cur" pointerEvents="none" />
                {/* ① 쓸기의 빛줄기: 드러나는 층의 앞날을 따라 왼쪽→오른쪽으로 지나간다(평소엔 투명) */}
                <rect className="rb-scan" x={PX0 - 30} y={RIBBON.TOP - 4} width="36" height={RIBBON.PH + 8} fill="url(#rb-scan-g)" opacity="0" pointerEvents="none" />
                <g pointerEvents="none" dangerouslySetInnerHTML={{ __html: dynSvg }} />
              </svg>
              {/* 툴팁도 리본을 가리지 않는 HUD 유리: dark 범위로 감싸 안의 글자·상태색이 어두운 유리용(다크 토큰) 값을 쓰고, 다크 바탕 88% + 흐림으로 뒤 리본이 번져 보인다 */}
              <div data-slot="board-tip" className="dark pointer-events-none absolute z-[3] min-w-[168px] rounded-[10px] border border-[var(--rb-hud-line)] bg-[color-mix(in_srgb,var(--popover)_88%,transparent)] px-[11px] py-[9px] text-[14px] leading-[1.5] text-foreground shadow-[var(--shadow-pop)] backdrop-blur-[6px]" ref={tipRef} hidden={!tip}>
                {tipView ? (
                  <>
                    <div className="mb-1 flex items-center gap-2"><b className={cn(disp, 'text-[18px]')}>{ml(tipView.m)}</b><Badge variant="solid" className={tipView.m <= NOW ? 'bg-foreground text-background' : 'bg-primary text-primary-foreground'}>{kind(tipView.m)}</Badge></div>
                    <div className={cn(sub, 'mb-[3px]')}>{2025 + yr(tipView.m)}년 총량 {f(tot(tipView.m))}호</div>
                    {K.map((k, i) => <div key={k} className={tipRow}><span className={tipRowKey}><i className="block size-[9px] rounded-[2px]" style={{ background: C[i] }} />{CIR[i]} {k}</span><b className={disp}>{f(r10(tipView.vv[i]))}</b></div>)}
                    <div className="mt-[3px] border-t border-border pt-[3px]">
                      {tipView.m <= NOW ? <><div className={tipRow}><span className={cn(tipRowKey, 'text-bad')}>지연</span><b className={disp}>{f(r10(ip(AD, tipView.m)))}</b></div><div className={tipRow}><span className={cn(tipRowKey, 'text-warn')}>주의</span><b className={disp}>{f(r10(ip(AW, tipView.m)))}</b></div></> : null}
                      <div className={tipRow}><span className={cn(tipRowKey, 'text-primary')}>병목 · {K[tipView.b]}</span><b className={disp}>{f(r10(tipView.dd[tipView.b]))}</b></div>
                    </div>
                  </>
                ) : null}
              </div>
            </div>
            </div>
          </Card>

          <Card variant="board" render={<section id="p-snap" aria-label="선택 시점의 판정과 단계별 호수" />}>
            <div className="mb-2.5 flex flex-wrap items-baseline gap-2.5">
              <h2 className={ptitle}>{ml(cursor)}</h2>
              <Badge variant="solid" className={past ? 'bg-foreground text-background' : 'bg-primary text-primary-foreground'}>{kind(cursor)}</Badge>
              <Sample />
              <span className={pacts}><PanelLink href={`/stage/0${bk + 1}`} full={`병목 단계(${K[bk]}) 상세`}>병목 단계</PanelLink>{monthLink ? <PanelLink href={monthLink} full={`${ml(cursor)} 월 상세`}>{cursor % 12 + 1}월</PanelLink> : null}</span>
            </div>
            <div>
              <div className="q-grow-x flex h-3.5 gap-0.5 overflow-hidden bg-pn2 [&>span]:block [&>span]:h-full [&>span]:min-w-0" role="img" aria-label={`전체 ${f(tt)}호 중 지연 ${pct(d)}, 주의 ${pct(w)}, 정상 ${pct(ok)}`}>
                <span className="bg-bad" style={{ width: `${(d / tt * 100).toFixed(2)}%` }} /><span className="bg-warn" style={{ width: `${(w / tt * 100).toFixed(2)}%` }} /><span className="bg-ok" style={{ width: `${(ok / tt * 100).toFixed(2)}%` }} />
              </div>
              <div className="mt-[9px] grid grid-cols-3 gap-2">
                {([['지연', 'bad', d], ['주의', 'warn', w], ['정상', 'ok', ok]] as const).map(([name, tone, n]) => (
                  <div key={name} className="min-w-0">
                    <div className="flex items-center gap-[5px] text-[14px] whitespace-nowrap text-muted-foreground"><i className={cn('block size-[9px] flex-none rounded-[3px]', tone === 'bad' ? 'bg-bad' : tone === 'warn' ? 'bg-warn' : 'bg-ok')} />{name}<em className="ml-0.5 text-[14px] not-italic">{pct(n)}</em></div>
                    <b className={cn('block font-display text-[20px] leading-[1.3] whitespace-nowrap tabular-nums', tone === 'bad' ? 'text-bad' : tone === 'warn' ? 'text-warn' : 'text-ok')}>{f(n)}<small className="ml-0.5 [font-family:inherit] text-[14px] font-normal opacity-80">호</small></b>
                  </div>
                ))}
              </div>
            </div>
            <div className={cn(sub, 'mt-1.5')}><Reserve live={txSnap(cursor)} list={[txSnap(LAST), 'x']} /></div>
            <div className="mt-2 flex flex-auto flex-col" aria-label="단계별 호수, 현재 대비 증감, 지연 호수">
              {K.map((k, i) => {
                const dlt = r10(v[i] - nv[i]);
                return (
                  <div key={k} className={cn('grid flex-auto grid-cols-[minmax(0,1fr)_70px_62px_78px] items-center gap-2 rounded-[6px] border-b border-border px-1.5 py-0.5 last:border-b-0 phone:grid-cols-[minmax(0,1fr)_62px_74px]', i === bk && 'bg-accent')}>
                    <span className="flex items-center gap-2 text-[15px] font-bold whitespace-nowrap"><i className="block size-[11px] flex-none rounded-[3px]" style={{ background: C[i] }} />{CIR[i]} {k}<Badge variant="solid" className={cn('ml-0.5 bg-primary/10 px-1.5 text-[12px] leading-[15px] text-primary', i === bk ? 'visible' : 'invisible')}>병목</Badge></span>
                    <span className={cn(disp, 'text-right text-[20px]')}>{f(r10(v[i]))}</span>
                    {/* 옛 dash.css 의 .dl(정의 목록 격자)이 이 칸에도 걸려 있었다. 겉모습을 그대로 두려고 같은 격자·여백을 남긴다. */}
                    <span className={cn('mt-2.5 grid grid-cols-[max-content_minmax(0,1fr)] gap-x-4 gap-y-1.5 text-right text-[14px] phone:hidden', dlt === 0 ? 'text-mute' : dlt > 0 ? 'text-ok' : 'text-warn')}>{dlt === 0 ? '현재' : sg(dlt)}</span>
                    <span className="text-right text-[14px] whitespace-nowrap text-bad">지연 {f(r10(ds[i]))}</span>
                  </div>
                );
              })}
            </div>
          </Card>
        </div>

        <div className={row2}>
          {middle}

          <Card variant="board" className={ringable(cur.p.includes('p-region'))} render={<section id="p-region" aria-label="전국 17개 시도" />}>
            <div className={phead}>
              <h2 className={ptitle}>전국 17개 시도 <Sample /> <small className={ptSmall}>· 지연 · 주의 · 정상 (사업 수) · 바탕색 = 지연율 단계</small></h2>
              <span className={pacts}><PanelLink href={`/area/${curReg.code}`} full={`${curReg.n} 실적(실데이터) 상세`}>{curReg.n} 실적</PanelLink></span>
            </div>
            <div className="mt-2.5 flex flex-wrap items-center gap-3 text-[14px] text-muted-foreground [&>span]:flex [&>span]:items-center [&>span]:gap-[5px]" aria-label="바탕색과 지연율 구간"><span className="font-bold text-ink2">지연율(%)</span>{RCOL.map((c, i) => <span key={i}><i className="block h-3 w-6 rounded-[3px] border border-border" style={{ background: c }} />{RLAB[i]}</span>)}</div>
            <div className="mt-2 flex flex-wrap items-center gap-3 text-[14px] text-muted-foreground" aria-label="사업 수 범례">
              <span className="text-bad">지연</span><span className="text-warn">주의</span><span className="text-ok">정상</span><span>순서 · 사업 수</span>
              {curReg.code === '12' ? <span className="ml-auto">2026-07부터 광주·전남은 전남광주로 집계됩니다</span> : null}
            </div>
            <div className="mx-0 my-2.5 grid flex-auto grid-cols-[repeat(auto-fill,minmax(112px,1fr))] auto-rows-[minmax(0,1fr)] gap-1.5">
              {REG.map((r, ri) => {
                const rate = r.d / r.tot * 100;
                return (
                  <button key={r.n} type="button" data-slot="board-region" className={cn(btn, 'q-rise card-lift flex flex-col justify-between gap-1.5 rounded-[10px] border border-border bg-[var(--rc)] px-[9px] py-2 aria-pressed:border-primary aria-pressed:[box-shadow:0_0_0_1px_var(--primary)]')} aria-pressed={r.n === region} onClick={() => setRegion(r.n)} style={{ ['--rc' as string]: RCOL[rcls(rate)], ['--i' as string]: ri * 0.5 }}
                    aria-label={`${r.n} 지연 ${r.d} 주의 ${r.w} 정상 ${r.ok} 지연율 ${rate.toFixed(1)}%`}>
                    <span className="flex items-baseline justify-between gap-1 text-[15px] font-bold text-foreground"><span>{r.n}{r.big ? <em className="ml-1 text-[12px] font-normal text-ink2 not-italic">상세</em> : null}</span><span className={cn(disp, 'text-[14px]')}>{rate.toFixed(1)}%</span></span>
                    <span className={cn(disp, 'flex gap-2 self-start rounded-[7px] bg-card/90 px-2 py-0.5 text-[16px]')}><span className="text-bad">{r.d}</span><span className="text-warn">{r.w}</span><span className="text-ok">{r.ok}</span></span>
                  </button>
                );
              })}
            </div>
          </Card>
        </div>

        <div className="mt-3.5 grid grid-cols-[repeat(auto-fit,minmax(min(300px,100%),1fr))] gap-3.5">
          <Card variant="board" className={ringable(cur.p.includes('p-trend'))} render={<section id="p-trend" aria-label="지연·주의 추이" />}>
            <h2 className={ptitle}>지연·주의 추이 <Sample /> <small className={ptSmallBlock}>· 호 · 실적 기준</small></h2>
            {/* 패널 폭에 따라 0.6~1배로 줄어 그려진다: 선·격자는 non-scaling-stroke 로 화면 px 굵기를 지킨다(1px 미만 흐림 방지, 계획서 14절 T2) */}
            <svg id="trend" className="mt-1.5 block h-auto w-full" viewBox="0 0 560 200" role="img" aria-label="지연과 주의 호수 추이">
              <line x1="0" y1="55" x2="560" y2="55" stroke="var(--border)" vectorEffect="non-scaling-stroke" /><line x1="0" y1="100" x2="560" y2="100" stroke="var(--border)" vectorEffect="non-scaling-stroke" /><line x1="0" y1="145" x2="560" y2="145" stroke="var(--border)" vectorEffect="non-scaling-stroke" />
              <g className="q-sweep"><polyline points={pts(AW)} fill="none" stroke="var(--warn)" strokeWidth="2.4" vectorEffect="non-scaling-stroke" strokeLinejoin="round" /><polyline points={pts(AD)} fill="none" stroke="var(--bad)" strokeWidth="2.8" vectorEffect="non-scaling-stroke" strokeLinejoin="round" /></g>
              <line x1={tx(cc)} y1="6" x2={tx(cc)} y2="194" stroke="var(--primary)" strokeWidth="2" vectorEffect="non-scaling-stroke" />
              <circle cx={tx(cc)} cy={ty(ip(AD, cc))} r="4.5" fill="var(--bad)" /><circle cx={tx(cc)} cy={ty(ip(AW, cc))} r="4.5" fill="var(--warn)" />
            </svg>
            <div className={cn(sub, 'flex justify-between')}><span>2025.01</span><span>2026.10</span></div>
            <div className="mt-1.5 text-[14px] text-ink2"><Reserve live={txTrend(cursor)} list={RANGE.map(txTrend)} /></div>
          </Card>

          <Card variant="board" className={ringable(cur.p.includes('p-fut'))} render={<section id="p-fut" aria-label="향후 12개월 공급 예정" />}>
            <div className={phead}>
              <h2 className={ptitle}>향후 12개월 공급 예정 <Real title={`LH 공공주택 준공예정현황(15141761), 파일 기준일 ${real.lhAsOf}`} /> <small className={ptSmallBlock}>· 준공 예정(LH) 월별 (세대)</small></h2>
              <span className={pacts}><PanelLink href="/agency/lh" full="LH 준공 예정 상세">LH 상세</PanelLink></span>
            </div>
            <svg id="fmonths" className="mt-3 block min-h-[76px] w-full flex-[1_1_76px]!" viewBox="0 0 240 100" preserveAspectRatio="none" role="img" aria-label="2026.10부터 2027.09까지 월별 LH 준공 예정 세대수">
              <defs><linearGradient id="fm-g" x1="0" y1="0" x2="0" y2="1"><stop offset="0" style={{ stopColor: `color-mix(in srgb, ${C[4]} 66%, var(--rb-hi))` }} /><stop offset="1" style={{ stopColor: C[4] }} /></linearGradient></defs>
              {real.lh.map((m, i) => { const h = m.units / maxLh * 92; return <rect key={m.ym} x={i * 20 + 1.5} y={(100 - h).toFixed(1)} width="17" height={Math.max(h - 0.6, 0.4).toFixed(1)} fill="url(#fm-g)" className="q-grow-y" style={{ ['--i' as string]: i }}><title>{`${m.ym.replace('-', '.')} LH 준공 예정 ${f(m.units)}세대 · ${m.blocks}블록`}</title></rect>; })}
              <rect x={fi * 20 + 0.5} y="1" width="20" height="99" fill="none" stroke="var(--foreground)" strokeWidth="2" style={{ vectorEffect: 'non-scaling-stroke' }} visibility={hasFut ? 'visible' : 'hidden'} />
            </svg>
            <div className={cn(sub, 'mt-[3px] flex justify-between')}><span>2026.10</span><span>2027.03</span><span>2027.09</span></div>
            <div className="mt-2 text-[14px] text-ink2"><Reserve live={futRead} list={futList} /></div>
            <p className={cn(sub, 'mt-1.5')}>착공·모집·입주 예정의 월별 자료는 원천이 없어 비어 있습니다. LH 파일은 기준일(<b>{real.lhAsOf}</b>)이 실적 자료보다 {real.lhAgeMonths}개월 묵었습니다.</p>
          </Card>

          <Card variant="board" className={ringable(cur.p.includes('p-agency'))} render={<section id="p-agency" aria-label="기관별 진행" />}>
            <div className={phead}>
              <h2 className={ptitle}>기관별 진행 <Sample /> <small className={ptSmallBlock}>· 호 · 지연은 전체 지연 10,000호 중 비중</small></h2>
              <span className={pacts}><PanelLink href="/agency" full="기관별 실데이터(시행주체별 호수)">시행주체별</PanelLink></span>
            </div>
            <div className={ags}>
              {AG.map((a, ai) => {
                const t = a[1] + a[2] + a[3];
                return (
                  <div key={a[0]} className={cn(ag, 'grid-cols-[minmax(0,142px)_minmax(0,1fr)_84px]')}>
                    <div className={agName}><b>{a[0]}</b><span className="text-[14px] text-muted-foreground">{f(t)}호</span></div>
                    <div className={cn(bar3, 'q-grow-x h-3')} style={{ ['--i' as string]: ai }}>
                      <span className="block bg-ok" style={{ width: `${(a[1] / t * 100).toFixed(1)}%` }} /><span className="block bg-warn" style={{ width: `${(a[2] / t * 100).toFixed(1)}%` }} /><span className="block bg-bad" style={{ width: `${(a[3] / t * 100).toFixed(1)}%` }} />
                    </div>
                    <div className={agVal}><b className={cn(disp, 'text-bad')}>{f(a[3])}</b><span className="text-[14px] text-muted-foreground">· {(a[3] / 100).toFixed(0)}%</span></div>
                  </div>
                );
              })}
            </div>
            <div className={cn(sub, 'mt-2')}>군인 특별공급(국방부)은 수작업 입력 대기 상태입니다.</div>
          </Card>
        </div>
      </div>
    </div>
  );
}
