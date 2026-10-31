"""Role configuration and append-only decisions, kept separate from business truth."""
import json,time,uuid
from .ai_agent_catalog import ROLES,validate

def init(store):
 with store.db() as c:c.executescript('''
 CREATE TABLE IF NOT EXISTS agent_settings(role TEXT PRIMARY KEY,payload TEXT NOT NULL);
 CREATE TABLE IF NOT EXISTS agent_results(id TEXT PRIMARY KEY,role TEXT NOT NULL,subject TEXT NOT NULL,
    fingerprint TEXT NOT NULL,run_id TEXT NOT NULL,state TEXT NOT NULL,payload TEXT NOT NULL,created REAL NOT NULL);
 CREATE INDEX IF NOT EXISTS agent_results_subject ON agent_results(role,subject,created DESC);
 ''')

def settings(store):
 init(store);base=store.settings()
 model=base.get('selected_model') or ('solar-pro4' if base['profile']=='SOLAR' else 'gpt-5.4-mini')
 values={r:dict(role=r,model=model if r=='collection' else 'solar-pro4',enabled=base['enabled'] if r=='collection' else False,
    review_model='',hour_kst=2 if r=='collection' else 1 if r=='algorithm' else 3,version=0) for r in ROLES}
 with store.db() as c:
  for row in c.execute('SELECT role,payload FROM agent_settings'):values[row[0]]=json.loads(row[1])
 for role,value in values.items():
  if not 1<=value['hour_kst']<5:value['hour_kst']={'algorithm':1,'collection':2,'officer':3}[role]
 return values

def configure(store,role,value):
 if not 1<=value['hour_kst']<5:raise ValueError('자동 일괄 작업은 한국시간 01~05시에 예약하세요')
 validate(role,value['model'])
 if value.get('review_model'):
  from .ai_agent_catalog import NEMO
  if role!='collection' or value['model'] not in ('gpt-5.4-mini',NEMO) or value['review_model'] not in ('gpt-5.4','gpt-6.1-terra'):
   raise ValueError('정밀 검토는 mini/Nemotron 수집의 애매한 건에만 사용할 수 있습니다')
  validate(role,value['review_model'])
 init(store)
 with store.db(True) as c:
  row=c.execute('SELECT payload FROM agent_settings WHERE role=?',(role,)).fetchone()
  previous=json.loads(row[0]) if row else {'version':0}
  if previous['version']!=value['version']:raise ValueError('설정이 변경됐습니다. 새로고침 후 저장하세요')
  data=dict(value,role=role,version=value['version']+1)
  c.execute('INSERT INTO agent_settings VALUES(?,?) ON CONFLICT(role) DO UPDATE SET payload=excluded.payload',(role,json.dumps(data)))
  c.execute('INSERT INTO events(run_id,created,kind,payload) VALUES(?,?,?,?)',('agent-settings',time.time(),'AGENT_SETTINGS',json.dumps(data)))
 return data

def enqueue(store,role,schedule_day=None):
 config=settings(store)[role];meta=validate(role,config['model'])
 return store.enqueue(actor=ROLES[role]+' 실행',schedule_day=schedule_day,overrides=dict(agent_role=role,
     selected_model=config['model'],review_model=config.get('review_model',''),profile=meta['provider'],agent_settings_version=config['version']))

def record(store,role,subject,fingerprint,run_id,state,**payload):
 if state not in ('DONE','HOLD'):raise ValueError('invalid agent decision')
 init(store)
 with store.db(True) as c:c.execute('INSERT INTO agent_results VALUES(?,?,?,?,?,?,?,?)',
   (str(uuid.uuid4()),role,subject,fingerprint,run_id,state,json.dumps(payload,ensure_ascii=False),time.time()))

def latest(store,role):
 init(store)
 with store.db() as c:rows=c.execute('SELECT * FROM agent_results WHERE role=? ORDER BY created DESC',(role,)).fetchall()
 result={}
 for r in rows:
  if r['subject'] not in result:result[r['subject']]={**dict(r),**json.loads(r['payload'])}
 return result


def economics(store):
 """Compare completed two-pass runs with a same-token single-review-model baseline.
 No free grants or unlimited-key discounts enter the comparison. It is an
 estimate, not proof of equivalent output quality or provider billing.
 """
 from .ai_collection_models import RATES
 results=[]
 with store.db() as c:
  for row in c.execute('SELECT id,config FROM runs ORDER BY created DESC LIMIT 20'):
   config=json.loads(row['config']);primary=config.get('selected_model');review=config.get('review_model')
   if primary not in RATES or review not in RATES:continue
   calls=[dict(r) for r in c.execute('SELECT model,input_tokens,output_tokens,cost_usd FROM calls WHERE run_id=?',(row['id'],))]
   first=[r for r in calls if r['model']==primary and r['input_tokens'] is not None and r['output_tokens'] is not None]
   if not first:continue
   ir,orr=RATES[review]
   baseline=sum((r['input_tokens']*ir+r['output_tokens']*orr)/1000000 for r in first)
   actual=sum(r['cost_usd'] or 0 for r in calls)
   unknown=any(r['input_tokens'] is None or r['output_tokens'] is None or r['cost_usd'] is None for r in calls)
   results.append(dict(run_id=row['id'],primary=primary,review=review,first_calls=len(first),
     review_calls=sum(r['model']==review for r in calls),estimated_cost=actual,comparison_cost=baseline,
     estimated_saving_percent=None if unknown or not baseline else round((1-actual/baseline)*100,1),
     note='동일 1차 토큰을 정밀 모델로 단독 처리한 가정 대비 · 품질 동일성/청구액 보장 아님 · 무료/무제한 혜택 제외'))
 return results
