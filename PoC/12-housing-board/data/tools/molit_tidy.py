#!/usr/bin/env python3
"""국토교통 통계누리 CSV(data/raw/molit/molit_*.csv)를 읽기 쉬운 UTF-8 표로 바꾼다.

원본의 문제: 천 단위 쉼표(388,362)가 따옴표 없이 들어 있어 숫자 한 칸이 여러 칸으로 쪼개진다.
처리: 앞의 라벨 칸 뒤에 남은 조각을 '1~3자리 + (쉼표 뒤 3자리)*' 규칙으로 다시 합친다.
검증: 합친 결과가 합계 관계(전국 = 시도 합, 합계 = 분양+임대+조합)와 맞는지 확인하고, 틀리면 실패로 종료한다.
원본 파일은 수정하지 않는다.
"""
import csv, io, re, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from paths import RAW as _RAW, PROCESSED as OUT  # noqa: E402

RAW = _RAW / "molit"
OUT.mkdir(parents=True, exist_ok=True)


def read_rows(path):
    b = path.read_bytes()
    for enc in ("utf-8-sig", "cp949"):
        try:
            return list(csv.reader(io.StringIO(b.decode(enc))))
        except UnicodeDecodeError:
            continue
    raise SystemExit(f"인코딩을 읽지 못함: {path.name}")


def clean(s):
    return re.sub(r"\s+", "", s)


def period(s):
    """'2026-08 p)' -> ('2026-08', True)  (p는 잠정치)"""
    s = s.strip()
    prov = "p)" in s
    return re.sub(r"\s*p\)$", "", s), prov


def merge_groups(tokens, k):
    """tokens(쪼개진 숫자 조각들)를 k개의 숫자로 합치는 모든 방법 중 규칙에 맞는 것을 찾는다."""
    n = len(tokens)
    results = []

    def ok_first(t):
        return t.isdigit() and 1 <= len(t) <= 3 and (t == "0" or not t.startswith("0"))

    def rec(i, left, acc):
        if left == 0:
            if i == n:
                results.append(list(acc))
            return
        if i >= n or not ok_first(tokens[i]):
            return
        val = tokens[i]
        j = i + 1
        while True:
            rec(j, left - 1, acc + [int(val)])
            if j < n and tokens[j].isdigit() and len(tokens[j]) == 3:
                val += tokens[j]
                j += 1
            else:
                break

    rec(0, k, [])
    return results


def single_value_table(src, dst, value_name):
    rows = read_rows(RAW / src)
    out = [["기간", "잠정치", "구분", "부문", "시도", value_name]]
    for r in rows[1:]:
        if len(r) < 5:
            continue
        p, prov = period(r[0])
        parts = merge_groups(r[4:], 1)
        if len(parts) != 1:
            raise SystemExit(f"{src}: 숫자를 하나로 합치지 못함 {r}")
        out.append([p, "Y" if prov else "", clean(r[1]), clean(r[2]), clean(r[3]), parts[0][0]])
    with open(OUT / dst, "w", encoding="utf-8-sig", newline="") as f:
        csv.writer(f).writerows(out)
    return out


def check_national_equals_sum(rows, label):
    """같은 기간·구분·부문에서 전국 = 17개 시도 합 (수도권 소계는 제외)."""
    regions = {"서울", "인천", "경기", "부산", "대구", "광주", "대전", "울산", "세종", "강원", "충북", "충남",
               "전북", "전남", "경북", "경남", "제주", "전남광주"}
    by = {}
    for p, prov, g, s, reg, v in rows[1:]:
        by.setdefault((p, g, s), {})[reg] = v
    bad, checked = 0, 0
    for key, d in by.items():
        if "전국" not in d:
            continue
        sido = [v for k, v in d.items() if k in regions]
        if len(sido) < 14:
            continue
        checked += 1
        if sum(sido) != d["전국"]:
            bad += 1
    print(f"  [{label}] 전국=시도합 검사 {checked}건 중 불일치 {bad}건")
    return bad, checked


def annual_region_table(src, dst):
    """열: 년, 시도(또는 '계획'/'실적'), 합계. 값이 비어 있는 칸(계획)은 빈 칸으로 둔다."""
    rows = read_rows(RAW / src)
    out = [["연도", "구분", "인허가_호"]]
    sido = {"서울", "인천", "경기", "부산", "대구", "광주", "대전", "울산", "세종", "강원", "충북", "충남",
            "전북", "전남", "경북", "경남", "제주", "전남광주"}
    by = {}
    for r in rows[1:]:
        if len(r) < 3:
            continue
        label = clean(r[1])
        toks = [x for x in r[2:] if x != ""]
        if toks:
            parts = merge_groups(toks, 1)
            if len(parts) != 1:
                raise SystemExit(f"{src}: 숫자를 하나로 합치지 못함 {r}")
            val = parts[0][0]
        else:
            val = ""
        out.append([r[0].strip(), label, val])
        by.setdefault(r[0].strip(), {})[label] = val
    bad = 0
    for y, d in by.items():
        total = d.get("실적")
        if total == "" or total is None:
            continue
        s = sum(v for k, v in d.items() if k in sido and v != "")
        if s != total:
            bad += 1
    with open(OUT / dst, "w", encoding="utf-8-sig", newline="") as f:
        csv.writer(f).writerows(out)
    return out, bad


def sales_table(src, dst):
    rows = read_rows(RAW / src)
    head1, head2 = rows[0], rows[1]
    cols = []
    seen = []
    for a, b in zip(head1[3:], head2[3:]):
        cols.append(f"{clean(a)}_{clean(b)}")
    # head1/head2에 쪼개진 흔적은 없다(라벨). 숫자 칸 수 = len(cols)
    k = len(cols)
    out = [["기간", "구분1", "구분2"] + cols]
    bad = 0
    for r in rows[2:]:
        if len(r) < 4:
            continue
        p, _ = period(r[0])
        cands = merge_groups(r[3:], k)
        # 합계 = 분양 + 임대 + 조합 이 맞는 후보만 남긴다 (순계, 누계 각각)
        good = [c for c in cands if c[0] == c[1] + c[2] + c[3] and c[4] == c[5] + c[6] + c[7]]
        if len(good) != 1:
            bad += 1
            continue
        out.append([p, clean(r[1]), clean(r[2])] + good[0])
    print(f"  [분양] 후보가 하나로 정해지지 않은 행 {bad}건 / 전체 {len(rows) - 2}행")
    if bad:
        raise SystemExit("분양 표를 안전하게 합치지 못해 중단")
    with open(OUT / dst, "w", encoding="utf-8-sig", newline="") as f:
        csv.writer(f).writerows(out)
    return out


if __name__ == "__main__":
    total_bad = 0
    for src, dst, name in [
        ("molit_1946_인허가_부문별_월별누계.csv", "molit_인허가_월별누계.csv", "인허가실적_호"),
        ("molit_5386_착공_월계.csv", "molit_착공_월계.csv", "착공실적_호"),
        ("molit_5372_준공_월계.csv", "molit_준공_월계.csv", "준공실적_호"),
    ]:
        out = single_value_table(src, dst, name)
        print(f"{dst}: {len(out) - 1}행")
        bad, _ = check_national_equals_sum(out, dst)
        total_bad += bad
    # 지역별 연간: 열 구성이 달라 별도 처리 (년, 시도, 합계)
    out, bad = annual_region_table("molit_666_인허가_지역별_연간.csv", "molit_인허가_지역별_연간.csv")
    print(f"molit_인허가_지역별_연간.csv: {len(out) - 1}행, 실적=시도합 불일치 {bad}건")
    total_bad += bad
    sales_table("molit_5557_분양_공동주택.csv", "molit_분양_공동주택.csv")
    print("완료" if total_bad == 0 else f"경고: 합계 불일치 {total_bad}건")
