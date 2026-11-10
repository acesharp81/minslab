from fastapi.testclient import TestClient
from app.main import create_app
from test_flow import seed

# Manually specified relevance judgments, not generated from search output.
QUERIES = [
    ("주민 수요조사", "주민 수요조사 결과"),
    ("영수증", "누락된 영수증"),
    ("부서별 지표", "부서별 지표 확인"),
    ("안내문 발송", "참여자 안내문 발송"),
    ("예산 검토", "예산 검토 의견 수합"),
    ("현장 동선", "점검표와 현장 동선"),
    ("보수 결과", "보수 결과 확인"),
    ("매월 5일", "매월 5일"),
    ("문화기획팀", "문화기획팀"),
    ("정산", "보조금 정산 검토"),
    ("예약", "장소 예약 완료"),
    ("기한 변경 제안", "기한 변경 제안"),
]


def test_synthetic_korean_recall_at_five(tmp_path):
    with TestClient(create_app(tmp_path)) as c:
        base, _ = seed(c)
        hits = 0
        for query, relevant in QUERIES:
            rows = c.get(base + "/search", params={"q": query}).json()["results"]
            hits += any(relevant in row["text"] for row in rows)
        assert hits == len(QUERIES), f"Recall@5 {hits}/{len(QUERIES)}"
