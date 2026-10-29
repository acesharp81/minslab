"""Mini uses the identical live summary schema and source validation as OpenRouter."""
from .grouped_models import quota_client
from .summary_contract import PROMPT_VERSION, build_summary_prompt, summary_response_schema, validated_summary_items
from .openrouter_summary import OpenRouterSummaryResult


class OpenAISummaryClient:
    provider = 'openai'
    prompt_version = PROMPT_VERSION

    def __init__(self, settings):
        self.client = quota_client(settings, 'mini')
        self.model = self.client.model

    def summarize(self, utterances):
        data, usage = self.client._post(build_summary_prompt(utterances), summary_response_schema(), 'assembly_summaries')
        parsed = data.get('summaries', [])
        items = validated_summary_items(parsed, utterances)
        accepted = {i['content_hash'] for i in items}
        return OpenRouterSummaryResult(items=items, usage_metadata={**usage,
            'rejected_ids': [u['content_hash'] for u in utterances if u['content_hash'] not in accepted]})
