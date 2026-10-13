import { Database, Layers, MapPin, CalendarClock } from 'lucide-react';
import { sources } from '../../lib/board/data';

export default function Overview() {
  const used = sources.items.filter((s) => s.usedBy.length > 0).length;
  const unknownDate = sources.items.filter((s) => !s.sourceAsOf).length;
  const metrics = [
    { label: '수집한 데이터셋', value: sources.items.length, unit: '건', note: '기관 원천 + 지역 지도 번들', href: '#catalog', icon: Database },
    { label: '화면에서 활용', value: used, unit: '건', note: `수집 자료 중 ${Math.round(used / sources.items.length * 100)}% 활용`, href: '#catalog', icon: Layers },
    { label: '수집 후 미활용', value: sources.items.length - used, unit: '건', note: '보관 완료 · 화면 연결 대기', href: '#catalog', icon: MapPin },
    { label: '원천 기준일 미확인', value: unknownDate, unit: '건', note: '자료 최신성 확인 필요', href: '#catalog', icon: CalendarClock },
  ];
  return (
    <div className="mt-5 mb-4">
      <div className="grid grid-cols-4 gap-3 mobile:grid-cols-2 phone:gap-2" aria-label="데이터 현황 요약">
        {metrics.map(({ label, value, unit, note, href, icon: Icon }) => (
          <a key={label} href={href} className="min-w-0 rounded-[14px] border border-border bg-card p-5 text-foreground no-underline shadow-[var(--shadow-card)] hover:border-primary focus-visible:outline-2 focus-visible:outline-primary phone:p-3">
            <span className="flex items-start justify-between gap-2 text-[13px] font-bold text-muted-foreground"><span>{label}</span><Icon className="size-4 flex-none" aria-hidden="true" /></span>
            <span className="mt-2 flex items-baseline gap-1.5"><b className="font-display text-[38px] leading-tight font-normal tabular-nums">{value}</b><span className="text-[14px] text-muted-foreground">{unit}</span></span>
            <span className="mt-2 block text-[12px] leading-[1.5] text-muted-foreground [word-break:keep-all]">{note}</span>
          </a>
        ))}
      </div>

    </div>
  );
}
