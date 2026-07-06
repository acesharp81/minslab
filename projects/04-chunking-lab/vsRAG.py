"""청킹 전략 비교 실험용 스케치 파일."""

# 다음 단계에서 아래 함수들에 실제 Supabase 벡터 검색 로직을 연결합니다.

def build_chunks(documents, strategy="semantic"):
    """문서를 strategy 기준으로 청킹한다."""
    raise NotImplementedError


def retrieve_similar_chunks(query, chunks, top_k=3):
    """질문과 가장 유사한 chunk를 찾는다."""
    raise NotImplementedError


def compare_answer_quality(query, retrieval_result):
    """검색 결과를 바탕으로 답변 품질을 비교 분석한다."""
    raise NotImplementedError
