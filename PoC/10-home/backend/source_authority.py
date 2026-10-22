"""Publisher identity, independent of an officer's approval of a fact."""
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

LABELS = {'OFFICIAL':'공식 출처', 'NONOFFICIAL':'비공식 출처', 'INTERNAL':'담당자 입력·내부 관리', 'UNKNOWN':'출처 확인 필요'}
OFFICIAL_DOMAINS = ('go.kr','korea.kr','lh.or.kr','gh.or.kr','i-sh.co.kr','ih.co.kr',
                    'kosis.kr','reb.or.kr','kdi.re.kr','vworld.kr','applyhome.co.kr','seoulhousing.kr','smc.seoul.kr')

def public_url(value):
    try:
        u=urlsplit(str(value or ''))
        if u.scheme not in ('http','https') or not u.hostname:return ''
        private={'servicekey','service_key','apikey','api_key','access_token','token','password','secret'}
        query=[(k,v) for k,v in parse_qsl(u.query,keep_blank_values=True) if k.lower() not in private]
        return urlunsplit((u.scheme,u.hostname+(':'+str(u.port) if u.port else ''),u.path,urlencode(query),u.fragment))
    except (ValueError,TypeError):return ''

def authority(url='', source_id='', inferred=False):
    if inferred:return 'INTERNAL'
    host=urlsplit(public_url(url)).hostname or ''
    if host:
        return 'OFFICIAL' if any(host==d or host.endswith('.'+d) for d in OFFICIAL_DOMAINS) else 'NONOFFICIAL'
    return 'INTERNAL' if source_id in ('officer','manual_delivery','manual_project') else 'UNKNOWN'

# Publisher display names are independent of source_id and approval labels.
PUBLISHERS = {
    'newsis.com': '뉴시스', 'newspim.com': '뉴스핌', 'seoul.co.kr': '서울신문',
    'richgo.ai': '리치고', 'lh.or.kr': 'LH 한국토지주택공사',
    'gwanak.go.kr': '관악구청', 'anyang.go.kr': '안양시청', 'myhome.go.kr': '마이홈포털',
}

def publisher_name(url='', fallback=''):
    host=urlsplit(public_url(url)).hostname or ''
    for domain,label in PUBLISHERS.items():
        if host==domain or host.endswith('.'+domain):return label
    if host:
        try:return host.encode('ascii').decode('idna').removeprefix('www.')
        except (UnicodeError,ValueError):return host
    return fallback if fallback and not fallback.lower().startswith('external_') else '출처 확인 필요'

def clean(value):
    if isinstance(value,dict):
        return {k:clean(v) for k,v in value.items() if k.lower() not in
                ('password','authorization','cookie','servicekey','service_key','api_key','apikey','access_token','token','secret','authentication')}
    if isinstance(value,list):return [clean(v) for v in value]
    if isinstance(value,str) and value.startswith(('http://','https://')):return public_url(value)
    return value
