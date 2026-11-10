"""Deterministic measures against a manually authored synthetic answer sheet."""
import json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.engine import normalize

def measure(items, expected, blocks):
    source={b['id']:b['text'] for d in blocks for b in d['blocks']}
    found={};misses=[];checks=0;passed=0
    for title,fields in expected['expected_tasks'].items():
        matches=[i for i in items if normalize(i['fields']['title']['value'])==normalize(title)]
        if len(matches)==1:found[title]=matches[0]
        for field,wanted in fields.items():
            values=wanted if isinstance(wanted,list) else [wanted]
            for needle in values:
                checks+=1;actual=' / '.join(i['fields'][field]['value'] for i in matches)
                if needle in actual:passed+=1
                else:misses.append({'task':title,'field':field,'expected':needle,'actual':actual})
    refs=[r for i in items for f in i['fields'].values() for r in f['evidence']]
    invalid=[r for r in refs if not r['quote'] or r['quote'] not in source.get(r['block_id'],'')]
    conflicts=found.get('2027년 생활문화 사업계획',{}).get('fields',{}).get('due_date',{}).get('review_status')=='CONFLICT'
    safe_owner=all(wrong not in found.get(title,{}).get('fields',{}).get('owner',{}).get('value','') for title,wrong in expected['forbidden_owner'].items())
    return {'expected_tasks':len(expected['expected_tasks']),'matched_tasks':len(found),'returned_tasks':len(items),'no_extra_or_duplicate_tasks':len(items)==len(expected['expected_tasks'])==len(found),'field_checks':checks,'field_passed':passed,'field_match_percent':round(100*passed/checks,2),'missing_fields':misses,'quotes':len(refs),'invalid_quotes':len(invalid),'due_conflict_preserved':conflicts,'collaborator_not_owner':safe_owner,'no_false_completion':all(i.get('business_status')!='COMPLETED' for i in items)}

if __name__=='__main__':
    root=Path(__file__).resolve().parents[1];folder=Path(sys.argv[1]);rev=json.loads((folder/'revision.json').read_text());sources=json.loads((folder/'sources.json').read_text());gold=json.loads((root/'release/public/expected.json').read_text())
    result=measure(rev['payload']['items'],gold,sources);print(json.dumps(result,ensure_ascii=False,indent=2));(folder/'metrics.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
