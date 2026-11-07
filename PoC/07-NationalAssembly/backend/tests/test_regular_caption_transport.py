from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch
import json
import pytest

from app.adapters.assembly_caption_transport import (is_regular_caption, regular_namespace,
    regular_event, parse_regular_caption, open_caption_stream, RegularCaptionStream)
from app.adapters.live_sources import parse_assembly_live_play
from app.ingestion.caption_worker import persist_caption_message
from test_caption_worker import RecordingSink

URL = 'wss://smi-dw.webcast.go.kr/10'
FRAME = '42/10,["receive message","예산 집행의 적정성을 검토합니다."]'


def test_official_player_transport_selection_and_old_url_compatibility():
    for host in ['smi', 'smi1', 'smi-dw', 'smi-hy2']:
        assert is_regular_caption(f'wss://{host}.webcast.go.kr/10')
    assert not is_regular_caption('wss://smi-dw.webcast.go.kr.evil.invalid/10')
    assert not is_regular_caption('wss://example.invalid/aistt/10/hls')
    assert regular_namespace(URL+'/hls') == regular_namespace(URL) == '/10'
    payload = json.loads((Path(__file__).parent/'fixtures/synthetic_assembly_live_play.json').read_text())
    payload['xsami'] = URL
    assert parse_assembly_live_play(json.dumps(payload).encode())['caption_websocket_url'] == URL


def test_events_ignore_heartbeat_other_namespace_and_blank_text():
    assert regular_event(FRAME, '/10') == '예산 집행의 적정성을 검토합니다.'
    for frame in ['3', '40/10,', '42/21,["receive message","wrong"]',
                  '42/10,["change name","name"]', '42/10,["receive message",{}]',
                  '42/10,["receive message"," "]', '42/10,invalid']:
        assert regular_event(frame, '/10') is None


def test_raw_event_and_repeated_speech_are_preserved_without_inventing_speaker(tmp_path):
    sink = RecordingSink();now = datetime(2026,11,6,tzinfo=timezone.utc)
    args = dict(broadcast_id='fixture', external_id='fixture', source_url=URL,
                raw_message=FRAME, received_at=now, raw_dir=tmp_path, sink=sink)
    persist_caption_message(**args)
    revision = sink.revisions[0][1]
    assert revision.source.raw_path.read_text() == FRAME
    assert revision.source.content_type == 'text/plain'
    assert revision.source.parser_version == 'assembly-regular-caption/1.0'
    assert revision.text == '예산 집행의 적정성을 검토합니다.'
    assert revision.speaker_label is None and revision.is_final
    one = parse_regular_caption(FRAME, URL, now)
    assert one == parse_regular_caption(FRAME, URL, now)
    assert one['segment_id'] != parse_regular_caption(FRAME, URL, now+timedelta(seconds=5))['segment_id']


def test_engine_handshake_namespace_and_heartbeat():
    ws = MagicMock()
    ws.recv.side_effect = ['0{"sid":"fixture","pingInterval":25000}', '40', '40/10,', '3', FRAME]
    cm = MagicMock();cm.__enter__.return_value = ws
    with patch('websockets.sync.client.connect', return_value=cm) as connect:
        with open_caption_stream(URL+'/hls') as stream:
            stream.next_ping = 0
            assert stream.recv(timeout=1) == FRAME
    assert connect.call_args.args[0] == 'wss://smi-dw.webcast.go.kr/socket.io/?EIO=3&transport=websocket'
    assert connect.call_args.kwargs['origin'] == 'https://assembly.webcast.go.kr'
    assert 'subprotocols' not in connect.call_args.kwargs
    assert [x.args[0] for x in ws.send.call_args_list] == ['40/10,', '2']


def test_ai_transport_remains_echo_protocol():
    cm = MagicMock()
    with patch('websockets.sync.client.connect', return_value=cm) as connect:
        with open_caption_stream('wss://example.invalid/aistt/10/hls') as ws:
            assert ws is cm.__enter__.return_value
    assert connect.call_args.kwargs['subprotocols'] == ['echo-protocol']


def test_disconnect_and_silence_return_control_to_fallback_clock():
    ws = MagicMock();ws.recv.return_value = '41/10,'
    with pytest.raises(ConnectionError): RegularCaptionStream(ws, '/10', 20).recv()
    ws.recv.side_effect = TimeoutError()
    with pytest.raises(TimeoutError): RegularCaptionStream(ws, '/10', 20).recv(timeout=.001)
