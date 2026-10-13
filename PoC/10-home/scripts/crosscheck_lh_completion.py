"""Read-only review proposals between an older HOME project export and LH forecast rows.

Usage: python -m scripts.crosscheck_lh_completion OLD_EXPORT.zip NEW_EXPORT_DIR OUTPUT.json
No database updates or administrator approvals are performed.
"""
import gzip
import json
import re
import sys
import zipfile
from collections import defaultdict, Counter
from pathlib import Path


def normal(value, block=False):
    text = re.sub(r'[^가-힣A-Za-z0-9]', '', value or '').lower()
    return text.removesuffix('bl') if block else text


def crosscheck(projects, forecasts):
    indexed = defaultdict(list)
    for project in projects:
        row = project['data']
        key = (row.get('region'), normal(row.get('district')), normal(row.get('block'), True))
        if all(key):
            indexed[key].append(project)
    proposals = []
    for forecast in forecasts:
        row = forecast['payload']
        key = (row['region'], normal(row.get('district')), normal(row.get('block'), True))
        matches = indexed.get(key, [])
        match_rows = [dict(project_id=p['id'], project_source_id=p['source_id'],
            name=p['data']['name'], planned_units=p['data'].get('planned_units'),
            project_mapping_status=p.get('link', {}).get('program_project_status'),
            policy_program_status=p.get('link', {}).get('policy_program_status')) for p in matches]
        proposals.append(dict(forecast_entity_id=forecast['entity_id'],
            forecast_name=row['name'], region=row['region'], district=row['district'],
            block=row['block'], completion_plan_date=row.get('completion_plan_date'),
            forecast_units=row.get('planned_units'), matches=match_rows,
            review_status='REVIEW' if matches else 'UNMATCHED',
            unit_comparison=('EQUAL' if row.get('planned_units') == matches[0]['data'].get('planned_units')
                else 'DIFFERENT') if len(matches) == 1 else None))
    counts = Counter(len(p['matches']) for p in proposals)
    return {'rule': 'region + district + block exact after removing spaces/punctuation and terminal BL; no name synonym or unit inference',
            'approval_effect': 'NONE', 'forecast_rows': len(proposals),
            'unique_candidate': counts[1], 'ambiguous_candidate': sum(n for k,n in counts.items() if k>1),
            'unmatched': counts[0],
            'unique_unit_different': sum(p['unit_comparison']=='DIFFERENT' for p in proposals),
            'proposals': proposals}


def main(old_zip, new_export, output):
    with zipfile.ZipFile(old_zip) as archive:
        name = next(name for name in archive.namelist() if name.endswith('/current_projects.json'))
        projects = json.loads(archive.read(name))
    with gzip.open(Path(new_export)/'revisions/lh_completion_plan.json.gz', 'rt') as stream:
        forecasts = json.load(stream)
    result = crosscheck(projects, forecasts)
    output = Path(output)
    if output.exists():
        raise SystemExit(f'기존 파일은 덮어쓰지 않습니다: {output}')
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n')
    print({key: result[key] for key in ('forecast_rows','unique_candidate','ambiguous_candidate','unmatched','unique_unit_different')})


if __name__ == '__main__':
    if len(sys.argv) != 4:
        raise SystemExit(__doc__)
    main(*sys.argv[1:])
