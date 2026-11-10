import io,zipfile
from pathlib import Path
OUT=Path(__file__).resolve().parents[1]/'release/public'
rows=[('01_운영계획.txt','통합예약 서비스 개선','예약운영팀','GROUP-A','2026-11-02','20'),('02_중간보고.txt','통합예약 서비스 개선','예약운영팀','GROUP-A','2026-11-08','65'),('03_현장개선.txt','문화시설 접근성 보완','시설지원팀','GROUP-B','2026-11-03','25'),('04_접근성조치.txt','예약포털 접근성 보완','디지털지원팀','GROUP-B','2026-11-06','50'),('05_최종점검.txt','예약 화면 이용편의 개선','서비스기획팀','GROUP-B','2026-11-08','75'),('06_정산.txt','보조금 정산 승인','사업지원팀','GROUP-C','2026-11-08','40')]
with zipfile.ZipFile(OUT/'grouping-samples.zip','w',zipfile.ZIP_DEFLATED) as z:
 for name,title,owner,code,day,pct in rows:
  z.writestr(name,f'''업무: {title}
보고일: {day}
보고단계: 중간보고
문서관리번호: {code}-RPT
사업관리번호: {code}
수정차수: {1 if day<'2026-11-06' else 2 if day<'2026-11-08' else 3}차
수정일시: {day} 16:00
문서상태: 확정
전체 진행률: {pct}%
계획 시작일: 2026-11-01
담당: {owner}
현재 상태: {pct}% 진행 중
기한: 2026-11-13
다음 행동: 미접수 증빙을 요청하고 담당 부서를 확인
업무 개요: 동일 사업의 명칭·담당부서가 다른 문서를 사람이 확인해 연결하는 합성 시연자료
업무 범위: 2026년 {code} 사업
완료한 일: 현장 의견 취합 및 1차 점검
남은 업무: 증빙 대조와 결과 결재
현안: 담당 부서 간 인계 범위 확인 필요
참고: 실제 기관 자료가 아닌 합성 샘플입니다.
''')
print('grouping-samples.zip: 6 documents -> 5 candidates -> 3 groups after manual merge of 3')
