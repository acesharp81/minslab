"""청킹실습(과제): 청킹 알고리즘별 RAG 비교 흐름."""

from chunking_compare import chunk_document, compare_tables, embed_plan


STRATEGIES = ["fixed", "recursive", "semantic"]


def run_chunking(document_text):
    """문서를 3가지 방식으로 나눠 비교 가능한 plan을 만든다."""
    return chunk_document(document_text, STRATEGIES)


def embed_each_plan(plans):
    """plan 순서대로 chucking_test1~3 테이블에 임베딩한다."""
    return [embed_plan(plan) for plan in plans]


def ask_with_rag(question, model="openai/gpt-4o-mini"):
    """임베딩된 3개 테이블에서 검색하고 모델 답변을 비교한다."""
    return compare_tables(question, model)
