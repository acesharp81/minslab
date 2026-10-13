/* PoC 12 공개 범위: PoC 10에서 확인한 9·7 정책 연결 제안만 사용한다.
   REVIEW 연결은 확정 사업이나 정책 실적으로 승격하지 않는다. */
import { home10 } from './data';

export const POLICY_ID = 'POL_2025_0907';
export const policy = home10.policies.find((item) => item.id === POLICY_ID)!;
export const policyProjects = home10.projects.filter((item) => item.policyId === POLICY_ID);
export type PolicyProject = (typeof policyProjects)[number];
export const policyProjectById = new Map(policyProjects.map((item) => [item.id, item]));
export const policyMonitor = home10.policyMonitor.items.find((item) => item.id === POLICY_ID)!;
export const policyProgramIds = new Set(policyProjects.map((item) => item.programId));
export const policyPrograms = home10.programs.filter((item) => policyProgramIds.has(item.id));
export const policySourceIds = new Set(policyProjects.map((item) => item.sourceId));
export const policySources = home10.sources.filter((item) => policySourceIds.has(item.id));
type CoverageRow = {
  sourceId: string | null;
  region: string | null;
  sourcePeriod: string | null;
  fetchedCount: number | null;
  populationStatus: string | null;
};
export const policyCoverage = (home10.coverage as CoverageRow[]).filter((item) => item.sourceId !== null && policySourceIds.has(item.sourceId));
export const located = (item: PolicyProject) => item.locationRole === 'LH_PUBLIC_BLOCK_LABEL_POINT'
  && item.longitude !== null && item.latitude !== null;
export const agencyId = (item: PolicyProject) => item.sourceId.startsWith('lh_') ? 'lh'
  : item.sourceId.startsWith('gh_') ? 'gh' : item.sourceId.startsWith('sh_') ? 'sh' : 'other';
export const agencies = [
  { id: 'lh', name: 'LH', fullName: '한국토지주택공사' },
  { id: 'gh', name: 'GH', fullName: '경기주택도시공사' },
  { id: 'sh', name: 'SH', fullName: '서울주택도시공사' },
] as const;
export const regions = [
  { id: '11', name: '서울특별시', map: 'home-907-seoul' },
  { id: '41', name: '경기도', map: 'home-907-gyeonggi' },
] as const;
export const count = (predicate: (item: PolicyProject) => boolean) => policyProjects.filter(predicate).length;
export const stageCounts = Object.fromEntries(['01', '02', '03', '04', '05', '06'].map((code) => [code, count((item) => item.stageCode === code)]));
export const completionYears = [...new Set(policyProjects.flatMap((item) => item.completionPlanDate ? [item.completionPlanDate.slice(0, 4)] : []))]
  .sort().map((year) => ({ year, count: count((item) => item.completionPlanDate?.startsWith(year) ?? false) }));
export const policyStats = {
  candidates: policyProjects.length,
  located: count(located),
  progress: count((item) => item.progressPct !== null),
  plannedUnits: count((item) => item.plannedUnits !== null),
  completionDate: count((item) => item.completionPlanDate !== null),
  actualDelivery: count((item) => item.actualDeliveryUnits !== null),
  review: count((item) => item.projectProgramStatus === 'REVIEW'),
};
