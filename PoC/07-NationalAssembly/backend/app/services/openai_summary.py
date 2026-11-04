"""Mini uses the identical live summary schema and source validation as OpenRouter."""
from .grouped_models import quota_client
from .summary_contract import PROMPT_VERSION, build_summary_prompt, summary_response_schema, validated_summary_items
from .openrouter_summary import OpenRouterSummaryResult


class OpenAISummaryClient:
    provider = 'openai'
    prompt_version = PROMPT_VERSION

    def __init__(self, settings):
        self.settings = settings
        if getattr(settings, 'openai_realtime_credit_enabled', False):
            from .realtime_credit import RealtimeMiniClient
            self.client = RealtimeMiniClient(settings)
        else:
            self.client = quota_client(settings, 'mini')

    @property
    def model(self):
        return self.client.model

    def summarize(self, utterances):
        data, usage = self.client._post(build_summary_prompt(utterances), summary_response_schema(), 'assembly_summaries')
        parsed = data.get('summaries', [])
        items = validated_summary_items(parsed, utterances)
        accepted = {i['content_hash'] for i in items}
        if self.model == 'gpt-6-luna':
            for item in items:
                item['_summary_model'] = 'gpt-6-luna'
            missing = [u for u in utterances if u['content_hash'] not in accepted]
            if missing:
                # Repair only rejected evidence, never resend the good Luna items.
                from .realtime_credit import credit_client
                repair = credit_client(self.settings, 'gpt-5.4-mini')
                try:
                    data2, usage2 = repair._post(build_summary_prompt(missing), summary_response_schema(), 'assembly_summaries')
                    repaired = validated_summary_items(data2.get('summaries', []), missing)
                    for item in repaired:
                        item['_summary_model'] = repair.model
                    items.extend(repaired)
                    accepted.update(i['content_hash'] for i in repaired)
                    usage = {**usage, 'quality_repair': {'model': repair.model, 'requested': len(missing),
                        'accepted': len(repaired), 'usage_metadata': usage2}}
                except Exception as exc:
                    usage = {**usage, 'quality_repair': {'model': repair.model, 'requested': len(missing),
                        'accepted': 0, 'error': type(exc).__name__}}
        return OpenRouterSummaryResult(items=items, usage_metadata={**usage,
            'rejected_ids': [u['content_hash'] for u in utterances if u['content_hash'] not in accepted]})
