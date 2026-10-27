"""Verified free-tier auxiliaries with bounded requests and unchanged validators."""
from __future__ import annotations
import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from typing import Any
import requests
from ..db.connection import connect
from ..db.auxiliary_model_budget import AuxiliaryModelBudget, AuxiliaryUnavailable
from .meeting_brief import OpenRouterMeetingBriefClient, MalformedMeetingBriefResponse, _parse_json_content


def enabled_auxiliaries(settings: Any) -> list[str]:
    return [p for p in ('gemini', 'groq') if getattr(settings, p + '_aux_enabled', False)
            and getattr(settings, p + '_api_key', '')]


_LOCAL_BOUNDS = {'maxItems', 'minItems', 'maxLength', 'minLength'}


def gemini_wire_schema(value: Any) -> Any:
    """Avoid Gemini grammar expansion for large nested array bounds.

    Keep the original contract for local validation; never cut evidence to fit.
    """
    if isinstance(value, list):
        return [gemini_wire_schema(item) for item in value]
    if not isinstance(value, dict):
        return value
    result = {key: gemini_wire_schema(item) for key, item in value.items()
              if key not in _LOCAL_BOUNDS}
    bounds = {key: value[key] for key in _LOCAL_BOUNDS if key in value}
    if bounds:
        result['description'] = (str(value.get('description', '')) +
                                 ' Required limits: ' + json.dumps(bounds, sort_keys=True)).strip()
    return result


def validate_local_bounds(value: Any, schema: dict) -> None:
    """Enforce every bound omitted from Gemini's wire schema without truncation."""
    if isinstance(value, (list, str)):
        suffix = 'Items' if isinstance(value, list) else 'Length'
        if len(value) < schema.get('min' + suffix, 0) or len(value) > schema.get('max' + suffix, float('inf')):
            raise ValueError('AUXILIARY_SCHEMA_BOUND')
    if isinstance(value, list):
        for item in value:
            validate_local_bounds(item, schema.get('items', {}))
    elif isinstance(value, dict):
        for key, item in value.items():
            validate_local_bounds(item, schema.get('properties', {}).get(key, {}))


def cooldown_seconds(provider: str, response: Any) -> int:
    # Plain 429 is a rate limit, never assumed to last all day.
    try:
        seconds = min(86400, max(65, int(response.headers.get('Retry-After', '65'))))
    except (ValueError, TypeError):
        seconds = 65
    body = str(response.text).lower()
    if any(x in body for x in ('tokens per day', 'requests per day', 'perday', 'daily quota', 'daily limit')):
        zone = ZoneInfo('America/Los_Angeles' if provider == 'gemini' else 'UTC')
        now = datetime.now(zone)
        seconds = max(seconds, int(((now + timedelta(days=1)).replace(hour=0,minute=0,second=0,microsecond=0)-now).total_seconds()))
    return seconds


def failure_cooldown(provider: str, response: Any) -> int:
    if response.status_code == 429:
        return cooldown_seconds(provider, response)
    # A bad schema or unavailable model is request-specific. It must not
    # disable every working model on this platform for an hour.
    return 3600 if response.status_code in {401, 403} else 65


class AuxiliaryMeetingBriefClient(OpenRouterMeetingBriefClient):
    def __init__(self, settings: Any, provider: str):
        if provider not in enabled_auxiliaries(settings):
            raise AuxiliaryUnavailable('AUXILIARY_DISABLED')
        self.provider = provider
        self.settings = settings
        super().__init__(getattr(settings, provider + '_api_key'),
                         model=getattr(settings, provider + '_aux_model'),
                         base_url=('https://api.groq.com/openai/v1' if provider == 'groq'
                                   else 'https://generativelanguage.googleapis.com/v1beta'),
                         timeout_seconds=90)

    def output_limit(self, schema: dict) -> int:
        if self.provider == 'groq':
            return 2000
        return 32768 if 'headline' in schema.get('properties', {}) else 8192

    def estimated_request_tokens(self, prompt: str, schema: dict) -> int:
        output_limit = self.output_limit(schema)
        if self.provider == 'gemini':
            schema = gemini_wire_schema(schema)
        return len(prompt.encode()) + len(json.dumps(schema,ensure_ascii=False).encode()) + 512 + output_limit

    def fits_request(self, prompt: str, schema: dict) -> bool:
        return self.estimated_request_tokens(prompt,schema) <= (7000 if self.provider=='groq' else 150000)

    def _post(self, prompt: str, schema: dict, schema_name: str,
              model_override: str | None = None) -> tuple[dict, dict]:
        # Never inherit OpenRouter alternate models or silently truncate evidence.
        output_limit = self.output_limit(schema)
        estimate = self.estimated_request_tokens(prompt,schema)
        if not self.fits_request(prompt,schema):
            raise AuxiliaryUnavailable('AUXILIARY_INPUT_TOO_LARGE')
        s = self.settings
        with connect(s.database_url) as c:
            reservation = AuxiliaryModelBudget(c).reserve(
                self.provider,self.model,estimate,
                token_limit=getattr(s,self.provider+'_aux_daily_tokens'),
                request_limit=getattr(s,self.provider+'_aux_daily_requests'),
                interval=65 if self.provider=='groq' else 15,
                zone='UTC' if self.provider=='groq' else 'America/Los_Angeles')
        metadata: dict[str, Any] = {'provider':self.provider,'model':self.model}
        status = 'UNKNOWN'
        try:
            if self.provider == 'groq':
                body = {'model':self.model,'messages':[{'role':'user','content':prompt}],
                        'reasoning_effort':'low','max_completion_tokens':output_limit,
                        'response_format':{'type':'json_schema','json_schema':{
                            'name':schema_name,'strict':True,'schema':schema}}}
                response = requests.post(self.base_url+'/chat/completions',
                    headers={'Authorization':'Bearer '+self.api_key},json=body,timeout=self.timeout_seconds)
            else:
                body = {'contents':[{'role':'user','parts':[{'text':prompt}]}],
                        'generationConfig':{'maxOutputTokens':output_limit,
                            'responseMimeType':'application/json','responseJsonSchema':gemini_wire_schema(schema),
                            'thinkingConfig':{'thinkingLevel':'MINIMAL'}}}
                response = requests.post(self.base_url+'/models/'+self.model+':generateContent',
                    headers={'x-goog-api-key':self.api_key},json=body,
                    timeout=max(self.timeout_seconds, 300) if output_limit > 8192 else self.timeout_seconds)
            if response.status_code >= 400:
                status = 'HTTP_'+str(response.status_code)
                with connect(s.database_url) as c:
                    AuxiliaryModelBudget(c).cooldown(self.provider,
                        failure_cooldown(self.provider,response))
                raise requests.HTTPError(f'{self.provider} HTTP {response.status_code}',response=response)
            payload = response.json()
            if self.provider == 'groq':
                choice = (payload.get('choices') or [{}])[0]
                content = (choice.get('message') or {}).get('content') or ''
                metadata.update(usage=payload.get('usage') or {},finish_reason=choice.get('finish_reason'),request_id=payload.get('id'))
            else:
                choice = (payload.get('candidates') or [{}])[0]
                content = ''.join(p.get('text','') for p in choice.get('content',{}).get('parts',[]) if not p.get('thought'))
                usage = payload.get('usageMetadata') or {}
                metadata.update(usage={'prompt_tokens':usage.get('promptTokenCount',0),
                    'completion_tokens':usage.get('candidatesTokenCount',0)+usage.get('thoughtsTokenCount',0),
                    'total_tokens':usage.get('totalTokenCount',0)},finish_reason=choice.get('finishReason'),request_id=payload.get('responseId'))
            status = 'RESPONSE'
            # No recovery of truncated JSON: missing source IDs remain pending.
            if metadata['finish_reason'] not in {'stop','STOP'}:
                raise MalformedMeetingBriefResponse(metadata)
            try:
                parsed = _parse_json_content(content)
                if self.provider == 'gemini':
                    validate_local_bounds(parsed, schema)
            except (ValueError,TypeError) as exc:
                raise MalformedMeetingBriefResponse(metadata) from exc
            status = 'COMPLETED'
            return parsed,metadata
        finally:
            with connect(s.database_url) as c:
                AuxiliaryModelBudget(c).settle(reservation,metadata,status)
