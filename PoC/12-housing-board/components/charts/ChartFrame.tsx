import type { ReactNode } from 'react';

/* SVG의 좌표계와 독립된 HTML 눈금: 두 칸으로 줄어도 글자는 13px로 유지한다. */
export default function ChartFrame({ months, ticks, children }: { months: string[]; ticks: number[]; children: ReactNode }) {
  const firstJanuary = months.findIndex(m => m.endsWith('-01'));
  return (
    <div data-slot="chart-frame" className="relative mt-3 rounded-[10px] border border-border bg-chartbg pt-4 pr-5 pb-10 pl-[72px]">
      <div aria-hidden="true" className="pointer-events-none absolute top-4 bottom-10 left-0 w-[64px] text-[13px] leading-none text-mute">
        {ticks.map((v, i) => <span key={i} data-slot="chart-axis" className="absolute right-0 -translate-y-1/2 whitespace-nowrap tabular-nums" style={{ top: `${i / (ticks.length - 1) * 100}%` }}>{v.toLocaleString('en-US')}</span>)}
      </div>
      {children}
      <div aria-hidden="true" className="pointer-events-none absolute right-5 bottom-3 left-[72px] h-4 text-[13px] leading-none text-mute">
        {months.map((m, i) => m.endsWith('-01') || (i === 0 && (firstJanuary < 0 || firstJanuary >= 7)) ? <span key={m} data-slot="chart-axis" className="absolute -translate-x-1/2 whitespace-nowrap tabular-nums" style={{ left: `${(i + 0.5) / months.length * 100}%` }}>{m.slice(0, 4)}</span> : null)}
      </div>
    </div>
  );
}
