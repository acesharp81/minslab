"""Independent source-failure and unit-confusion cases from 2026-10-30 review."""
from unittest.mock import MagicMock,patch
import pytest
from backend.ai_collection_fetch import Fetcher,canonical,text_content
from backend.ai_collection_models import Analysis,checks

def response(status,headers,body=b'<html>notice</html>'):
 r=MagicMock(status=status)
 r.getheaders.return_value=list(headers.items())
 r.getheader.side_effect=lambda key,default='':headers.get(key,default)
 r.read1.side_effect=[body,b'']
 return r

@pytest.mark.parametrize('destination,expected_cookie',[
 ('https://www.molit.go.kr/USR/NEWS/detail','JSESSIONID=public123'),
 ('https://other.example/USR/NEWS/detail',None),
 ('https://www.molit.go.kr/outside',None)])
def test_cookie_survives_same_origin_redirect_only(tmp_path,destination,expected_cookie):
 a,b=MagicMock(),MagicMock()
 a.getresponse.return_value=response(302,{'Location':destination,'Set-Cookie':'JSESSIONID=public123; Path=/USR/NEWS; Secure'})
 b.getresponse.return_value=response(200,{'Content-Type':'text/html'})
 with patch('backend.ai_collection_fetch.public_addresses',return_value=['1.1.1.1']),patch('backend.ai_collection_fetch.PinnedHTTPS',side_effect=[a,b]):
  Fetcher(tmp_path).get('https://www.molit.go.kr/USR/NEWS/detail')
 assert b.request.call_args.kwargs['headers'].get('Cookie')==expected_cookie

def test_failed_fetch_does_not_reuse_last_documents_hash(tmp_path):
 f=Fetcher(tmp_path);f.last={'sha256':'previous'}
 with pytest.raises(ValueError):f.get('http://127.0.0.1/')
 assert f.last=={}

def test_seoul_article_identity_does_not_collapse_into_listing():
 a=canonical('https://www.seoul.go.kr/news/news_report.do#view/468710')
 b=canonical('https://www.seoul.go.kr/news/news_report.do#view/469091')
 assert a!=b and a.endswith('?nttNo=468710')
 assert canonical('https://example.com/a#view/123')=='https://example.com/a'

@pytest.mark.parametrize('html,expected',[
 ('<article>menu 9999호</article><div class="board-view-txt">불광동 329-32 주택사업의 공식 현장점검 본문입니다. 예정 착공과 완료 실적은 구분합니다.</div>','불광동'),
 ('<div class="viewer">주택 100호 계획의 실제 기사 본문입니다. 주택 100호 계획의 실제 기사 본문입니다.</div><aside>인기기사 999호</aside>','100호'),
 ('<div class="detailTable"><td class="cont">장기전세 예비자 후속공고 본문입니다. 신규 건설 실적이 아니며 단지와 모공고 대조가 필요합니다.</td></div><footer>999호</footer>','모공고')])
def test_article_body_excludes_navigation(html,expected):
 _,body,_=text_content(html.encode());assert expected in body and '999' not in body

def test_attachment_only_board_stays_explicitly_unresolved():
 with pytest.raises(ValueError,match='본문 부족'):
  text_content(b'<article class="board_view">long title and menus enough to look valid but no body<div class="contents"></div></article>')

@pytest.mark.parametrize('quote,value',[('빈소 401호실',401),('부지 5000㎡',5000),('교육 2회',2),('7호선 연장',7),('제4호 공고',4)])
def test_nonhousing_numbers_cannot_be_valid_housing_counts(quote,value):
 a=Analysis(relevance='관련',summary='검토',project_names=[],quantities=[dict(value=value,unit='호',scope='전체',quote=quote)],dates=[],evidence_quotes=[quote],issues=[],review_question='확인')
 assert any('단위' in x for x in checks(a,quote))

def test_room_and_subway_numbers_are_not_missing_housing_counts():
 a=Analysis(relevance='관련',summary='검토',project_names=[],quantities=[],dates=[],evidence_quotes=['빈소 401호실과 7호선'],issues=[],review_question='확인')
 assert not checks(a,'빈소 401호실과 7호선')


def test_old_or_unpinned_manual_body_never_overrides_new_evidence():
 from backend.publication_supplements import usable
 manual=dict(source_revision_no=1,body_text='old',collected_at='2026-10-30T01:00:00+00:00')
 assert usable(manual,1,{})
 assert not usable(manual,2,{})
 assert not usable(manual,1,dict(body_text='new',collected_at='2026-10-30T02:00:00+00:00'))
 assert usable(manual,1,dict(body_text='older',collected_at='2026-10-29T02:00:00+00:00'))


def test_molit_embedded_pdf_is_not_mistaken_for_full_article():
 with pytest.raises(ValueError,match='본문 부족'):
  text_content(b'<article>title and attachment names are not the full content<div class="bd_view_cont"><iframe src="/viewer"></iframe></div></article>')


def test_seoul_detail_scrap_area_excludes_navigation():
 _,body,_=text_content('<nav>9999호 메뉴</nav><div id="scrabArea">서울시 공식 상세자료입니다. 면목 사당 모아주택 사업성 개선 및 예정 착공에 관한 본문입니다.</div><aside>인기기사 9999호</aside>'.encode())
 assert '면목' in body and '9999' not in body
