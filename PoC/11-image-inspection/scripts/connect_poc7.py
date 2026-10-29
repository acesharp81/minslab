"""One-time local integration; deployed runtime never reads another PoC folder.
Run: .venv/bin/python scripts/connect_poc7.py /absolute/path/to/PoC7/.env [--initialize]
Requires an accessible PoC7 PostgreSQL URL or the existing local Docker DB.
"""
from pathlib import Path
import argparse,json,subprocess,sys
from urllib.parse import urlsplit,urlunsplit
from datetime import datetime,timezone
from calendar import monthrange
from zoneinfo import ZoneInfo
from dotenv import dotenv_values,set_key
import psycopg
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.config import ROOT
parser=argparse.ArgumentParser();parser.add_argument('poc7_env');parser.add_argument('--initialize',action='store_true');args=parser.parse_args()
v=dotenv_values(args.poc7_env);target=ROOT/'.env'
if v.get('OPENROUTER_METER_TOKEN'):set_key(target,'USAGE_METER_TOKEN',v['OPENROUTER_METER_TOKEN'])
url=v.get('DATABASE_URL','').replace('postgresql+psycopg://','postgresql://')
parts=urlsplit(url)
if parts.hostname in ('db','localhost','127.0.0.1'):
    result=subprocess.run(['sudo','-n','docker','inspect','poc07-national-assembly-db'],capture_output=True,text=True,check=True)
    info=json.loads(result.stdout)[0];ip=next(x['IPAddress'] for x in info['NetworkSettings']['Networks'].values() if x.get('IPAddress'))
    userinfo=parts.netloc.rsplit('@',1)[0] if '@' in parts.netloc else ''
    url=urlunsplit((parts.scheme,userinfo+'@'+ip+':5432',parts.path,parts.query,parts.fragment))
if not url:raise SystemExit('PoC7 DATABASE_URL is missing.')
set_key(target,'SHARED_BUDGET_DATABASE_URL',url)
grant=v.get('OPENAI_CREDIT_GRANT_ID','');expiry=v.get('OPENAI_CREDIT_EXPIRES_AT','');amount=v.get('OPENAI_CREDIT_BUDGET_USD','0')
for k,value in [('SHARED_CREDIT_GRANT_ID',grant),('SHARED_CREDIT_EXPIRES_AT',expiry),('SHARED_CREDIT_BUDGET_USD',amount)]:set_key(target,k,value)
for k,source in [('SHARED_CREDIT_MONTH_END_RENEWAL','OPENAI_CREDIT_MONTH_END_RENEWAL'),('SHARED_CREDIT_MONTHLY_BUDGET_USD','OPENAI_CREDIT_MONTHLY_BUDGET_USD')]:set_key(target,k,v.get(source,'false' if 'RENEWAL' in k else '0'))
target.chmod(0o600)
with psycopg.connect(url,connect_timeout=5) as c:
    exists=c.execute("SELECT to_regclass('openai_credit_grant_usage')").fetchone()[0]
    if not exists:raise SystemExit('Existing PoC7 shared credit ledger is missing; no changes made.')
    if args.initialize:
        c.execute((ROOT/'deploy/shared-token-reservations.sql').read_text())
        c.execute('''CREATE TABLE IF NOT EXISTS poc11_credit_reservations(
            event_id text PRIMARY KEY,grant_id text NOT NULL,reserved_usd numeric(18,8) NOT NULL,
            settled boolean NOT NULL DEFAULT false,created_at timestamptz NOT NULL DEFAULT now())''')
print('PoC7 integration configured. Existing source, collectors and historical data were not changed.')
print('Credit period valid:',bool(expiry and datetime.fromisoformat(expiry.replace('Z','+00:00'))>datetime.now(timezone.utc)))
