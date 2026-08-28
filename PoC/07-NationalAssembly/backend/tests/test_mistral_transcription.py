from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from app.services.mistral_transcription import MistralTranscriptionClient


class MistralTranscriptionTests(unittest.TestCase):
    def test_requests_diarized_segments_and_records_audio_cost(self):
        response = mock.Mock()
        response.headers = {"x-request-id": "voxtral-request-1"}
        response.json.return_value = {
            "text": "질의합니다. 답변드리겠습니다.",
            "segments": [
                {"text": "질의합니다.", "start": 0.0, "end": 2.1, "speaker_id": "speaker_0"},
                {"text": "답변드리겠습니다.", "start": 2.1, "end": 4.5, "speaker_id": "speaker_1"},
            ],
        }
        response.raise_for_status.return_value = None
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "sample.mp3"
            path.write_bytes(b"ID3" + b"0" * 1024)
            with mock.patch(
                "app.services.mistral_transcription.requests.post", return_value=response,
            ) as request:
                result = MistralTranscriptionClient(
                    "secret", model="voxtral-mini-latest", usd_per_minute=0.003,
                ).transcribe(path, duration_seconds=60)
        self.assertEqual(["speaker_0", "speaker_1"], [item["speaker"] for item in result.segments])
        self.assertEqual("voxtral-request-1", result.usage_metadata["request_id"])
        self.assertEqual(0.003, result.usage_metadata["cost_usd"])
        self.assertEqual("true", request.call_args.kwargs["data"]["diarize"])
        self.assertIn("/audio/transcriptions", request.call_args.args[0])


if __name__ == "__main__":
    unittest.main()
