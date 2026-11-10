"""List only deliberate public deliverables; no workspace file enumeration."""
import hashlib,json
from pathlib import Path
root=Path(__file__).resolve().parents[1];out=root/'release/public'
CATALOG=[
 ('v160-review.md','v1.6 개선·검증 기록','보고서 계승·시연 3종·원문 팝업·가상 안내'),
 ('inheritance-kit.zip','이전 인계 보고서 이어서 작성 샘플','HWPX 이전본 2개 · XLSX 현행화 · PDF 신규 업무'),
 ('01_이전인계_원본.zip','이어서 작성 1단계 · 이전 보고서 원본','직원 1→2 인수 완료 보고서용 HWPX 2개'),
 ('02_현행화_신규업무.zip','이어서 작성 2단계 · 현행화·신규 자료','기존 20%→80% 갱신 및 신규 10% 업무'),
 ('inheritance-guide.md','이전 보고서 이어 쓰기 안내','체크박스 선택·이력 표시·기대 결과'),
 ('inheritance-expected.json','계승 시연 기대값','갱신 1건 · 유지 1건 · 신규 1건'),

 ('employee-kit.zip','직원 순환·동일 파일명·그림 후처리 샘플','내부 ZIP 3개를 순서대로 등록하는 역순 판본 시험'),
 ('01_최신본_먼저등록.zip','1단계 · 최신본 먼저 등록','HWPX·XLSX·PDF 4개 / 본문 11월 8일 3차'),
 ('02_구판_나중등록.zip','2단계 · 같은 이름의 구판 추가','동일 경로·파일명 / 본문 11월 2일 1차'),
 ('03_미승인초안_마지막등록.zip','3단계 · 같은 이름의 미승인 초안','더 늦은 날짜·높은 차수라도 최신 확정본에서 제외'),
 ('employee-guide.md','직원별 인수인계 시작 안내','직원 전환·등록·확정·인수 확인'),
 ('employee-expected.json','직원·판본·그림 기대 결과','진행률과 최신본 그림 전송 범위'),
 ('grouping-samples.zip','여러 업무 묶기 샘플','6개 자료 → 자동 묶음 포함 5개 후보 → 3개 업무'),
 ('v150-review.md','v1.5 개선·검증 결과','직원·판본·그림·업무 그룹핑 및 알려진 제한'),
 ('version-samples.zip','파일명·버전 혼선 샘플 13개','중앙부처 개조식 · HWPX 4개 / XLSX 4개 / PDF 5개'),
 ('version-samples-shuffled.zip','파일명·업로드 순서 변경 샘플','동일 본문 13개를 무관한 파일명과 역순으로 재구성'),
 ('version-edge-conflict.zip','예외 1 · 같은 판본의 내용 상충','최신본 자동 선택을 보류해야 하는 입력 2개'),
 ('version-edge-undated.zip','예외 2 · 기준일 불명확','날짜가 불명확할 때 자동 선택을 보류하는 입력 2개'),
 ('version-edge-reversed.zip','예외 3 · 차수와 수정일시 모순','수정차수가 높아도 수정일시가 앞서면 선택 보류'),
 ('version-expected.json','파일명·버전 검증 정답표','4개 사업의 채택 판본·진행률·담당·현안 및 제외 초안'),
 ('version-guide.md','파일명·버전 혼선 시연 방법','시험 구성·기대값·판정 기준·지원 범위'),
 ('version-validation.json','실제 Solar 버전 판정 검증','실제 호출 결과·원문 근거·순서 변경 재검증'),
 ('version-review.md','파일명·버전 검토 결과','샘플 결과와 실문서 적용 한계'),
 ('version-report.html','버전 통합 인수인계 보고서 HTML','4개 사업의 최신 기준본·간트·진행 흐름'),
 ('version-report.pdf','버전 통합 인수인계 보고서 PDF','같은 확정본의 인쇄용 보고서'),
 ('version-report.docx','버전 통합 인수인계 보고서 DOCX','동일 확정본의 편집 가능한 보고서'),
 ('version-report.md','버전 통합 인수인계 보고서 Markdown','원문 근거를 포함한 텍스트'),
 ('practice-samples.zip','4개 업무 · 상세실무 원본 15개','단계별 보고·실무 기준·예산·연락망·증빙·동일업무 확인'),
 ('practice-report.html','완성된 상세실무편 HTML','간트·보고 흐름·실행서·공통 예산·관계자'),
 ('practice-report.pdf','완성된 상세실무편 PDF','원본에서 실제 생성한 최종 보고서'),
 ('practice-report.docx','완성된 상세실무편 DOCX','동일 확정본의 편집 가능한 사본'),
 ('practice-report.md','완성된 상세실무편 Markdown','원문 인용과 수정 이력을 포함한 텍스트'),
 ('handover-guide.pdf','사용·구동 안내서 PDF','15개 원본으로 처음부터 따라 하기'),
 ('handover-guide.docx','사용 안내서 DOCX','편집 가능한 사용 설명서'),
 ('handover-guide.md','사용 안내서 Markdown','텍스트 사용 설명서'),
 ('practice-expected.json','실무 샘플 정답표','업무별 실무 내용·금액·관계자·예상 결과'),
 ('practice-validation.json','실무 보고서 최종 검증','이번 Solar 원문 대조·기능·출력 검증과 충족 기준'),
 ('practice-review.md','최종 보고서 검토 결과','개선 내용·점검 결과·검증 범위'),
 ('quality-report.md','기존 모델 품질 비교 결과','이전 7개 업무 샘플의 GPT 1회 검증 보존'),
 ('quality-results.json','기존 품질 측정 JSON','이전 7개 업무에 한정된 측정 결과'),
 ('handover-source-v1.6.4.zip','프로그램 소스·실행 패키지','설치·테스트·라이선스 고지 포함'),
 ('handover-demo-kit-v1.6.4.zip','체험 자료 한 번에 받기','샘플·안내서·최종 보고서·검증 기록'),
 ('flow-samples.zip','이전 단계별 보고 샘플 11개','호환 체험 자료'),
 ('flow-report.html','이전 간트 중심 보고서 HTML','이전 확정본 보존'),
 ('flow-report.pdf','이전 간트 중심 보고서 PDF','이전 확정본 보존'),
 ('flow-validation.json','이전 4개 업무 검증 결과','이전 11개 원본 분석 기록')]
files=[]
for name,title,description in CATALOG:
 p=out/name
 if p.is_file():files.append({'file':name,'title':title,'description':description,'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
(out/'manifest.json').write_text(json.dumps({'version':'1.6.4','synthetic_only':True,'files':files},ensure_ascii=False,indent=2)+'\n')
print('Public deliverables:',len(files))
