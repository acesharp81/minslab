#!/usr/bin/env python3
"""Offline/read-only verification. Uses Python stdlib; never opens DB/network."""
from pathlib import Path
import importlib.util,json,tempfile,zipfile,hashlib
from task_span_contract import verified_task_spans
P=Path(__file__).resolve().parent.parent; E=P/'evidence'
path=P/'tools/home-contract/tools/ledger/home-slice.py'
spec=importlib.util.spec_from_file_location('home_slice',path); module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
contract=module.load_spec()
with tempfile.TemporaryDirectory(prefix='challenge-receiver-') as tmp:
    base=Path(tmp).resolve()
    archive = E/'home-slices-submission-redacted.zip'
    if not archive.exists(): archive = E/'home-slices-existing.zip'
    with zipfile.ZipFile(archive) as z:
        for name in z.namelist():
            if not (base/name).resolve().is_relative_to(base): raise ValueError('unsafe archive member')
        z.extractall(base)
    manifest,_,data=module.read_package(contract,str(base))
    for definition in contract['slices']:
        s=module.Slice(definition)
        for i,row in enumerate(data[s.name]): s.check_row(row,f'{s.name}:{i}')
report=json.loads((E/'national-interior-report.json').read_text()); transcript=json.loads((E/'national-interior-transcript.json').read_text())
brief=report.get('structured_brief') or report['brief'];tasks=brief['tasks']
valid=sum(bool(verified_task_spans(task,transcript['utterances'])) for task in tasks)
result={'home':{'archive':archive.name,'format':manifest['format'],'slice_types':len(data),'rows':sum(map(len,data.values())),'manifest_files':len(manifest['files']),'sha_and_fields':'PASS','delta_apply':'NOT_RUN_NO_BASE_EDITION'},'national':{'tasks':len(tasks),'verified_source_spans':valid,'remaining':len(tasks)-valid,'meaning_accuracy':'NOT_MEASURED'},'model_calls':0,'database_writes':0}
assert result['home']['slice_types']==31 and result['home']['rows']==39359
assert (len(tasks),valid)==(66,62)
print(json.dumps(result,ensure_ascii=False,indent=2))
