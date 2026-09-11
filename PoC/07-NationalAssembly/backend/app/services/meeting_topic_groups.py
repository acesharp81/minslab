from __future__ import annotations

import hashlib
import re
from copy import deepcopy
from typing import Any


GROUPING_VERSION = "assembly-meeting-topic-grouping/1.0"
GROUPING_METHOD = "TARGET_ONTOLOGY_WITH_TITLE_FALLBACK"


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
        ),
    ),
    (
        "prosecution-judiciary",
        "검찰·사법제도",
        (
            "검찰개혁", "검찰청", "공소청", "기소권", "대법관",
            "대법원장", "대법원", "사법개혁", "재판독립", "법원",
            "형소법", "보완수사", "주임검사", "소송지휘권", "직접수사",
            "특검조사", "대법원행정처",
        ),
    ),
    (
        "public-discipline",
        "공직기강·감찰",
        (
            "공직기강", "공직자감찰", "감찰제도", "감찰권", "내부감찰",
            "수사자료유출", "수사문건유출", "공무상비밀", "총리실과장",
            "감찰", "공직자범위", "기획총균과정",
        ),
    ),
    (
        "public-appointments",
        "공직 인사·검증",
        (
            "인사검증", "인사청문", "공직후보", "장관후보", "후보자검증",
            "내각인사", "공정한인사", "공직인사", "인사권",
            "후보자", "국무위원임명", "대통령임명", "내각인사",
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
        ),
    ),
    (
        "industry-semiconductors",
        "산업·반도체 정책",
        (
            "반도체클러스터", "반도체산업", "첨단산업", "산업클러스터",
            "산업정책", "공급망",
        ),
    ),
    (
        "housing-real-estate",
        "주택·부동산 정책",
        ("부동산", "주택공급", "아파트", "전세", "주거안정", "부동산세"),
    ),
    (
        "finance-investment",
        "금융·투자자 보호",
        (
            "주가조작", "불공정거래", "금융투자", "투자자보호", "ETF",
            "KH필룩스", "배상윤", "금융시장", "자본시장",
        ),
    ),
    (
        "livelihood-economy",
        "민생·경제 안정",
        (
            "민생경제", "민생안정", "생활안정", "시장경제", "경제양극화",
            "소득양극화", "고용안정", "물가안정", "소상공인", "자영업자",
        ),
    ),
    (
        "budget-public-finance",
        "예산·재정 운용",
        (
            "예산", "재정규모", "재정운용", "기금재원", "미래대응기금",
            "통치자금", "세입처리", "국고자금", "회계연도", "이월사업",
            "예산전용", "지급불능", "미지급", "교부세", "통합지원금",
        ),
    ),
    (
        "welfare-care-family",
        "복지·돌봄·가족 지원",
        (
            "사회복지", "복지시설", "한부모", "양육비", "다문화가정",
            "아이돌봄", "자녀돌봄", "어린이집", "돌봄지원", "공적돌봄",
            "국가복지", "성평등정책", "결혼페널티",
        ),
    ),
    (
        "youth-employment",
        "청년·고용·노동",
        (
            "청년고용", "청년층", "고용률", "고용제도", "외국인노동자",
            "외국인근로자", "근무처변경", "근로자", "임금차별", "노동정책",
        ),
    ),
    (
        "public-safety-health",
        "국민안전·보건 대응",
        (
            "교제폭력", "관계성폭력", "마약범죄", "재활체계", "구급대",
            "어린이보호구역", "속도제한", "국민생명", "재난안전",
            "강풍피해", "홍수실종", "보건의료", "감염병",
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
        ),
    ),
    (
        "transport-infrastructure",
        "교통·공항·지역 인프라",
        (
            "고속도로", "도로연결", "휴게소", "군용비행장", "신공항건설",
            "공항사업", "서해평화도로", "접경지역종합계획", "도로공사",
            "기부대양여", "소음피해보상",
        ),
    ),
    (
        "veterans-history",
        "보훈·독립유공자 예우",
        (
            "국가보훈", "보훈병원", "보훈수당", "보훈의료", "보훈예우",
            "독립유공자", "625전쟁희생자", "안중근", "유해관리",
            "명예수당", "공적재평가",
        ),
    ),
    (
        "education",
        "교육 정책·교육기관",
        (
            "교육부", "교육감", "수능", "채점신뢰성", "서울대학교",
            "국립대", "교육정책", "학술림", "학교교육",
        ),
    ),
    (
        "culture-tourism",
        "문화예술·관광 정책",
        (
            "영화발전기금", "영화지원", "예술인", "관광인구", "관광정책",
            "체류형관광", "문화예술", "문체부",
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
            "공공재산",
        ),
    ),
    (
        "ai-digital-infrastructure",
        "AI·디지털 인프라",
        (
            "인공지능", "AI정책", "AI산업", "데이터센터", "디지털전환",
            "알고리즘규제", "온라인플랫폼", "AI기반", "AI인력",
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
            "전역전환", "합동성",
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
            "민주당폄훼", "폭로성발언", "정책동의여부",
        ),
    ),
)


_DETAIL_MARKERS = re.compile(
    r"\s*(?:관련|에\s*대한|대응|강화|필요성?|촉구|제안|검토|문제점?|논란|"
    r"개선|방안|대책|평가|지적|요구|질의|우려|과제|입장|책임|점검|확인).*$"
)
_NON_WORD = re.compile(r"[^0-9A-Za-z가-힣]+")


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
    for topic in topics:
        key, title = _ontology_target(topic) or _fallback_target(topic)
        group = grouped.setdefault(key, {"key": key, "title": title, "topics": []})
        group["topics"].append(topic)

    task_by_topic: dict[str, list[dict[str, Any]]] = {}
    for task in brief.get("tasks") or []:
        if not isinstance(task, dict):
            continue
        topic_id = str(task.get("topic_id") or "")
        if topic_id:
            task_by_topic.setdefault(topic_id, []).append(task)

    result: list[dict[str, Any]] = []
    for group in grouped.values():
        child_topics = group.pop("topics")
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
    source = deepcopy(brief)
    groups = build_meeting_topic_groups(source)
    source["topic_groups"] = groups
    source["topic_grouping"] = {
        "version": GROUPING_VERSION,
        "method": GROUPING_METHOD,
        "group_count": len(groups),
        "detailed_topic_count": len(source.get("topics") or []),
    }
    return source
