"""Resolve official portal download metadata without executing page JavaScript."""
import json
import re
from html import unescape
from urllib.parse import urlencode, urlparse

from bs4 import BeautifulSoup

LEGACY_LINK = re.compile(r'"contentUrl"\s*:\s*"(https://www\.data\.go\.kr/cmm/cmm/fileDownload\.do\?[^"\s]+)"')
BUTTON = re.compile(r"fileDetailObj\.fn_fileDataDown\(\s*'([0-9]+)'\s*,\s*'([\w:-]+)'\s*,\s*'([\w-]*)'\s*,\s*'([0-9]+)'\s*,\s*'([0-9]+)'\s*\)")


def download_url(page, source, fetcher):
    legacy = LEGACY_LINK.search(page)
    if legacy:
        return unescape(legacy[1])
    dataset = re.fullmatch(r'/data/(\d+)/fileData.do', urlparse(source['url']).path)
    if not dataset or urlparse(source['url']).hostname != 'www.data.go.kr':
        raise ValueError('공식 파일 링크·기준일 확인 실패: 등록 데이터셋 주소 확인 필요')
    matches = set()
    for button in BeautifulSoup(page, 'html.parser').select('button[onclick]'):
        match = BUTTON.fullmatch(button['onclick'].strip().rstrip(';'))
        if match and match[1] == dataset[1]:
            matches.add(match.groups())
    if len(matches) != 1:
        raise ValueError('공식 파일 링크·기준일 확인 실패: 다운로드 대상 누락·중복')
    pk, detail, attachment, sequence, history = matches.pop()
    query = urlencode(dict(publicDataPk=pk, publicDataDetailPk=detail,
                           atchFileId=attachment, fileDetailSn=sequence, publicDataTyCode='PR0051'))
    metadata = json.loads(fetcher.get('https://www.data.go.kr/tcs/dss/selectFileDataDownload.do?' + query, 'json'))
    info = metadata.get('dataSetFileDetailInfo') or {}
    file_id, file_no = metadata.get('atchFileId'), str(metadata.get('fileDetailSn', ''))
    if (metadata.get('status') is not True or str(info.get('publicDataPk')) != pk
            or info.get('publicDataDetailPk') != detail
            or str(info.get('publicDataHistSn')) != history
            or not isinstance(file_id, str) or not re.fullmatch(r'[\w-]+', file_id)
            or file_no != sequence):
        raise ValueError('공식 파일 링크·기준일 확인 실패: 다운로드 응답의 데이터셋·판본 불일치')
    return 'https://www.data.go.kr/cmm/cmm/fileDownload.do?' + urlencode(dict(atchFileId=file_id, fileDetailSn=file_no))
