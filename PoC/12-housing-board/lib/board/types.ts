/* data/board/*.json 의 모양(tools/boarddata 가 만든다). */
export type Metric = 'permit' | 'start' | 'complete' | 'sale';
export type Actor = '지자체' | 'LH' | '주택업체' | '민간';

export type Series = { total: (number | null)[]; actors?: Record<Actor, (number | null)[]> };
export type Molit = {
  months: string[];
  provisional: string[];
  sido: { code: string; name: string }[];
  actors: Actor[];
  metrics: Record<Metric, { label: string; unit: string; basis: string; series: Record<string, Series> }>;
};

export type LhBlock = { district: string; block: string; location: string; type: string; units: number; date: string; sido: string };
export type LhData = { sourceAsOf: string; count: number; units: number; blocks: LhBlock[] };

export type Source = {
  id: string; group: string; provider: string; dataset: string; query: Record<string, unknown>;
  collectedAt: string | null; sourceAsOf: string | null; count: number; description: string; license: string | null; usedBy: string[];
};
export type Sources = { items: Source[] };

export type RegistryProject = {
  id: string; name: string; sgg: string; bjdCodes: string[]; pnus?: string[]; stageCode: string; units?: number | null;
  source: { provider: string; dataset: string; url?: string }; asOf: string; issuedAt: string;
};
