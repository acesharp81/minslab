"""Reuse report coverage validation, with the integration group's transport."""
import json
from .grouped_models import WorkloadBriefClient
from .topic_report import OpenRouterTopicReportClient


class GroupedTopicReportClient(OpenRouterTopicReportClient):
    provider = 'openai'

    def __init__(self, settings, *, before_additional_request=None):
        super().__init__(settings.openai_api_key, model=settings.openai_integration_model,
            base_url=settings.openai_base_url, before_additional_request=before_additional_request)
        self.transport = WorkloadBriefClient(settings)

    def _request(self, body, *, additional=False):
        if additional and self.before_additional_request:
            self.before_additional_request()
        prompt = '\n'.join(str(m.get('content') or '') for m in body['messages'])
        spec = body['response_format']['json_schema']
        data, metadata = self.transport._post(prompt, spec['schema'], 'topic_report')
        payload = {'id':metadata.get('request_id'), 'model':metadata.get('model'),
            'provider':metadata.get('provider'), 'usage':metadata.get('usage'),
            'choices':[{'finish_reason':metadata.get('finish_reason','stop'),
                        'message':{'content':json.dumps(data,ensure_ascii=False)}}]}
        self.responses.append(payload)
        return payload


class GroupedOfficialRevisionClient:
    def __init__(self, settings):
        self.transport = WorkloadBriefClient(settings)

    def compare(self, live_brief, official_rows):
        from .official_revision_client import build_revision_prompt, revision_response_schema, OfficialRevisionResult
        from .official_edit_validation import filter_supported_official_edits
        rows = list(official_rows)
        prompt, valid_ids = build_revision_prompt(live_brief, rows)
        data, usage = self.transport._post(prompt, revision_response_schema(), 'official_brief_delta')
        edits = filter_supported_official_edits(data, live_brief,
            [row for row in rows if str(row.get('utterance_id')) in valid_ids])
        return OfficialRevisionResult(edits=edits, usage_metadata=usage)
