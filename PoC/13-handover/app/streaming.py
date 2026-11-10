"""Provider SSE transport and incremental JSON text preview, excluding citation IDs."""
import json
import time
import httpx


def partial_string(raw):
    """Decode the complete prefix of an unfinished JSON string, holding escapes."""
    result = []; i = 1
    escapes = {'"':'"', '\\':'\\', '/':'/', 'b':'\b', 'f':'\f', 'n':'\n', 'r':'\r', 't':'\t'}
    while i < len(raw):
        char = raw[i]
        if char == '"': break
        if char != '\\':
            result.append(char); i += 1; continue
        if i+1 >= len(raw): break
        escape = raw[i+1]
        if escape in escapes:
            result.append(escapes[escape]); i += 2; continue
        if escape != 'u' or i+6 > len(raw): break
        try:
            code = int(raw[i+2:i+6], 16)
            if 0xD800 <= code <= 0xDBFF:
                if i+12 > len(raw) or raw[i+6:i+8] != '\\u': break
                low = int(raw[i+8:i+12], 16)
                if not 0xDC00 <= low <= 0xDFFF: break
                result.append(chr(0x10000+(code-0xD800)*1024+low-0xDC00)); i += 12
            elif 0xDC00 <= code <= 0xDFFF: break
            else: result.append(chr(code)); i += 6
        except ValueError: break
    return ''.join(result)


def preview_text(raw):
    """Lex JSON strings so quoted text resembling a key cannot become a new field."""
    decoder = json.JSONDecoder(); texts = []; i = 0; text_value = False
    while i < len(raw):
        if raw[i] != '"': i += 1; continue
        try:
            value, end = decoder.raw_decode(raw, i)
        except json.JSONDecodeError:
            if text_value: texts.append(partial_string(raw[i:]))
            break
        if text_value:
            texts.append(value); text_value = False
        else:
            after = end
            while after < len(raw) and raw[after].isspace(): after += 1
            if after < len(raw) and raw[after] == ':':
                text_value = value == 'text'
        i = end
    return '\n\n'.join(texts)


def completion_stream(config, payload, timeout, operation, on_content, cancelled=None):
    if cancelled and cancelled.is_set(): raise ValueError('답변 생성을 중지했습니다.')
    meter = config.get('_meter'); event = meter.start(config, operation,payload) if meter else None
    content = ''; usage = None; model = config['model']; finish = None; done = False
    started = time.monotonic();status=None
    try:
        with httpx.Client(timeout=timeout) as client:
            with client.stream('POST', config['url'].rstrip('/')+'/chat/completions',
                               headers={'Authorization':'Bearer '+config['key']},
                               json={**payload, 'stream':True, 'stream_options':{'include_usage':True}}) as response:
                status=response.status_code
                if response.status_code != 200:
                    raise ValueError(f'질의 모델 API 오류 HTTP {response.status_code}. 연결·사용량을 확인하세요.')
                for line in response.iter_lines():
                    if cancelled and cancelled.is_set(): raise ValueError('답변 생성을 중지했습니다.')
                    if time.monotonic()-started > 150: raise ValueError('답변 생성 제한 시간을 초과했습니다.')
                    if not line.startswith('data:'): continue
                    raw = line[5:].strip()
                    if raw == '[DONE]': done = True; break
                    try: data = json.loads(raw)
                    except (TypeError, ValueError) as exc: raise ValueError('모델 스트림 형식을 확인하지 못했습니다.') from exc
                    if not isinstance(data, dict) or data.get('error'): raise ValueError('모델 스트림에 오류가 발생했습니다.')
                    model = data.get('model') or model
                    if data.get('usage') is not None: usage = data['usage']
                    for choice in data.get('choices') or []:
                        if choice.get('index',0) != 0: continue
                        finish = choice.get('finish_reason') or finish
                        delta = (choice.get('delta') or {}).get('content') or ''
                        if not isinstance(delta, str): raise ValueError('모델 스트림 형식을 확인하지 못했습니다.')
                        if delta:
                            content += delta
                            if len(content) > 100000: raise ValueError('답변 길이 제한을 초과했습니다.')
                            on_content(content)
        if not done or finish != 'stop': raise ValueError('답변 수신이 완료되지 않았습니다. 다시 질문해 주세요.')
        return httpx.Response(200, json={'model':model,'usage':usage or {},'choices':[{'finish_reason':finish,'message':{'content':content}}]})
    finally:
        # The final usage frame is charged even if validation fails or the socket later breaks.
        if meter and usage is not None:
            meter.finish(event, config, httpx.Response(200,json={'model':model,'usage':usage}))
        elif meter:
            meter.finish(event,config,httpx.Response(status,json={}) if status else None)
