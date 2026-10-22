from __future__ import annotations

import re
import unicodedata


# Official names/short names are documented in docs/MINISTRY_SEARCH_ALIASES.md.
# Historical organizations remain separate: a reorganization is not an abbreviation.
MINISTRY_NAME_VARIANTS: dict[str, tuple[str, ...]] = {
    "재정경제부": ("재경부",),
    "기획예산처": ("기획처", "예산처"),
    "과학기술정보통신부": ("과기정통부", "과기통신부"),
    "교육부": (),
    "외교부": (),
    "통일부": (),
    "법무부": (),
    "국방부": (),
    "행정안전부": ("행안부", "행정안정부"),
    "국가보훈부": ("보훈부",),
    "문화체육관광부": ("문체부",),
    "농림축산식품부": ("농식품부",),
    "산업통상부": ("산업부",),
    "보건복지부": ("복지부",),
    "기후에너지환경부": ("기후부",),
    "고용노동부": ("노동부", "고용부"),
    "성평등가족부": ("성평등부",),
    "국토교통부": ("국토부",),
    "해양수산부": ("해수부",),
    "중소벤처기업부": ("중기부",),
    "국무조정실": ("국조실",),
    "국무총리비서실": ("총리비서실",),
    "대통령비서실": (),
    "대통령경호처": ("경호처",),
    "인사혁신처": ("인사처",),
    "법제처": (),
    "식품의약품안전처": ("식약처",),
    "국가데이터처": ("데이터처",),
    "지식재산처": ("지재처",),
    "방송미디어통신위원회": ("방미통위",),
    "공정거래위원회": ("공정위",),
    "금융위원회": ("금융위",),
    "국민권익위원회": ("국민권익위", "권익위"),
    "원자력안전위원회": ("원안위",),
    "개인정보보호위원회": ("개인정보위",),
    "국가교육위원회": ("국교위",),
    "국가인권위원회": ("인권위",),
    "고위공직자범죄수사처": ("공수처",),
    "국세청": (),
    "관세청": (),
    "조달청": (),
    "우주항공청": ("우주청",),
    "재외동포청": ("동포청",),
    "대검찰청": ("대검",),
    "병무청": (),
    "방위사업청": ("방사청",),
    "경찰청": (),
    "소방청": (),
    "국가유산청": ("유산청",),
    "농촌진흥청": ("농진청",),
    "산림청": (),
    "질병관리청": ("질병청",),
    "기상청": (),
    "행정중심복합도시건설청": ("행복청",),
    "새만금개발청": ("새만금청",),
    "해양경찰청": ("해경청", "해경"),
    "국가정보원": ("국정원",),
    "금융감독원": ("금감원",),
    # Past names are searchable in historical source material in their own right.
    "기획재정부": ("기재부",),
    "산업통상자원부": ("산자부",),
    "여성가족부": ("여가부",),
    "환경부": (),
    "방송통신위원회": ("방통위",),
    "국가보훈처": ("보훈처",),
    "식품의약품안전청": ("식약청",),
    "문화재청": (),
    "통계청": (),
    "특허청": (),
}

MINISTRY_ALIASES = {
    alias: canonical
    for canonical, aliases in MINISTRY_NAME_VARIANTS.items()
    for alias in aliases
}


def _name_key(value: str) -> str:
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", value)).casefold()


_NAME_LOOKUP = {
    _name_key(name): canonical
    for canonical, aliases in MINISTRY_NAME_VARIANTS.items()
    for name in (canonical, *aliases)
}
# Longest first prevents a shorter agency name consuming the start of a full name.
_MENTION_PATTERN = re.compile(
    r"(?<![0-9A-Za-z가-힣])(?:"
    + "|".join(r"\s*".join(map(re.escape, name))
               for name in sorted((*MINISTRY_NAME_VARIANTS, *MINISTRY_ALIASES), key=len, reverse=True))
    + r")(?=$|[^0-9A-Za-z가-힣]|은|는|이|가|을|를|의|에|와|과|로|도|만|께|장관|차관|소관|산하|관계|측|등)",
)


def canonical_ministry_name(value: object) -> str:
    name = " ".join(str(value or "").split())
    return _NAME_LOOKUP.get(_name_key(name), name)


def normalize_ministry_mentions(value: object) -> str:
    """Normalize a comparison copy; preserve the actual stored/displayed source."""
    return _MENTION_PATTERN.sub(
        lambda match: canonical_ministry_name(match.group()), str(value or ""),
    )
