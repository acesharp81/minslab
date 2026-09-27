from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

from app.services.official_revision_client import OpenRouterOfficialRevisionClient


class OpenRouterOfficialRevisionClientTests(unittest.TestCase):
    def test_comparison_does_not_disable_required_fallback_reasoning(self):
        response = Mock(status_code=200)
        response.json.return_value = {
            "choices": [{"message": {"content": '{"edits": []}'}}],
        }
        with patch("app.services.official_revision_client.requests.post", return_value=response) as post:
            result = OpenRouterOfficialRevisionClient(
                "test-key", model="dots-studio/dots-3-note-preview:free",
                base_url="http://gateway.local/api/v1",
            ).compare({}, [])
        body = post.call_args.kwargs["json"]
        self.assertNotIn("reasoning", body)
        self.assertEqual("json_schema", body["response_format"]["type"])
        self.assertEqual("official_revision", post.call_args.kwargs["headers"]["X-Minslab-Workload"])
        self.assertEqual([], result.edits)


if __name__ == "__main__":
    unittest.main()
