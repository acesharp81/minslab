"""Bundle current presentation, scorecard and selected reproducibility evidence."""
from pathlib import Path
import hashlib,json,zipfile
ROOT=Path(__file__).resolve().parents[1];A=ROOT/'docs/analysis';W=A/'reliability_update_20261022'
files=[A/x for x in ['THE_JUTAEK_RELIABILITY_PRESENTATION_20261022.md','THE_JUTAEK_RELIABILITY_SLIDES_20261022.md','THE_JUTAEK_INTEGRITY_R02_20261022.md','THE_JUTAEK_CUMULATIVE_FORECAST_REVIEW_20261022.md','THE_JUTAEK_COLLEAGUE_CANDIDATE_REVIEW_20261022.md','HOME_OFFICIAL_FOLLOWUP_COLLECTION_20261021.md','HOME_ADDITIONAL_MAPPING_REVIEW_20261021.md','HOME_SUPPLY_TYPE_VERIFICATION_20261021.md']]
files += [ROOT/'docs'/x for x in ['HOME_OFFICIAL_HOME_START_COMPARISON_PRESENTATION_20261020.md','HOME_NONOFFICIAL_CONFIRMATION_APPLIED_20261020.md']]
files += [W/x for x in ['official-32.csv','official_185_comparison.csv','official-scorecard.json','comparison-summary.json','cumulative-audit.json','round.json','published.json','delivery-verification.json','report-validation.json','browser-verification.json','scorecard-screen.png']]
for folder,names in [('colleague_candidate_review_20261022',['candidate_223_results.csv','verified_sources.json','applied.json','verification.json','source_manifest.json']),('cumulative_forecast_review_20261022',['stage_summary.csv','project_stage_forecast.csv','prior_year_start_included.csv','export.csv','verification.json']),('official_followup_sources_20261021',['A04_seoul_monthly_types.csv'])]:files += [A/folder/x for x in names]
files += list((A/'colleague_candidate_review_20261022/sources').glob('*.pdf'))
files += [ROOT/'scripts'/x for x in ['update_reliability_scorecard_20261022.py','build_reliability_presentation_20261022.py','package_reliability_handoff_20261022.py']]
files += list((W/'scorecard_archives').glob('*.json'))
files += [W/'restored-scorecard-check.json']
for p in files:assert p.is_file(),str(p)
files=sorted(set(files));manifest={str(p.relative_to(ROOT)):dict(bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in files}
(W/'presentation-package-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
readme='''# the주택 발표·성적표 인계 묶음 · 2026-10-22

1. `docs/analysis/THE_JUTAEK_RELIABILITY_SLIDES_20261022.md`: 2페이지 발표용 Marp 원고.
2. `docs/analysis/THE_JUTAEK_RELIABILITY_PRESENTATION_20261022.md`: 상세 발표 마스터·32행 표·차이 설명.
3. `docs/analysis/THE_JUTAEK_INTEGRITY_R02_20261022.md`: 최신 2차 성적표(기존63.2/100, 신규 공식 비교12.95/20; 합산 금지).
4. `docs/analysis/reliability_update_20261022/`: 공식32행·185항목 CSV, 성적표JSON, 반영·화면 검증.
5. `docs/analysis/colleague_candidate_review_20261022/`: 223후보 처리대장·63공식근거·원문PDF.

공식32행 원표는10월21일 기준으로 고정했고10월22일 최신 관리사업 수량과 다시 대조했습니다. 185항목은10월21일 고정판이며 전체 수치의 새 독립 재검증을 뜻하지 않습니다. 원문 URL·판본·사업ID는CSV에 있습니다.

DB덤프는 별도 `backups/HOME_DB_20261022_*.zip`으로 전달합니다. 이 묶음은 발표용으로 선택한 근거이며 운영DB·원문 전체를 포함하지 않습니다. 첨부한 과거 검토보고서의 부속파일 링크 중 일부는 원 프로젝트 디렉터리를 기준으로 합니다. 원문 자체는 해당 보고서와CSV의 외부URL을 참고하세요. 과거 보고서의 누적값은 작성 당시 값으로 최신 발표 마스터와 구분합니다.

manifest.json의SHA-256으로 선택된 파일들의 무결성을 확인할 수 있습니다. scripts의재산정코드는운영환경과별도입력파일을필요로하며발표파일을읽기위해실행할필요는없습니다.
'''
out=A/'THE_JUTAEK_RELIABILITY_HANDOFF_20261022.zip'
with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
 z.writestr('README.md',readme);z.writestr('manifest.json',json.dumps(manifest,ensure_ascii=False,indent=2))
 for p in files:z.write(p,str(p.relative_to(ROOT)))
with zipfile.ZipFile(out) as z:
 assert z.testzip() is None
 for name,meta in manifest.items():assert hashlib.sha256(z.read(name)).hexdigest()==meta['sha256']
sha=hashlib.sha256(out.read_bytes()).hexdigest();out.with_suffix('.zip.sha256').write_text(sha+'  '+out.name+'\n')
print(json.dumps(dict(path=str(out),files=len(files)+2,bytes=out.stat().st_size,sha256=sha),ensure_ascii=False))
