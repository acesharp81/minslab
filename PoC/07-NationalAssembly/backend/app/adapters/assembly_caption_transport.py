"""Public Assembly player transports: AI WebSocket and regular Socket.IO/EIO3.

Contract verified in the official player/openos_util.js and live receive-message
frames. Only the text event is normalized; original frames are retained by the
caption worker. The narrow adapter implements the observed WebSocket transport,
not Socket.IO polling, binary packets, or an inferred alternative service.
"""
from contextlib import contextmanager
from datetime import datetime
import hashlib
import json
import re
import time
from urllib.parse import urlsplit, urlunsplit

from .national_assembly.base import AdapterError

REGULAR_HOST = re.compile(r'smi(?:-(?:hy|dw))?\d?\.webcast\.go\.kr', re.I)
REGULAR_PARSER_VERSION = 'assembly-regular-caption/1.0'


def is_regular_caption(url: str) -> bool:
    return bool(REGULAR_HOST.fullmatch(urlsplit(url).hostname or ''))


def regular_namespace(url: str) -> str:
    # Compatibility with previously stored URLs that incorrectly appended /hls.
    path = urlsplit(url).path.rstrip('/')
    return path.removesuffix('/hls') or '/'


def regular_event(frame: str, namespace: str) -> str | None:
    prefix = '42' if namespace == '/' else '42' + namespace + ','
    if not frame.startswith(prefix):
        return None
    try:
        payload = json.loads(frame[len(prefix):])
    except (ValueError, TypeError):
        return None
    if (isinstance(payload, list) and len(payload) == 2
            and payload[0] == 'receive message' and isinstance(payload[1], str)):
        return payload[1].strip() or None
    return None


def parse_regular_caption(frame: str, url: str, received_at: datetime) -> dict:
    text = regular_event(frame, regular_namespace(url))
    if not text:
        raise AdapterError('invalid regular caption event')
    # This feed supplies text only, without source segment/speaker identifiers.
    # Keep distinct repeated utterances while making a replay of the same stored
    # receipt deterministic. Never infer a speaker or rewrite previous STT.
    receipt = received_at.isoformat(timespec='microseconds')
    key = hashlib.sha256((receipt + '\0' + frame).encode()).hexdigest()[:24]
    return {'segment_id': 'smi-' + key, 'transcript': text,
            'speaker_segments': [], 'is_final': True, 'speech_code': None}


class RegularCaptionStream:
    def __init__(self, websocket, namespace: str, ping_seconds: float):
        self.websocket = websocket
        self.namespace = namespace
        self.ping_seconds = ping_seconds
        self.next_ping = time.monotonic() + ping_seconds

    def recv(self, timeout: float = 15):
        deadline = time.monotonic() + timeout
        while True:
            now = time.monotonic()
            if now >= self.next_ping:
                self.websocket.send('2')  # EIO3 client-originated heartbeat.
                self.next_ping = now + self.ping_seconds
            remaining = min(deadline - now, self.next_ping - now)
            if remaining <= 0:
                raise TimeoutError()
            try:
                frame = self.websocket.recv(timeout=remaining)
            except TimeoutError:
                if time.monotonic() >= deadline:
                    raise
                continue
            if not isinstance(frame, str):
                continue
            if frame == '2':
                self.websocket.send('3')
            if frame == '1' or frame.startswith(('41', '44')):
                raise ConnectionError('regular caption namespace disconnected')
            if regular_event(frame, self.namespace) is not None:
                return frame
            if time.monotonic() >= deadline:
                raise TimeoutError()


@contextmanager
def open_caption_stream(url: str):
    from websockets.sync.client import connect
    if not is_regular_caption(url):
        with connect(url, subprotocols=['echo-protocol'], open_timeout=10,
                     close_timeout=5, ping_interval=20, ping_timeout=20) as websocket:
            yield websocket
        return
    parts = urlsplit(url)
    endpoint = urlunsplit(('wss' if parts.scheme in ('wss', 'https') else 'ws',
                           parts.netloc, '/socket.io/', 'EIO=3&transport=websocket', ''))
    with connect(endpoint, origin='https://assembly.webcast.go.kr', open_timeout=10,
                 close_timeout=5, ping_interval=20, ping_timeout=20) as websocket:
        opening = websocket.recv(timeout=10)
        try:
            if not isinstance(opening, str) or not opening.startswith('0'):
                raise ValueError('missing engine open')
            info = json.loads(opening[1:])
            ping_seconds = min(20.0, max(1.0, float(info['pingInterval']) / 1000.0))
        except (ValueError, TypeError, KeyError) as exc:
            raise AdapterError('invalid regular caption handshake') from exc
        namespace = regular_namespace(url)
        if namespace != '/':
            websocket.send('40' + namespace + ',')
        yield RegularCaptionStream(websocket, namespace, ping_seconds)
