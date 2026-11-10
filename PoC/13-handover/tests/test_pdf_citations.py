import pytest
from app.citations import exact_pdf_span
from app.engine import validate_model_result


def test_restore_pdf_wrap_and_exact_evidence():
    text='○ (완료 기준) 계획이나 사본 접수만\n으로 완료 처리하지 않는다. 다음 확인은 \n담당 검토 후 진행한다.'
    quote='계획이나 사본 접수만으로 완료 처리하지 않는다. 다음 확인은 담당 검토 후 진행한다.'
    block={'id':'b','doc_id':'d','parse_id':'p','text':text}
    data={'items':[{'fields':{'title':{'block_id':'b','quote':'완료 기준'},'completion_criteria':{'block_id':'b','quote':quote}}}]}
    item=validate_model_result(data,{'id':'d','format':'.pdf'},[block])[0]
    field=item['fields']['completion_criteria']
    assert field['value']=='계획이나 사본 접수만\n으로 완료 처리하지 않는다. 다음 확인은 \n담당 검토 후 진행한다.'
    assert field['value'] in text and field['evidence'][0]['quote'] in text
    assert field['citation_recovery']=='pdf-visual-line-wrap-to-original'
    assert data['items'][0]['fields']['completion_criteria']['quote']==quote
    with pytest.raises(ValueError):validate_model_result(data,{'id':'d','format':'.xlsx'},[block])


@pytest.mark.parametrize('proposed',[
 '계획이나 사본 접수만으로 완료 처리한다.', # negation removed
 '계획이나 원본 접수만으로 완료 처리하지 않는다.', # word changed
 '집행액 100원', # a digit changed
 '집행액 10원', # an ordinary space between numbers cannot be removed
 '계획이나 사본 접수만으로 / 담당 검토', # disjoint spans
])
def test_reject_content_changes(proposed):
    with pytest.raises(ValueError):exact_pdf_span('계획이나 사본 접수만\n으로 완료 처리하지 않는다. 집행액 1 0원\n담당 검토',proposed)


def test_reject_ambiguous_wrap_and_preserve_exact_spans():
    with pytest.raises(ValueError):exact_pdf_span('접수만\n으로 접수만\n으로','접수만으로')
    assert exact_pdf_span('집행액 10원\n확인','집행액 10원')=='집행액 10원'
    with pytest.raises(ValueError):exact_pdf_span('수량 1\n0','수량 10')
