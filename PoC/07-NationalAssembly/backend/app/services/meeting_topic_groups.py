from __future__ import annotations

import hashlib
import re
from copy import deepcopy
from math import ceil
from typing import Any

from .official_brief_integration import semantic_tokens


GROUPING_VERSION = "assembly-meeting-topic-grouping/1.3"
GROUPING_METHOD = "TARGET_ONTOLOGY_WITH_CONSERVATIVE_DYNAMIC_TARGETS_AND_AUDIT"


# A parent represents the policy target. Stance, request, criticism, and proposed
# action remain separate child topics so their evidence trails are not collapsed.
TARGET_ONTOLOGY: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    (
        "constitutional-order",
        "헌법·민주주의 제도",
        (
            "개헌", "헌법개정", "헌정질서", "권력분립", "삼권분립",
            "518민주화", "부마항쟁", "민주화운동",
        ),
    ),
    (
        "police-investigation",
        "경찰·수사제도",
        (
            "경찰개혁", "경찰청", "경찰수사", "수사인력", "수사관행",
            "중대범죄수사청", "중수청",
            "특별사법경찰", "특사경",
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
            "형사사법체계", "공소청출범", "검찰청건물",
            "공수처", "고위공직자범죄수사처", "공소장", "기소유예",
            "형사소송법", "통신영장", "재판배당", "피해자권리",
            "군형사소송법", "보안수사권", "보완수사권",
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
        ),
    ),
    (
        "public-appointments",
        "공직 인사·검증",
        (
            "인사검증", "인사청문", "공직후보", "장관후보", "후보자검증",
            "내각인사", "공정한인사", "공직인사", "인사권",
            "후보자", "국무위원임명", "대통령임명", "내각인사",
            "김현지실장", "실장해임",
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
            "공직선거법", "위탁선거",
            "선거무효", "당선무효", "선거소청", "중앙선관위",
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
        ),
    ),
    (
        "water-resources-climate",
        "수자원·가뭄 대응",
        (
            "용수공급", "물공급", "물관리", "가뭄", "생활용수",
            "공업용수", "농업용수", "냉각수", "재이용수", "댐수",
            "동복댐", "물사용우선순위",
        ),
    ),
    (
        "environment-waste",
        "환경·폐기물 관리",
        (
            "쓰레기직매립", "폐기물반입", "민간위탁폐기물", "매립지",
            "환경오염", "환경변화", "훼손지역", "훼손부지", "주민보상",
            "환경간접세", "자원순환",
        ),
    ),
    (
        "enterprise-innovation",
        "기업·중소기업 혁신",
        (
            "중소기업R&D", "중소기업연구개발", "기업투자전략",
            "기업지원", "연구개발삭감", "R&D삭감",
            "기업과국가의투자전략",
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
        ),
    ),
    (
        "finance-investment",
        "금융·투자자 보호",
        (
            "주가조작", "불공정거래", "금융투자", "투자자보호", "ETF",
            "KH필룩스", "배상윤", "금융시장", "자본시장", "통화정책",
            "금융정책", "금융규제", "공적자금", "IMF사태", "홈플러스",
            "전단채", "전단체사기",
            "청년도약계좌", "ISA", "자금세탁방지", "국민성장펀드",
            "위험자산투자", "코스피", "카지노사업자",
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
        "taxation",
        "조세·세제 정책",
        (
            "세제혜택", "세법", "부가가치세", "환경간접세", "조세감면",
            "세부담", "과세기준", "비과세", "세액공제", "소득공제",
            "공정시장가액비율", "조세정책",
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
            "성수품", "가격안정", "민생대개혁",
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
            "공공기금", "기금통합", "의무지출",
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
            "체불임금", "채불임금", "공무원노조", "전교조", "법외노조",
        ),
    ),
    (
        "public-safety-health",
        "국민안전·보건 대응",
        (
            "교제폭력", "관계성폭력", "마약범죄", "재활체계", "구급대",
            "어린이보호구역", "속도제한", "국민생명", "재난안전",
            "강풍피해", "홍수실종", "보건의료", "감염병", "폭우피해",
            "칼858", "KAL858", "항공기사고", "유족감시단",
            "세월호", "이태원참사", "실종사건", "물류창고화재",
            "배터리화재", "리튬배터리", "소방구급차", "재난기본법",
            "대홍수", "인명수색",
        ),
    ),
    (
        "healthcare-medical-system",
        "보건의료·공공의료",
        (
            "공공병원", "의료인프라", "의료취약", "상급종합병원",
            "지역의료", "지방의료", "국립의전원", "국립중앙의료원",
            "의료중심도시", "의료공공기관", "미프진", "의약품접근",
            "여성건강", "태아생명", "약물도입",
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
            "학교폭력", "디지털과의존",
        ),
    ),
    (
        "agriculture-rural",
        "농업·농촌 정책",
        (
            "농촌", "농민", "농지", "임차농", "고령농", "영농권",
            "스마트팜", "비닐하우스", "농생명용지", "농업정책",
            "논콩", "농축산물보호", "농어촌상생기금",
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
        ),
    ),
    (
        "veterans-history",
        "보훈·독립유공자 예우",
        (
            "국가보훈", "보훈병원", "보훈수당", "보훈의료", "보훈예우",
            "독립유공자", "625전쟁희생자", "안중근", "유해관리",
            "명예수당", "공적재평가", "참전유공", "참전수당",
            "유공자배우자", "미망인배우자",
        ),
    ),
    (
        "education",
        "교육 정책·교육기관",
        (
            "교육부", "교육감", "수능", "채점신뢰성", "서울대학교",
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
        ),
    ),
    (
        "public-assets",
        "국유재산·공공시설 관리",
        (
            "국유재산", "국유지", "공공시설", "무상임대", "무상양여",
            "공공재산", "공유재산", "물품관리법",
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
            "인도적지원",
        ),
    ),
    (
        "presidential-accountability",
        "대통령 권한·책임",
        (
            "대통령책임", "대통령권한", "대통령사법", "대통령의혹",
            "대통령자격", "대통령국정운영", "대통령법위반", "대통령탄핵",
            "대통령의사법", "대통령의법", "대통령장남", "군골프장",
            "대통령의국정", "청와대정책실",
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
        ),
    ),
    (
        "national-security-strategy",
        "국가안보 전략",
        (
            "안보정책", "안보개념", "동북아시아안보", "국가안보",
            "국방전략", "정부준비태세",
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
    "기관", "공공기관",
}
_DYNAMIC_GROUP_THRESHOLD = 0.76


_REPORT_LANGUAGE_REPAIRS: tuple[tuple[str, str], ...] = (
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


def _ontology_target(topic: dict[str, Any]) -> tuple[str, str] | None:
    title_haystack = _compact(topic.get("title") or "")
    summary_haystack = _compact(topic.get("summary") or "")
    best: tuple[int, int, str, str] | None = None
    for order, (key, title, keywords) in enumerate(TARGET_ONTOLOGY):
        normalized = [_compact(keyword) for keyword in keywords]
        title_matches = [
            keyword for keyword in normalized
            if keyword and keyword in title_haystack
        ]
        summary_matches = [
            keyword for keyword in normalized
            if keyword and keyword in summary_haystack
        ]
        matches = title_matches or summary_matches
        if not matches:
            continue
        score = (
            (1000 if title_matches else 0)
            + max(len(keyword) for keyword in matches) * 10
            + len(matches)
        )
        candidate = (score, -order, key, title)
        if best is None or candidate > best:
            best = candidate
    return (best[2], best[3]) if best else None


def _fallback_target(topic: dict[str, Any]) -> tuple[str, str]:
    raw_title = re.sub(r"\s+", " ", str(topic.get("title") or "주제")).strip()
    target = raw_title.split(":", 1)[0].strip()
    target = _DETAIL_MARKERS.sub("", target).strip(" -·,.:()[]") or raw_title
    if len(target) > 36:
        target = target[:36].rstrip() + "…"
    digest = hashlib.sha1(_compact(target).encode("utf-8")).hexdigest()[:12]
    return f"title-{digest}", target


def _specific_tokens(*values: object) -> set[str]:
    return semantic_tokens(*values) - _DYNAMIC_GENERIC_TOKENS


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
        target = _ontology_target(topic)
        if target is None:
            fallback_records.append(_fallback_record(index, topic))
            continue
        key, title = target
        group = grouped.setdefault(
            key,
            {
                "key": key,
                "title": title,
                "topics": [],
                "assignment_method": "ONTOLOGY",
                "first_index": index,
            },
        )
        group["topics"].append(topic)

    for records in _dynamic_clusters(fallback_records):
        key, title, method = _dynamic_target(records)
        grouped[key] = {
            "key": key,
            "title": title,
            "topics": [record["topic"] for record in records],
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
    detailed_topic_count = len(source.get("topics") or [])
    ontology_topic_count = sum(
        group["topic_count"] for group in groups
        if group.get("assignment_method") == "ONTOLOGY"
    )
    dynamic_topic_count = sum(
        group["topic_count"] for group in groups
        if group.get("assignment_method") == "DYNAMIC_SEMANTIC"
    )
    unclassified_topic_count = detailed_topic_count - ontology_topic_count
    singleton_unclassified_group_count = sum(
        1 for group in groups
        if group.get("assignment_method") != "ONTOLOGY"
        and group.get("topic_count") == 1
    )
    review_threshold = max(3, ceil(detailed_topic_count * 0.2))
    review_reasons: list[str] = []
    if unclassified_topic_count > review_threshold:
        review_reasons.append("ONTOLOGY_COVERAGE_LOW")
    if singleton_unclassified_group_count > max(2, ceil(detailed_topic_count * 0.15)):
        review_reasons.append("UNCLASSIFIED_SINGLETONS_HIGH")
    source["topic_grouping"] = {
        "version": GROUPING_VERSION,
        "method": GROUPING_METHOD,
        "group_count": len(groups),
        "detailed_topic_count": detailed_topic_count,
        "ontology_topic_count": ontology_topic_count,
        "ontology_coverage": round(
            ontology_topic_count / detailed_topic_count, 4
        ) if detailed_topic_count else 1.0,
        "dynamic_topic_count": dynamic_topic_count,
        "unclassified_topic_count": unclassified_topic_count,
        "singleton_unclassified_group_count": singleton_unclassified_group_count,
        "quality_status": "REVIEW_REQUIRED" if review_reasons else "PASS",
        "review_reasons": review_reasons,
    }
    return source
