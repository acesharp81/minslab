/* 월별 선 그래프(서버가 SVG 로 그린다). 월마다 /month 로 가는 링크 칸이 있고 키보드로도 닿는다. 값이 없는 달(null)은 선을 끊는다. 잠정치 구간은 빗금. */
import ChartFrame from './ChartFrame';
import { ymDot } from '../../lib/board/calc';

export type Line = { key: string; label: string; color: string; values: (number | null)[] };
const W = 960, H = 240, L = 0, R = 0, T = 0, B = 0;

export default function MonthLines({ months, lines, provisional, href, label }: { months: string[]; lines: Line[]; provisional: string[]; href: (ym: string) => string; label: string }) {
  const max = Math.max(1, ...lines.flatMap((l) => l.values.filter((v): v is number => v !== null)));
  const top = niceMax(max);
  const pw = W - L - R, step = pw / months.length;
  const x = (i: number) => L + step * (i + 0.5), y = (v: number) => T + (H - T - B) * (1 - v / top);
  const prov = months.map((m, i) => (provisional.includes(m) ? i : -1)).filter((i) => i >= 0);
  return (
    <ChartFrame months={months} ticks={[1, 0.75, 0.5, 0.25, 0].map(f => Math.round(top * f))}>
    <div className="relative">
    {/* 잠정치 빗금: SVG 무늬는 가로로만 늘어나는 그래프(preserveAspectRatio none)에서 기울기·굵기가 틀어져 흐려진다 → 그래프 뒤 HTML 띠(45°, 계획서 14절 T3) */}
    {prov.length > 0 ? <div data-slot="chart-prov" aria-hidden="true" className="pointer-events-none absolute inset-y-0 [background:repeating-linear-gradient(45deg,color-mix(in_srgb,var(--muted-foreground)_22%,transparent)_0_2px,transparent_2px_8px)]" style={{ left: `${(L + step * prov[0]) / W * 100}%`, width: `${step * prov.length / W * 100}%` }} /> : null}
    <svg preserveAspectRatio="none" className="relative block h-[240px] w-full overflow-visible" viewBox={`0 0 ${W} ${H}`} role="img" aria-label={label}>
      {[0, 0.25, 0.5, 0.75, 1].map((f) => (
        <line key={f} x1={L} x2={W - R} y1={y(top * f)} y2={y(top * f)} stroke="var(--border)" vectorEffect="non-scaling-stroke" />
      ))}
      {/* 첫 화면: 선이 왼쪽부터 드러난다(조용한 등장 q-sweep, 움직임 줄이기면 없음) */}
      <g className="q-sweep">
      {lines.map((l) => segments(l.values).map((seg, k) => (
        <polyline key={`${l.key}-${k}`} fill="none" stroke={l.color} strokeWidth="2.4" vectorEffect="non-scaling-stroke" strokeLinejoin="round" strokeLinecap="round" points={seg.map(([i, v]) => `${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(' ')} />
      )))}
      </g>
      {months.map((m, i) => (
        <a key={m} href={`/poc/housing-board${href(m)}`} className="cursor-pointer focus-visible:outline-none [&:hover_rect:first-of-type]:fill-foreground/10 [&:focus-visible_rect:first-of-type]:fill-foreground/10">
          <title>{`${ymDot(m)}${provisional.includes(m) ? ' (잠정)' : ''} — ` + lines.map((l) => `${l.label} ${l.values[i] === null ? '알 수 없음' : l.values[i]!.toLocaleString('en-US') + '호'}`).join(' · ')}</title>
          <rect x={L + step * i} y={T} width={step} height={H - T - B} fill="transparent" />
        </a>
      ))}
    </svg>
    </div>
    </ChartFrame>
  );
}

/* null 로 끊기는 구간들: [[인덱스, 값], ...][] */
function segments(values: (number | null)[]) {
  const out: [number, number][][] = [];
  let cur: [number, number][] = [];
  values.forEach((v, i) => { if (v === null) { if (cur.length) out.push(cur); cur = []; } else cur.push([i, v]); });
  if (cur.length) out.push(cur);
  return out;
}
/* 눈금 위쪽 끝을 읽기 좋은 수로(1·2·2.5·5 × 10^n). */
export function niceMax(v: number) {
  const p = Math.pow(10, Math.floor(Math.log10(v)));
  for (const m of [1, 2, 2.5, 5, 10]) if (v <= m * p) return m * p;
  return 10 * p;
}
