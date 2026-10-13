/* 6단계 범례: 실적 지표(통계누리 인허가·착공·분양·준공) 범례를 공급 6단계 틀에 놓는다(계획서 11절 "6단계가 아닌 3단·4단 표기를 고쳐").
   지표가 있는 단계는 지표 색 견본, 없는 단계는 점선 견본 + '자료 없음'으로 자리만 보인다.
   names 'official' 은 공식 6단계(01 정책~06 입주, METRIC_STAGE 대응), 'board' 는 종합상황판 리본의 이름(①계획~⑥입주, 사용자 결정 '지금 그대로'). */
import { cn } from 'cn';
import { METRIC_COLOR } from './palette';
import { METRIC_LABEL, METRIC_STAGE, STAGES } from '../../lib/board/stages';
import { CIR, K } from '../../lib/board/sample';
import type { Metric } from '../../lib/board/types';

/* 리본 이름에서 지표의 자리: ②인허가 ③착공 ④모집(분양) ⑤준공. ①계획·⑥입주는 통계누리에 없다 */
const ON_BOARD: Record<Metric, number> = { permit: 1, start: 2, sale: 3, complete: 4 };

export default function StageLegend({ metrics, names = 'official' }: { metrics: readonly Metric[]; names?: 'official' | 'board' }) {
  return (
    <ul className="m-0 mt-2 flex list-none flex-wrap gap-x-[14px] gap-y-1.5 p-0 text-[14px] text-foreground" aria-label="범례 · 공급 6단계">
      {STAGES.map((s, i) => {
        const k = metrics.find((m) => (names === 'board' ? ON_BOARD[m] === i : METRIC_STAGE[m] === s.code));
        const stage = names === 'board' ? K[i] : s.name;
        return (
          <li key={s.code} className={cn('flex items-center gap-1.5', !k && 'text-muted-foreground')}>
            <i className={cn('block size-[11px] rounded-[3px]', !k && 'border-[1.5px] border-dashed border-line2')} style={k ? { background: METRIC_COLOR[k] } : undefined} aria-hidden="true" />
            <span className="tabular-nums">{names === 'board' ? CIR[i] : s.code}</span>{stage}{k && METRIC_LABEL[k] !== stage ? `(${METRIC_LABEL[k]})` : ''}
            {k ? null : <span className="text-[12px]">자료 없음</span>}
          </li>
        );
      })}
    </ul>
  );
}
