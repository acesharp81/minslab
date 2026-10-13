/* 공급 6단계(기획서 1절). data 는 지금 확보한 데이터(신청 API·파일 기준).
   q 는 단계마다 답해야 할 질문, scope 는 공개 범위: 01~04 는 담당자 열람(gov), 05~06 은 국민에게도 공개(pub) — 발표자료 SHEET 03 '주택공급 6단계, 단계마다 답해야 할 질문'과 같은 문구다. */
export const STAGES = [
  { code: '01', name: '정책', q: '정부가 무엇을 얼마나 공급할 것인가', scope: 'gov', data: '없음(통계 목록 URL뿐)' },
  { code: '02', name: '사업화', q: '어느 위치에 누가 몇 호를 추진할 것인가', scope: 'gov', data: '파일로 받은 SH 공공재개발·재건축 현황' },
  { code: '03', name: '인허가', q: '실제로 사업할 수 있는 단계까지 왔는가', scope: 'gov', data: '건축HUB 주택·건축인허가' },
  { code: '04', name: '건설', q: '착공했고 현재 얼마나 진행됐는가', scope: 'gov', data: '건축HUB 착공·사용승인, 행복도시 준공계획, LH 준공예정 파일' },
  { code: '05', name: '공급', q: '언제, 누구에게, 몇 호를 분양·임대하는가', scope: 'pub', data: '마이홈 모집공고, LH 공급정보, 청약홈 2건' },
  { code: '06', name: '입주', q: '언제 실제 주택으로 완성되어 국민이 들어가는가', scope: 'pub', data: '청약홈 입주예정월, LH 단지정보 파일' },
] as const;
export const stageName = (code: string) => STAGES.find((s) => s.code === code)?.name ?? code;

/* 통계누리 실적 지표 → 6단계. 스펙 9.2·사업 레지스트리(lib/projects.js stageOf)와 같은 대응이다(준공 = 사용검사 = 06 입주).
   01 정책·02 사업화는 통계누리에 없어 지표를 보이는 화면에서 '자료 없음' 칸으로 자리만 보인다(components/charts/StageLegend.tsx · components/StageKpis.tsx) */
export const METRIC_STAGE = { permit: '03', start: '04', sale: '05', complete: '06' } as const;
export const METRIC_LABEL = { permit: '인허가', start: '착공', sale: '분양', complete: '준공' } as const;
