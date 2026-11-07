"""Exact user-supplied report bytes, with a separate normalized-text digest."""
import hashlib
from pathlib import Path
REPORTS={
 'EVIDENCE_REVIEW_20261104':'20261104-integrity',
 'EVIDENCE_REVIEW_20261105':'20261105-integrity',
}

PRIVATE_REPORTS={'EVIDENCE_REVIEW_20261106':'20261106-integrity'}

def artifact_path(data_dir,report_id,include_private=False):
 available=dict(REPORTS,**PRIVATE_REPORTS) if include_private else REPORTS
 if report_id not in available:raise ValueError('등록된 검토보고서가 아닙니다')
 return Path(data_dir)/'raw/officer_review'/available[report_id]/'original-report.txt'

def manifest(data_dir,report_id):
 try:path=artifact_path(data_dir,report_id,include_private=True)
 except ValueError:return dict(report_id=report_id,status='UNREGISTERED')
 if not path.is_file():return dict(report_id=report_id,status='MISSING')
 raw=path.read_bytes();text=raw.decode('utf-8-sig').replace('\r\n','\n').replace('\r','\n')
 return dict(report_id=report_id,status='PRESENT',filename=report_id+'.txt',original_name='붙여넣은 텍스트.txt',
  byte_sha256=hashlib.sha256(raw).hexdigest(),bytes=len(raw),normalized_text_sha256=hashlib.sha256(text.encode('utf-8')).hexdigest(),
  normalization='UTF8_BOM_REMOVED_LF_ONLY_V1',origin='USER_ATTACHMENT_ORIGINAL_BYTES',
  download_url=('/poc/home/api/publication-reviews/reports/'+report_id+'/original.txt') if report_id in REPORTS else None,
  access='PUBLIC_RECORDED_REPORT' if report_id in REPORTS else 'PRIVATE_REVIEW_ARCHIVE',
  scope='첨부된 원본 바이트. 별도로 변환·배포한 MD/PDF와 동일 파일이라고 추정하지 않음')
