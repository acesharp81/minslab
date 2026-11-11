#!/usr/bin/env python3
"""Revalidate saved real model output; no network, model calls, or business writes."""
import argparse
from pathlib import Path
import json,sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.evidence_chain import validate_assessment,save_case
from backend.ai_collection_store import Store


def main():
    p=argparse.ArgumentParser();p.add_argument('--work-dir',type=Path,required=True);p.add_argument('--out-dir',type=Path,required=True);args=p.parse_args()
    responses=json.loads((args.work_dir/'model-responses.json').read_text())
    source=json.loads((args.work_dir/'incomplete-case.json').read_text())
    documents=json.loads((args.work_dir/'sources.json').read_text())
    final=next(r for r in reversed(responses) if 'findings' in r['response'])
    assessment=validate_assessment(final['response'],source['project_id'],documents)
    assessment['requested_stage_present']=any(f['stage']==source['research_plan']['stage'] for f in assessment['findings'])
    case=dict(source,original_execution_error=source.get('error'),execution_mode='REAL_DATA_OFFLINE_VALIDATION_REPLAY',
        original_execution_mode=source['execution_mode'],assessment=assessment,sources=documents,
        replay_model_calls=0,model_calls=responses,
        summary=dict(linked=assessment['linked'],held=assessment['held'],unique_stage_count=assessment['unique_stage_count'],
                     verified_citations=assessment['verified_citation_count'],source_documents=len(documents),
                     actuals_added=0,rule_repeat_model_calls=0,real_model_calls=len(responses)))
    case.pop('error',None)
    args.out_dir.mkdir(parents=True,exist_ok=True)
    case=save_case(Store(args.out_dir),case)
    (args.out_dir/'case.json').write_text(json.dumps(case,ensure_ascii=False,indent=2))
    print(json.dumps(dict(case_id=case['id'],status='REPLAYED_WITH_HOLDS' if assessment['held'] else 'REPLAYED',summary=case['summary']),ensure_ascii=False))


if __name__=='__main__':main()
