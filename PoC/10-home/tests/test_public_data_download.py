import json
from urllib.parse import parse_qs, urlparse
import pytest
from backend.public_data_download import download_url

SOURCE={'url':'https://www.data.go.kr/data/15043330/fileData.do'}
PAGE="<button onclick=\"fileDetailObj.fn_fileDataDown('15043330', 'uddi:test', '', '1', '10')\">다운로드</button>"
REPLY=dict(status=True,atchFileId='FILE_123',fileDetailSn='1',dataSetFileDetailInfo=dict(publicDataPk='15043330',publicDataDetailPk='uddi:test',publicDataHistSn=10))
class Fetch:
    def __init__(self,reply=REPLY):self.reply=reply;self.calls=[]
    def get(self,url,suffix):
        self.calls.append(url)
        assert suffix=='json'
        assert parse_qs(urlparse(url).query)['publicDataPk']==['15043330']
        return json.dumps(self.reply).encode()

def test_current_portal_download_is_bound_to_registered_dataset_and_revision():
    f=Fetch();url=download_url(PAGE,SOURCE,f)
    assert url=='https://www.data.go.kr/cmm/cmm/fileDownload.do?atchFileId=FILE_123&fileDetailSn=1'
    assert len(f.calls)==1

@pytest.mark.parametrize('change',[{'status':False},{'atchFileId':'../other'}, {'fileDetailSn':'2'}, {'dataSetFileDetailInfo':dict(REPLY['dataSetFileDetailInfo'],publicDataPk='999')},{'dataSetFileDetailInfo':dict(REPLY['dataSetFileDetailInfo'],publicDataHistSn=11)}])
def test_failed_or_other_dataset_or_revision_response_is_rejected(change):
    with pytest.raises(ValueError,match='불일치'):download_url(PAGE,SOURCE,Fetch(dict(REPLY,**change)))

@pytest.mark.parametrize('page',[PAGE.replace('15043330','999'),PAGE+PAGE.replace('uddi:test','uddi:other'),'<script>'+PAGE+'</script>'])
def test_missing_ambiguous_or_script_only_download_is_rejected(page):
    f=Fetch()
    with pytest.raises(ValueError):download_url(page,SOURCE,f)
    assert not f.calls

def test_legacy_link_is_preserved_without_metadata_request():
    f=Fetch();url=download_url('"contentUrl":"https://www.data.go.kr/cmm/cmm/fileDownload.do?atchFileId=FILE_old&amp;fileDetailSn=1"',SOURCE,f)
    assert '&fileDetailSn=1' in url and not f.calls
