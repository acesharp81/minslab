import { DataGrid } from '../ui/data-grid';
import { stageName } from '../../lib/board/stages';
import { located, type PolicyProject } from '../../lib/home10/policy-907';

export default function ProjectTable({ rows, label = '9·7 사업후보' }: { rows: PolicyProject[]; label?: string }) {
  return <DataGrid label={label} virtualize={false}
    cols={[{ key: 'name', label: '사업후보', kind: 'text', wrap: true }, { key: 'region', label: '지역', kind: 'text' }, { key: 'stage', label: '원천 단계', kind: 'text' }, { key: 'units', label: '계획 규모(호)' }, { key: 'progress', label: '원천 공정률' }, { key: 'location', label: '위치 근거', kind: 'text' }, { key: 'source', label: '원천', kind: 'text' }]}
    rows={rows.map((item) => ({ id: item.id, c: {
      name: { text: item.name, href: `/home-project/${item.id}` },
      region: `${item.region} · ${item.municipality ?? '시군구 미확보'}`,
      stage: item.stageCode ? `${item.stageCode} ${stageName(item.stageCode)} · ${item.stageLabel ?? ''}` : { na: '단계 미확인' },
      units: item.plannedUnits ?? { na: '미확인' },
      progress: item.progressPct === null ? { na: '미확인' } : `${item.progressPct}%`,
      location: located(item) ? { text: '지도에서 위치 보기', href: `/map?region=home-907&homeProject=${item.id}` } : { text: '가상 3D 보기 (위치 미확보)', href: `/map?region=home-907&homeProject=${item.id}` },
      source: item.sourceName,
    } }))} />;
}
