import type { ReactNode } from 'react';
import { Badge } from './ui/badge';
import { Card } from './ui/card';

export function Kpi({ label, value, unit = '호', sub, tone }: { label: string; value: ReactNode; unit?: string; sub?: ReactNode; tone?: string }) {
  return (
    <Card variant="kpi">
      <span className="flex items-center gap-1.5 text-[14px] text-muted-foreground"><i className="block size-[9px] rounded-[3px] bg-line2" style={tone ? { background: tone } : undefined} aria-hidden="true" />{label}</span>
      <b className="font-display text-[32px] leading-[1.2] font-normal tabular-nums">{value}<small className="ml-[3px] font-sans text-[14px] font-normal text-muted-foreground">{unit}</small></b>
      {sub ? <span className="text-[14px] text-muted-foreground">{sub}</span> : null}
    </Card>
  );
}

export const Prov = () => <Badge variant="warn" className="ml-1.5" title="통계누리가 잠정치로 낸 달입니다. 확정치는 2027년 9월 공표 예정">잠정</Badge>;

/* 이 화면이 읽는 원천과 기준일. 수집일과 원천 기준을 섞지 않는다(스펙 9.3). */
export function Basis({ children }: { children: ReactNode }) {
  return <p className="mt-2.5 mb-0 text-[14px] text-muted-foreground [&_a]:text-primary">{children} <a href="/poc/housing-board/sources">데이터 원본</a></p>;
}
