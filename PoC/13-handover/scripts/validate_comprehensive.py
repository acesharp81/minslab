"""Run the integrated sample offline and publish the resulting report artifacts."""
import json,sys,tempfile
from pathlib import Path
from fastapi.testclient import TestClient
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tests'))
from app.main import create_app
from test_comprehensive import exercise,inspect_source_tables
with tempfile.TemporaryDirectory(prefix='handover-comprehensive-') as temp:
 with TestClient(create_app(Path(temp))) as client:
  result=exercise(client,ROOT/'test-results/comprehensive/verified')
  result['table_extraction']=inspect_source_tables(Path(temp))
  (ROOT/'test-results/comprehensive/verified/validation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
print(json.dumps(result,ensure_ascii=False))
