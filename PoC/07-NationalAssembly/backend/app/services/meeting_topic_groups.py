from __future__ import annotations

import hashlib
import re
from copy import deepcopy
from math import ceil
from typing import Any

from .official_brief_integration import semantic_tokens


GROUPING_VERSION = "assembly-meeting-topic-grouping/1.7"
GROUPING_METHOD = "TARGET_ONTOLOGY_WITH_ARTIFACT_SEPARATION_AND_AUDIT"


# A parent represents the policy target. Stance, request, criticism, and proposed
# action remain separate child topics so their evidence trails are not collapsed.
TARGET_ONTOLOGY: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    (
        "constitutional-order",
        "헌법·민주주의 제도",
        (
            "개헌", "헌법개정", "헌정질서", "권력분립", "삼권분립",
            "518민주화", "부마항쟁", "민주화운동",
            "정당해산", "해산제소", "민주적기본질서", "내란청산",
            "국민의힘해산", "헌법소원", "표현의자유",
        ),
    ),
    (
        "police-investigation",
        "경찰·수사제도",
        (
            "경찰개혁", "경찰청", "경찰수사", "수사인력", "수사관행",
            "중대범죄수사청", "중수청",
            "특별사법경찰", "특사경", "제주청장", "경찰청장사망사건",
            "경무관경찰서", "경찰내부감독", "치안혼란",
            "경찰의내부감독",
        ),
    ),
    (
        "criminal-case-procedure",
        "수사·기소·형사절차",
        (
            "공소장", "기소유예", "불기소", "불기소장", "기소계획서",
            "수사기록", "수사보고서", "수사처리계획보고서", "수사과정",
            "조작수사", "정치수사", "쪼개기기소", "피의사실공표",
            "녹취록", "녹음자료", "위법수집증거", "증거조작", "자료유출",
            "구속영장", "통신영장", "영장기각", "장기미제", "미제사건",
            "독립몰수", "범죄수익환수", "피해자회복", "형사재판",
            "수사권", "기소", "불기소처분", "수사처리계획",
            "공소취소", "공소취소특검법", "정치적수사", "허위자료",
            "허위서류", "협동수사", "공소기각", "경제법형사처벌",
            "경제법의형사처벌", "수사에서의인권보장", "수사인권보장",
            "수사준칙", "불송치",
        ),
    ),
    (
        "prosecution-judiciary",
        "검찰·사법제도",
        (
            "검찰개혁", "검찰청", "공소청", "기소권", "대법관",
            "대법원장", "대법원", "사법개혁", "재판독립", "법원",
            "형소법", "보완수사", "주임검사", "소송지휘권", "직접수사",
            "특검조사", "대법원행정처", "검찰총장공석", "법무부장관공석",
            "형사사법체계", "공소청출범", "검찰청건물", "서부지검",
            "공수처", "고위공직자범죄수사처", "공소장", "기소유예",
            "형사소송법", "통신영장", "재판배당", "피해자권리",
            "군형사소송법", "보안수사권", "보완수사권",
            "파면검사", "피선거권박탈", "전관예우",
            "특별검사", "특검법", "재정신청", "군사법정보시스템",
            "군사법원법",
            "사법제도", "검사정원",
        ),
    ),
    (
        "public-discipline",
        "공직기강·감찰",
        (
            "공직기강", "공직자감찰", "감찰제도", "감찰권", "내부감찰",
            "수사자료유출", "수사문건유출", "공무상비밀", "총리실과장",
            "감찰", "공직자범위", "기획총균과정", "총리실직원",
            "과충성행위", "내부자료유출",
            "감사원", "강압적감사", "특수활동비", "자체감사",
            "감사위원특수비",
            "특검특활비",
        ),
    ),
    (
        "public-integrity-funds",
        "청탁·후원금·공직윤리",
        (
            "정치자금", "후원금", "알선뇌물", "알선약속", "부정청탁",
            "청탁금지법", "직무관련성", "회계부정", "공모절차",
            "정보공유", "이해충돌", "민원전달", "고충민원", "청탁의혹",
            "유착설", "행위와이익", "이익간관계", "후원회",
            "청탁문자", "청탁부당성", "청탁의부당성",
            "배우자주식보유", "사외이사임명", "금융실명동의서",
            "차용증서", "재원출처",
        ),
    ),
    (
        "public-appointments",
        "공직 인사·검증",
        (
            "인사검증", "인사청문", "공직후보", "장관후보", "후보자검증",
            "내각인사", "공정한인사", "공직인사", "인사권",
            "국무위원임명", "대통령임명", "내각인사", "법무후보자",
            "후보자자격", "후보자지명", "직무적합성", "장관임명",
            "임명반대", "임명부적절성", "지명철회", "정치적중립성",
            "후보자의눈물", "후보자비판", "후보자임명", "후보자재청",
            "후보자자격", "개각발표", "이사장해임",
            "김현지실장", "실장해임",
            "수사기관수장", "직무대행체제", "기관장임명지연",
            "후보자의적격성",
            "국무총리재청", "재청권",
        ),
    ),
    (
        "assembly-procedure",
        "국회 운영·의사절차",
        (
            "대정부질문", "본회의출석", "국무위원출석", "회의폐회",
            "의사진행", "국회의원호칭", "의원협조", "국회절차",
            "장관출석", "출석지연", "총리질의", "대정부질의",
            "출장경위", "회의후남은실행", "회의마무리", "산회선포",
            "간사선임", "소위원장선출", "법안심사소위원회", "소위원회기능",
            "안건회부", "대체토론", "증인채택", "의사일정별", "법안처리절차",
            "출석확인", "토론자지정", "위원장발언",
            "정기국회개막", "초당적협치",
            "국정감사계획", "국정감사계획서", "국정감사운영",
            "의사일정마무리", "회의산회", "인사청문회종료", "산회선포",
            "자료제출요구", "자료제출", "증인출두", "증인출석",
            "질문기회", "질의순서", "발언기회", "회의진행", "간사협의",
            "출석정보", "청문회진행", "발언예의", "대상자출석",
            "예의적조율", "의원의공부", "인사청문회대상자의출석",
            "법안의결절차", "안건재검토", "토론순서", "간사간회의",
            "회의개회", "의사일정안내", "후속법안절차",
            "의사일정작성", "법안상정", "법률안의결", "국무위원불출석",
            "국회불출석", "국회도서관강당", "위원장반말", "위원장의반말",
            "증인협의", "기관증인", "일반증인", "숙려기간", "제안설명",
            "심사보고", "투표실시", "가결선포", "무기명투표", "투표방법",
            "국정감사대상기관", "외빈방청", "방청석",
            "법안의결", "행정안전위원회제안",
            "간사직적합성", "법률안심사", "청원심사소위원회", "소위원회구성", "정회선포",
            "정책실장출석",
        ),
    ),
    (
        "medical-pharma-regulation",
        "의약품·임상시험 규제",
        (
            "식약처", "식품의약품안전처", "임상시험", "인간임상시험",
            "임상승인", "치료제", "백신", "동물실험", "실험자료",
            "의약품허가", "제네셀", "의약품개발", "식약사",
        ),
    ),
    (
        "elections-public-opinion",
        "선거제도·공론 환경",
        (
            "사전투표", "선거관리", "선거구", "유권자", "여론조사",
            "침묵의나선", "탈진실", "허위정보", "가짜뉴스", "당파성",
            "정치적의식", "국정소통", "여론왜곡", "추천알고리즘",
            "알고리즘", "공정성민감도", "유권자이념", "국민의생각과느낌",
            "국민여론", "컨센서스",
            "공직선거법", "위탁선거",
            "선거무효", "당선무효", "선거소청", "중앙선관위",
            "선관위자료제출",
            "투표관리",
        ),
    ),
    (
        "balanced-development",
        "균형발전·지역 현안",
        (
            "균형발전", "지역균형", "지방거점국립대", "지역별투자",
            "새만금", "전북", "경기도재정", "지역발전", "지역소멸",
            "광주군공항", "통합신공항", "지방공항", "지역SOC",
            "지역별공항", "공항사업", "광주공공항", "대구경북통합신공항",
            "공항이전", "군공항이전", "메가프로젝트", "지역소외감",
            "메가특구", "특구기업지원", "평택지원특별법",
            "기회발전특구", "개발제한구역", "광주전남통합", "초광역",
            "접경지역지원", "농어촌기본소득", "지역사랑상품권",
            "혁신도시2차", "민통선조정",
            "마을공동체지원법",
        ),
    ),
    (
        "industry-semiconductors",
        "산업·반도체 정책",
        (
            "반도체클러스터", "반도체산업", "첨단산업", "산업클러스터",
            "산업정책", "공급망", "반도체정책", "반도체인력",
            "호남반도체", "현장실무용반도체", "전력용수공급",
            "2030년양산",
            "반도체서남권",
        ),
    ),
    (
        "automotive-ev",
        "자동차·전기차 산업",
        (
            "전기차", "자동차산업", "자동차부품", "구매보조금",
            "전기차생태계", "전기차전략산업",
        ),
    ),
    (
        "shipbuilding-maritime",
        "조선업·해양산업",
        (
            "조선업", "조선소", "선박", "화물창", "하물창", "MASGA",
            "마스가", "마스카", "조선수요", "조선규제", "조선인력",
            "로열티자금", "로열티수익", "로자금", "로소송",
        ),
    ),
    (
        "energy-electricity",
        "에너지·전력 정책",
        (
            "전기본", "에너지믹스", "전력망", "전력공급", "열에너지",
            "전력정책", "전력인프라", "송전망", "전력생산", "비축탄",
            "지역별전기요금", "에너지정책",
            "재생에너지", "해상풍력", "햇빛소득마을", "가상발전소",
        ),
    ),
    (
        "water-resources-climate",
        "수자원·가뭄 대응",
        (
            "용수공급", "물공급", "물관리", "가뭄", "생활용수",
            "공업용수", "농업용수", "냉각수", "재이용수", "댐수",
            "동복댐", "물사용우선순위", "지천댐", "댐건설",
        ),
    ),
    (
        "environment-waste",
        "환경·폐기물 관리",
        (
            "쓰레기직매립", "폐기물반입", "민간위탁폐기물", "매립지",
            "환경오염", "환경변화", "훼손지역", "훼손부지", "주민보상",
            "환경간접세", "자원순환",
            "해양쓰레기", "도서지역쓰레기",
        ),
    ),
    (
        "enterprise-innovation",
        "기업·중소기업 혁신",
        (
            "중소기업R&D", "중소기업연구개발", "기업투자전략",
            "기업지원", "연구개발삭감", "R&D삭감",
            "기업과국가의투자전략", "이차전지산업", "이차전지지원",
        ),
    ),
    (
        "housing-real-estate",
        "주택·부동산 정책",
        (
            "부동산", "주택공급", "아파트", "전세", "주거안정", "부동산세",
            "가계대출", "대출정책", "실수요자", "1가구1주택", "1주택자",
            "주택세제", "도심복합", "도심공공주택", "도심복합개발",
            "LH용지", "비주택용지", "임대차보호법", "종부세", "양도소득세",
            "용산공원", "도시재구조화", "수도권외곽지역금융규제",
            "청산유보금", "조합해산",
            "공시가격", "공정시장가액비율", "실거주판정", "민간임대",
            "지식산업센터", "3기신도시", "신도시건설",
            "주거난", "지분적립형주택", "서울시주택공", "LH구조개편", "전월세시장",
        ),
    ),
    (
        "finance-investment",
        "금융·투자자 보호",
        (
            "주가조작", "불공정거래", "금융투자", "투자자보호", "ETF",
            "KH필룩스", "배상윤", "금융시장", "자본시장", "통화정책",
            "금융정책", "금융규제", "금융위원회", "공적자금", "IMF사태", "홈플러스",
            "전단채", "전단체사기",
            "청년도약계좌", "ISA", "자금세탁방지", "국민성장펀드",
            "위험자산투자", "코스피", "카지노사업자",
            "레버리지", "가계총량관리",
        ),
    ),
    (
        "fair-trade-platform",
        "공정거래·플랫폼 상생",
        (
            "납품대금", "납품기간", "지급기한", "대규모유통업법",
            "대형유통업법", "납품업자", "납품업체", "입점업체",
            "플랫폼입점", "온라인중개플랫폼", "수수료공개", "하도급대금",
            "중소납품", "유통업체",
        ),
    ),
    (
        "consumer-financial-protection",
        "소비자·금융사기 보호",
        (
            "방문판매", "방문판매법", "전자금융거래법", "전기통신금융사기",
            "통신금융사기", "금융사기방지", "보이스피싱", "피해금환급",
            "통신사기피해자", "사기피해환급",
        ),
    ),
    (
        "taxation",
        "조세·세제 정책",
        (
            "세제혜택", "세법", "부가가치세", "환경간접세", "조세감면",
            "세부담", "과세기준", "비과세", "세액공제", "소득공제",
            "공정시장가액비율", "조세정책",
            "양도세",
        ),
    ),
    (
        "livelihood-economy",
        "민생·경제 안정",
        (
            "민생경제", "민생안정", "생활안정", "시장경제", "경제양극화",
            "소득양극화", "고용안정", "물가안정", "소상공인", "자영업자",
            "생활물가", "주거부담", "저성장", "국민소득", "경제성장",
            "잠재성장률", "공정한분배", "K양극화",
            "성수품", "가격안정", "민생대개혁", "경제살리기",
        ),
    ),
    (
        "budget-public-finance",
        "예산·재정 운용",
        (
            "예산", "재정규모", "재정운용", "기금재원", "미래대응기금",
            "통치자금", "세입처리", "국고자금", "회계연도", "이월사업",
            "예산전용", "지급불능", "미지급", "교부세", "통합지원금",
            "미래기금", "미래대응기금", "미래대행기금", "세수증가",
            "국가채무", "재정정책", "재정정책혼선", "세제개편안",
            "농특세", "농특회계", "목적세",
            "정부기금", "통합기금", "초과세수", "조세지출", "재정지출",
            "공공기금", "기금통합", "의무지출", "세수전달",
            "국방비미지출", "미지출사태",
            "기금재정건전성", "정책펀드", "지방재정교부금",
        ),
    ),
    (
        "disability-care-services",
        "장애인 돌봄·발달 서비스",
        (
            "발달장애", "장애인가족", "아동발달센터", "한국아동발달센터",
            "사회적협동조합", "발달재활", "장애아동", "바우처",
            "주간활동서비스", "서비스기관선정", "청각장애인",
            "장애인교육", "돌봄공간", "발달장애가족",
        ),
    ),
    (
        "welfare-care-family",
        "복지·돌봄·가족 지원",
        (
            "사회복지", "복지시설", "한부모", "양육비", "다문화가정",
            "아이돌봄", "자녀돌봄", "어린이집", "돌봄지원", "공적돌봄",
            "국가복지", "성평등정책", "결혼페널티", "경로당", "노인식사",
            "어르신식사", "부식비", "급식지원",
            "기초연금", "기준중위소득", "중앙생활보장위원회", "발달재활",
            "장애아동", "노후소득보장", "상대적빈곤", "육아휴직",
            "공무원재해보상", "재해보상법", "복지체제",
        ),
    ),
    (
        "youth-employment",
        "청년·고용·노동",
        (
            "청년고용", "청년층", "고용률", "고용제도", "외국인노동자",
            "외국인근로자", "근무처변경", "근로자", "임금차별", "노동정책",
            "청년일자리", "플랫폼노동", "폭염노동", "열사병", "노동중지",
            "소득보전", "일하는사람기본법", "채용연계", "훈련프로그램",
            "노동시장이중구조", "고용평등", "임금공시", "동일가치노동",
            "체불임금", "채불임금", "체불", "공무원노조", "전교조", "법외노조",
            "노조결정",
            "노동시장의이중구조", "배달라이더",
        ),
    ),
    (
        "public-safety-health",
        "국민안전·보건 대응",
        (
            "교제폭력", "관계성폭력", "마약범죄", "재활체계", "구급대",
            "어린이보호구역", "속도제한", "국민생명", "재난안전",
            "유실지뢰",
            "강풍피해", "홍수실종", "보건의료", "감염병", "폭우피해",
            "칼858", "KAL858", "항공기사고", "유족감시단",
            "세월호", "이태원참사", "실종사건", "물류창고화재",
            "배터리화재", "리튬배터리", "소방구급차", "재난기본법",
            "대홍수", "인명수색", "방염", "소방시설",
            "재난취약계층", "자살률", "날씨예보", "원산지표시",
            "급식업체",
            "마약류치료보호", "소방인력", "재난대응시스템", "해양경찰실종",
        ),
    ),
    (
        "healthcare-medical-system",
        "보건의료·공공의료",
        (
            "공공병원", "의료인프라", "의료취약", "상급종합병원",
            "지역의료", "지방의료", "국립의전원", "국립중앙의료원",
            "의료중심도시", "의료공공기관", "미프진", "의약품접근",
            "여성건강", "태아생명", "약물도입", "의대병원", "치대병원",
        ),
    ),
    (
        "tobacco-product-safety",
        "담배·유해제품 관리",
        (
            "전자담배", "담배세금", "담배협회", "독성시험", "불법유통",
        ),
    ),
    (
        "children-digital-safety",
        "아동·청소년 보호",
        (
            "청소년SNS", "SNS과의존", "아동보호", "청소년보호",
            "학교폭력", "디지털과의존", "소년보호처분",
        ),
    ),
    (
        "sexual-violence-victim-protection",
        "성폭력·범죄피해자 보호",
        (
            "성폭력범죄", "성폭력처벌법", "성폭력피해자", "미성년성폭력",
            "아동청소년성보호법", "아동청소년의성보호", "성범죄피해",
            "영상녹화증거능력", "검사면담증거능력",
        ),
    ),
    (
        "immigration-birth-registration",
        "이민·출생등록·체류권",
        (
            "외국인아동", "출생등록", "미등록부모", "그림자아동",
            "국적법", "출입국", "체류권", "이주아동",
        ),
    ),
    (
        "agriculture-rural",
        "농업·농촌 정책",
        (
            "농촌", "농민", "농지", "임차농", "고령농", "영농권",
            "스마트팜", "비닐하우스", "농생명용지", "농업정책",
            "논콩", "농축산물보호", "농어촌상생기금",
            "농어촌상생협력기금", "농업인력", "국가농업AX",
        ),
    ),
    (
        "forest-disaster",
        "산림·산림재난 대응",
        (
            "산림재난", "산불", "산사태", "산림병해충", "재선충",
            "소나무재선충", "긴급산림재난", "산림대응",
        ),
    ),
    (
        "transport-infrastructure",
        "교통·공항·지역 인프라",
        (
            "고속도로", "도로연결", "휴게소", "군용비행장", "신공항건설",
            "공항사업", "서해평화도로", "접경지역종합계획", "도로공사",
            "기부대양여", "소음피해보상", "거가대교", "거제통영고속도로",
            "통행료", "예타조건부", "완도강진", "예비타당성",
            "통합심의절차",
            "달빛고속철도", "광역교통망", "광역버스", "트램", "철도망",
            "BRT", "청주공항", "무안공항", "광주공항", "국도79호선",
            "지천다리",
        ),
    ),
    (
        "veterans-history",
        "보훈·독립유공자 예우",
        (
            "국가보훈", "보훈병원", "보훈수당", "보훈의료", "보훈예우",
            "독립유공자", "625전쟁희생자", "안중근", "유해관리", "무덤발굴",
            "명예수당", "공적재평가", "참전유공", "참전수당",
            "유공자배우자", "미망인배우자",
            "국가유공자", "4·3보상금",
        ),
    ),
    (
        "education",
        "교육 정책·교육기관",
        (
            "교육부", "교육감", "수능", "채점신뢰성", "서울대학교",
            "올리브학교",
            "국립대", "교육정책", "학술림", "학교교육", "수시모집",
            "수시원서", "학생구제", "교권", "교사보호", "아동학대신고",
            "정서적학대", "교육재정", "지방인재장학", "적정학생수",
            "교육인재계정", "국교위포럼", "공론화부재",
            "지방학생", "수도권대학진학",
        ),
    ),
    (
        "culture-tourism",
        "문화예술·관광 정책",
        (
            "영화발전기금", "영화지원", "예술인", "관광인구", "관광정책",
            "체류형관광", "문화예술", "문체부", "영화할인권", "유네스코",
            "유산청", "문화재", "문화유산",
        ),
    ),
    (
        "media-public-communication",
        "언론·정부광고 정책",
        (
            "정부광고", "광고집행", "광고매체", "집행률", "열독률",
            "TBS", "공영방송", "언론정책", "미디어정책", "YTN", "JTBC",
            "방송법", "방송통신위원회", "KOBACO", "언론진흥재단",
            "시청자미디어재단", "보편적시청권", "언론보도", "방송사",
        ),
    ),
    (
        "trade-climate-industry",
        "통상·산업전환",
        (
            "통상국가", "통상정책", "철강", "생산세액공제", "탄소중립",
            "핵심소재", "정책금융", "산업은행", "LCC통합", "경제안보",
            "대미투자", "관세협상",
        ),
    ),
    (
        "public-assets",
        "국유재산·공공시설 관리",
        (
            "국유재산", "국유지", "공공시설", "무상임대", "무상양여",
            "공공재산", "공유재산", "물품관리법",
            "국가자산",
        ),
    ),
    (
        "privacy-communications",
        "개인정보·통신 이용자 보호",
        (
            "개인정보", "개인정보유출", "통신품질", "해외로밍", "이심",
            "2심사용", "위치정보", "GPS자료", "통신자료", "정보보호",
        ),
    ),
    (
        "ai-digital-infrastructure",
        "AI·디지털 인프라",
        (
            "인공지능", "AI정책", "AI산업", "데이터센터", "디지털전환",
            "알고리즘규제", "온라인플랫폼", "AI기반", "AI인력",
            "AI산업대전환", "AI규제", "글로벌AI투자", "GTC코리아",
            "디지털격차", "업스테이지", "업스테리지", "독파모", "도파모",
            "모두의AI", "플랫폼경제",
            "AI의료플랫폼", "AX플랫폼", "AI인재유치",
        ),
    ),
    (
        "north-korea-nuclear",
        "북핵 위협·억제 대응",
        (
            "북핵", "핵무기", "핵공유", "전술핵", "핵억제", "핵위협",
            "핵잠수함", "확장억제", "전략자산", "정찰위성", "위성영상",
            "미사일방어", "방공미사일", "핵무장", "핵방격", "F35", "B16",
        ),
    ),
    (
        "inter-korean-peace",
        "남북관계·평화체제",
        (
            "남북관계", "남북대화", "남북정상", "북미대화", "북미정상",
            "평화체제", "판문점", "4자대화", "사자대화", "북방정책",
            "두국가론", "919군사합의", "남북소통", "대북정책",
            "한반도평화", "한반도정세", "남북평화", "북미관계", "북미회담",
            "대화재개", "소통채널복원", "북한군포로", "북극항로",
        ),
    ),
    (
        "frontline-operations",
        "군사분계선·전방 경계",
        (
            "군사분계선", "MDL", "최전선", "전방경계", "경계태세",
            "경계작전", "경고사격", "월선", "GP환경", "비무장지대",
            "DMZ", "휴전선", "경계선", "불법침범", "GP부대", "최전방",
        ),
    ),
    (
        "military-personnel-reform",
        "군 구조·인력·복무",
        (
            "모병제", "선택적모병", "전작권", "전시작전통제권", "사관학교",
            "군복무", "복무기간", "군지휘관", "지휘관인사", "자주국방",
            "군통수권", "군구조", "병력구조", "병역제도", "지휘관",
            "전역전환", "합동성", "병역특례",
            "군생활",
        ),
    ),
    (
        "alliance-defense",
        "한미동맹·연합방위",
        (
            "한미동맹", "한미관계", "연합방위", "연합훈련", "한미훈련",
            "군사연습", "상호군수지원", "주한미군", "방위비분담",
            "한미연합", "군수지원", "한미간",
        ),
    ),
    (
        "defense-industry-capability",
        "국방전력·방위산업",
        (
            "드론전력", "무인기", "방산수출", "무기수출", "국방전력",
            "전력강화", "장보고프로젝트", "우크라이나무기", "방위산업",
            "드론산업", "드론기반", "우크라이나수출",
            "군의드론도입",
            "드론도입",
        ),
    ),
    (
        "middle-east-dispatch",
        "중동 정세·파병",
        (
            "호르무즈", "이란전", "중동파병", "국군파병", "파병동의",
            "중동정세", "파병", "이란관련", "이란반응",
        ),
    ),
    (
        "japan-relations",
        "한일관계·대일 현안",
        ("한일관계", "대일외교", "일본외교", "후쿠시마", "강제징용", "독도"),
    ),
    (
        "china-taiwan",
        "중국·대만 정세",
        ("대만해협", "대만문제", "양안관계", "중국외교", "한중관계", "대만"),
    ),
    (
        "public-diplomacy-culture",
        "공공외교·문화 협력",
        (
            "공공외교", "문화외교", "한국문화", "한글확산", "한류",
            "영화기금", "국제문화", "문화협력",
        ),
    ),
    (
        "international-cooperation",
        "외교·국제협력",
        (
            "다자외교", "국제협력", "외교전략", "외교정책", "국제정세",
            "재외국민", "개발협력", "ODA", "외교정상화", "지정학적위기",
            "인도적지원", "재외공관", "G20",
        ),
    ),
    (
        "presidential-accountability",
        "대통령 권한·책임",
        (
            "대통령책임", "대통령권한", "대통령사법", "대통령의혹",
            "대통령자격", "대통령국정운영", "대통령법위반", "대통령탄핵",
            "대통령의사법", "대통령의법", "대통령장남", "군골프장",
            "대통령의국정", "청와대정책실", "태릉CC", "태릉골프장",
        ),
    ),
    (
        "government-operations",
        "정부 운영·행정 책임",
        (
            "국무위원책임", "총리책임", "정부조직", "행정절차", "정부운영",
            "국정운영책임", "부처간협업", "행정책임",
            "국민통합", "실용정부", "공무원및행정", "국정운영현황",
            "부처간칸막이", "정부통합운영", "행정통합정책", "특례시",
            "공공기관지방이전", "국무조정실", "담당부처역할",
            "총리책임", "민심전달", "국가기본임무", "정부국가관",
            "총리의민심", "총리지지율", "개혁초심", "정책일관성",
            "출연기관재지정", "출연기관지정",
            "법무부장관소통", "법무부장관의소통", "시행령개정안",
            "기관분리통합", "공공기관통합",
            "정부신뢰도", "훈장부여오류",
        ),
    ),
    (
        "national-security-strategy",
        "국가안보 전략",
        (
            "안보정책", "안보개념", "동북아시아안보", "국가안보",
            "국방전략", "정부준비태세", "국방부공청회",
        ),
    ),
    (
        "political-accountability",
        "정치 현안·공직 책임",
        (
            "철거민특공", "한동훈", "용혜인", "용희인", "이재명정권",
            "민주당폄훼", "폭로성발언", "정책동의여부", "사찰의혹",
            "부당포렌식", "이재명대표이름", "언더조직", "정부내영향력",
        ),
    ),
)


# This visual hierarchy is separate from matching rules. Moving a star-map
# branch must never change how report topics are classified.
ONTOLOGY_DOMAINS: tuple[tuple[str, str, str, tuple[str, ...]], ...] = (
    (
        "institutions", "헌정·사법·행정", "#5eead4",
        (
            "constitutional-order", "police-investigation",
            "criminal-case-procedure", "prosecution-judiciary",
            "public-discipline", "public-integrity-funds",
            "public-appointments", "assembly-procedure",
            "medical-pharma-regulation", "elections-public-opinion",
            "presidential-accountability", "government-operations",
            "political-accountability",
        ),
    ),
    (
        "economy", "경제·산업·재정", "#fbbf24",
        (
            "balanced-development", "industry-semiconductors",
            "automotive-ev", "shipbuilding-maritime", "energy-electricity",
            "water-resources-climate", "environment-waste",
            "enterprise-innovation", "housing-real-estate",
            "finance-investment", "fair-trade-platform",
            "consumer-financial-protection", "taxation",
            "livelihood-economy", "budget-public-finance",
        ),
    ),
    (
        "society", "사회·생활·문화", "#fb7185",
        (
            "disability-care-services", "welfare-care-family",
            "youth-employment", "public-safety-health",
            "healthcare-medical-system", "tobacco-product-safety",
            "children-digital-safety", "sexual-violence-victim-protection",
            "immigration-birth-registration",
            "agriculture-rural", "forest-disaster", "veterans-history",
            "education", "culture-tourism", "media-public-communication",
        ),
    ),
    (
        "infrastructure", "국토·통상·디지털", "#60a5fa",
        (
            "transport-infrastructure", "trade-climate-industry",
            "public-assets", "privacy-communications",
            "ai-digital-infrastructure",
        ),
    ),
    (
        "security", "외교·안보·국방", "#c084fc",
        (
            "north-korea-nuclear", "inter-korean-peace",
            "frontline-operations", "military-personnel-reform",
            "alliance-defense", "defense-industry-capability",
            "middle-east-dispatch", "japan-relations", "china-taiwan",
            "public-diplomacy-culture", "international-cooperation",
            "national-security-strategy",
        ),
    ),
)


_DETAIL_MARKERS = re.compile(
    r"\s*(?:관련|에\s*대한|대응|강화|필요성?|촉구|제안|검토|문제점?|논란|"
    r"개선|방안|대책|평가|지적|요구|질의|우려|과제|입장|책임|점검|확인).*$"
)
_NON_WORD = re.compile(r"[^0-9A-Za-z가-힣]+")

_DYNAMIC_GENERIC_TOKENS = {
    "관련", "대응", "강화", "필요", "필요성", "촉구", "제안", "검토",
    "문제", "문제점", "논란", "개선", "방안", "대책", "평가", "지적",
    "요구", "질의", "우려", "과제", "입장", "책임", "점검", "확인",
    "정부", "국회", "위원회", "회의", "정책", "제도", "사업", "예산",
    "지원", "추진", "마련", "운영", "현황", "계획", "필요하다",
    "개정안", "제정안", "법률안", "법안", "특별법", "시행령", "의결",
    "가결", "보류", "처리", "절차", "적절성", "실효성", "효과성",
    "신뢰성", "타당성", "위법성", "합법성", "정당성", "형평성",
    "공정성", "투명성", "부당성", "사실관계", "판단", "기준", "방향",
    "일정", "발표", "자료", "제출", "약속", "비판", "주장", "해명",
    "결정", "이유", "사유", "역할", "대비", "oecd", "통합", "분리",
    "기관", "공공기관", "마무리", "산회", "당부", "인사",
    "후보자", "장관후보자", "법무부장관", "청문회",
}
_DYNAMIC_GROUP_THRESHOLD = 0.76

# These describe the transcript/reporting interaction rather than a policy
# target. They remain visible and evidence-linked, but do not distort policy
# ontology coverage.
_REPORT_ARTIFACT_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"^사실관계(?:확인)?(?:의)?(?:필요성)?$"),
    re.compile(r"^발언자교정.*질문시작$"),
    re.compile(r"^가정적질문.*답변거부.*$"),
    re.compile(r"^화자간발언신뢰성.*갈등.*$"),
    re.compile(r"^불명확한반복발언.*의사소통.*$"),
    re.compile(r"^질의자교체$"),
    re.compile(r"^인사발언$"),
    re.compile(r"^개회및신규임원인사$"),
    re.compile(r"^법안심사업무.*정회선포$"),
    re.compile(r"^재재청요구가능여부논의시작$"),
)

_DYNAMIC_GENERIC_SUFFIXES = (
    "일부개정법률안", "전부개정법률안", "개정법률안", "제정법률안",
    "일부개정안", "전부개정안", "법률안", "개정안", "제정안",
)


_REPORT_LANGUAGE_REPAIRS: tuple[tuple[str, str], ...] = (
    ("어린이 보호고", "어린이 보호구역"),
    ("책임과자 회복", "책임과 피해자 회복"),
    ("출석 불고", "출석 불응"),
    ("양순희 @(양순희) @(양순희) 씨", "양순희 씨"),
    ("마스카", "마스가(MASGA)"),
    ("미중 정부 간 협력", "한미 정부 간 협력"),
    ("하물창", "화물창"),
    ("커터제", "쿼터제"),
    ("미래대행기금", "미래대응기금"),
    ("매거 프로젝트", "메가 프로젝트"),
    ("강주군공항", "광주 군공항"),
    ("로 자금", "로열티 자금"),
    ("로 소송", "로열티 관련 소송"),
    ("로 수익", "로열티 수익"),
    ("선박 로 지급", "선박 로열티 지급"),
    ("지급된 로가", "지급된 로열티가"),
    ("원의 로가", "원의 로열티가"),
    ("inter-agency", "기관 간"),
    ("정기금융사기", "전기통신금융사기"),
    ("및금 환급", "피해금 환급"),
    ("국가수사본부장 혼의", "국가수사본부장 협의"),
    # Source-checked against linked official utterances; stored report text stays intact.
    ("정책편드", "정책펀드"),
    ("감천 - 건설", "감천댐 건설"),
    ("감천 건설", "감천댐 건설"),
    ("광세 협상", "관세 협상"),
    ("서해5도 무인도 유실지 문제", "강화도 등 섬 지역 유실지뢰 출입 통제 문제"),
    ("서해5도 무인도에서 유실지이", "강화도 등 섬 지역에서 유실지뢰가"),
    ("가 대응 및 소방력 강화", "가뭄 대응 및 소방력 강화"),
    # Correct an unambiguous Korean labor-law spelling error in the derived view.
    ("채불 노동자", "체불 노동자"),
    ("채불된 노동자", "체불된 노동자"),
    ("채불 관련", "체불 관련"),
    ("채불 형량", "체불 형량"),
    ("채불 과징금", "체불 과징금"),
    # Adjacent official utterances identify the actual justice and prison topics.
    ("윤석열 정부 검찰 결정 및 사법부 오염 논란", "서부지검·대검 수발신 문서 제출 요구"),
    ("윤석열 정부 시절 검찰의 결정과 사법부 오염주장에 대해 화자 0은 일개 으로서 의견을 밝히고, 상층부 권력의 핵심부에서 결정이 내렸고, 자료 수신이하다는를 밝혔다.",
     "김의겸 위원은 2024년 8월 서부지검과 대검 사이에 오간 김승원 후보자 관련 수발신 문서의 제출을 요구했다."),
    ("교육과 잠자리 문제의 분리 및 개선 요구", "교도소 내 마약범죄 초범·전문 유통사범 수용실 분리 요구"),
    ("교육과 잠자리 문제를 분리하고 기준에 맞춰 점검·개선을 요구하는 논의",
     "단순 투약 초범과 전문 유통사범의 교육·수용실 분리를 점검하고 개선하도록 요구했다."),
)


def _repair_report_text(value: object) -> str:
    text = str(value or "")
    for source, replacement in _REPORT_LANGUAGE_REPAIRS:
        text = text.replace(source, replacement)
    return text


def _repair_brief_language(brief: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(brief)
    for field in ("headline", "summary"):
        if result.get(field) is not None:
            result[field] = _repair_report_text(result[field])
    for topic in result.get("topics") or []:
        if not isinstance(topic, dict):
            continue
        for field in ("title", "summary"):
            if topic.get(field) is not None:
                topic[field] = _repair_report_text(topic[field])
        for point in topic.get("speaker_points") or []:
            if isinstance(point, dict) and point.get("summary") is not None:
                point["summary"] = _repair_report_text(point["summary"])
    for task in result.get("tasks") or []:
        if not isinstance(task, dict):
            continue
        for field in ("title", "topic_title"):
            if task.get(field) is not None:
                task[field] = _repair_report_text(task[field])
    return result


def _compact(value: object) -> str:
    return _NON_WORD.sub("", str(value or "")).upper()


def _ontology_match(topic: dict[str, Any]) -> dict[str, Any] | None:
    title_haystack = _compact(topic.get("title") or "")
    summary_haystack = _compact(topic.get("summary") or "")
    best: tuple[int, int, str, str, str, str] | None = None
    for order, (key, title, keywords) in enumerate(TARGET_ONTOLOGY):
        normalized = [(_compact(keyword), keyword) for keyword in keywords]
        title_matches = [
            (keyword, raw) for keyword, raw in normalized
            if keyword and keyword in title_haystack
        ]
        summary_matches = [
            (keyword, raw) for keyword, raw in normalized
            if keyword and keyword in summary_haystack
        ]
        matches = title_matches or summary_matches
        if not matches:
            continue
        matched_keyword, matched_raw = max(
            matches, key=lambda item: (len(item[0]), item[0])
        )
        score = (
            (1000 if title_matches else 0)
            + len(matched_keyword) * 10
            + len(matches)
        )
        candidate = (
            score, -order, key, title, str(matched_raw),
            "title" if title_matches else "summary",
        )
        if best is None or candidate > best:
            best = candidate
    if best is None:
        return None
    return {
        "key": best[2],
        "title": best[3],
        "matched_keyword": best[4],
        "matched_field": best[5],
        "score": best[0],
    }


def _is_report_artifact(topic: dict[str, Any]) -> bool:
    title = _compact(topic.get("title") or "")
    return any(pattern.search(title) for pattern in _REPORT_ARTIFACT_PATTERNS)


def _fallback_target(topic: dict[str, Any]) -> tuple[str, str]:
    raw_title = re.sub(r"\s+", " ", str(topic.get("title") or "주제")).strip()
    target = raw_title.split(":", 1)[0].strip()
    target = _DETAIL_MARKERS.sub("", target).strip(" -·,.:()[]") or raw_title
    if len(target) > 36:
        target = target[:36].rstrip() + "…"
    digest = hashlib.sha1(_compact(target).encode("utf-8")).hexdigest()[:12]
    return f"title-{digest}", target


def _specific_tokens(*values: object) -> set[str]:
    return {
        token for token in semantic_tokens(*values) - _DYNAMIC_GENERIC_TOKENS
        if not re.fullmatch(r"(?:19|20)\d{2}년?", token)
        and not any(token.endswith(suffix) for suffix in _DYNAMIC_GENERIC_SUFFIXES)
    }


def _fallback_record(index: int, topic: dict[str, Any]) -> dict[str, Any]:
    fallback_key, fallback_title = _fallback_target(topic)
    return {
        "index": index,
        "topic": topic,
        "fallback_key": fallback_key,
        "fallback_title": fallback_title,
        "title_tokens": _specific_tokens(topic.get("title")),
        "context_tokens": _specific_tokens(
            topic.get("title"), topic.get("summary"),
        ),
    }


def _dynamic_similarity(left: dict[str, Any], right: dict[str, Any]) -> float:
    """Return a conservative similarity for topics absent from the ontology.

    This is deliberately stricter than report-wide semantic search. A wrong
    parent hides a policy issue, while an unmatched singleton remains visible
    and is surfaced by the grouping quality audit.
    """
    if left["fallback_key"] == right["fallback_key"]:
        return 1.0
    left_title = left["title_tokens"]
    right_title = right["title_tokens"]
    shared_title = left_title & right_title
    title_coverage = len(shared_title) / max(1, min(len(left_title), len(right_title)))
    distinctive_title = {token for token in shared_title if len(token) >= 3}
    if len(distinctive_title) >= 2:
        return 0.92
    if distinctive_title and title_coverage >= 0.5:
        return 0.86
    if any(len(token) >= 3 for token in distinctive_title):
        return 0.82
    return 0.0


def _dynamic_clusters(records: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    clusters: list[list[dict[str, Any]]] = []
    for record in records:
        candidates: list[tuple[float, list[dict[str, Any]]]] = []
        for cluster in clusters:
            scores = [_dynamic_similarity(record, member) for member in cluster]
            minimum_score = min(scores, default=0.0)
            if minimum_score >= _DYNAMIC_GROUP_THRESHOLD:
                candidates.append((minimum_score, cluster))
        if not candidates:
            clusters.append([record])
            continue
        _, best = max(candidates, key=lambda candidate: candidate[0])
        best.append(record)
    return clusters


def _dynamic_target(records: list[dict[str, Any]]) -> tuple[str, str, str]:
    fallback_keys = {record["fallback_key"] for record in records}
    if len(fallback_keys) == 1:
        first = records[0]
        return first["fallback_key"], first["fallback_title"], "TITLE_FALLBACK"

    common_title = set.intersection(*(record["title_tokens"] for record in records))
    common_title = {token for token in common_title if len(token) >= 3}
    if common_title:
        title = "·".join(sorted(common_title, key=lambda token: (-len(token), token))[:2])
    else:
        common_context = set.intersection(
            *(record["context_tokens"] for record in records)
        )
        common_context = {token for token in common_context if len(token) >= 3}
        if common_context:
            anchors = sorted(common_context, key=lambda token: (-len(token), token))[:2]
            title = f"{'·'.join(anchors)} 관련 현안"
        else:
            title = min(
                (record["fallback_title"] for record in records),
                key=lambda value: (len(value), value),
            )
    digest_source = "|".join(sorted(fallback_keys))
    digest = hashlib.sha1(digest_source.encode("utf-8")).hexdigest()[:12]
    return f"dynamic-{digest}", title, "DYNAMIC_SEMANTIC"


def _unique_values(items: list[dict[str, Any]], field: str) -> list[str]:
    seen: set[str] = set()
    values: list[str] = []
    for item in items:
        for raw in item.get(field) or []:
            value = str(raw)
            if value and value not in seen:
                seen.add(value)
                values.append(value)
    return values


def build_meeting_topic_groups(brief: dict[str, Any]) -> list[dict[str, Any]]:
    topics = [
        topic for topic in brief.get("topics") or []
        if isinstance(topic, dict) and topic.get("id")
    ]
    grouped: dict[str, dict[str, Any]] = {}
    fallback_records: list[dict[str, Any]] = []
    for index, topic in enumerate(topics):
        if _is_report_artifact(topic):
            group = grouped.setdefault(
                "report-artifacts",
                {
                    "key": "report-artifacts",
                    "title": "보고서 초안·대화 구조",
                    "topics": [],
                    "classification_evidence": [],
                    "assignment_method": "REPORT_ARTIFACT",
                    "first_index": index,
                },
            )
            group["topics"].append(topic)
            continue
        match = _ontology_match(topic)
        if match is None:
            fallback_records.append(_fallback_record(index, topic))
            continue
        key, title = match["key"], match["title"]
        group = grouped.setdefault(
            key,
            {
                "key": key,
                "title": title,
                "topics": [],
                "classification_evidence": [],
                "assignment_method": "ONTOLOGY",
                "first_index": index,
            },
        )
        group["topics"].append(topic)
        group["classification_evidence"].append({
            "topic_id": str(topic["id"]),
            "keyword": match["matched_keyword"],
            "field": match["matched_field"],
            "score": match["score"],
        })

    for records in _dynamic_clusters(fallback_records):
        key, title, method = _dynamic_target(records)
        grouped[key] = {
            "key": key,
            "title": title,
            "topics": [record["topic"] for record in records],
            "classification_evidence": [],
            "assignment_method": method,
            "first_index": min(record["index"] for record in records),
        }

    task_by_topic: dict[str, list[dict[str, Any]]] = {}
    for task in brief.get("tasks") or []:
        if not isinstance(task, dict):
            continue
        topic_id = str(task.get("topic_id") or "")
        if topic_id:
            task_by_topic.setdefault(topic_id, []).append(task)

    result: list[dict[str, Any]] = []
    for group in sorted(grouped.values(), key=lambda value: value["first_index"]):
        child_topics = group.pop("topics")
        group.pop("first_index", None)
        child_titles = [str(topic.get("title") or "주제") for topic in child_topics]
        summary = " · ".join(child_titles[:3])
        if len(child_titles) > 3:
            summary += f" 외 {len(child_titles) - 3}건"
        topic_ids = [str(topic["id"]) for topic in child_topics]
        tasks = [task for topic_id in topic_ids for task in task_by_topic.get(topic_id, [])]
        result.append(
            {
                "id": f"topic-group-{group['key']}",
                "key": group["key"],
                "title": group["title"],
                "assignment_method": group["assignment_method"],
                "classification_evidence": group.pop("classification_evidence", []),
                "summary": summary,
                "topic_ids": topic_ids,
                "topic_count": len(topic_ids),
                "task_ids": [str(task["id"]) for task in tasks if task.get("id")],
                "evidence_ids": _unique_values(child_topics, "evidence_ids"),
                "live_topic_cluster_ids": _unique_values(
                    child_topics, "live_topic_cluster_ids"
                ),
            }
        )
    return result


def attach_meeting_topic_groups(brief: dict[str, Any]) -> dict[str, Any]:
    source = _repair_brief_language(brief)
    groups = build_meeting_topic_groups(source)
    source["topic_groups"] = groups
    topics = [
        topic for topic in source.get("topics") or []
        if isinstance(topic, dict) and topic.get("id")
    ]
    detailed_topic_count = len(topics)
    ontology_topic_count = sum(
        group["topic_count"] for group in groups
        if group.get("assignment_method") == "ONTOLOGY"
    )
    dynamic_topic_count = sum(
        group["topic_count"] for group in groups
        if group.get("assignment_method") == "DYNAMIC_SEMANTIC"
    )
    report_artifact_topic_count = sum(
        group["topic_count"] for group in groups
        if group.get("assignment_method") == "REPORT_ARTIFACT"
    )
    policy_topic_count = detailed_topic_count - report_artifact_topic_count
    unclassified_topic_count = policy_topic_count - ontology_topic_count
    singleton_unclassified_group_count = sum(
        1 for group in groups
        if group.get("assignment_method") in {"DYNAMIC_SEMANTIC", "TITLE_FALLBACK"}
        and group.get("topic_count") == 1
    )
    review_threshold = max(3, ceil(policy_topic_count * 0.2))
    review_reasons: list[str] = []
    if unclassified_topic_count > review_threshold:
        review_reasons.append("ONTOLOGY_COVERAGE_LOW")
    if singleton_unclassified_group_count > max(2, ceil(policy_topic_count * 0.15)):
        review_reasons.append("UNCLASSIFIED_SINGLETONS_HIGH")
    if any(
        _is_report_artifact(topic)
        and not topic.get("official_evidence_ids")
        for topic in topics
    ):
        review_reasons.append("REPORT_ARTIFACT_SOURCE_UNVERIFIED")
    source_topic_ids = [str(topic["id"]) for topic in topics]
    source_topic_id_set = set(source_topic_ids)
    assigned_topic_ids = [
        str(topic_id)
        for group in groups
        for topic_id in group.get("topic_ids") or []
    ]
    duplicate_topic_ids = sorted({
        topic_id for topic_id in assigned_topic_ids
        if assigned_topic_ids.count(topic_id) > 1
    })
    missing_topic_ids = sorted(source_topic_id_set - set(assigned_topic_ids))
    unknown_topic_ids = sorted(set(assigned_topic_ids) - source_topic_id_set)
    source_live_topic_ids = {
        str(cluster_id)
        for topic in topics
        for cluster_id in topic.get("live_topic_cluster_ids") or []
    }
    grouped_live_topic_ids = {
        str(cluster_id)
        for group in groups
        for cluster_id in group.get("live_topic_cluster_ids") or []
    }
    missing_live_topic_ids = sorted(
        source_live_topic_ids - grouped_live_topic_ids
    )
    unlinked_task_ids = sorted(
        str(task.get("id") or "")
        for task in source.get("tasks") or []
        if isinstance(task, dict)
        and (
            not task.get("topic_id")
            or str(task.get("topic_id")) not in source_topic_id_set
        )
    )
    if missing_topic_ids:
        review_reasons.append("GROUPING_TOPIC_LOSS")
    if duplicate_topic_ids:
        review_reasons.append("GROUPING_TOPIC_DUPLICATE")
    if unknown_topic_ids:
        review_reasons.append("GROUPING_UNKNOWN_TOPIC")
    if missing_live_topic_ids:
        review_reasons.append("GROUPING_LIVE_TOPIC_LOSS")
    if unlinked_task_ids:
        review_reasons.append("GROUPING_UNLINKED_TASKS")
    integrity_status = (
        "PASS"
        if not any(
            (
                missing_topic_ids,
                duplicate_topic_ids,
                unknown_topic_ids,
                missing_live_topic_ids,
                unlinked_task_ids,
            )
        )
        else "REVIEW_REQUIRED"
    )
    source["topic_grouping"] = {
        "version": GROUPING_VERSION,
        "method": GROUPING_METHOD,
        "group_count": len(groups),
        "detailed_topic_count": detailed_topic_count,
        "policy_topic_count": policy_topic_count,
        "ontology_topic_count": ontology_topic_count,
        "ontology_coverage": round(
            ontology_topic_count / policy_topic_count, 4
        ) if policy_topic_count else 1.0,
        "dynamic_topic_count": dynamic_topic_count,
        "unclassified_topic_count": unclassified_topic_count,
        "report_artifact_topic_count": report_artifact_topic_count,
        "singleton_unclassified_group_count": singleton_unclassified_group_count,
        "integrity_status": integrity_status,
        "assigned_topic_count": len(assigned_topic_ids),
        "missing_topic_count": len(missing_topic_ids),
        "duplicate_topic_count": len(duplicate_topic_ids),
        "missing_live_topic_count": len(missing_live_topic_ids),
        "unlinked_task_count": len(unlinked_task_ids),
        "quality_status": "REVIEW_REQUIRED" if review_reasons else "PASS",
        "review_reasons": review_reasons,
    }
    return source


def build_meeting_topic_ontology(
    briefs: list[dict[str, Any]] | tuple[dict[str, Any], ...] = (),
) -> dict[str, Any]:
    """Expose the matching ontology and its current report usage for inspection."""
    ontology = {
        key: {"key": key, "title": title, "keywords": list(keywords)}
        for key, title, keywords in TARGET_ONTOLOGY
    }
    domain_keys = [key for _, _, _, keys in ONTOLOGY_DOMAINS for key in keys]
    if len(domain_keys) != len(set(domain_keys)) or set(domain_keys) != set(ontology):
        raise RuntimeError("ontology domain map must cover every target exactly once")

    usage = {
        key: {"topic_count": 0, "report_count": 0, "keyword_usage": {}}
        for key in ontology
    }
    totals = {
        "report_count": 0,
        "topic_count": 0,
        "policy_topic_count": 0,
        "ontology_topic_count": 0,
        "dynamic_topic_count": 0,
        "unclassified_topic_count": 0,
        "report_artifact_topic_count": 0,
        "integrity_failure_count": 0,
        "quality_review_count": 0,
    }
    for brief in briefs:
        if not isinstance(brief, dict):
            continue
        grouped = attach_meeting_topic_groups(brief)
        audit = grouped.get("topic_grouping") or {}
        totals["report_count"] += 1
        totals["topic_count"] += int(audit.get("detailed_topic_count") or 0)
        totals["policy_topic_count"] += int(audit.get("policy_topic_count") or 0)
        totals["ontology_topic_count"] += int(audit.get("ontology_topic_count") or 0)
        totals["dynamic_topic_count"] += int(audit.get("dynamic_topic_count") or 0)
        totals["unclassified_topic_count"] += int(audit.get("unclassified_topic_count") or 0)
        totals["report_artifact_topic_count"] += int(
            audit.get("report_artifact_topic_count") or 0
        )
        if audit.get("integrity_status") != "PASS":
            totals["integrity_failure_count"] += 1
        if audit.get("quality_status") != "PASS":
            totals["quality_review_count"] += 1
        for group in grouped.get("topic_groups") or []:
            key = str(group.get("key") or "")
            if key not in usage:
                continue
            usage[key]["topic_count"] += int(group.get("topic_count") or 0)
            usage[key]["report_count"] += 1
            for evidence in group.get("classification_evidence") or []:
                keyword = str(evidence.get("keyword") or "")
                if keyword:
                    keyword_usage = usage[key]["keyword_usage"]
                    keyword_usage[keyword] = int(keyword_usage.get(keyword) or 0) + 1

    topic_total = totals["policy_topic_count"]
    totals["ontology_coverage"] = round(
        totals["ontology_topic_count"] / topic_total, 4
    ) if topic_total else 1.0
    groups = []
    domains = []
    for domain_key, title, color, keys in ONTOLOGY_DOMAINS:
        domain_topic_count = sum(usage[key]["topic_count"] for key in keys)
        domains.append({
            "key": domain_key,
            "title": title,
            "color": color,
            "group_keys": list(keys),
            "topic_count": domain_topic_count,
        })
        for key in keys:
            keyword_usage = usage[key].pop("keyword_usage")
            groups.append({
                **ontology[key],
                "domain_key": domain_key,
                "keyword_count": len(ontology[key]["keywords"]),
                "matched_keywords": [
                    {"keyword": keyword, "topic_count": count}
                    for keyword, count in sorted(
                        keyword_usage.items(), key=lambda item: (-item[1], item[0])
                    )
                ],
                **usage[key],
            })
    return {
        "version": GROUPING_VERSION,
        "method": GROUPING_METHOD,
        "root": {"key": "national-policy", "title": "국정 온톨로지"},
        "domains": domains,
        "groups": groups,
        "metrics": totals,
    }
