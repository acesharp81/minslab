/* 데이터 원본(/sources) 표의 행을 눌렀을 때 펼치는 실제 레코드 예시(서버 전용). 원천 파일·지역 번들·로컬 캐시(.cache)에서 앞의 10건을 그대로 보인다.
   원본 파일(data/raw·data/processed)과 캐시는 배포에 올라가지 않아 운영 화면에서는 그 행에 예시가 없다(번들·레지스트리는 있다). 시험: tests/js/pipeline.test.cjs */
import { readFileSync, readdirSync } from 'node:fs';
import path from 'node:path';
import type { Col, Detail, Row } from '../grid/spec';

export const SAMPLE_N = 10;
const MAX_COLS = 20;   // 보관 CSV 는 최대 18열이라 모두 보인다
type Rec = Record<string, unknown>;

/* 레코드 → 예시 표. 열은 keys 를 주면 그것, 아니면 예시에서 값이 있는 글자·숫자 칸(최대 20열). 글은 자르지 않고, 배열·객체는 개수만 */
export function detailOf(records: Rec[], source: string, opts: { keys?: string[]; total?: number } = {}): Detail | undefined {
  const sample = records.slice(0, SAMPLE_N);
  if (!sample.length) return undefined;
  const keys = (opts.keys ?? [...new Set(sample.flatMap((r) => Object.keys(r)))].filter((k) => sample.some((r) => { const v = r[k]; return v !== null && v !== undefined && v !== '' && typeof v !== 'object'; }))).slice(0, MAX_COLS);
  const num = (k: string) => sample.every((r) => r[k] === null || r[k] === undefined || typeof r[k] === 'number');
  const cols: Col[] = keys.map((k) => ({ key: k, label: k, kind: num(k) ? 'int' : 'text' }));
  const cell = (v: unknown) => v === null || v === undefined || v === '' ? null : typeof v === 'number' ? v : Array.isArray(v) ? `[${v.length}]` : typeof v === 'object' ? '{…}' : String(v);
  const rows: Row[] = sample.map((r, i) => ({ id: String(i), c: Object.fromEntries(keys.map((k) => [k, cell(r[k])])) }));
  return { cols, rows, total: opts.total ?? records.length, source };
}

const ROOT = process.cwd();
const readText = (rel: string): string | null => {
  let buf: Buffer;
  try { buf = readFileSync(path.join(ROOT, rel)); } catch { return null; }
  if (buf[0] === 0xef && buf[1] === 0xbb && buf[2] === 0xbf) return buf.subarray(3).toString('utf8');
  try { return new TextDecoder('utf-8', { fatal: true }).decode(buf); } catch { return new TextDecoder('euc-kr').decode(buf); }   // 공공데이터포털 CSV 다수가 CP949
};
export const readJson = (rel: string): Rec | null => { const t = readText(rel); try { return t ? JSON.parse(t) : null; } catch { return null; } };

/* CSV(따옴표 안 쉼표·줄바꿈 처리) → 머리 줄을 열 이름으로 한 레코드. 값은 원본 글자 그대로(연도에 쉼표가 붙지 않게). 전체 건수는 데이터 줄 수 */
export function csvDetail(rel: string): Detail | undefined {
  const text = readText(rel);
  if (!text) return undefined;
  const rows: string[][] = [];
  let row: string[] = [], f = '', q = false;
  for (let i = 0; i < text.length; i++) {
    const ch = text[i];
    if (q) { if (ch === '"') { if (text[i + 1] === '"') { f += '"'; i++; } else q = false; } else f += ch; continue; }
    if (ch === '"') q = true;
    else if (ch === ',') { row.push(f); f = ''; }
    else if (ch === '\n' || ch === '\r') { if (ch === '\r' && text[i + 1] === '\n') i++; row.push(f); f = ''; if (row.some((x) => x !== '')) rows.push(row); row = []; }
    else f += ch;
  }
  if (f !== '' || row.length) { row.push(f); if (row.some((x) => x !== '')) rows.push(row); }
  const [head, ...body] = rows;
  if (!head) return undefined;
  const keys = head.map((h, i) => h.trim() || `열${i + 1}`);
  const recs = body.slice(0, SAMPLE_N).map((r) => Object.fromEntries(keys.map((k, i) => [k, (r[i] ?? '').trim()])));
  return detailOf(recs, rel.split('/').pop()!, { keys: keys.slice(0, MAX_COLS), total: body.length });
}

/* 로컬 캐시(.cache, 24시간 보관)의 값을 API(키 앞부분 — handlers/** 의 cache.wrap 키)별로 모은다: 응답 수와 그 응답들에 들어 있던 레코드 */
export function cacheRecords(): { records: Record<string, Rec[]>; responses: Record<string, number> } {
  const out: Record<string, Rec[]> = {}, responses: Record<string, number> = {};
  const dir = path.join(ROOT, '.cache');
  let files: string[] = [];
  try { files = readdirSync(dir).sort(); } catch { return { records: out, responses }; }
  for (const file of files) {
    if (!file.endsWith('.json') || file === 'key-usage.json') continue;
    let e: { key?: unknown; value?: unknown };
    try { e = JSON.parse(readFileSync(path.join(dir, file), 'utf8')); } catch { continue; }
    if (typeof e.key !== 'string') continue;
    const [api, ...rest] = e.key.split(':'), key = rest.join(':'), v = e.value;
    const o = v && typeof v === 'object' && !Array.isArray(v) ? v as Rec : null;
    const geom = (g: unknown) => { const x = g as { type?: string; coordinates?: unknown } | undefined; return { type: x?.type ?? null, points: JSON.stringify(x?.coordinates ?? []).split('],[').length }; };
    const list: Rec[] = Array.isArray(v) ? v as Rec[]
      : api === 'terrain' ? [{ tile: key, bytes: typeof v === 'string' ? v.length : null }]
      : api === 'parcel' ? (o?.none ? [] : [{ pnu: key, ...geom(o?.geometry) }])
      : api === 'vw' ? [{ key, ...geom(o?.geometry), ...(o?.props as Rec ?? {}) }]
      : api === 'plat' ? Object.entries(o ?? {}).map(([mgm, area]) => ({ bjd: key, mgmHsrgstPk: mgm, platArea: area as number }))
      : api === 'bus' ? [{ key, at: (o?.body as Rec)?.at ?? null, ttl: (o?.body as Rec)?.ttl ?? null, buses: ((o?.body as Rec)?.buses as unknown[] ?? []).length }]
      : Array.isArray(o?.features) ? (o!.features as { properties?: Rec }[]).map((x) => ({ ...(x.properties ?? {}) }))
      : Array.isArray(o?.stops) ? o!.stops as Rec[]
      : o ? [o] : [];
    (out[api] ??= []).push(...list);
    responses[api] = (responses[api] ?? 0) + 1;
  }
  return { records: out, responses };
}
