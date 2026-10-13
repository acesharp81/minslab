import PanelLink from './PanelLink';
/* 종합상황판의 실데이터 위젯: 월별 실적 흐름(전국). 서버 컴포넌트가 data/board 의 값을 읽어 그린다. Board 가 '전국 17개 시도'와 같은 줄에 둔다. */
import { cn } from 'cn';
import { sub } from '../page';
import { Card } from '../ui/card';
import StageLegend from '../charts/StageLegend';
import MonthLines from '../charts/MonthLines';
import { METRIC_COLOR } from '../charts/palette';
import { METRICS, NATION, isProvisional, lastMonth, monthLabel, seriesOf } from '../../lib/board/calc';
import { molit } from '../../lib/board/data';
import { Real } from './tags';
import { pacts, phead, ptSmall, ptitle } from './styles';

const LABEL = { permit: '인허가', start: '착공', complete: '준공', sale: '분양' } as const;

export default function RealPanels() {
  const last = lastMonth(molit);
  const lines = METRICS.map((k) => ({ key: k, label: LABEL[k], color: METRIC_COLOR[k], values: seriesOf(molit, k, NATION).total }));
  return (
    <Card variant="board" render={<section id="p-actual" aria-label="월별 실적 흐름" />}>
      <div className={phead}>
        <h2 className={ptitle}>월별 실적 흐름 <Real title="국토교통 통계누리 주택건설실적통계" /> <small className={ptSmall}>· 전국 · 호 · 빗금은 잠정치</small></h2>
        <span className={pacts}><PanelLink href="/area" full="지역별 실적">지역별</PanelLink><PanelLink href={`/month/${last}`} full={`${monthLabel(last)} 월 상세`}>{Number(last.slice(5))}월</PanelLink></span>
      </div>
      <StageLegend metrics={METRICS} names="board" />
      <MonthLines months={molit.months} lines={lines} provisional={molit.provisional} href={(ym) => `/month/${ym}`} label={`전국 월별 인허가·착공·분양·준공 호수, ${molit.months[0]}부터 ${last}까지`} />
      <p className={cn(sub, 'mt-2')}>통계누리 · 자료 {molit.months[0].replace('-', '.')} ~ {last.replace('-', '.')}{isProvisional(molit, last) ? '(2026.01~ 잠정치)' : ''}. 그래프의 달을 누르면 월 상세로 내려갑니다.</p>
    </Card>
  );
}
