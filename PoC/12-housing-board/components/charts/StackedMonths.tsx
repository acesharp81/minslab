/* 월별 쌓은 막대(시행주체별). 막대마다 /month 링크. 알 수 없는 달(null)은 빈 칸. 잠정치는 윗면을 빗금으로 구분하지 않고 아래 눈금 글자로 알린다. */
import ChartFrame from './ChartFrame';
import { ymDot } from '../../lib/board/calc';
import { niceMax } from './MonthLines';

export type Stack = { key: string; label: string; color: string; values: (number | null)[] };
const W = 960, H = 200, L = 0, R = 0, T = 0, B = 0;

export default function StackedMonths({ months, stacks, provisional, href, label }: { months: string[]; stacks: Stack[]; provisional: string[]; href: (ym: string) => string; label: string }) {
  const totals = months.map((_, i) => stacks.reduce((a, s) => a + (s.values[i] ?? 0), 0));
  const top = niceMax(Math.max(1, ...totals));
  const pw = W - L - R, step = pw / months.length, bw = Math.max(2, step * 0.7);
  const y = (v: number) => T + (H - T - B) * (1 - v / top);
  return (
    <ChartFrame months={months} ticks={[top, Math.round(top / 2), 0]}>
    <svg preserveAspectRatio="none" className="block h-[200px] w-full overflow-visible" viewBox={`0 0 ${W} ${H}`} role="img" aria-label={label}>
      {[0, 0.5, 1].map((f) => (
        <line key={f} x1={L} x2={W - R} y1={y(top * f)} y2={y(top * f)} stroke="var(--border)" vectorEffect="non-scaling-stroke" />
      ))}
      {months.map((m, i) => {
        let acc = 0;
        const xs = L + step * i + (step - bw) / 2;
        return (
          <a key={m} href={`/poc/housing-board${href(m)}`} className="cursor-pointer focus-visible:outline-none [&:hover_rect:first-of-type]:fill-foreground/10 [&:focus-visible_rect:first-of-type]:fill-foreground/10">
            <title>{`${ymDot(m)}${provisional.includes(m) ? ' (잠정)' : ''} — ` + stacks.map((s) => `${s.label} ${s.values[i] === null ? '알 수 없음' : s.values[i]!.toLocaleString('en-US') + '호'}`).join(' · ')}</title>
            <rect x={L + step * i} y={T} width={step} height={H - T - B} fill="transparent" />
            {/* 첫 화면: 달마다 바닥에서 솟는다(조용한 등장 q-grow-y, 차례는 달 순서) */}
            <g className="q-grow-y" style={{ ['--i' as string]: i * 0.3 }}>
            {stacks.map((s) => {
              const v = s.values[i] ?? 0;
              const h = (H - T - B) * (v / top);
              acc += v;
              return h > 0 ? <rect key={s.key} x={xs} y={y(acc)} width={bw} height={h} fill={s.color} /> : null;
            })}
            </g>
          </a>
        );
      })}
    </svg>
    </ChartFrame>
  );
}
