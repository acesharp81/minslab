import type { Metadata } from 'next';
import Crumbs from '../../../components/Crumbs';
import StageLadder from '../../../components/StageLadder';
import { Lede, Page, PageTitle } from '../../../components/page';
import { Badge } from '../../../components/ui/badge';
import { Card } from '../../../components/ui/card';
import { Basis } from '../../../components/ui';
import { policyStats, stageCounts } from '../../../lib/home10/policy-907';

export const metadata: Metadata = { title: '9·7 단계별 후보' };
export default function StagePage() { return <Page>
  <Crumbs items={[{ label: '9·7 상황판', href: '/' }, { label: '단계별' }]} />
  <PageTitle>9·7 단계별 후보 <Badge variant="warn">원천 단계</Badge></PageTitle>
  <Lede>PoC 10 사업후보 {policyStats.candidates}건의 원천 상태를 화면 탐색을 위한 6단계에 대응했습니다. 단계 번호는 공식 정책 사업 승인이나 실제 공급 실적을 뜻하지 않습니다.</Lede>
  <Card render={<section aria-label="9·7 단계별 후보 수" />}><StageLadder className="mt-0" counts={stageCounts} />
    <Basis>공급·입주 완료로 확인된 후보는 없습니다. 01 정책은 사업 건수가 아닌 하나의 정책으로 별도 표시합니다. 일정 지연과 단계별 머문 기간은 비교 가능한 이력이 없어 계산하지 않습니다.</Basis>
  </Card>
</Page>; }
