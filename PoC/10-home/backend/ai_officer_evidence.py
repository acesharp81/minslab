"""Bounded official HTML recovery. Reuses the public DNS-pinned fetcher, no model call."""
import hashlib
from .ai_collection_fetch import Fetcher,text_content
from .publication_evidence import text_quality,redact
from .publication_supplements import save
from .source_authority import authority


def recover(service,doc):
    if authority(doc.get('evidence_url',''))!='OFFICIAL':raise ValueError('비공식 자료 · 공식 근거 추가 확보 필요')
    fetcher=Fetcher(service.data_dir);raw=fetcher.get(doc['evidence_url'])
    # A redirect to an unofficial site cannot retain official-source status.
    if authority(fetcher.last.get('url',''))!='OFFICIAL':raise ValueError('최종 원문이 공식 출처가 아닙니다')
    _,body,truncated=text_content(raw);body=redact(body)
    if truncated or text_quality(body,doc.get('title',''))!='TEXT_AVAILABLE_UNVERIFIED':raise ValueError('완전한 본문 미확보 · 첨부·원문 수동 확인 필요')
    save(service,doc['id'],doc['source_revision_no'],body,'공식 HTML 원문 자동 복구 · 사실·물량 승인은 별도',[],
         '업무담당자 AI · 원문 복구',fetcher.last['sha256'])
    return dict(body_text=body,body_sha256=hashlib.sha256(body.encode()).hexdigest(),body_origin='MANUAL',source_revision_no=doc['source_revision_no'])
