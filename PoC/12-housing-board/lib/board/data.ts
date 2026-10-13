/* data/board/*.json 을 읽는 곳(서버 컴포넌트가 쓴다. 클라이언트 번들에는 실리지 않는다). 계산은 calc.ts. */
import lhJson from '../../data/board/lh-completion.json';
import molitJson from '../../data/board/molit.json';
import sourcesJson from '../../data/board/sources.json';
import registryJson from '../../registry/projects.json';
import type { LhData, Molit, RegistryProject, Sources } from './types';

export const molit = molitJson as unknown as Molit;
export const lh = lhJson as unknown as LhData;
export const sources = sourcesJson as unknown as Sources;
export const projects = (registryJson as unknown as { projects: RegistryProject[] }).projects;

/* 사업 레지스트리가 다루는 시군구: 이름은 /api/v1/resolve 응답(행정표준코드)으로 확인한 값이다(2026-10-09). */
export const SGG: Record<string, { name: string; sido: string }> = {
  '11290': { name: '서울특별시 성북구', sido: '11' },
  '12170': { name: '전남광주통합특별시 나주시', sido: '12' },
  '12330': { name: '전남광주통합특별시 광산구', sido: '12' },
  '28245': { name: '인천광역시 계양구', sido: '28' },
  '41450': { name: '경기도 하남시', sido: '41' },
};
