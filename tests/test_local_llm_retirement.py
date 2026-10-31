import json,unittest
from unittest import mock
import main
from test_site_api import call_app

class LocalLlmRetirementTests(unittest.IsolatedAsyncioTestCase):
    async def test_chat_models_do_not_contact_retired_local_service(self):
        remote=[{'name':'upstage:solar-pro4','provider':'upstage'}]
        with mock.patch.object(main,'local_llm_enabled',return_value=False),mock.patch.object(main,'upstage_chat_model_options',return_value=remote),mock.patch.object(main,'call_ollama',side_effect=AssertionError('local inference must not be contacted')):
            response,body=await call_app('/api/models')
        self.assertEqual(response['status'],200)
        self.assertEqual(json.loads(body)['models'],remote)
        self.assertEqual(json.loads(body)['default'],'upstage:solar-pro4')

    def test_poc1_has_only_remote_models_and_a_valid_default(self):
        with mock.patch.object(main,'local_llm_enabled',return_value=False),mock.patch.object(main,'call_ollama',side_effect=AssertionError('local inference must not be contacted')):
            choices=main.ai_safe_model_options()
        self.assertTrue(choices['models'])
        self.assertTrue(all(x['provider']!='ollama' for x in choices['models']))
        self.assertIn(choices['default'],[x['value'] for x in choices['models']])

    def test_intentional_retirement_is_not_reported_as_an_outage(self):
        with mock.patch.object(main,'local_llm_enabled',return_value=False),mock.patch.object(main,'call_ollama_quick',side_effect=AssertionError('retired service must not be contacted')),mock.patch.object(main,'_tcp_port_is_open',return_value=True),mock.patch.object(main,'get_analytics_summary',return_value={}),mock.patch.object(main,'analytics_status',return_value={}):
            result=main.check_services()
        self.assertTrue(result['ok'])
        self.assertFalse(result['services']['ollama']['enabled'])
