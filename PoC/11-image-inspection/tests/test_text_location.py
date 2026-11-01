from app.text_location import protect


def fixture():
    obj=dict(id='o1',text='힘께 만드는 미래',transcription_inferred=False)
    detector=dict(id='OCR1',text=obj['text'],source='paddle-detector',recognition_score=.96,detection_score=.9,rect=[.4,.8,.55,.86])
    run={'observation':{'objects':[obj]},'pixel_text':{'status':'COMPLETED','detector_regions':[detector]}}
    row=dict(rule_id='D-02-l',status='FAIL',evidence_ids=['o1'],observation='카드 제목',reason='‘힘께 만드는 미래’는 오자 후보입니다.',rects=[[0,0,.1,.1]])
    return run,row


def test_independent_exact_ocr_locates_original_without_changing_verdict():
    run,row=fixture();protect(run,[row])
    assert row['rects']==[[.4,.8,.55,.86]] and row['status']=='FAIL'
    assert row['location_evidence']['method']=='independent-detector-and-scene'


def test_correction_or_low_confidence_is_not_used_as_source_location():
    run,row=fixture();row['reason']='‘함께 만드는 미래’로 수정하세요.';protect(run,[row])
    assert row['rects']==[[0,0,.1,.1]]
    run,row=fixture();run['pixel_text']['detector_regions'][0]['recognition_score']=.5;protect(run,[row])
    assert row['rects']==[[0,0,.1,.1]]


def test_duplicate_literal_does_not_choose_an_arbitrary_card():
    run,row=fixture();r=run['pixel_text']['detector_regions'][0]
    run['pixel_text']['detector_regions'].append({**r,'id':'OCR2','rect':[.7,.8,.85,.86]})
    protect(run,[row]);assert row['location_unresolved'] and row['rects']==[]
