/* 종합상황판 시안의 팔레트(단계 색)에서 가져온 차트 색. 값은 테마별 CSS 변수(app/tailwind.css 의 --st-* · --actor-*)다. 색만으로 구분하지 않도록 차트마다 범례·값 글자를 함께 둔다. */
import type { Actor, Metric } from '../../lib/board/types';

/* 실적 지표는 종합상황판 리본의 같은 단계 색을 쓴다: 인허가·착공·분양(모집)·준공 */
export const METRIC_COLOR: Record<Metric, string> = { permit: 'var(--st-permit)', start: 'var(--st-build)', complete: 'var(--st-soon)', sale: 'var(--st-sale)' };
export const ACTOR_COLOR: Record<Actor, string> = { 지자체: 'var(--actor-local)', LH: 'var(--actor-lh)', 주택업체: 'var(--actor-builder)', 민간: 'var(--actor-private)' };
