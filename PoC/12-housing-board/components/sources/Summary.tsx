/* 데이터 원본 첫 화면의 핵심 세 가지: 카드마다 결론 한 줄 + 작은 그림 하나.
   ① 중심은 사업 원장과 월별 일정 기록(원장 단계 분포 막대 + 일정 기록 0 막대) ② 보관·혼합·실시간 비율 막대 ③ 신호판은 시간이 지나야 열린다(시간축 세 점).
   막대 색은 뜻을 따르고(단계 = components/charts/palette.ts 와 같은 지표 색, 갈래 = 보관 주색·실시간 청록), 값과 이름은 본문 색 글자로 함께 적는다. */
import type { ReactNode } from 'react';
import { projects } from '../../lib/board/data';
import { stageName } from '../../lib/board/stages';
import { ITEMS, MODE_LABEL, SIGNAL_NOTE, TIMELINE, type Mode } from '../../lib/board/pipeline';
import { MODE_TONE } from './Flow';

const STAGE_TONE: Record<string, string> = { '01': 'var(--st-plan)', '02': 'var(--st-plan)', '03': 'var(--st-permit)', '04': 'var(--st-build)', '05': 'var(--st-sale)', '06': 'var(--st-soon)' };
export const MODE_FILL: Record<Mode, string> = { store: MODE_TONE.store, live: MODE_TONE.live, mixed: `linear-gradient(90deg, ${MODE_TONE.store} 50%, ${MODE_TONE.live} 50%)` };

/* 비율 막대: 조각 사이 2px 틈, 끝은 둥글게. 이름·값은 아래 범례 글자로 */
function Bar({ parts, label }: { parts: { key: string; n: number; fill: string }[]; label: string }) {
  const total = parts.reduce((a, p) => a + p.n, 0);
  return (
    <div className="flex h-[14px] gap-[2px] overflow-hidden rounded-full" role="img" aria-label={label}>
      {parts.filter((p) => p.n > 0).map((p) => <span key={p.key} className="q-grow-x h-full first:rounded-l-full last:rounded-r-full" style={{ width: `${(p.n / total) * 100}%`, background: p.fill }} />)}
    </div>
  );
}
const Key = ({ fill, children }: { fill: string; children: ReactNode }) => (
  <span className="flex items-center gap-1.5 [word-break:keep-all]"><i className="inline-block size-[10px] flex-none rounded-[3px]" style={{ background: fill }} aria-hidden="true" />{children}</span>
);

function Takeaway({ no, title, children, note }: { no: string; title: ReactNode; children: ReactNode; note: string }) {
  return (
    <section className="card-soft flex min-w-0 flex-col rounded-[14px] border border-border bg-card px-5 py-4 shadow-[var(--shadow-card)]" aria-label={`핵심 ${no}`}>
      <p className="m-0 text-[13px] font-bold text-muted-foreground">핵심 {no}</p>
      <h3 className="m-0 mt-1 text-[18px] leading-[1.4] [word-break:keep-all]">{title}</h3>
      <div className="mt-3 flex-1">{children}</div>
      <p className="m-0 mt-3 border-t border-border pt-2.5 text-[13px] leading-[1.55] text-muted-foreground [word-break:keep-all]">{note}</p>
    </section>
  );
}

export default function Summary() {
  const byStage = ['01', '02', '03', '04', '05', '06'].map((c) => ({ key: c, n: projects.filter((p) => p.stageCode === c).length, fill: STAGE_TONE[c] })).filter((s) => s.n > 0);
  const stageCodes = ['01', '02', '03', '04', '05', '06'];
  const noProject = stageCodes.filter((c) => !byStage.some((s) => s.key === c));
  const scheduled = projects.filter((p) => (p as { schedule?: unknown }).schedule).length;
  const modes = (['store', 'mixed', 'live'] as Mode[]).map((m) => ({ key: m, n: ITEMS.filter((i) => i.mode === m).length, fill: MODE_FILL[m] }));
  return (
    <div className="grid grid-cols-3 gap-3 mobile:grid-cols-1">
      <Takeaway no="1" title={<>사업 단계는 있고,<br /><b className="text-primary">일정 이력은 비어 있습니다</b></>} note="신호판(정상·주의·지연)은 일정 기록이 있어야 계산된다. 지금은 사업의 단계만 있고 일정은 비어 있다.">
        <p className="m-0 mb-1.5 flex items-baseline justify-between text-[13px] text-muted-foreground"><span>사업 원장</span><span><b className="font-display text-[22px] font-normal text-foreground tabular-nums">{projects.length}</b>건</span></p>
        <Bar parts={byStage} label={`사업 원장 ${projects.length}건의 단계 분포`} />
        <p className="m-0 mt-1.5 flex flex-wrap gap-x-3 gap-y-0.5 text-[12px] text-muted-foreground">{byStage.map((s) => <Key key={s.key} fill={s.fill}>{s.key} {stageName(s.key)} {s.n}</Key>)}</p>
        <p className="m-0 mt-1 text-[12px] text-muted-foreground [word-break:keep-all]">공급 6단계: {stageCodes.map((c) => `${c} ${stageName(c)}`).join(' → ')}{noProject.length ? ` (${noProject.join('·')}단계는 사업 없음)` : ''}</p>
        <p className="m-0 mt-3 mb-1.5 flex items-baseline justify-between text-[13px] text-muted-foreground"><span>일정 기록이 있는 사업</span><span><b className="font-display text-[22px] font-normal text-foreground tabular-nums">{scheduled}</b>/{projects.length}</span></p>
        <div className="h-[14px] rounded-full border-2 border-dashed border-line2" role="img" aria-label={`일정 기록 ${scheduled}건 / ${projects.length}건`} />
      </Takeaway>
      <Takeaway no="2" title={<>이력은 보관하고,<br /><b className="text-primary">현재 상세는 실시간으로</b></>} note="지난 기록·여러 곳을 합친 값·사람이 판단한 값·파일로만 받는 자료는 미리 보관해 두고, 한 위치의 상세와 지금 값이 중요한 것만 열 때 가져온다.">
        <Bar parts={modes} label={`자료 ${ITEMS.length}가지의 판정 비율`} />
        <p className="m-0 mt-1.5 flex flex-wrap gap-x-3 gap-y-0.5 text-[12px] text-muted-foreground">{modes.map((m) => <Key key={m.key} fill={m.fill}>{MODE_LABEL[m.key as Mode]} {m.n}</Key>)}</p>
        <ul className="m-0 mt-3 grid list-none gap-1 p-0 text-[13px] [word-break:keep-all]">
          <li><Key fill={MODE_FILL.store}>보관: 인허가 · 통계 · 일정 이력</Key></li>
          <li><Key fill={MODE_FILL.mixed}>혼합: 공고 조회 + 이력 저장</Key></li>
          <li><Key fill={MODE_FILL.live}>실시간: 건물 · 필지 · 교통 상세</Key></li>
        </ul>
      </Takeaway>
      <Takeaway no="3" title={<>지연 판단의 시작은<br /><b className="text-primary">월별 기록의 축적</b></>} note={SIGNAL_NOTE}>
        <p className="m-0 mb-3 text-[12px] text-muted-foreground">2026년 10월에 기록을 시작할 경우</p>
        <ol className="m-0 grid list-none grid-cols-3 p-0" aria-label="일정 기록 시간축">
          {TIMELINE.map((t, i) => (
            <li key={t.ym} className="relative min-w-0 border-t-2 border-line2 pt-3 pr-2">
              <span className={`absolute -top-[7px] left-0 size-[12px] rounded-full border-2 border-primary ${i === 0 ? 'bg-primary' : 'bg-card'}`} aria-hidden="true" />
              <b className="font-display text-[17px] leading-none font-normal tabular-nums">{t.ym}</b>
              <p className="m-0 mt-1 text-[12px] leading-[1.45] text-muted-foreground [word-break:keep-all]" title={t.what}>{t.short}</p>
            </li>
          ))}
        </ol>
        <p className="m-0 mt-3 text-[13px] leading-[1.55] [word-break:keep-all]">지연은 예정일이 달마다 바뀌는지 비교해야 보여서, 기록을 시작한 달부터 시간이 걸린다. 비교할 과거 기록을 확보하기 위해 <b>가장 먼저</b> 시작합니다.</p>
      </Takeaway>
    </div>
  );
}
