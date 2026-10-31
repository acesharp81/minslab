from scripts.score_suite import matches,metrics


def test_roi_boundary_overlap_counts_but_whole_image_and_adjacent_box_do_not():
    roi=[.2,.2,.4,.4]
    assert matches({'rects':[[.18,.25,.24,.3]]},roi)
    assert not matches({'rects':[[0,0,1,1]]},roi)
    assert not matches({'rects':[[.4,.2,.5,.3]]},roi)


def test_review_and_missing_location_do_not_inflate_detection_or_accuracy():
    rows=[dict(expected='FAIL',predicted='REVIEW'),dict(expected='PASS',predicted='FAIL'),dict(expected='PASS',predicted='NO_LOCATION'),dict(expected='REVIEW',predicted='REVIEW')]
    m=metrics(rows)
    assert m['fail_recall']==0 and m['normal_pass_rate']==0 and m['false_positive_rate']==.5
    assert m['required_review_accuracy']==1 and m['error_or_omission_rate']==.25
