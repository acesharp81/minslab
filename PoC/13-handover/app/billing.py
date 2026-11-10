"""Persistent per-key token estimates; never represents provider account balance."""
import hashlib
import re
from decimal import Decimal
from urllib.parse import urlsplit
import httpx
from .store import now, uid

# Published list rates, USD / 1M tokens. Store integer nano-USD per token.
RATES = {'solar-pro4': (300, 60, 1200), 'solar-mini4': (100, 10, 400)}

class Meter:
    def __init__(self, store, allowance='100', shared=None):
        self.store = store
        self.shared = shared
        self.allowance = int(Decimal(str(allowance)) * 1_000_000_000)
        if self.allowance <= 0:
            raise ValueError('HANDOVER_LLM_BUDGET_USD must be positive')
        with store.connect(write=True) as db:
            db.execute('CREATE TABLE IF NOT EXISTS llm_accounts (fingerprint TEXT PRIMARY KEY, created TEXT)')
            db.execute('''CREATE TABLE IF NOT EXISTS llm_costs (
              id TEXT PRIMARY KEY, fingerprint TEXT, created TEXT, operation TEXT, model TEXT,
              status TEXT, prompt INTEGER, cached INTEGER, completion INTEGER, nano_usd INTEGER)''')
            db.execute('CREATE INDEX IF NOT EXISTS llm_cost_key ON llm_costs(fingerprint)')

    def account(self, config):
        fingerprint = hashlib.sha256((config['url'].rstrip('/')+'\0'+config['key']).encode()).hexdigest()
        with self.store.connect(write=True) as db:
            db.execute('INSERT OR IGNORE INTO llm_accounts VALUES (?,?)', (fingerprint, now()))
        return fingerprint

    def start(self, config, operation, payload=None):
        key = self.account(config)
        event = uid()
        if self.shared:self.shared.reserve(event,config,payload or {})
        with self.store.connect(write=True) as db:
            db.execute('INSERT INTO llm_costs VALUES (?,?,?,?,?,?,?,?,?,?)',
                       (event, key, now(), operation, config['model'], 'UNKNOWN', None, None, None, None))
        return event

    def finish(self, event, config, response):
        try:self._finish_local(event,config,response)
        finally:
            if self.shared:self.shared.finish(event,config,response)

    def _finish_local(self, event, config, response):
        try:
            data = response.json()
            usage = data['usage']
            prompt, completion = usage['prompt_tokens'], usage['completion_tokens']
            cached = (usage.get('prompt_tokens_details') or {}).get('cached_tokens', 0)
            if any(type(v) is not int or v < 0 for v in (prompt, completion, cached)) or cached > prompt:
                return
            resolved = data.get('model', config['model'])
            if not isinstance(resolved, str) or not re.fullmatch(re.escape(config['model'])+r'(?:-\d{6,8})?', resolved) or urlsplit(config['url']).hostname != 'api.upstage.ai':
                return
            input_rate, cache_rate, output_rate = RATES[config['model']]
            cost = (prompt-cached)*input_rate + cached*cache_rate + completion*output_rate
        except (KeyError, TypeError, ValueError, AttributeError):
            return
        with self.store.connect(write=True) as db:
            db.execute("UPDATE llm_costs SET status='ESTIMATED',prompt=?,cached=?,completion=?,nano_usd=? WHERE id=?",
                       (prompt, cached, completion, cost, event))

    def summary(self, config):
        if not config.get('key'):
            return {'available': False}
        key = self.account(config)
        row = self.store.one('''SELECT COUNT(*) calls, COALESCE(SUM(nano_usd),0) used,
            COALESCE(SUM(CASE WHEN status='UNKNOWN' THEN 1 ELSE 0 END),0) unknown_calls,
            COALESCE(SUM(prompt),0) prompt_tokens, COALESCE(SUM(cached),0) cached_tokens,
            COALESCE(SUM(completion),0) completion_tokens FROM llm_costs WHERE fingerprint=?''', (key,))
        since = self.store.one('SELECT created FROM llm_accounts WHERE fingerprint=?', (key,))['created']
        result = {'available': True, 'estimated': True, 'budget_usd': self.allowance/1e9,
                'used_usd': row.pop('used')/1e9, 'tracked_since': since, **row,
                'model': config['model'], 'console_url': 'https://console.upstage.ai/billing',
                'pricing_url': 'https://www.upstage.ai/pricing/api',
                'note': '정가 기준 추정입니다. 집계 시작 이전·다른 앱의 사용액, 할인·세금은 반영하지 않습니다. 사용량 미확인 호출은 차감액에 포함되지 않습니다. 실제 잔액은 Upstage 콘솔에서 확인하세요.'}
        if self.shared:
            shared=self.shared.summary(config)
            if shared:result.update(own_used_usd=result['used_usd'],**shared)
        return result


def completion_request(config, payload, timeout, operation):
    meter = config.get('_meter')
    event = meter.start(config, operation, payload) if meter else None
    response=None
    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.post(config['url'].rstrip('/')+'/chat/completions',
                                   headers={'Authorization': 'Bearer '+config['key']}, json=payload)
        return response
    finally:
        if meter:meter.finish(event, config, response)
