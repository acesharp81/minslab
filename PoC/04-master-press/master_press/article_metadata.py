from __future__ import annotations

import re
import urllib.parse


PUBLISHER_NAMES = {
    "yna.co.kr": "연합뉴스", "newsis.com": "뉴시스", "news1.kr": "뉴스1",
    "ytn.co.kr": "YTN", "edaily.co.kr": "이데일리", "fnnews.com": "파이낸셜뉴스",
    "newspim.com": "뉴스핌", "news.kbs.co.kr": "KBS", "kbs.co.kr": "KBS",
    "mt.co.kr": "머니투데이", "segye.com": "세계일보", "nocutnews.co.kr": "노컷뉴스",
    "khan.co.kr": "경향신문", "imnews.imbc.com": "MBC", "imbc.com": "MBC",
    "yonhapnewstv.co.kr": "연합뉴스TV", "seoul.co.kr": "서울신문",
    "news.sbs.co.kr": "SBS", "sbs.co.kr": "SBS", "sedaily.com": "서울경제",
    "gukjenews.com": "국제뉴스", "donga.com": "동아일보", "chosun.com": "조선일보",
    "joongang.co.kr": "중앙일보", "hani.co.kr": "한겨레", "hankookilbo.com": "한국일보",
    "mk.co.kr": "매일경제", "hankyung.com": "한국경제", "etnews.com": "전자신문",
    "zdnet.co.kr": "지디넷코리아", "ohmynews.com": "오마이뉴스",
}
REPORTER_EXCLUSIONS = {
    "연합뉴스", "뉴시스", "뉴스원", "뉴스1", "취재", "편집국", "사회부", "정치부",
    "경제부", "문화부", "산업부", "사진", "영상", "온라인", "시민", "객원", "전문",
}


def publisher_name(raw_publisher: str = "", source_url: str = "", llm_value: str = "") -> str:
    """Return a readable publisher while retaining unknown RSS publisher names."""
    raw = str(raw_publisher or "").strip()
    host = urllib.parse.urlsplit(str(source_url or "")).netloc.casefold().split(":")[0]
    candidates = [raw.casefold(), host]
    for candidate in candidates:
        candidate = candidate.removeprefix("www.")
        for domain, name in PUBLISHER_NAMES.items():
            if candidate == domain or candidate.endswith("." + domain):
                return name
    llm_name = str(llm_value or "").strip()[:80]
    if llm_name and "." not in llm_name:
        return llm_name
    return raw[:80]


def reporter_name(text: str, llm_value: object = "") -> str:
    """Validate model-proposed bylines against source text, then use deterministic patterns."""
    source = str(text or "")
    proposed = llm_value if isinstance(llm_value, list) else re.split(r"[,·/]", str(llm_value or ""))
    names: list[str] = []
    for value in proposed:
        name = re.sub(r"\s*기자\s*$", "", str(value or "").strip())
        if re.fullmatch(r"[가-힣]{2,4}", name) and name in source and name not in REPORTER_EXCLUSIONS and not name.endswith("전문"):
            names.append(name)
    patterns = (
        r"(?:^|[\s(=·,])([가-힣]{2,4})\s*기자\b",
        r"기자\s*[:：]\s*([가-힣]{2,4})\b",
    )
    for pattern in patterns:
        for name in re.findall(pattern, source, re.M):
            if name not in REPORTER_EXCLUSIONS and not name.endswith("전문"):
                names.append(name)
    return " · ".join(dict.fromkeys(names))[:120]
