import { Badge } from '../ui/badge';

/* 위젯 표지: 시안 수치(SAMPLE)와 실제 자료(실데이터) */
export const Sample = () => <Badge variant="solid" className="ml-2 bg-[var(--sample-bg)] align-middle text-[var(--sample-ink)]" title="시안용 SAMPLE 수치입니다. 실제 자료가 아닙니다.">SAMPLE</Badge>;
export const Real = ({ title }: { title: string }) => <Badge variant="solid" className="ml-2 bg-[var(--real-bg)] align-middle text-ok" title={title}>실데이터</Badge>;
