"""Bounded public HTML/official PDF recovery. Reuses the public DNS-pinned fetcher, no model call."""
import hashlib
from .ai_collection_fetch import Fetcher
from .publication_evidence import text_quality,redact
from .publication_supplements import save
from .source_authority import authority


def recover(service,doc,official_only=True):
    if official_only and authority(doc.get('evidence_url',''))!='OFFICIAL':raise ValueError('비공식 자료 · 공식 근거 추가 확보 필요')
    fetcher=Fetcher(service.data_dir);raw=fetcher.get(doc['evidence_url'])
    # A redirect to an unofficial site cannot retain official-source status.
    if authority(doc.get('evidence_url',''))=='OFFICIAL' and authority(fetcher.last.get('url',''))!='OFFICIAL':raise ValueError('최종 원문이 공식 출처가 아닙니다')
    from .publication_capture import capture
    (_,body,truncated),meta=capture(raw,fetcher.last['url'],fetcher)
    if authority(doc.get('evidence_url',''))=='OFFICIAL' and authority(meta.get('url',''))!='OFFICIAL':raise ValueError('첨부 최종 출처가 공식 출처가 아닙니다')
    body=redact(body)
    if truncated or text_quality(body,doc.get('title',''))!='TEXT_AVAILABLE_UNVERIFIED':raise ValueError('완전한 본문 미확보 · 첨부·원문 수동 확인 필요')
    save(service,doc['id'],doc['source_revision_no'],body,'공개 HTML/PDF 원문 자동 복구 · 공식성·동일 사업·사실·물량 승인은 별도',meta.get('attachments',[]),
         '업무담당자 AI · 원문 복구',fetcher.last['sha256'])
    return dict(body_text=body,body_sha256=hashlib.sha256(body.encode()).hexdigest(),body_origin='MANUAL',source_revision_no=doc['source_revision_no'])
