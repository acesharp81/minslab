import csv,io,json,hashlib
import pytest
from backend.publication_capture import attachment_links,capture
from backend.publication_watch import scope_exclusion,housing_title
from backend.review_report_artifacts import artifact_path,manifest
from backend.publication_review_export import export_csv,export_json
from backend.publication_supplements import save as supplement
from test_publication_reviews import env

@pytest.mark.parametrize('title,reason',[
 ('2027년 금천주거안심종합센터 희망돌보미(사무지원) 채용 공고','STAFF_RECRUITMENT'),
 ('중부발전, 함안복합발전소 철골 입주 기념 안전다짐행사','NON_HOUSING_POWER_FACILITY'),
 ('가스公, 대구혁신도시 교육여건 개선','NON_HOUSING_EDUCATION_SUPPORT'),
 ('발전소 부지에 공공주택 건설 추진',None),('교육환경 개선과 아파트 재개발 사업 추진',None),
 ('전월세 안심신탁 첫 임대인 모집 공고',None),('고양창릉 S-2BL 1,057세대 중 284세대 분양 계획',None)])
def test_scope_rules(title,reason):
 assert scope_exclusion(title)==reason
 if reason:assert not housing_title(title)

def test_sh_attachment_metadata():
 raw=b'<script>initParam.downList = [{"brdId":"GS0401","seq":"312816","fileTp":"A","fileSeq":"2","oriFileNm":"notice.pdf"}];</script>'
 a=attachment_links(raw,'https://www.i-sh.co.kr/main/view.do')[0]
 assert a['url']=='https://www.i-sh.co.kr/main/com/file/innoFD.do?brdId=GS0401&seq=312816&fileTp=A&fileSeq=2'
 assert a['file_state']=='MISSING' and a['verification_status']=='UNVERIFIED'

def test_pdf_capture_skips_preview_and_other_host(monkeypatch,tmp_path):
 raw=b'<title>release</title><div class="bd_view_cont"><iframe src="/viewer.do"></iframe></div><a href="/preview?file=x.pdf">preview</a><a href="https://other.test/foreign.pdf">foreign</a><a href="/download?file=x.pdf">release.pdf</a>'
 class Fetcher:
  folder=tmp_path;last={'url':'https://www.molit.go.kr/article','sha256':'a'*64}
  def get(self,url,*,allow_pdf=False):
   assert url=='https://www.molit.go.kr/download?file=x.pdf' and allow_pdf
   self.last={'url':url,'sha256':'b'*64};return b'%PDF-1.4'
 monkeypatch.setattr('backend.publication_capture.pdf_text',lambda path:dict(text='고양창릉 S-2BL 총 1,057세대 중 284세대는 포함 물량입니다. 2026년 12월 분양 계획입니다.',pages=2,truncated=False))
 (_,body,_),meta=capture(raw,'https://www.molit.go.kr/article',Fetcher())
 assert '1,057' in body and meta['body_source']=='ATTACHMENT_TEXT'
 assert meta['attachments'][0]['file_state']=='PRESENT' and meta['attachments'][0]['verification_status']=='UNVERIFIED'

def test_personal_roster_not_fetched(tmp_path):
 raw='<title>선정 자료</title><div class="bd_view_cont"></div><a href="/download?file=x.pdf">당첨자 명단.pdf</a>'.encode()
 class Fetcher:
  last={};folder=tmp_path
  def get(self,*args,**kwargs):raise AssertionError('personal roster must not be fetched')
 with pytest.raises(ValueError,match='ATTACHMENT_REQUIRED'):capture(raw,'https://www.i-sh.co.kr/article',Fetcher())

def test_report_byte_and_content_hashes(tmp_path):
 path=artifact_path(tmp_path,'EVIDENCE_REVIEW_20261105');path.parent.mkdir(parents=True);raw='원본\r\n보고서\r\n'.encode();path.write_bytes(raw)
 m=manifest(tmp_path,'EVIDENCE_REVIEW_20261105')
 assert m['byte_sha256']==hashlib.sha256(raw).hexdigest()
 assert m['normalized_text_sha256']==hashlib.sha256('원본\n보고서\n'.encode()).hexdigest()
 assert m['byte_sha256']!=m['normalized_text_sha256']
 with pytest.raises(ValueError):artifact_path(tmp_path,'../../.env')
 assert manifest(tmp_path,'EVIDENCE_REVIEW_20261104')['status']=='MISSING'

def test_export_attachment_link_does_not_mean_verified(env):
 service,did,_=env
 supplement(service,did,1,'입주 안내 본문입니다. 신청 일정과 모집 기준은 해당 공고 및 첨부 확인이 필요합니다. 기존 재고 모집이며 새로운 착공 실적이 아닙니다.','첨부 링크만 확인',[dict(name='안내.pdf',url='https://www.i-sh.co.kr/a.pdf'),dict(name='과거해시.pdf',url='https://www.i-sh.co.kr/b.pdf',sha256='b'*64)],'검토자','a'*64)
 r=list(csv.DictReader(io.StringIO(export_csv(service).lstrip('\ufeff'))))[0]
 assert '원문·첨부 수집' not in r['수동수집상태']
 a=json.loads(r['첨부확보상태_JSON']);assert a['items'][0]['file_state']=='MISSING' and not a['verified']
 assert a['items'][1]['file_state']=='UNVERIFIED'
 assert not export_json(service)['items'][0]['attachment_verified']


def test_article_selector_excludes_recommendation_sidebar():
 from backend.ai_collection_fetch import text_content
 raw=('<div class="news-contents"><div class="article">'+('공급 전망 자료이며 확인된 착공 실적과 구분합니다. '*4)+'</div></div><div class="itemContainer">다른 추천기사와 관련 없는 수치</div>').encode()
 _,body,_=text_content(raw)
 assert '공급 전망' in body and '추천기사' not in body
