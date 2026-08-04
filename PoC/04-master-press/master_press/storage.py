from __future__ import annotations

import hashlib
import json
import math
import re
import secrets
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

from .article_metadata import publisher_name, reporter_name
from .similarity import SIMILARITY_GROUPING_VERSION, build_article_similarity_groups, raw_semantic_similarity
from .terminology import canonical_editorial_term, inferred_editorial_events


KST = timezone(timedelta(hours=9))
RECIPIENT_UNSUBSCRIBE_INVITE_LABEL = "__recipient_unsubscribe__"
DASHBOARD_TOPIC_TYPES = (
    "정책·행정", "정치·입법", "경제·산업", "사회·안전", "재난·환경",
    "과학·기술", "AI·디지털", "보건·복지", "교육", "지역",
    "국제", "문화·생활", "인사·조직", "사건·논란", "기타",
)
DASHBOARD_TONES = ("사실전달", "부정적", "긍정적")
NON_NOUN_ENTITY_ENDINGS = (
    "합니다", "했습니다", "하였다", "했다", "한다", "하는", "됩니다", "되었다",
    "된다", "되는", "있습니다", "있었다", "있다", "있는", "없습니다", "없다", "없는",
    "밝혔다", "강조했다", "말했다", "전했다", "나타났다", "보인다", "예정이다",
)


def now_iso() -> str:
    return datetime.now(KST).isoformat(timespec="seconds")


def candidate_exclusion_message(reason: str) -> str:
    labels = {
        "publisher_filtered": "허용된 언론사가 아니라 후보에서 제외했습니다.",
        "exclude_terms_matched": "제외 키워드가 포함되어 후보에서 제외했습니다.",
        "required_terms_missing": "필수 키워드가 확인되지 않아 후보에서 제외했습니다.",
        "include_terms_missing": "포함 키워드가 확인되지 않아 후보에서 제외했습니다.",
        "negative_signal_missing": "부정 이슈를 찾는 케이스지만 기사에서 부정 신호가 확인되지 않았습니다.",
        "semantic_below_threshold": "케이스 주제와 의미 유사도가 낮아 후보에서 제외했습니다.",
    }
    clean = str(reason or "").strip()
    return labels.get(clean, "케이스 조건과 맞지 않아 LLM 판정 전에 제외했습니다." if clean else "")


def kst_day_start_iso(reference: datetime | None = None) -> str:
    current = reference.astimezone(KST) if reference else datetime.now(KST)
    return current.replace(hour=0, minute=0, second=0, microsecond=0).isoformat(timespec="seconds")


def utc_day_start_kst_iso(reference: datetime | None = None) -> str:
    current = reference.astimezone(timezone.utc) if reference else datetime.now(timezone.utc)
    return current.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(KST).isoformat(timespec="seconds")


def json_value(value, default):
    if value is None:
        return default
    if isinstance(value, (list, dict)):
        return value
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return default


def normalized_clock_values(values: Any) -> list[str]:
    result = []
    for value in values if isinstance(values, list) else []:
        parts = str(value).strip().split(":", 1)
        try:
            hour, minute = int(parts[0]), int(parts[1])
        except (ValueError, IndexError):
            continue
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            result.append(f"{hour:02d}:{minute:02d}")
    return sorted(dict.fromkeys(result))


def verified_content_nouns(values: Any, article_text: str, stopwords: set[str], identity_terms: list[str]) -> list[str]:
    """Keep LLM-extracted noun/proper-noun phrases only when they occur in the source article."""
    compact_article = re.sub(r"\s+", "", str(article_text or "")).casefold()
    compact_stopwords = {re.sub(r"\s+", "", value).casefold() for value in stopwords}
    compact_identities = [re.sub(r"\s+", "", value).casefold() for value in identity_terms if value]
    result: list[str] = []
    for value in values if isinstance(values, list) else []:
        clean = str(value or "").strip().strip("#[]\"'")[:60]
        compact = re.sub(r"\s+", "", clean).casefold()
        if len(compact) < 2 or compact not in compact_article or compact in compact_stopwords:
            continue
        if not re.search(r"[가-힣A-Za-z0-9]", clean) or "\n" in clean:
            continue
        if any(compact.endswith(ending) for ending in NON_NOUN_ENTITY_ENDINGS):
            continue
        if any(identity in compact for identity in compact_identities):
            continue
        canonical = canonical_editorial_term(clean)
        if canonical not in result:
            result.append(canonical)
    return result

def inferred_content_nouns(article_text: str, stopwords: set[str], identity_terms: list[str]) -> list[str]:
    """Extract conservative, source-verifiable headline terms when LLM entities are absent."""
    fallback_stopwords = {
        "기자", "뉴스", "단독", "종합", "속보", "포토", "영상", "오늘", "어제", "내일",
        "올해", "지난", "이번", "이날", "최근", "전국", "관련", "대해", "통해", "위해",
        "운영", "진행", "실시", "예정", "밝혀", "밝혔다", "나서", "나선다", "한다",
    }
    compact_stopwords = {re.sub(r"\s+", "", value).casefold() for value in {*stopwords, *fallback_stopwords}}
    compact_identities = [re.sub(r"\s+", "", value).casefold() for value in identity_terms if value]
    particles = ("으로부터", "에게서", "에서는", "으로는", "까지도", "부터는", "에게", "에서", "으로", "와의", "과의", "에는", "에도", "까지", "부터", "은", "는", "이", "가", "을", "를", "에", "의", "와", "과", "도", "만")
    result: list[str] = []
    for raw in re.findall(r"[가-힣A-Za-z][가-힣A-Za-z0-9·.+_-]{1,39}", str(article_text or "")):
        clean = raw.strip("#[]\\\"'")
        for particle in particles:
            if clean.endswith(particle) and len(clean) >= len(particle) + 2:
                clean = clean[:-len(particle)]
                break
        compact = re.sub(r"\s+", "", clean).casefold()
        if len(compact) < 2 or compact in compact_stopwords or compact.isdigit():
            continue
        if any(identity in compact for identity in compact_identities):
            continue
        if compact.endswith(("세요", "습니다")) or any(compact.endswith(ending) for ending in NON_NOUN_ENTITY_ENDINGS):
            continue
        canonical = canonical_editorial_term(clean)
        if canonical not in result:
            result.append(canonical)
        if len(result) >= 8:
            break
    return result


def topic_noun_similarity(left: set[str], right: set[str], document_frequency: dict[str, int], document_count: int) -> float:
    """IDF-weighted topic overlap; institution, tone and full-text embeddings are intentionally absent."""
    intersection, union = left & right, left | right
    if not intersection or not union:
        return 0.0

    def weight(term: str) -> float:
        return math.log((1 + max(1, document_count)) / (1 + document_frequency.get(term, 0))) + 1.0

    weighted_jaccard = sum(weight(term) for term in intersection) / sum(weight(term) for term in union)
    coverage = len(intersection) / max(1, min(len(left), len(right)))
    return round(0.7 * weighted_jaccard + 0.3 * coverage, 4)


ABSTRACT_TOPIC_RULES = (
    ("호우·재난 대응", ("호우", "폭우", "집중호우", "물폭탄", "침수", "산사태", "대피", "중대본", "수해", "재난 대응", "비상 대응")),
    ("폭염 대응", ("폭염", "열대야", "온열질환", "무더위", "폭염 대응", "폭염 대책")),
    ("재생에너지·햇빛소득마을", ("햇빛소득마을", "햇빛 소득마을", "태양광", "재생에너지", "마을 태양광")),
    ("적극행정·공직혁신", ("적극행정", "공직혁신", "적극행정 우수", "적극행정 면책")),
    ("수사기관 개혁·사법제도", ("검찰", "경찰", "수사권", "보완수사권", "검경", "수사기관", "순환인사", "사법개혁", "검찰개혁", "경찰개혁", "광주경찰청", "장윤기")),
    ("지방재정·투자심사", ("중앙투자심사", "중투심", "지방재정", "국비", "보조금", "재정투자")),
    ("지방행정·의회 감시", ("지방의회", "시의원", "도의원", "집행부", "조례", "행정사무감사")),
    ("지역개발·공공사업", ("파크골프장", "유휴부지", "개발사업", "공공사업", "도시개발")),
    ("선거·정치제도", ("선관위", "선거관리위원회", "공직선거", "선거제도")),
)


def inferred_topic_concepts(article_text: str) -> list[str]:
    """Backfill one-level-up concepts for historical analyses without another LLM call."""
    normalized = re.sub(r"\s+", " ", str(article_text or "")).casefold().strip()
    concepts = inferred_editorial_events(normalized)
    for label, terms in ABSTRACT_TOPIC_RULES:
        if any(str(term).casefold() in normalized for term in terms):
            concepts.append(label)
    return concepts[:4]


def centered_semantic_similarity(left: list[float], right: list[float], centroid: list[float]) -> float:
    """Cosine similarity after removing the corpus-level institution/context component."""
    if not left or len(left) != len(right) or len(left) != len(centroid):
        return 0.0
    left_centered = [value - centroid[index] for index, value in enumerate(left)]
    right_centered = [value - centroid[index] for index, value in enumerate(right)]
    left_norm = math.sqrt(sum(value * value for value in left_centered))
    right_norm = math.sqrt(sum(value * value for value in right_centered))
    if left_norm <= 1e-12 or right_norm <= 1e-12:
        return 0.0
    return round(sum(a * b for a, b in zip(left_centered, right_centered)) / (left_norm * right_norm), 4)


SCHEMA = """
CREATE TABLE IF NOT EXISTS organizations (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  abbreviations TEXT NOT NULL DEFAULT '[]',
  former_names TEXT NOT NULL DEFAULT '[]',
  people TEXT NOT NULL DEFAULT '[]',
  exclude_terms TEXT NOT NULL DEFAULT '[]',
  domains TEXT NOT NULL DEFAULT '[]',
  rss_urls TEXT NOT NULL DEFAULT '[]',
  collection_mode TEXT NOT NULL DEFAULT 'interval',
  collection_interval_minutes INTEGER NOT NULL DEFAULT 30,
  collection_times TEXT NOT NULL DEFAULT '[]',
  max_search_queries INTEGER NOT NULL DEFAULT 8,
  max_articles_per_run INTEGER NOT NULL DEFAULT 50,
  is_active INTEGER NOT NULL DEFAULT 1,
  next_collect_at TEXT,
  last_collected_at TEXT,
  archived_at TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS cases (
  id TEXT PRIMARY KEY,
  organization_id TEXT REFERENCES organizations(id) ON DELETE SET NULL,
  name TEXT NOT NULL,
  topic_description TEXT NOT NULL DEFAULT '',
  include_terms TEXT NOT NULL DEFAULT '[]',
  required_terms TEXT NOT NULL DEFAULT '[]',
  exclude_terms TEXT NOT NULL DEFAULT '[]',
  synonym_terms TEXT NOT NULL DEFAULT '{}',
  urgent_terms TEXT NOT NULL DEFAULT '[]',
  include_publishers TEXT NOT NULL DEFAULT '[]',
  exclude_publishers TEXT NOT NULL DEFAULT '[]',
  rss_urls TEXT NOT NULL DEFAULT '[]',
  collection_mode TEXT NOT NULL DEFAULT 'interval',
  collection_interval_minutes INTEGER NOT NULL DEFAULT 30,
  collection_times TEXT NOT NULL DEFAULT '[]',
  delivery_mode TEXT NOT NULL DEFAULT 'immediate',
  delivery_times TEXT NOT NULL DEFAULT '[]',
  send_relevant_immediately INTEGER NOT NULL DEFAULT 1,
  relevance_threshold REAL NOT NULL DEFAULT 70,
  hold_threshold REAL NOT NULL DEFAULT 55,
  keyword_weight REAL NOT NULL DEFAULT 0,
  semantic_weight REAL NOT NULL DEFAULT 0.25,
  llm_weight REAL NOT NULL DEFAULT 0.75,
  max_articles_per_message INTEGER NOT NULL DEFAULT 2,
  is_active INTEGER NOT NULL DEFAULT 1,
  sort_order INTEGER NOT NULL DEFAULT 0,
  version INTEGER NOT NULL DEFAULT 1,
  next_collect_at TEXT,
  last_collected_at TEXT,
  monitor_from TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS case_versions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  case_id TEXT NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
  version INTEGER NOT NULL,
  snapshot TEXT NOT NULL,
  created_at TEXT NOT NULL,
  UNIQUE(case_id, version)
);

CREATE TABLE IF NOT EXISTS recipients (
  id TEXT PRIMARY KEY,
  label TEXT NOT NULL,
  kakao_user_id TEXT UNIQUE,
  access_token_ciphertext TEXT,
  refresh_token_ciphertext TEXT,
  access_token_expires_at TEXT,
  refresh_token_expires_at TEXT,
  scopes TEXT NOT NULL DEFAULT '[]',
  status TEXT NOT NULL DEFAULT 'pending',
  last_error TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS case_recipients (
  case_id TEXT NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
  recipient_id TEXT NOT NULL REFERENCES recipients(id) ON DELETE CASCADE,
  PRIMARY KEY(case_id, recipient_id)
);

CREATE TABLE IF NOT EXISTS recipient_invites (
  id TEXT PRIMARY KEY,
  token_hash TEXT NOT NULL UNIQUE,
  label TEXT NOT NULL,
  expires_at TEXT NOT NULL,
  used_at TEXT,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS signup_requests (
  id TEXT PRIMARY KEY,
  invite_id TEXT NOT NULL REFERENCES recipient_invites(id) ON DELETE CASCADE,
  recipient_id TEXT REFERENCES recipients(id) ON DELETE SET NULL,
  applicant_name TEXT NOT NULL,
  organization_id TEXT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  status TEXT NOT NULL DEFAULT 'requested',
  admin_note TEXT NOT NULL DEFAULT '',
  kakao_registered_at TEXT,
  decided_at TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS signup_request_cases (
  request_id TEXT NOT NULL REFERENCES signup_requests(id) ON DELETE CASCADE,
  case_id TEXT NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
  status TEXT NOT NULL DEFAULT 'pending',
  decided_at TEXT,
  updated_at TEXT NOT NULL,
  PRIMARY KEY(request_id,case_id)
);
CREATE INDEX IF NOT EXISTS idx_signup_requests_status ON signup_requests(status,created_at DESC);
CREATE INDEX IF NOT EXISTS idx_signup_request_cases_case ON signup_request_cases(case_id,status);

CREATE TABLE IF NOT EXISTS articles (
  id TEXT PRIMARY KEY,
  canonical_url TEXT NOT NULL UNIQUE,
  original_url TEXT NOT NULL,
  title TEXT NOT NULL,
  publisher TEXT NOT NULL DEFAULT '',
  published_at TEXT,
  snippet TEXT NOT NULL DEFAULT '',
  body TEXT NOT NULL DEFAULT '',
  image_url TEXT NOT NULL DEFAULT '',
    body_error TEXT NOT NULL DEFAULT '',
  body_expires_at TEXT,
  content_hash TEXT,
  source_type TEXT NOT NULL DEFAULT 'naver',
  first_seen_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS article_scores (
  id TEXT PRIMARY KEY,
  article_id TEXT NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
  case_id TEXT NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
  case_version INTEGER NOT NULL,
  keyword_score REAL NOT NULL,
  semantic_score REAL NOT NULL,
  llm_score REAL NOT NULL,
  final_score REAL NOT NULL,
  summary TEXT NOT NULL DEFAULT '',
  organization_tag TEXT NOT NULL DEFAULT '',
  article_type TEXT NOT NULL DEFAULT '기타',
  tone TEXT NOT NULL DEFAULT '사실전달',
  evidence_status TEXT NOT NULL DEFAULT '',
  classification_tags TEXT NOT NULL DEFAULT '[]',
  reasons TEXT NOT NULL DEFAULT '[]',
  matched_terms TEXT NOT NULL DEFAULT '[]',
  low_score_categories TEXT NOT NULL DEFAULT '[]',
  analysis_report TEXT NOT NULL DEFAULT '{}',
  decision TEXT NOT NULL,
  analysis_completed INTEGER NOT NULL DEFAULT 1,
  delivery_classified INTEGER NOT NULL DEFAULT 1,
  finalized_at TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE(article_id, case_id)
);

CREATE TABLE IF NOT EXISTS app_settings (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS announcements (
  id TEXT PRIMARY KEY,
  title TEXT NOT NULL DEFAULT '',
  body TEXT NOT NULL DEFAULT '',
  starts_at TEXT NOT NULL DEFAULT '',
  ends_at TEXT NOT NULL DEFAULT '',
  is_active INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_announcements_active ON announcements(is_active,ends_at,created_at DESC);

CREATE TABLE IF NOT EXISTS case_proposals (
  id TEXT PRIMARY KEY,
  nickname TEXT NOT NULL DEFAULT '',
  password_salt TEXT NOT NULL DEFAULT '',
  password_hash TEXT NOT NULL DEFAULT '',
  title TEXT NOT NULL DEFAULT '',
  prompt TEXT NOT NULL DEFAULT '',
  include_terms TEXT NOT NULL DEFAULT '[]',
  required_terms TEXT NOT NULL DEFAULT '[]',
  moderation_status TEXT NOT NULL DEFAULT 'pending',
  moderation_flagged INTEGER NOT NULL DEFAULT 0,
  moderation_exempt INTEGER NOT NULL DEFAULT 0,
  moderation_reason TEXT NOT NULL DEFAULT '',
  moderation_model TEXT NOT NULL DEFAULT '',
  moderated_at TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_case_proposals_created ON case_proposals(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_case_proposals_moderation ON case_proposals(moderation_status,updated_at);

CREATE TABLE IF NOT EXISTS llm_api_calls (
  id TEXT PRIMARY KEY,
  provider TEXT NOT NULL,
  stage TEXT NOT NULL,
  model TEXT NOT NULL,
  status TEXT NOT NULL,
  http_status INTEGER,
  request_id TEXT,
  input_tokens INTEGER NOT NULL DEFAULT 0,
  output_tokens INTEGER NOT NULL DEFAULT 0,
  usage_units INTEGER NOT NULL DEFAULT 0,
  duration_ms INTEGER NOT NULL DEFAULT 0,
  error TEXT,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_llm_api_calls_provider_created ON llm_api_calls(provider,stage,created_at DESC);

CREATE TABLE IF NOT EXISTS reanalysis_jobs (
  id TEXT PRIMARY KEY,
  article_id TEXT NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
  case_id TEXT NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
  model TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending',
  queued_at TEXT NOT NULL,
  started_at TEXT,
  finished_at TEXT,
  duration_ms INTEGER,
  error TEXT,
  result TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS llm_jobs (
  id TEXT PRIMARY KEY,
  article_id TEXT NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
  case_id TEXT NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
  case_version INTEGER NOT NULL,
  organization_id TEXT REFERENCES organizations(id) ON DELETE SET NULL,
  status TEXT NOT NULL DEFAULT 'pending',
  queued_at TEXT NOT NULL,
  started_at TEXT,
  finished_at TEXT,
  duration_ms INTEGER,
  error TEXT,
  UNIQUE(article_id, case_id, case_version)
);


CREATE TABLE IF NOT EXISTS deliveries (
  id TEXT PRIMARY KEY,
  article_id TEXT NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
  case_id TEXT NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
  recipient_id TEXT NOT NULL REFERENCES recipients(id) ON DELETE CASCADE,
  scheduled_at TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending',
  attempts INTEGER NOT NULL DEFAULT 0,
  response_code INTEGER,
  last_error TEXT,
  sent_at TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE(article_id, case_id, recipient_id)
);

CREATE TABLE IF NOT EXISTS collection_runs (
  id TEXT PRIMARY KEY,
  case_id TEXT REFERENCES cases(id) ON DELETE SET NULL,
  organization_id TEXT REFERENCES organizations(id) ON DELETE SET NULL,
  started_at TEXT NOT NULL,
  finished_at TEXT,
  status TEXT NOT NULL,
  collected_count INTEGER NOT NULL DEFAULT 0,
  new_count INTEGER NOT NULL DEFAULT 0,
  scored_count INTEGER NOT NULL DEFAULT 0,
  queued_count INTEGER NOT NULL DEFAULT 0,
  error TEXT
);

CREATE TABLE IF NOT EXISTS improvement_reports (
  id TEXT PRIMARY KEY,
  case_id TEXT NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
  period_start TEXT NOT NULL,
  period_end TEXT NOT NULL,
  sample_count INTEGER NOT NULL,
  average_score REAL NOT NULL,
  categories TEXT NOT NULL,
  suggestions TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS analysis_feedback (
  id TEXT PRIMARY KEY,
  article_id TEXT NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
  case_id TEXT NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
  reason TEXT NOT NULL,
  comment TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS article_analyses (
  id TEXT PRIMARY KEY,
  article_id TEXT NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
  organization_id TEXT REFERENCES organizations(id) ON DELETE SET NULL,
  content_key TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending',
  model TEXT NOT NULL DEFAULT '',
  prompt_version TEXT NOT NULL DEFAULT 'article-v1',
  summary TEXT NOT NULL DEFAULT '',
  publisher_name TEXT NOT NULL DEFAULT '',
  reporter_name TEXT NOT NULL DEFAULT '',
  article_type TEXT NOT NULL DEFAULT '분류대기',
  tone TEXT NOT NULL DEFAULT '사실전달',
  classification_tags TEXT NOT NULL DEFAULT '[]',
  entities TEXT NOT NULL DEFAULT '[]',
  topic_concepts TEXT NOT NULL DEFAULT '[]',
  evidence TEXT NOT NULL DEFAULT '[]',
  analysis_report TEXT NOT NULL DEFAULT '{}',
  error TEXT,
  analyzed_at TEXT,
  case_routed_at TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE(article_id, content_key)
);

CREATE TABLE IF NOT EXISTS article_analysis_jobs (
  id TEXT PRIMARY KEY,
  article_analysis_id TEXT NOT NULL REFERENCES article_analyses(id) ON DELETE CASCADE,
  organization_id TEXT REFERENCES organizations(id) ON DELETE SET NULL,
  status TEXT NOT NULL DEFAULT 'pending',
  queued_at TEXT NOT NULL,
  started_at TEXT,
  finished_at TEXT,
  duration_ms INTEGER,
  attempts INTEGER NOT NULL DEFAULT 0,
  retry_after TEXT,
  lease_owner TEXT NOT NULL DEFAULT '',
  lease_expires_at TEXT,
  provider_lane TEXT NOT NULL DEFAULT 'primary',
  error TEXT,
  UNIQUE(article_analysis_id)
);

CREATE TABLE IF NOT EXISTS case_evaluations (
  id TEXT PRIMARY KEY,
  article_analysis_id TEXT NOT NULL REFERENCES article_analyses(id) ON DELETE CASCADE,
  article_id TEXT NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
  case_id TEXT NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
  case_version INTEGER NOT NULL,
  candidate_status TEXT NOT NULL DEFAULT 'candidate',
  status TEXT NOT NULL DEFAULT 'pending',
  model TEXT NOT NULL DEFAULT '',
  keyword_score REAL NOT NULL DEFAULT 0,
  semantic_raw REAL NOT NULL DEFAULT 0,
  semantic_score REAL NOT NULL DEFAULT 0,
  llm_score REAL NOT NULL DEFAULT 0,
  final_score REAL NOT NULL DEFAULT 0,
  evidence_status TEXT NOT NULL DEFAULT '',
  reasons TEXT NOT NULL DEFAULT '[]',
  matched_terms TEXT NOT NULL DEFAULT '[]',
  low_score_categories TEXT NOT NULL DEFAULT '[]',
  analysis_report TEXT NOT NULL DEFAULT '{}',
  decision TEXT NOT NULL DEFAULT 'pending',
  error TEXT,
  completed_at TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE(article_analysis_id, case_id, case_version)
);

CREATE TABLE IF NOT EXISTS article_processing_flags (
  article_id TEXT PRIMARY KEY REFERENCES articles(id) ON DELETE CASCADE,
  analysis_id TEXT NOT NULL,
  common_analysis_completed INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS article_case_processing_flags (
  article_id TEXT NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
  case_id TEXT NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
  analysis_id TEXT NOT NULL,
  evaluation_id TEXT NOT NULL,
  case_version INTEGER NOT NULL,
  common_analysis_completed INTEGER NOT NULL DEFAULT 1,
  case_evaluation_completed INTEGER NOT NULL DEFAULT 0,
  delivery_classified INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  PRIMARY KEY(article_id, case_id)
);

CREATE TABLE IF NOT EXISTS case_evaluation_jobs (
  id TEXT PRIMARY KEY,
  case_evaluation_id TEXT NOT NULL REFERENCES case_evaluations(id) ON DELETE CASCADE,
  provider TEXT NOT NULL DEFAULT 'openrouter',
  status TEXT NOT NULL DEFAULT 'pending',
  queued_at TEXT NOT NULL,
  started_at TEXT,
  finished_at TEXT,
  duration_ms INTEGER,
  attempts INTEGER NOT NULL DEFAULT 0,
  retry_after TEXT,
  batch_id TEXT NOT NULL DEFAULT '',
  batch_size INTEGER NOT NULL DEFAULT 1,
  lease_owner TEXT NOT NULL DEFAULT '',
  lease_expires_at TEXT,
  provider_lane TEXT NOT NULL DEFAULT 'primary',
  error TEXT,
  UNIQUE(case_evaluation_id)
);

CREATE TABLE IF NOT EXISTS case_embeddings (
  case_id TEXT NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
  case_version INTEGER NOT NULL,
  model TEXT NOT NULL,
  retrieval_text TEXT NOT NULL,
  dimensions INTEGER NOT NULL DEFAULT 0,
  vector TEXT NOT NULL DEFAULT '[]',
  calibration TEXT NOT NULL DEFAULT '{}',
  status TEXT NOT NULL DEFAULT 'completed',
  error TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  PRIMARY KEY(case_id,case_version,model)
);

CREATE TABLE IF NOT EXISTS article_embeddings (
  article_analysis_id TEXT PRIMARY KEY REFERENCES article_analyses(id) ON DELETE CASCADE,
  model TEXT NOT NULL,
  dimensions INTEGER NOT NULL DEFAULT 0,
  vector TEXT NOT NULL DEFAULT '[]',
  status TEXT NOT NULL DEFAULT 'completed',
  error TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS press_releases (
  id TEXT PRIMARY KEY,
  organization_id TEXT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  source TEXT NOT NULL DEFAULT 'mois',
  external_id TEXT NOT NULL,
  canonical_url TEXT NOT NULL UNIQUE,
  title TEXT NOT NULL,
  department TEXT NOT NULL DEFAULT '',
  contact_name TEXT NOT NULL DEFAULT '',
  contact_phone TEXT NOT NULL DEFAULT '',
  published_at TEXT,
  summary TEXT NOT NULL DEFAULT '',
  markdown_path TEXT NOT NULL,
  content_hash TEXT NOT NULL,
  document_fingerprint TEXT NOT NULL DEFAULT '',
  embedding_status TEXT NOT NULL DEFAULT 'pending',
  embedding_model TEXT NOT NULL DEFAULT '',
  last_error TEXT,
  supabase_synced_at TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS press_release_chunks (
  id TEXT PRIMARY KEY,
  press_release_id TEXT NOT NULL REFERENCES press_releases(id) ON DELETE CASCADE,
  chunk_index INTEGER NOT NULL,
  content TEXT NOT NULL,
  content_hash TEXT NOT NULL,
  embedding_model TEXT NOT NULL,
  dimensions INTEGER NOT NULL DEFAULT 0,
  vector TEXT NOT NULL DEFAULT '[]',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE(press_release_id,chunk_index)
);
CREATE TABLE IF NOT EXISTS press_release_match_jobs (
  article_id TEXT NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
  press_release_id TEXT NOT NULL REFERENCES press_releases(id) ON DELETE CASCADE,
  status TEXT NOT NULL DEFAULT 'pending',
  queued_at TEXT NOT NULL,
  started_at TEXT,
  finished_at TEXT,
  error TEXT,
  PRIMARY KEY(article_id,press_release_id)
);
CREATE TABLE IF NOT EXISTS article_press_release_matches (
  article_id TEXT NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
  press_release_id TEXT NOT NULL REFERENCES press_releases(id) ON DELETE CASCADE,
  status TEXT NOT NULL DEFAULT 'completed',
  is_related INTEGER NOT NULL DEFAULT 0,
  semantic_score REAL NOT NULL DEFAULT 0,
  lexical_score REAL NOT NULL DEFAULT 0,
  similarity_score REAL NOT NULL DEFAULT 0,
  matcher_version TEXT NOT NULL,
  matched_at TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  supabase_synced_at TEXT,
  PRIMARY KEY(article_id,press_release_id)
);
CREATE INDEX IF NOT EXISTS idx_press_releases_org_published ON press_releases(organization_id,published_at DESC);
CREATE INDEX IF NOT EXISTS idx_press_releases_embedding ON press_releases(embedding_status,updated_at);
CREATE INDEX IF NOT EXISTS idx_press_release_match_jobs_status ON press_release_match_jobs(status,queued_at);
CREATE INDEX IF NOT EXISTS idx_article_press_release_related ON article_press_release_matches(article_id,is_related,similarity_score DESC);
CREATE INDEX IF NOT EXISTS idx_press_release_articles_related ON article_press_release_matches(press_release_id,is_related,similarity_score DESC);

CREATE INDEX IF NOT EXISTS idx_article_embeddings_status ON article_embeddings(status, updated_at);
CREATE TABLE IF NOT EXISTS article_similarity_groups (
  article_id TEXT PRIMARY KEY REFERENCES articles(id) ON DELETE CASCADE,
  group_id TEXT NOT NULL DEFAULT '',
  group_size INTEGER NOT NULL DEFAULT 1,
  basis TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT '',
  score REAL NOT NULL DEFAULT 0,
  semantic_score REAL NOT NULL DEFAULT 0,
  noun_score REAL NOT NULL DEFAULT 0,
  topics TEXT NOT NULL DEFAULT '[]',
  concepts TEXT NOT NULL DEFAULT '[]',
  computed_at TEXT NOT NULL

);
CREATE INDEX IF NOT EXISTS idx_article_similarity_groups_group ON article_similarity_groups(group_id, computed_at DESC);
CREATE INDEX IF NOT EXISTS idx_article_analyses_status ON article_analyses(status, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_article_analysis_jobs_status ON article_analysis_jobs(status, queued_at);
CREATE INDEX IF NOT EXISTS idx_case_evaluations_article ON case_evaluations(article_analysis_id, status);
CREATE INDEX IF NOT EXISTS idx_case_evaluation_jobs_status ON case_evaluation_jobs(status, queued_at);
CREATE INDEX IF NOT EXISTS idx_case_embeddings_status ON case_embeddings(status,updated_at);

CREATE INDEX IF NOT EXISTS idx_scores_case_created ON article_scores(case_id, created_at DESC);
-- Supports the unfiltered dashboard's newest-first score history without a full sort.
CREATE INDEX IF NOT EXISTS idx_scores_created ON article_scores(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_scores_final ON article_scores(final_score);
CREATE INDEX IF NOT EXISTS idx_llm_jobs_status_queued ON llm_jobs(status, queued_at DESC);
CREATE INDEX IF NOT EXISTS idx_reanalysis_jobs_status_queued ON reanalysis_jobs(status, queued_at);
CREATE INDEX IF NOT EXISTS idx_organizations_due ON organizations(is_active, next_collect_at);
CREATE INDEX IF NOT EXISTS idx_deliveries_due ON deliveries(status, scheduled_at);
-- Used by the administrator's sent-article keyword preview. Keep the
-- case/status/date lookup narrow so it never has to read article bodies for
-- every delivery in the system.
CREATE INDEX IF NOT EXISTS idx_deliveries_case_status_sent_at ON deliveries(case_id, status, sent_at DESC, article_id);

-- A magazine is an immutable, shared editorial snapshot. Browser-specific
-- case choices are deliberately not stored here.
CREATE TABLE IF NOT EXISTS magazine_editions (
  id TEXT PRIMARY KEY,
  organization_id TEXT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  organization_name TEXT NOT NULL DEFAULT '',
  edition_date TEXT NOT NULL,
  edition_slot TEXT NOT NULL CHECK(edition_slot IN ('morning','lunch','evening','daily')),
  window_start_at TEXT NOT NULL,
  window_end_at TEXT NOT NULL,
  case_catalog TEXT NOT NULL DEFAULT '[]',
  daily_topics TEXT NOT NULL DEFAULT '[]',
  issue_count INTEGER NOT NULL DEFAULT 0,
  article_count INTEGER NOT NULL DEFAULT 0,
  status TEXT NOT NULL DEFAULT 'published',
  generated_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE(organization_id, edition_date, edition_slot)
);
CREATE INDEX IF NOT EXISTS idx_magazine_editions_org_date
  ON magazine_editions(organization_id,edition_date DESC,edition_slot);

CREATE TABLE IF NOT EXISTS magazine_issue_members (
  edition_id TEXT NOT NULL REFERENCES magazine_editions(id) ON DELETE CASCADE,
  article_id TEXT NOT NULL,
  issue_key TEXT NOT NULL,
  rank INTEGER NOT NULL DEFAULT 0,
  title TEXT NOT NULL DEFAULT '',
  summary TEXT NOT NULL DEFAULT '',
  publisher TEXT NOT NULL DEFAULT '',
  tone TEXT NOT NULL DEFAULT '사실전달',
  article_type TEXT NOT NULL DEFAULT '기타',
  published_at TEXT,
  original_url TEXT NOT NULL DEFAULT '',
  image_url TEXT NOT NULL DEFAULT '',
  case_matches TEXT NOT NULL DEFAULT '[]',
  related_press_releases TEXT NOT NULL DEFAULT '[]',
  created_at TEXT NOT NULL,
  PRIMARY KEY(edition_id, article_id)
);
CREATE INDEX IF NOT EXISTS idx_magazine_members_issue
  ON magazine_issue_members(edition_id,issue_key,rank);
CREATE INDEX IF NOT EXISTS idx_articles_published ON articles(published_at DESC);
CREATE TABLE IF NOT EXISTS supabase_outbox (
  id TEXT PRIMARY KEY,
  table_name TEXT NOT NULL,
  conflict_key TEXT NOT NULL DEFAULT 'id',
  payload TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending',
  attempts INTEGER NOT NULL DEFAULT 0,
  next_attempt_at TEXT,
  last_error TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE(table_name, conflict_key, id)
);
CREATE INDEX IF NOT EXISTS idx_supabase_outbox_due ON supabase_outbox(status,next_attempt_at,created_at);

CREATE TABLE IF NOT EXISTS processing_daily_stats (
  day TEXT PRIMARY KEY,
  article_count INTEGER NOT NULL DEFAULT 0,
  recorded_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_processing_daily_stats_day ON processing_daily_stats(day DESC);
"""

MAGAZINE_EXTENSION_SCHEMA = "CREATE TABLE IF NOT EXISTS signup_request_magazine_slots (request_id TEXT NOT NULL REFERENCES signup_requests(id) ON DELETE CASCADE,edition_slot TEXT NOT NULL CHECK(edition_slot IN ('morning','lunch','evening','daily')),PRIMARY KEY(request_id,edition_slot));\nCREATE TABLE IF NOT EXISTS recipient_magazine_subscriptions (organization_id TEXT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,recipient_id TEXT NOT NULL REFERENCES recipients(id) ON DELETE CASCADE,edition_slots TEXT NOT NULL DEFAULT '[]',case_ids TEXT NOT NULL DEFAULT '[]',updated_at TEXT NOT NULL,PRIMARY KEY(organization_id,recipient_id));\nCREATE INDEX IF NOT EXISTS idx_magazine_subscriptions_recipient ON recipient_magazine_subscriptions(recipient_id,organization_id);\nCREATE TABLE IF NOT EXISTS magazine_deliveries (id TEXT PRIMARY KEY,edition_id TEXT NOT NULL REFERENCES magazine_editions(id) ON DELETE CASCADE,recipient_id TEXT NOT NULL REFERENCES recipients(id) ON DELETE CASCADE,selected_case_ids TEXT NOT NULL DEFAULT '[]',scheduled_at TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'pending',attempts INTEGER NOT NULL DEFAULT 0,response_code INTEGER,last_error TEXT,created_at TEXT NOT NULL,updated_at TEXT NOT NULL,sent_at TEXT,UNIQUE(edition_id,recipient_id));\nCREATE INDEX IF NOT EXISTS idx_magazine_deliveries_due ON magazine_deliveries(status,scheduled_at);"

SHADOW_CASE_SCHEMA = """
CREATE TABLE IF NOT EXISTS shadow_case_evaluations (
  id TEXT PRIMARY KEY,
  case_evaluation_id TEXT NOT NULL UNIQUE REFERENCES case_evaluations(id) ON DELETE CASCADE,
  status TEXT NOT NULL DEFAULT 'pending',
  queued_at TEXT NOT NULL,
  started_at TEXT,
  completed_at TEXT,
  duration_ms INTEGER NOT NULL DEFAULT 0,
  attempts INTEGER NOT NULL DEFAULT 0,
  primary_model TEXT NOT NULL DEFAULT '',
  primary_decision TEXT NOT NULL DEFAULT '',
  primary_final_score REAL NOT NULL DEFAULT 0,
  primary_llm_score REAL NOT NULL DEFAULT 0,
  shadow_model TEXT NOT NULL DEFAULT '',
  shadow_decision TEXT NOT NULL DEFAULT '',
  shadow_final_score REAL NOT NULL DEFAULT 0,
  shadow_llm_score REAL NOT NULL DEFAULT 0,
  decision_match INTEGER,
  input_tokens INTEGER NOT NULL DEFAULT 0,
  output_tokens INTEGER NOT NULL DEFAULT 0,
  error TEXT
);
CREATE INDEX IF NOT EXISTS idx_shadow_case_evaluations_due ON shadow_case_evaluations(status,queued_at);
CREATE INDEX IF NOT EXISTS idx_shadow_case_evaluations_review ON shadow_case_evaluations(status,decision_match,queued_at DESC);
CREATE INDEX IF NOT EXISTS idx_shadow_case_evaluations_completed ON shadow_case_evaluations(completed_at DESC);
CREATE TABLE IF NOT EXISTS shadow_case_feedback (
  id TEXT PRIMARY KEY,
  shadow_case_evaluation_id TEXT NOT NULL UNIQUE REFERENCES shadow_case_evaluations(id) ON DELETE CASCADE,
  verdict TEXT NOT NULL CHECK(verdict IN ('primary_correct','shadow_correct','uncertain')),
  reason TEXT NOT NULL DEFAULT '',
  comment TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_shadow_case_feedback_verdict ON shadow_case_feedback(verdict,updated_at DESC);
"""



class Store:
    CASE_JSON_FIELDS = {
        "include_terms": [], "required_terms": [], "exclude_terms": [], "synonym_terms": {},
        "urgent_terms": [], "include_publishers": [], "exclude_publishers": [], "rss_urls": [],
        "collection_times": [], "delivery_times": [],
    }
    ORGANIZATION_JSON_FIELDS = {
        "abbreviations": [], "former_names": [], "people": [], "exclude_terms": [],
        "domains": [], "rss_urls": [], "collection_times": [],
    }
    PIPELINE_SUMMARY_CACHE_TTL_SECONDS = 20
    # Cover the full 24-hour dashboard and the previous-day morning magazine
    # window, with enough grace for delayed embedding/snapshot completion.
    SIMILARITY_GROUP_LOOKBACK_HOURS = 48

    def __init__(self, path: str | Path, initialize: bool = True):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._pipeline_summary_cache: dict[tuple, tuple[float, tuple[int, int, int, int], dict]] = {}
        self._magazine_schema_ready = False
        if not initialize:
            return
        with self.connect() as connection:
            connection.executescript(SCHEMA)
            connection.executescript(SHADOW_CASE_SCHEMA)
            magazine_member_columns = {row[1] for row in connection.execute("PRAGMA table_info(magazine_issue_members)")}
            if "image_url" not in magazine_member_columns:
                connection.execute("ALTER TABLE magazine_issue_members ADD COLUMN image_url TEXT NOT NULL DEFAULT ''")
            self._migrate_article_case_flag_schema(connection)
            article_columns = {row[1] for row in connection.execute("PRAGMA table_info(articles)")}
            if "image_url" not in article_columns:
                connection.execute("ALTER TABLE articles ADD COLUMN image_url TEXT NOT NULL DEFAULT ''")
            if "body_error" not in article_columns:
                connection.execute("ALTER TABLE articles ADD COLUMN body_error TEXT NOT NULL DEFAULT ''")
            for column, definition in (
                ("body_attempts", "INTEGER NOT NULL DEFAULT 0"),
                ("body_last_attempt_at", "TEXT"),
                ("body_next_attempt_at", "TEXT"),
                ("body_retryable", "INTEGER NOT NULL DEFAULT 1"),
                ("body_http_status", "INTEGER"),
            ):
                if column not in article_columns:
                    connection.execute(f"ALTER TABLE articles ADD COLUMN {column} {definition}")
            connection.execute("UPDATE articles SET body_retryable=0 WHERE COALESCE(body,'')='' AND body_error='robots_disallowed'")
            connection.execute("CREATE INDEX IF NOT EXISTS idx_articles_body_backfill ON articles(body_retryable,body_next_attempt_at,first_seen_at)")
            recipient_columns = {row[1] for row in connection.execute("PRAGMA table_info(recipients)")}
            if "scopes" not in recipient_columns:
                connection.execute("ALTER TABLE recipients ADD COLUMN scopes TEXT NOT NULL DEFAULT '[]'")
            connection.execute(
                """UPDATE recipients
                   SET label=(
                     SELECT sr.applicant_name FROM signup_requests sr
                     WHERE sr.recipient_id=recipients.id AND COALESCE(sr.applicant_name,'')<>''
                     ORDER BY COALESCE(sr.updated_at,sr.created_at) DESC LIMIT 1
                   ),updated_at=?
                   WHERE label IN ('구독 신청자','카카오 수신자','')
                     AND EXISTS (
                       SELECT 1 FROM signup_requests sr
                       WHERE sr.recipient_id=recipients.id AND COALESCE(sr.applicant_name,'')<>''
                     )""",
                (now_iso(),),
            )
            connection.execute("DROP TRIGGER IF EXISTS cases_max_five")
            columns = {row[1] for row in connection.execute("PRAGMA table_info(cases)")}
            if "organization_id" not in columns:
                connection.execute(
                    "ALTER TABLE cases ADD COLUMN organization_id TEXT REFERENCES organizations(id) ON DELETE SET NULL"
                )
            if "send_relevant_immediately" not in columns:
                connection.execute(
                    "ALTER TABLE cases ADD COLUMN send_relevant_immediately INTEGER NOT NULL DEFAULT 1"
                )
            if "monitor_from" not in columns:
                connection.execute("ALTER TABLE cases ADD COLUMN monitor_from TEXT")
            if "sort_order" not in columns:
                connection.execute("ALTER TABLE cases ADD COLUMN sort_order INTEGER NOT NULL DEFAULT 0")
            connection.execute(
                "UPDATE cases SET monitor_from=created_at WHERE monitor_from IS NULL OR monitor_from=''"
            )
            self._backfill_case_sort_order(connection)
            common_columns = {row[1] for row in connection.execute("PRAGMA table_info(article_analyses)")}
            if "organization_id" not in common_columns:
                connection.execute("ALTER TABLE article_analyses ADD COLUMN organization_id TEXT REFERENCES organizations(id) ON DELETE SET NULL")
            if "topic_concepts" not in common_columns:
                connection.execute("ALTER TABLE article_analyses ADD COLUMN topic_concepts TEXT NOT NULL DEFAULT '[]'")
            if "publisher_name" not in common_columns:
                connection.execute("ALTER TABLE article_analyses ADD COLUMN publisher_name TEXT NOT NULL DEFAULT ''")
            if "reporter_name" not in common_columns:
                connection.execute("ALTER TABLE article_analyses ADD COLUMN reporter_name TEXT NOT NULL DEFAULT ''")
            if "case_routed_at" not in common_columns:
                connection.execute("ALTER TABLE article_analyses ADD COLUMN case_routed_at TEXT")
                connection.execute(
                    """UPDATE article_analyses SET case_routed_at=COALESCE(
                         (SELECT MAX(j.finished_at) FROM article_analysis_jobs j WHERE j.article_analysis_id=article_analyses.id AND j.status='completed'),
                         analyzed_at,updated_at)
                       WHERE status='completed' AND EXISTS (
                         SELECT 1 FROM article_embeddings ae WHERE ae.article_analysis_id=article_analyses.id AND ae.status='completed')"""
                )
            common_job_columns = {row[1] for row in connection.execute("PRAGMA table_info(article_analysis_jobs)")}
            api_call_columns = {row[1] for row in connection.execute("PRAGMA table_info(llm_api_calls)")}
            if "usage_units" not in api_call_columns:
                connection.execute("ALTER TABLE llm_api_calls ADD COLUMN usage_units INTEGER NOT NULL DEFAULT 0")
            if "organization_id" not in common_job_columns:
                connection.execute("ALTER TABLE article_analysis_jobs ADD COLUMN organization_id TEXT REFERENCES organizations(id) ON DELETE SET NULL")
            if "attempts" not in common_job_columns:
                connection.execute("ALTER TABLE article_analysis_jobs ADD COLUMN attempts INTEGER NOT NULL DEFAULT 0")
            if "retry_after" not in common_job_columns:
                connection.execute("ALTER TABLE article_analysis_jobs ADD COLUMN retry_after TEXT")
            if "lease_owner" not in common_job_columns:
                connection.execute("ALTER TABLE article_analysis_jobs ADD COLUMN lease_owner TEXT NOT NULL DEFAULT ''")
            if "lease_expires_at" not in common_job_columns:
                connection.execute("ALTER TABLE article_analysis_jobs ADD COLUMN lease_expires_at TEXT")
            if "provider_lane" not in common_job_columns:
                connection.execute("ALTER TABLE article_analysis_jobs ADD COLUMN provider_lane TEXT NOT NULL DEFAULT 'primary'")
            case_job_columns = {row[1] for row in connection.execute("PRAGMA table_info(case_evaluation_jobs)")}
            if "provider" not in case_job_columns:
                connection.execute("ALTER TABLE case_evaluation_jobs ADD COLUMN provider TEXT NOT NULL DEFAULT 'openrouter'")
            if "attempts" not in case_job_columns:
                connection.execute("ALTER TABLE case_evaluation_jobs ADD COLUMN attempts INTEGER NOT NULL DEFAULT 0")
            if "retry_after" not in case_job_columns:
                connection.execute("ALTER TABLE case_evaluation_jobs ADD COLUMN retry_after TEXT")
            if "batch_id" not in case_job_columns:
                connection.execute("ALTER TABLE case_evaluation_jobs ADD COLUMN batch_id TEXT NOT NULL DEFAULT ''")
            if "batch_size" not in case_job_columns:
                connection.execute("ALTER TABLE case_evaluation_jobs ADD COLUMN batch_size INTEGER NOT NULL DEFAULT 1")
            if "lease_owner" not in case_job_columns:
                connection.execute("ALTER TABLE case_evaluation_jobs ADD COLUMN lease_owner TEXT NOT NULL DEFAULT ''")
            if "lease_expires_at" not in case_job_columns:
                connection.execute("ALTER TABLE case_evaluation_jobs ADD COLUMN lease_expires_at TEXT")
            if "provider_lane" not in case_job_columns:
                connection.execute("ALTER TABLE case_evaluation_jobs ADD COLUMN provider_lane TEXT NOT NULL DEFAULT 'primary'")
            evaluation_columns = {row[1] for row in connection.execute("PRAGMA table_info(case_evaluations)")}
            if "semantic_raw" not in evaluation_columns:
                connection.execute("ALTER TABLE case_evaluations ADD COLUMN semantic_raw REAL NOT NULL DEFAULT 0")
            hybrid_migration = connection.execute("SELECT value FROM app_settings WHERE key='case_hybrid_weights_v1'").fetchone()
            if not hybrid_migration:
                connection.execute("UPDATE cases SET keyword_weight=0,semantic_weight=0.5,llm_weight=0.5")
                connection.execute(
                    "INSERT INTO app_settings(key,value,updated_at) VALUES('case_hybrid_weights_v1','applied',?)",
                    (now_iso(),),
                )
            delivery_defaults_migration = connection.execute("SELECT value FROM app_settings WHERE key='case_delivery_defaults_70_llm75_v1'").fetchone()
            if not delivery_defaults_migration:
                connection.execute("UPDATE cases SET relevance_threshold=70,keyword_weight=0,semantic_weight=0.25,llm_weight=0.75")
                connection.execute(
                    "INSERT INTO app_settings(key,value,updated_at) VALUES('case_delivery_defaults_70_llm75_v1','applied',?)",
                    (now_iso(),),
                )
            # One-time recovery for timeouts recorded before retry scheduling was introduced.
            connection.execute("UPDATE article_analysis_jobs SET status='pending',retry_after=NULL WHERE status='failed' AND attempts=0 AND error LIKE '%timed out%'")
            connection.execute("UPDATE article_analyses SET status='pending',error=NULL WHERE id IN (SELECT article_analysis_id FROM article_analysis_jobs WHERE status='pending') AND status='failed'")
            score_columns = {row[1] for row in connection.execute("PRAGMA table_info(article_scores)")}
            if "article_type" not in score_columns:
                connection.execute("ALTER TABLE article_scores ADD COLUMN article_type TEXT NOT NULL DEFAULT '기타'")
            if "organization_tag" not in score_columns:
                connection.execute("ALTER TABLE article_scores ADD COLUMN organization_tag TEXT NOT NULL DEFAULT ''")
            if "tone" not in score_columns:
                connection.execute("ALTER TABLE article_scores ADD COLUMN tone TEXT NOT NULL DEFAULT '사실전달'")
            if "evidence_status" not in score_columns:
                connection.execute("ALTER TABLE article_scores ADD COLUMN evidence_status TEXT NOT NULL DEFAULT ''")
            if "classification_tags" not in score_columns:
                connection.execute(
                    "ALTER TABLE article_scores ADD COLUMN classification_tags TEXT NOT NULL DEFAULT '[]'"
                )
            if "analysis_report" not in score_columns:
                connection.execute("ALTER TABLE article_scores ADD COLUMN analysis_report TEXT NOT NULL DEFAULT '{}'")
            if "analysis_completed" not in score_columns:
                connection.execute("ALTER TABLE article_scores ADD COLUMN analysis_completed INTEGER NOT NULL DEFAULT 1")
            if "delivery_classified" not in score_columns:
                connection.execute("ALTER TABLE article_scores ADD COLUMN delivery_classified INTEGER NOT NULL DEFAULT 1")
            if "finalized_at" not in score_columns:
                connection.execute("ALTER TABLE article_scores ADD COLUMN finalized_at TEXT")
            connection.execute("UPDATE article_scores SET analysis_completed=1,delivery_classified=CASE WHEN decision IN ('send','low') THEN 1 ELSE 0 END,finalized_at=COALESCE(finalized_at,updated_at)")
            run_columns = {row[1] for row in connection.execute("PRAGMA table_info(collection_runs)")}
            if "organization_id" not in run_columns:
                connection.execute(
                    "ALTER TABLE collection_runs ADD COLUMN organization_id TEXT REFERENCES organizations(id) ON DELETE SET NULL"
                )
            connection.execute(
                """INSERT OR IGNORE INTO llm_jobs(
                   id,article_id,case_id,case_version,organization_id,status,queued_at,started_at,finished_at
                   ) SELECT 'legacy-' || id,article_id,case_id,case_version,NULL,'completed',created_at,created_at,updated_at
                     FROM article_scores"""
            )
            connection.execute(
                """UPDATE article_scores SET organization_tag=COALESCE((
                       SELECT o.name FROM cases c JOIN organizations o ON o.id=c.organization_id
                       WHERE c.id=article_scores.case_id
                   ),'')"""
            )
            self._migrate_legacy_scores(connection)
            self._backfill_article_source_metadata(connection)
            self._sync_article_processing_flags(connection)
            self._discard_pre_case_pending_evaluations(connection)
        self.path.chmod(0o600)

    @staticmethod
    def _backfill_case_sort_order(connection: sqlite3.Connection) -> int:
        if connection.execute("SELECT value FROM app_settings WHERE key='case_sort_order_v1'").fetchone():
            return 0
        rows = connection.execute(
            "SELECT id,COALESCE(organization_id,'') organization_id FROM cases ORDER BY COALESCE(organization_id,''),created_at,rowid"
        ).fetchall()
        count = 0
        current_org, index = None, 0
        for row in rows:
            organization_id = str(row["organization_id"] or "")
            if organization_id != current_org:
                current_org, index = organization_id, 0
            index += 1
            connection.execute("UPDATE cases SET sort_order=? WHERE id=?", (index * 10, row["id"]))
            count += 1
        connection.execute(
            "INSERT INTO app_settings(key,value,updated_at) VALUES('case_sort_order_v1','applied',?)",
            (now_iso(),),
        )
        return count

    @staticmethod
    def _backfill_article_source_metadata(connection: sqlite3.Connection) -> int:
        if connection.execute("SELECT value FROM app_settings WHERE key='article_source_metadata_v1'").fetchone():
            return 0
        rows = connection.execute(
            """SELECT aa.id,a.publisher,a.original_url,a.title,a.snippet,a.body
               FROM article_analyses aa JOIN articles a ON a.id=aa.article_id"""
        ).fetchall()
        for row in rows:
            source_text = " ".join([str(row["title"] or ""), str(row["snippet"] or ""), str(row["body"] or "")])
            connection.execute(
                "UPDATE article_analyses SET publisher_name=?,reporter_name=? WHERE id=?",
                (publisher_name(row["publisher"], row["original_url"]), reporter_name(source_text), row["id"]),
            )
        connection.execute(
            "INSERT INTO app_settings(key,value,updated_at) VALUES('article_source_metadata_v1','applied',?)",
            (now_iso(),),
        )
        return len(rows)

    @staticmethod
    def _discard_pre_case_pending_evaluations(connection: sqlite3.Connection) -> int:
        """Remove unfinished automatic work for articles collected before a case existed."""
        rows = connection.execute(
            """SELECT ce.id FROM case_evaluations ce
               JOIN cases c ON c.id=ce.case_id
               JOIN articles a ON a.id=ce.article_id
               WHERE a.first_seen_at < COALESCE(NULLIF(c.monitor_from,''),c.created_at)
                 AND ce.status IN ('pending','processing','failed')"""
        ).fetchall()
        evaluation_ids = [str(row["id"]) for row in rows]
        if not evaluation_ids:
            return 0
        marks = ",".join("?" for _ in evaluation_ids)
        connection.execute(
            f"DELETE FROM article_case_processing_flags WHERE evaluation_id IN ({marks})",
            evaluation_ids,
        )
        connection.execute(
            f"DELETE FROM case_evaluations WHERE id IN ({marks})",
            evaluation_ids,
        )
        return len(evaluation_ids)

    def _migrate_legacy_scores(self, connection: sqlite3.Connection) -> None:
        """Keep old completed case scores visible in the article-first dashboard without any new LLM call."""
        rows = connection.execute(
            """SELECT s.*,a.content_hash,a.title,a.snippet,a.body,c.organization_id
               FROM article_scores s JOIN articles a ON a.id=s.article_id
               LEFT JOIN cases c ON c.id=s.case_id ORDER BY s.updated_at DESC"""
        ).fetchall()
        analyses: dict[str, str] = {}
        for row in rows:
            item = dict(row)
            article_id = str(item["article_id"])
            fallback = str(item.get("title") or "") + str(item.get("snippet") or "") + str(item.get("body") or "")
            key = str(item.get("content_hash") or hashlib.sha256(fallback.encode("utf-8")).hexdigest())[:128]
            analysis_id = analyses.get(article_id)
            if not analysis_id:
                analysis_id = "legacy-common-" + hashlib.sha256((article_id + key).encode("utf-8")).hexdigest()[:24]
                analyses[article_id] = analysis_id
                connection.execute(
                    """INSERT OR IGNORE INTO article_analyses(
                       id,article_id,organization_id,content_key,status,model,prompt_version,summary,article_type,tone,classification_tags,analysis_report,analyzed_at,created_at,updated_at
                    ) VALUES(?,?,?,?, 'completed','legacy','legacy-v0',?,?,?,?,?,?,?,?)""",
                    (analysis_id, article_id, item.get("organization_id"), key, item.get("summary") or "", item.get("article_type") or "기타", item.get("tone") or "사실전달", item.get("classification_tags") or "[]", item.get("analysis_report") or "{}", item.get("updated_at"), item.get("created_at"), item.get("updated_at")),
                )
                existing_analysis = connection.execute("SELECT id FROM article_analyses WHERE article_id=? AND content_key=?", (article_id, key)).fetchone()
                analysis_id = str(existing_analysis["id"])
                analyses[article_id] = analysis_id
            evaluation_id = "legacy-case-" + hashlib.sha256((analysis_id + str(item["case_id"]) + str(item.get("case_version") or 1)).encode("utf-8")).hexdigest()[:24]
            connection.execute(
                """INSERT OR IGNORE INTO case_evaluations(
                   id,article_analysis_id,article_id,case_id,case_version,candidate_status,status,model,keyword_score,semantic_score,llm_score,final_score,evidence_status,reasons,matched_terms,low_score_categories,analysis_report,decision,completed_at,created_at,updated_at
                ) VALUES(?,?,?,?,?,'legacy','completed','legacy',?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (evaluation_id, analysis_id, article_id, item["case_id"], item.get("case_version") or 1, item.get("keyword_score") or 0, item.get("semantic_score") or 0, item.get("llm_score") or 0, item.get("final_score") or 0, item.get("evidence_status") or "", item.get("reasons") or "[]", item.get("matched_terms") or "[]", item.get("low_score_categories") or "[]", item.get("analysis_report") or "{}", item.get("decision") or "low", item.get("finalized_at") or item.get("updated_at"), item.get("created_at"), item.get("updated_at")),
            )

    def _migrate_article_case_flag_schema(self, connection: sqlite3.Connection) -> None:
        """Replace the short-lived analysis-keyed flag table while retaining it as an audit backup."""
        columns = {row[1] for row in connection.execute("PRAGMA table_info(article_case_processing_flags)")}
        if not columns or "article_id" in columns:
            return
        backup = "article_case_processing_flags_legacy_v1"
        existing = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (backup,)
        ).fetchone()
        if existing:
            backup = "article_case_processing_flags_legacy_v1_retry"
        connection.execute(f"ALTER TABLE article_case_processing_flags RENAME TO {backup}")
        connection.execute(
            """CREATE TABLE article_case_processing_flags (
                 article_id TEXT NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
                 case_id TEXT NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
                 analysis_id TEXT NOT NULL,
                 evaluation_id TEXT NOT NULL,
                 case_version INTEGER NOT NULL,
                 common_analysis_completed INTEGER NOT NULL DEFAULT 1,
                 case_evaluation_completed INTEGER NOT NULL DEFAULT 0,
                 delivery_classified INTEGER NOT NULL DEFAULT 0,
                 created_at TEXT NOT NULL,
                 updated_at TEXT NOT NULL,
                 PRIMARY KEY(article_id, case_id)
               )"""
        )

    def _sync_article_processing_flags(self, connection: sqlite3.Connection) -> None:
        """Backfill durable one-time flags by article and by article/case."""
        marker = connection.execute("SELECT value FROM app_settings WHERE key='article_processing_flags_sync_v1'").fetchone()
        if marker:
            freshness = connection.execute(
                "SELECT "
                "MAX((SELECT MAX(updated_at) FROM article_analyses),(SELECT MAX(updated_at) FROM case_evaluations)) source_latest, "
                "MAX((SELECT MAX(updated_at) FROM article_processing_flags),(SELECT MAX(updated_at) FROM article_case_processing_flags)) flag_latest"
            ).fetchone()
            if str(freshness["source_latest"] or "") <= str(freshness["flag_latest"] or ""):
                return
        if not marker:
            existing = connection.execute(
                "SELECT (SELECT COUNT(*) FROM article_processing_flags) article_flags, "
                "(SELECT COUNT(*) FROM article_case_processing_flags) case_flags"
            ).fetchone()
            if int(existing["article_flags"] or 0) and int(existing["case_flags"] or 0):
                connection.execute(
                    """INSERT INTO app_settings(key,value,updated_at) VALUES('article_processing_flags_sync_v1','existing',?)
                       ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at""",
                    (now_iso(),),
                )
                return
        connection.execute(
            """INSERT INTO article_processing_flags(article_id,analysis_id,common_analysis_completed,created_at,updated_at)
               SELECT aa.article_id,aa.id,CASE WHEN aa.status='completed' THEN 1 ELSE 0 END,aa.created_at,aa.updated_at
               FROM article_analyses aa
               WHERE aa.id=(
                   SELECT aa2.id FROM article_analyses aa2 WHERE aa2.article_id=aa.article_id
                   ORDER BY CASE WHEN aa2.status='completed' THEN 0 ELSE 1 END,
                            COALESCE(aa2.analyzed_at,aa2.updated_at) DESC,aa2.id DESC LIMIT 1
               )
               ON CONFLICT(article_id) DO UPDATE SET
                   analysis_id=excluded.analysis_id,
                   common_analysis_completed=MAX(article_processing_flags.common_analysis_completed,excluded.common_analysis_completed),
                   updated_at=MAX(article_processing_flags.updated_at,excluded.updated_at)"""
        )
        connection.execute(
            """INSERT INTO article_case_processing_flags(
                   article_id,case_id,analysis_id,evaluation_id,case_version,
                   common_analysis_completed,case_evaluation_completed,delivery_classified,created_at,updated_at
               )
               SELECT ce.article_id,ce.case_id,ce.article_analysis_id,ce.id,ce.case_version,
                      CASE WHEN aa.status='completed' THEN 1 ELSE 0 END,
                      CASE WHEN ce.status IN ('completed','excluded') THEN 1 ELSE 0 END,
                      CASE WHEN ce.decision IN ('send','low','excluded') THEN 1 ELSE 0 END,
                      ce.created_at,ce.updated_at
               FROM case_evaluations ce JOIN article_analyses aa ON aa.id=ce.article_analysis_id
               WHERE ce.id=(
                   SELECT ce2.id FROM case_evaluations ce2
                   WHERE ce2.article_id=ce.article_id AND ce2.case_id=ce.case_id
                   ORDER BY ce2.case_version DESC,
                            CASE WHEN ce2.status IN ('completed','excluded') THEN 0 ELSE 1 END,
                            ce2.updated_at DESC,ce2.id DESC LIMIT 1
               )
               ON CONFLICT(article_id,case_id) DO UPDATE SET
                   analysis_id=excluded.analysis_id,evaluation_id=excluded.evaluation_id,
                   case_version=MAX(article_case_processing_flags.case_version,excluded.case_version),
                   common_analysis_completed=MAX(article_case_processing_flags.common_analysis_completed,excluded.common_analysis_completed),
                   case_evaluation_completed=MAX(article_case_processing_flags.case_evaluation_completed,excluded.case_evaluation_completed),
                   delivery_classified=MAX(article_case_processing_flags.delivery_classified,excluded.delivery_classified),
                   updated_at=MAX(article_case_processing_flags.updated_at,excluded.updated_at)"""
        )
        connection.execute(
            """INSERT INTO app_settings(key,value,updated_at) VALUES('article_processing_flags_sync_v1','completed',?)
               ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at""",
            (now_iso(),),
        )

    def ensure_magazine_schema(self) -> None:
        if self._magazine_schema_ready:
            return
        with self.connect() as connection:
            row = connection.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='magazine_editions'").fetchone()
            definition = str(row["sql"] or "") if row else ""
            if definition and "'daily'" not in definition:
                connection.execute("PRAGMA foreign_keys=OFF")
                connection.execute("ALTER TABLE magazine_issue_members RENAME TO magazine_issue_members_legacy")
                connection.execute("ALTER TABLE magazine_editions RENAME TO magazine_editions_legacy")
                connection.executescript("CREATE TABLE magazine_editions (id TEXT PRIMARY KEY,organization_id TEXT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,organization_name TEXT NOT NULL DEFAULT '',edition_date TEXT NOT NULL,edition_slot TEXT NOT NULL CHECK(edition_slot IN ('morning','lunch','evening','daily')),window_start_at TEXT NOT NULL,window_end_at TEXT NOT NULL,case_catalog TEXT NOT NULL DEFAULT '[]',issue_count INTEGER NOT NULL DEFAULT 0,article_count INTEGER NOT NULL DEFAULT 0,status TEXT NOT NULL DEFAULT 'published',generated_at TEXT NOT NULL,updated_at TEXT NOT NULL,UNIQUE(organization_id,edition_date,edition_slot));\nCREATE TABLE magazine_issue_members (edition_id TEXT NOT NULL REFERENCES magazine_editions(id) ON DELETE CASCADE,article_id TEXT NOT NULL,issue_key TEXT NOT NULL,rank INTEGER NOT NULL DEFAULT 0,title TEXT NOT NULL DEFAULT '',summary TEXT NOT NULL DEFAULT '',publisher TEXT NOT NULL DEFAULT '',tone TEXT NOT NULL DEFAULT '사실전달',article_type TEXT NOT NULL DEFAULT '기타',published_at TEXT,original_url TEXT NOT NULL DEFAULT '',image_url TEXT NOT NULL DEFAULT '',case_matches TEXT NOT NULL DEFAULT '[]',related_press_releases TEXT NOT NULL DEFAULT '[]',created_at TEXT NOT NULL,PRIMARY KEY(edition_id,article_id));")
                connection.execute("INSERT INTO magazine_editions SELECT * FROM magazine_editions_legacy")
                connection.execute("INSERT INTO magazine_issue_members SELECT * FROM magazine_issue_members_legacy")
                connection.execute("DROP TABLE magazine_issue_members_legacy")
                connection.execute("DROP TABLE magazine_editions_legacy")
                connection.execute("CREATE INDEX IF NOT EXISTS idx_magazine_editions_org_date ON magazine_editions(organization_id,edition_date DESC,edition_slot)")
                connection.execute("CREATE INDEX IF NOT EXISTS idx_magazine_members_issue ON magazine_issue_members(edition_id,issue_key,rank)")
                connection.execute("PRAGMA foreign_keys=ON")
            connection.executescript(MAGAZINE_EXTENSION_SCHEMA)
            edition_columns = {row[1] for row in connection.execute("PRAGMA table_info(magazine_editions)")}
            if "daily_topics" not in edition_columns:
                connection.execute("ALTER TABLE magazine_editions ADD COLUMN daily_topics TEXT NOT NULL DEFAULT '[]'")
            # Early snapshots were written while image_url was appended to the
            # table; their final four values are shifted by one column. This
            # scans historical snapshots, so retain a one-time repair marker.
            repaired = connection.execute("SELECT 1 FROM app_settings WHERE key='magazine_member_columns_repaired_v1'").fetchone()
            if not repaired:
                connection.execute(
                    "UPDATE magazine_issue_members SET image_url=created_at,case_matches=image_url,related_press_releases=case_matches,created_at=related_press_releases WHERE image_url LIKE '[%' AND case_matches LIKE '[%' AND related_press_releases GLOB '????-??-??T*'"
                )
                connection.execute("INSERT INTO app_settings(key,value,updated_at) VALUES('magazine_member_columns_repaired_v1','1',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at", (now_iso(),))
        self._magazine_schema_ready = True

    def ensure_shadow_case_schema(self) -> None:
        with self.connect() as connection:
            connection.executescript(SHADOW_CASE_SCHEMA)

    def shadow_disagreements(self, limit: int = 50) -> dict[str, Any]:
        """Read-only review list; never participates in delivery or worker queues."""
        limit = max(1, min(100, int(limit)))
        with self.connect() as connection:
            total = connection.execute("SELECT COUNT(*) value FROM shadow_case_evaluations s LEFT JOIN shadow_case_feedback f ON f.shadow_case_evaluation_id=s.id WHERE s.status='completed' AND s.decision_match=0 AND f.shadow_case_evaluation_id IS NULL").fetchone()["value"]
            rows = connection.execute(
                """SELECT s.id,s.queued_at,s.completed_at,s.primary_model,s.shadow_model,s.primary_decision,s.shadow_decision,
                          s.primary_final_score,s.shadow_final_score,s.primary_llm_score,s.shadow_llm_score,s.duration_ms,
                          a.title,a.original_url,c.name case_name,ce.reasons,ce.low_score_categories,ce.evidence_status,f.verdict feedback_verdict,f.reason feedback_reason,f.comment feedback_comment,f.updated_at feedback_updated_at
                   FROM shadow_case_evaluations s
                   JOIN case_evaluations ce ON ce.id=s.case_evaluation_id
                   JOIN articles a ON a.id=ce.article_id
                   JOIN cases c ON c.id=ce.case_id
                   LEFT JOIN shadow_case_feedback f ON f.shadow_case_evaluation_id=s.id
                   WHERE s.status='completed' AND s.decision_match=0 AND f.shadow_case_evaluation_id IS NULL
                   ORDER BY s.queued_at DESC LIMIT ?""", (limit,)
            ).fetchall()
        items = []
        for row in rows:
            item = dict(row)
            item["score_gap"] = round(float(item.get("shadow_final_score") or 0) - float(item.get("primary_final_score") or 0), 1)
            item["priority"] = "high" if abs(float(item["score_gap"])) >= 15 else "normal"
            item["reasons"] = json_value(item.get("reasons"), [])
            item["low_score_categories"] = json_value(item.get("low_score_categories"), [])
            items.append(item)
        return {"total": int(total or 0), "items": items}

    def shadow_feedback_history(self, limit: int = 100) -> dict[str, Any]:
        """Text-only record of completed shadow reviews."""
        limit = max(1, min(200, int(limit)))
        with self.connect() as connection:
            total = connection.execute("SELECT COUNT(*) value FROM shadow_case_feedback").fetchone()["value"]
            rows = connection.execute(
                """SELECT f.verdict,f.reason,f.comment,f.updated_at,c.name case_name,a.title,a.original_url
                   FROM shadow_case_feedback f
                   JOIN shadow_case_evaluations s ON s.id=f.shadow_case_evaluation_id
                   JOIN case_evaluations ce ON ce.id=s.case_evaluation_id
                   JOIN articles a ON a.id=ce.article_id JOIN cases c ON c.id=ce.case_id
                   ORDER BY f.updated_at DESC LIMIT ?""", (limit,)
            ).fetchall()
        return {"total": int(total or 0), "items": [dict(row) for row in rows]}

    def save_shadow_feedback(self, evaluation_id: str, verdict: str, reason: str = "", comment: str = "") -> dict[str, Any]:
        """Save an admin review only; it never changes a case decision or delivery."""
        evaluation_id = str(evaluation_id or "").strip()
        verdict = str(verdict or "").strip()
        reason = str(reason or "").strip()[:120]
        comment = str(comment or "").strip()[:1000]
        if verdict not in {"primary_correct", "shadow_correct", "uncertain"}:
            raise ValueError("검토 의견이 올바르지 않습니다.")
        with self.connect() as connection:
            exists = connection.execute("SELECT 1 FROM shadow_case_evaluations WHERE id=?", (evaluation_id,)).fetchone()
            if not exists:
                raise ValueError("그림자 판정 결과를 찾지 못했습니다.")
            now = now_iso()
            connection.execute(
                """INSERT INTO shadow_case_feedback(id,shadow_case_evaluation_id,verdict,reason,comment,created_at,updated_at)
                   VALUES(?,?,?,?,?,?,?)
                   ON CONFLICT(shadow_case_evaluation_id) DO UPDATE SET verdict=excluded.verdict,reason=excluded.reason,comment=excluded.comment,updated_at=excluded.updated_at""",
                (str(uuid.uuid4()), evaluation_id, verdict, reason, comment, now, now),
            )
            row = connection.execute(
                "SELECT verdict,reason,comment,updated_at FROM shadow_case_feedback WHERE shadow_case_evaluation_id=?", (evaluation_id,)
            ).fetchone()
        return dict(row)

    @contextmanager
    def connect(self):
        with self._lock:
            connection = sqlite3.connect(self.path, timeout=60)
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA busy_timeout=60000")
            try:
                yield connection
                connection.commit()
                # Local writes invalidate immediately; external worker writes are
                # detected through the database/WAL file marker on the next read.
                if connection.total_changes:
                    self._pipeline_summary_cache.clear()
            finally:
                connection.close()

    def _database_change_marker(self) -> tuple[int, int, int, int]:
        marker: list[int] = []
        for path in (self.path, self.path.with_name(self.path.name + "-wal")):
            try:
                state = path.stat()
                marker.extend((state.st_mtime_ns, state.st_size))
            except OSError:
                marker.extend((0, 0))
        return tuple(marker)  # type: ignore[return-value]

    def ensure_pipeline_lease_schema(self) -> None:
        """Install the small worker-lease migration even for fast, non-DDL store startup."""
        with self.connect() as connection:
            for table in ("article_analysis_jobs", "case_evaluation_jobs"):
                columns = {str(row[1]) for row in connection.execute(f"PRAGMA table_info({table})")}
                if "lease_owner" not in columns:
                    connection.execute(f"ALTER TABLE {table} ADD COLUMN lease_owner TEXT NOT NULL DEFAULT ''")
                if "lease_expires_at" not in columns:
                    connection.execute(f"ALTER TABLE {table} ADD COLUMN lease_expires_at TEXT")
                if "provider_lane" not in columns:
                    connection.execute(f"ALTER TABLE {table} ADD COLUMN provider_lane TEXT NOT NULL DEFAULT 'primary'")

    def _pipeline_summary_cache_get(self, key: tuple, change_marker: tuple[int, int, int, int]) -> dict | None:
        cached = self._pipeline_summary_cache.get(key)
        if not cached:
            return None
        expires_at, cached_marker, payload = cached
        if time.monotonic() >= expires_at or cached_marker != change_marker:
            self._pipeline_summary_cache.pop(key, None)
            return None
        return json.loads(json.dumps(payload, ensure_ascii=False))

    def _pipeline_summary_cache_set(self, key: tuple, change_marker: tuple[int, int, int, int], payload: dict) -> None:
        self._pipeline_summary_cache[key] = (
            time.monotonic() + self.PIPELINE_SUMMARY_CACHE_TTL_SECONDS,
            change_marker,
            json.loads(json.dumps(payload, ensure_ascii=False)),
        )

    @classmethod
    def decode_case(cls, row: sqlite3.Row | dict) -> dict:
        item = dict(row)
        for field, default in cls.CASE_JSON_FIELDS.items():
            item[field] = json_value(item.get(field), default)
        item["is_active"] = bool(item.get("is_active"))
        item["send_relevant_immediately"] = bool(item.get("send_relevant_immediately", 1))
        item["topic_search_prompt"] = item.get("topic_description", "")
        return item

    @classmethod
    def decode_organization(cls, row: sqlite3.Row | dict) -> dict:
        item = dict(row)
        for field, default in cls.ORGANIZATION_JSON_FIELDS.items():
            item[field] = json_value(item.get(field), default)
        item["is_active"] = bool(item.get("is_active"))
        return item

    def list_organizations(self, active_only: bool = False) -> list[dict]:
        query = "SELECT * FROM organizations"
        clauses = ["archived_at IS NULL"]
        if active_only:
            clauses.append("is_active=1")
        query += " WHERE " + " AND ".join(clauses) + " ORDER BY name"
        with self.connect() as connection:
            return [self.decode_organization(row) for row in connection.execute(query)]

    def get_organization(self, organization_id: str) -> dict | None:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM organizations WHERE id=?", (organization_id,)).fetchone()
        return self.decode_organization(row) if row else None

    def save_organization(self, payload: dict, organization_id: str | None = None) -> dict:
        now = now_iso()
        existing = self.get_organization(organization_id) if organization_id else None
        name = str(payload.get("name") or (existing or {}).get("name") or "").strip()[:100]
        if not name:
            raise ValueError("기관명을 입력하세요.")
        values: dict[str, Any] = {
            "name": name,
            "collection_mode": payload.get("collection_mode", (existing or {}).get("collection_mode", "interval")),
            "collection_interval_minutes": max(1, min(1440, int(payload.get("collection_interval_minutes", (existing or {}).get("collection_interval_minutes", 30))))),
            "max_search_queries": max(1, min(20, int(payload.get("max_search_queries", (existing or {}).get("max_search_queries", 8))))),
            "max_articles_per_run": max(1, min(200, int(payload.get("max_articles_per_run", (existing or {}).get("max_articles_per_run", 50))))),
            "is_active": 1 if payload.get("is_active", (existing or {}).get("is_active", True)) else 0,
            "archived_at": None,
        }
        if values["collection_mode"] not in {"interval", "times"}:
            raise ValueError("올바르지 않은 수집 방식입니다.")
        for field, default in self.ORGANIZATION_JSON_FIELDS.items():
            raw = payload.get(field, (existing or {}).get(field, default))
            clean = raw if isinstance(raw, list) else default
            values[field] = json.dumps(list(dict.fromkeys(str(item).strip()[:200] for item in clean if str(item).strip())), ensure_ascii=False)
        collection_times = normalized_clock_values(json_value(values["collection_times"], []))
        values["collection_times"] = json.dumps(collection_times, ensure_ascii=False)
        if values["collection_mode"] == "times" and not collection_times:
            raise ValueError("지정 시각 수집에는 올바른 HH:MM 시각이 하나 이상 필요합니다.")
        organization_id = organization_id or str(uuid.uuid4())
        with self.connect() as connection:
            if existing:
                assignments = ",".join(f"{key}=?" for key in values)
                connection.execute(
                    f"UPDATE organizations SET {assignments},updated_at=? WHERE id=?",
                    (*values.values(), now, organization_id),
                )
            else:
                columns = ["id", *values, "created_at", "updated_at"]
                marks = ",".join("?" for _ in columns)
                connection.execute(
                    f"INSERT INTO organizations ({','.join(columns)}) VALUES ({marks})",
                    (organization_id, *values.values(), now, now),
                )
            connection.execute(
                "UPDATE article_scores SET organization_tag=?,updated_at=? WHERE case_id IN (SELECT id FROM cases WHERE organization_id=?)",
                (name, now, organization_id),
            )
        return self.get_organization(organization_id) or {}

    def archive_organization(self, organization_id: str) -> bool:
        now = now_iso()
        with self.connect() as connection:
            cursor = connection.execute(
                "UPDATE organizations SET is_active=0,archived_at=?,updated_at=? WHERE id=? AND archived_at IS NULL",
                (now, now, organization_id),
            )
        return cursor.rowcount > 0


    def list_cases(self, active_only: bool = False) -> list[dict]:
        query = "SELECT * FROM cases"
        if active_only:
            query += " WHERE is_active=1"
        query += " ORDER BY COALESCE(organization_id,''),sort_order,created_at"
        with self.connect() as connection:
            return [self.decode_case(row) for row in connection.execute(query)]

    def list_cases_for_organization(self, organization_id: str, active_only: bool = True) -> list[dict]:
        query = "SELECT * FROM cases WHERE organization_id=?"
        if active_only:
            query += " AND is_active=1"
        query += " ORDER BY sort_order,created_at"
        with self.connect() as connection:
            return [self.decode_case(row) for row in connection.execute(query, (organization_id,))]


    def get_case(self, case_id: str) -> dict | None:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM cases WHERE id=?", (case_id,)).fetchone()
        return self.decode_case(row) if row else None

    def save_case(self, payload: dict, case_id: str | None = None) -> dict:
        now = now_iso()
        existing = self.get_case(case_id) if case_id else None
        organization_id = str(payload.get("organization_id", (existing or {}).get("organization_id") or "")).strip() or None
        if organization_id and not self.get_organization(organization_id):
            raise ValueError("연결할 기관을 찾지 못했습니다.")
        if not organization_id and self.list_organizations():
            raise ValueError("사용 기관을 선택하세요.")
        values: dict[str, Any] = {
            "organization_id": organization_id,
            "name": str(payload.get("name") or (existing or {}).get("name") or "새 케이스").strip()[:80],
            "topic_description": str(payload.get("topic_search_prompt", payload.get("topic_description", (existing or {}).get("topic_description", "")))).strip()[:4000],
            "collection_mode": payload.get("collection_mode", (existing or {}).get("collection_mode", "interval")),
            "collection_interval_minutes": max(1, min(1440, int(payload.get("collection_interval_minutes", (existing or {}).get("collection_interval_minutes", 30))))),
            "delivery_mode": payload.get("delivery_mode", (existing or {}).get("delivery_mode", "immediate")),
            "send_relevant_immediately": 1 if payload.get(
                "send_relevant_immediately", (existing or {}).get("send_relevant_immediately", True)
            ) else 0,
            "relevance_threshold": max(0, min(100, float(payload.get("relevance_threshold", (existing or {}).get("relevance_threshold", 70))))),
            "hold_threshold": max(0, min(100, float(payload.get("hold_threshold", (existing or {}).get("hold_threshold", 55))))),
            "keyword_weight": max(0, float(payload.get("keyword_weight", (existing or {}).get("keyword_weight", 0)))),
            "semantic_weight": max(0, float(payload.get("semantic_weight", (existing or {}).get("semantic_weight", 0.25)))),
            "llm_weight": max(0, float(payload.get("llm_weight", (existing or {}).get("llm_weight", 0.75)))),
            "max_articles_per_message": max(1, min(5, int(payload.get("max_articles_per_message", (existing or {}).get("max_articles_per_message", 2))))),
            "is_active": 1 if payload.get("is_active", (existing or {}).get("is_active", True)) else 0,
        }
        if existing:
            values["sort_order"] = int(payload.get("sort_order", existing.get("sort_order") or 0))
        if values["collection_mode"] not in {"interval", "times"}:
            raise ValueError("올바르지 않은 수집 방식입니다.")
        if values["delivery_mode"] not in {"immediate", "times"}:
            raise ValueError("올바르지 않은 발송 방식입니다.")
        for field, default in self.CASE_JSON_FIELDS.items():
            raw = payload.get(field, (existing or {}).get(field, default))
            values[field] = json.dumps(raw if isinstance(raw, type(default)) else default, ensure_ascii=False)

        collection_times = normalized_clock_values(json_value(values["collection_times"], []))
        delivery_times = normalized_clock_values(json_value(values["delivery_times"], []))
        values["collection_times"] = json.dumps(collection_times, ensure_ascii=False)
        values["delivery_times"] = json.dumps(delivery_times, ensure_ascii=False)
        if values["collection_mode"] == "times" and not collection_times:
            raise ValueError("지정 시각 수집에는 올바른 HH:MM 시각이 하나 이상 필요합니다.")
        if values["delivery_mode"] == "times" and not delivery_times:
            raise ValueError("지정 시각 발송에는 올바른 HH:MM 시각이 하나 이상 필요합니다.")
        if values["hold_threshold"] > values["relevance_threshold"]:
            raise ValueError("보류 기준은 전송 기준보다 높을 수 없습니다.")

        weight_total = values["semantic_weight"] + values["llm_weight"]
        if weight_total <= 0:
            raise ValueError("관련도 가중치 합은 0보다 커야 합니다.")
        case_id = case_id or str(uuid.uuid4())
        version = int((existing or {}).get("version", 0)) + 1
        with self._lock, self.connect() as connection:
            if not existing:
                row = connection.execute(
                    "SELECT COALESCE(MAX(sort_order),0) value FROM cases WHERE COALESCE(organization_id,'')=COALESCE(?, '')",
                    (organization_id,),
                ).fetchone()
                values["sort_order"] = int(row["value"] or 0) + 10
            if existing:
                assignments = ",".join(f"{key}=?" for key in values)
                connection.execute(
                    f"UPDATE cases SET {assignments},version=?,updated_at=? WHERE id=?",
                    (*values.values(), version, now, case_id),
                )
            else:
                columns = ["id", *values, "version", "monitor_from", "created_at", "updated_at"]
                marks = ",".join("?" for _ in columns)
                connection.execute(
                    f"INSERT INTO cases ({','.join(columns)}) VALUES ({marks})",
                    (case_id, *values.values(), version, now, now, now),
                )
            row = connection.execute("SELECT * FROM cases WHERE id=?", (case_id,)).fetchone()
            snapshot = self.decode_case(row) if row else {"id": case_id, **values, "version": version}
            connection.execute(
                "INSERT OR REPLACE INTO case_versions(case_id,version,snapshot,created_at) VALUES(?,?,?,?)",
                (case_id, version, json.dumps(snapshot, ensure_ascii=False, default=str), now),
            )
            organization_name = ""
            if organization_id:
                organization = connection.execute(
                    "SELECT name FROM organizations WHERE id=?", (organization_id,)
                ).fetchone()
                organization_name = str(organization["name"] or "") if organization else ""
            connection.execute(
                "UPDATE article_scores SET organization_tag=?,updated_at=? WHERE case_id=?",
                (organization_name, now, case_id),
            )
        return self.get_case(case_id) or {}

    def delete_case(self, case_id: str) -> bool:
        with self.connect() as connection:
            cursor = connection.execute("DELETE FROM cases WHERE id=?", (case_id,))
            return cursor.rowcount > 0

    def reorder_cases(self, organization_id: str, case_ids: Iterable[str]) -> list[dict]:
        ordered_ids = [str(value).strip() for value in case_ids if str(value).strip()]
        if not ordered_ids:
            raise ValueError("정렬할 케이스가 없습니다.")
        unique_ids = list(dict.fromkeys(ordered_ids))
        if len(unique_ids) != len(ordered_ids):
            raise ValueError("중복된 케이스가 포함되어 있습니다.")
        now = now_iso()
        with self._lock, self.connect() as connection:
            rows = connection.execute(
                "SELECT id FROM cases WHERE organization_id=? ORDER BY sort_order,created_at",
                (organization_id,),
            ).fetchall()
            existing_ids = [str(row["id"]) for row in rows]
            if set(unique_ids) != set(existing_ids):
                raise ValueError("해당 기관의 전체 케이스 순서를 보내야 합니다.")
            for index, case_id in enumerate(unique_ids, start=1):
                connection.execute(
                    "UPDATE cases SET sort_order=?,updated_at=? WHERE id=? AND organization_id=?",
                    (index * 10, now, case_id, organization_id),
                )
        return self.list_cases_for_organization(organization_id, active_only=False)

    def set_case_recipients(self, case_id: str, recipient_ids: Iterable[str]) -> None:
        with self.connect() as connection:
            connection.execute("DELETE FROM case_recipients WHERE case_id=?", (case_id,))
            connection.executemany(
                "INSERT INTO case_recipients(case_id,recipient_id) VALUES(?,?)",
                [(case_id, value) for value in dict.fromkeys(recipient_ids)],
            )

    def case_recipient_ids(self, case_id: str) -> list[str]:
        with self.connect() as connection:
            return [row[0] for row in connection.execute("SELECT recipient_id FROM case_recipients WHERE case_id=?", (case_id,))]

    def list_recipients(self) -> list[dict]:
        with self.connect() as connection:
            self._cleanup_expired_signup_requests(connection)
            rows = connection.execute(
                "SELECT id,label,kakao_user_id,access_token_expires_at,refresh_token_expires_at,status,last_error,created_at,updated_at FROM recipients WHERE status<>'deleted' ORDER BY created_at DESC"
            ).fetchall()
        return [dict(row) for row in rows]

    def mark_recipient_reauthorize(self, recipient_id: str, message: str) -> None:
        with self.connect() as connection:
            connection.execute(
                "UPDATE recipients SET status='reauthorize',last_error=?,updated_at=? WHERE id=?",
                (str(message)[:500], now_iso(), str(recipient_id)),
            )
            connection.execute(
                """UPDATE deliveries SET status='failed',attempts=3,response_code=403,last_error=?,updated_at=?
                   WHERE recipient_id=? AND status IN ('pending','retry')""",
                (str(message)[:500], now_iso(), str(recipient_id)),
            )

    @staticmethod
    def mask_applicant_name(value: str) -> str:
        name = re.sub(r"\s+", "", str(value or "").strip())
        if not name:
            return "신청자"
        if len(name) == 1:
            return "*"
        if len(name) == 2:
            return name[0] + "*"
        return name[0] + "*" * (len(name) - 2) + name[-1]

    def _signup_request_cases(self, connection: sqlite3.Connection, request_id: str) -> list[dict]:
        rows = connection.execute(
            """SELECT src.case_id,src.status,src.decided_at,c.name case_name,c.organization_id,c.is_active
               FROM signup_request_cases src JOIN cases c ON c.id=src.case_id
               WHERE src.request_id=? ORDER BY c.created_at""",
            (request_id,),
        ).fetchall()
        return [{**dict(row), "is_active": bool(row["is_active"])} for row in rows]

    def _signup_request_magazine_slots(self, connection: sqlite3.Connection, request_id: str) -> list[str]:
        return [str(row["edition_slot"]) for row in connection.execute(
            "SELECT edition_slot FROM signup_request_magazine_slots WHERE request_id=? ORDER BY CASE edition_slot WHEN 'morning' THEN 1 WHEN 'lunch' THEN 2 WHEN 'evening' THEN 3 ELSE 4 END", (request_id,)
        ).fetchall()]

    def _decode_signup_request(self, connection: sqlite3.Connection, row: sqlite3.Row | dict, include_private: bool = False) -> dict:
        item = dict(row)
        magazine_slots = self._signup_request_magazine_slots(connection, str(item["id"]))
        cases = self._signup_request_cases(connection, str(item["id"]))
        result = {
            "id": item["id"],
            "masked_name": self.mask_applicant_name(str(item.get("applicant_name") or "")),
            "organization_id": item.get("organization_id"),
            "organization_name": item.get("organization_name") or "",
            "status": item.get("status") or "requested",
            "kakao_registered": bool(item.get("recipient_id")),
            "kakao_registered_at": item.get("kakao_registered_at"),
            "case_requests": cases,
            "magazine_slots": magazine_slots,
            "admin_note": item.get("admin_note") or "",
            "created_at": item.get("created_at"),
            "updated_at": item.get("updated_at"),
        }
        if include_private:
            result.update({
                "applicant_name": item.get("applicant_name") or "",
                "recipient_id": item.get("recipient_id"),
                "invite_id": item.get("invite_id"),
            })
        return result

    def list_signup_requests(self, include_private: bool = False, limit: int = 80) -> list[dict]:
        with self.connect() as connection:
            self._cleanup_expired_signup_requests(connection)
            rows = connection.execute(
                """SELECT sr.*,o.name organization_name
                   FROM signup_requests sr JOIN organizations o ON o.id=sr.organization_id
                   ORDER BY sr.created_at DESC LIMIT ?""",
                (max(1, min(int(limit), 200)),),
            ).fetchall()
            return [self._decode_signup_request(connection, row, include_private) for row in rows]

    def _cleanup_expired_signup_requests(self, connection: sqlite3.Connection, hours: int = 6) -> int:
        cutoff = (datetime.now(KST) - timedelta(hours=max(1, int(hours)))).isoformat(timespec="seconds")
        expired = connection.execute(
            """DELETE FROM signup_requests
               WHERE status IN ('approved','partial','rejected','revoked')
                 AND COALESCE(decided_at,updated_at,created_at) < ?""",
            (cutoff,),
        ).rowcount or 0
        orphaned = connection.execute(
            """DELETE FROM signup_requests
               WHERE recipient_id IS NULL AND kakao_registered_at IS NOT NULL"""
        ).rowcount or 0
        return int(expired + orphaned)

    def create_signup_request(self, applicant_name: str, organization_id: str, case_ids: Iterable[str], ttl_minutes: int = 1440, recipient_id: str = "", magazine_slots: Iterable[str] = ()) -> tuple[dict, str]:
        self.ensure_magazine_schema()
        name = re.sub(r"\s+", " ", str(applicant_name or "").strip())[:80]
        if not name:
            raise ValueError("신청자 이름을 입력하세요.")
        organization = self.get_organization(str(organization_id or ""))
        if not organization or not organization.get("is_active"):
            raise ValueError("활성화된 부처를 선택하세요.")
        requested_case_ids = [str(value) for value in dict.fromkeys(case_ids) if str(value).strip()]
        requested_magazine_slots = [str(value).strip() for value in dict.fromkeys(magazine_slots) if str(value).strip()]
        invalid_slots = set(requested_magazine_slots) - {"morning", "lunch", "evening", "daily"}
        if invalid_slots:
            raise ValueError("선택한 매거진 에디션이 올바르지 않습니다.")
        if requested_magazine_slots and not requested_case_ids:
            raise ValueError("매거진 구독은 주요뉴스를 고를 케이스를 하나 이상 선택해야 합니다.")
        active_cases = {
            item["id"]: item for item in self.list_cases_for_organization(organization["id"], active_only=True)
        }
        invalid = [case_id for case_id in requested_case_ids if case_id not in active_cases]
        if invalid:
            raise ValueError("선택한 부처의 활성 케이스만 신청할 수 있습니다.")
        now, request_id = now_iso(), str(uuid.uuid4())
        recipient_id = str(recipient_id or "").strip()
        invite, token = self.create_invite(name, ttl_minutes)
        with self.connect() as connection:
            if recipient_id:
                recipient = connection.execute(
                    "SELECT id,status FROM recipients WHERE id=? AND status<>'deleted'",
                    (recipient_id,),
                ).fetchone()
                if not recipient:
                    raise ValueError("카카오 메시지 동의 상태를 먼저 확인하세요.")
                connection.execute("UPDATE recipient_invites SET used_at=COALESCE(used_at,?) WHERE id=?", (now, invite["id"]))
                connection.execute("UPDATE recipients SET label=?,updated_at=? WHERE id=?", (name, now, recipient_id))
            connection.execute(
                """INSERT INTO signup_requests(
                   id,invite_id,recipient_id,applicant_name,organization_id,status,kakao_registered_at,created_at,updated_at
                   ) VALUES(?,?,?,?,?,?,?,?,?)""",
                (request_id, invite["id"], recipient_id or None, name, organization["id"], "kakao_registered" if recipient_id else "requested", now if recipient_id else None, now, now),
            )
            connection.executemany(
                "INSERT INTO signup_request_cases(request_id,case_id,status,updated_at) VALUES(?,?, 'pending',?)",
                [(request_id, case_id, now) for case_id in requested_case_ids],
            )
            connection.executemany(
                "INSERT INTO signup_request_magazine_slots(request_id,edition_slot) VALUES(?,?)",
                [(request_id, slot) for slot in requested_magazine_slots],
            )
            row = connection.execute(
                """SELECT sr.*,o.name organization_name FROM signup_requests sr
                   JOIN organizations o ON o.id=sr.organization_id WHERE sr.id=?""",
                (request_id,),
            ).fetchone()
            record = self._decode_signup_request(connection, row, include_private=False)
        if recipient_id and self.signup_auto_approve_enabled():
            record = self.approve_signup_request(request_id, "자동 승인")
        return record, "" if recipient_id else token

    def mark_signup_request_kakao_registered(self, token: str, recipient_id: str) -> dict | None:
        token_hash, now = hashlib.sha256(str(token).encode()).hexdigest(), now_iso()
        request_id = ""
        with self.connect() as connection:
            row = connection.execute(
                """SELECT sr.id FROM signup_requests sr JOIN recipient_invites ri ON ri.id=sr.invite_id
                   WHERE ri.token_hash=?""",
                (token_hash,),
            ).fetchone()
            if not row:
                return None
            request_id = str(row["id"])
            connection.execute(
                """UPDATE signup_requests
                   SET recipient_id=?,status=CASE WHEN status='requested' THEN 'kakao_registered' ELSE status END,
                       kakao_registered_at=COALESCE(kakao_registered_at,?),updated_at=?
                   WHERE id=?""",
                (recipient_id, now, now, request_id),
            )
            updated = connection.execute(
                """SELECT sr.*,o.name organization_name FROM signup_requests sr
                   JOIN organizations o ON o.id=sr.organization_id WHERE sr.id=?""",
                (request_id,),
            ).fetchone()
            result = self._decode_signup_request(connection, updated, include_private=True) if updated else None
        if result and self.signup_auto_approve_enabled():
            return self.approve_signup_request(request_id, "자동 승인")
        return result

    def delete_signup_request(self, request_id: str) -> bool:
        with self.connect() as connection:
            return connection.execute("DELETE FROM signup_requests WHERE id=?", (str(request_id),)).rowcount > 0

    def add_case_recipient(self, case_id: str, recipient_id: str) -> None:
        with self.connect() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO case_recipients(case_id,recipient_id) VALUES(?,?)",
                (case_id, recipient_id),
            )

    def _refresh_signup_request_status(self, connection: sqlite3.Connection, request_id: str, admin_note: str = "") -> sqlite3.Row:
        now = now_iso()
        request = connection.execute("SELECT * FROM signup_requests WHERE id=?", (request_id,)).fetchone()
        if not request:
            raise ValueError("구독 요청을 찾지 못했습니다.")
        counts = connection.execute(
            """SELECT SUM(CASE WHEN status='pending' THEN 1 ELSE 0 END) pending_count,
                      SUM(CASE WHEN status='approved' THEN 1 ELSE 0 END) approved_count,
                      SUM(CASE WHEN status='rejected' THEN 1 ELSE 0 END) rejected_count,
                      SUM(CASE WHEN status='revoked' THEN 1 ELSE 0 END) revoked_count,
                      COUNT(*) total_count
               FROM signup_request_cases WHERE request_id=?""",
            (request_id,),
        ).fetchone()
        pending = int(counts["pending_count"] or 0)
        approved = int(counts["approved_count"] or 0)
        rejected = int(counts["rejected_count"] or 0)
        revoked = int(counts["revoked_count"] or 0)
        total = int(counts["total_count"] or 0)
        if total == 0:
            status = "revoked" if request["recipient_id"] else "requested"
            decided_at = now if request["recipient_id"] else request["decided_at"]
        elif pending:
            status = "kakao_registered" if request["recipient_id"] else "requested"
            decided_at = request["decided_at"]
        elif approved == total:
            status, decided_at = "approved", now
        elif approved:
            status, decided_at = "partial", now
        elif revoked == total or revoked:
            status, decided_at = "revoked", now
        elif rejected == total:
            status, decided_at = "rejected", now
        else:
            status, decided_at = "rejected", now
        connection.execute(
            "UPDATE signup_requests SET status=?,admin_note=?,decided_at=?,updated_at=? WHERE id=?",
            (status, str(admin_note or "").strip()[:300], decided_at, now, request_id),
        )
        row = connection.execute(
            """SELECT sr.*,o.name organization_name FROM signup_requests sr
               JOIN organizations o ON o.id=sr.organization_id WHERE sr.id=?""",
            (request_id,),
        ).fetchone()
        if not row:
            raise ValueError("구독 요청을 찾지 못했습니다.")
        return row

    def signup_case_context(self, request_id: str, case_id: str) -> dict:
        with self.connect() as connection:
            row = connection.execute(
                """SELECT sr.*,o.name organization_name,c.name case_name,src.status case_status
                   FROM signup_requests sr
                   JOIN organizations o ON o.id=sr.organization_id
                   JOIN signup_request_cases src ON src.request_id=sr.id
                   JOIN cases c ON c.id=src.case_id
                   WHERE sr.id=? AND src.case_id=?""",
                (request_id, case_id),
            ).fetchone()
        if not row:
            raise ValueError("구독 요청 또는 케이스를 찾지 못했습니다.")
        return dict(row)

    def decide_signup_case(self, request_id: str, case_id: str, decision: str, admin_note: str = "") -> dict:
        decision = str(decision or "").strip()
        if decision not in {"approved", "rejected"}:
            raise ValueError("승인 또는 반려만 선택할 수 있습니다.")
        now = now_iso()
        with self.connect() as connection:
            request = connection.execute("SELECT * FROM signup_requests WHERE id=?", (request_id,)).fetchone()
            if not request:
                raise ValueError("구독 요청을 찾지 못했습니다.")
            case_row = connection.execute(
                "SELECT 1 FROM signup_request_cases WHERE request_id=? AND case_id=?",
                (request_id, case_id),
            ).fetchone()
            if not case_row:
                raise ValueError("신청한 케이스가 아닙니다.")
            if decision == "approved" and not request["recipient_id"]:
                raise ValueError("카카오 수신 등록이 완료된 신청만 승인할 수 있습니다.")
            connection.execute(
                """UPDATE signup_request_cases SET status=?,decided_at=?,updated_at=?
                   WHERE request_id=? AND case_id=?""",
                (decision, now, now, request_id, case_id),
            )
            if decision == "approved":
                connection.execute(
                    "INSERT OR IGNORE INTO case_recipients(case_id,recipient_id) VALUES(?,?)",
                    (case_id, request["recipient_id"]),
                )
            row = self._refresh_signup_request_status(connection, request_id, admin_note)
            self._sync_magazine_subscription(connection, request_id)
            return self._decode_signup_request(connection, row, include_private=True)

    def revoke_signup_case(self, request_id: str, case_id: str, admin_note: str = "") -> dict:
        now = now_iso()
        with self.connect() as connection:
            request = connection.execute("SELECT * FROM signup_requests WHERE id=?", (request_id,)).fetchone()
            if not request:
                raise ValueError("구독 요청을 찾지 못했습니다.")
            case_row = connection.execute(
                "SELECT status FROM signup_request_cases WHERE request_id=? AND case_id=?",
                (request_id, case_id),
            ).fetchone()
            if not case_row:
                raise ValueError("신청한 케이스가 아닙니다.")
            if case_row["status"] != "approved":
                raise ValueError("승인된 케이스만 해제할 수 있습니다.")
            if request["recipient_id"]:
                connection.execute(
                    "DELETE FROM case_recipients WHERE case_id=? AND recipient_id=?",
                    (case_id, request["recipient_id"]),
                )
            connection.execute(
                """UPDATE signup_request_cases SET status='revoked',decided_at=?,updated_at=?
                   WHERE request_id=? AND case_id=?""",
                (now, now, request_id, case_id),
            )
            row = self._refresh_signup_request_status(connection, request_id, admin_note)
            self._sync_magazine_subscription(connection, request_id)
            return self._decode_signup_request(connection, row, include_private=True)

    def _sync_magazine_subscription(self, connection: sqlite3.Connection, request_id: str) -> None:
        request = connection.execute("SELECT organization_id,recipient_id FROM signup_requests WHERE id=?", (request_id,)).fetchone()
        if not request or not request["recipient_id"]:
            return
        slots = self._signup_request_magazine_slots(connection, request_id)
        cases = [str(row["case_id"]) for row in connection.execute("SELECT case_id FROM signup_request_cases WHERE request_id=? AND status='approved'", (request_id,)).fetchall()]
        if slots and cases:
            connection.execute("INSERT INTO recipient_magazine_subscriptions(organization_id,recipient_id,edition_slots,case_ids,updated_at) VALUES(?,?,?,?,?) ON CONFLICT(organization_id,recipient_id) DO UPDATE SET edition_slots=excluded.edition_slots,case_ids=excluded.case_ids,updated_at=excluded.updated_at", (request["organization_id"], request["recipient_id"], json.dumps(slots), json.dumps(cases), now_iso()))
        else:
            connection.execute("DELETE FROM recipient_magazine_subscriptions WHERE organization_id=? AND recipient_id=?", (request["organization_id"], request["recipient_id"]))

    def set_signup_request_subscriptions(self, request_id: str, case_ids: Iterable[str], admin_note: str = "", magazine_slots: Iterable[str] | None = None) -> dict:
        self.ensure_magazine_schema()
        selected = {str(value).strip() for value in case_ids if str(value).strip()}
        selected_slots = None if magazine_slots is None else {
            str(value).strip() for value in magazine_slots if str(value).strip()
        }
        if selected_slots is not None:
            invalid_slots = selected_slots - {"morning", "lunch", "evening"}
            if invalid_slots:
                raise ValueError("선택한 매거진 알림이 올바르지 않습니다.")
            if selected_slots and not selected:
                raise ValueError("매거진 알림은 구독 케이스를 하나 이상 선택해야 합니다.")
        now = now_iso()
        with self.connect() as connection:
            request = connection.execute("SELECT * FROM signup_requests WHERE id=?", (request_id,)).fetchone()
            if not request:
                raise ValueError("구독 요청을 찾지 못했습니다.")
            active_rows = connection.execute(
                "SELECT id FROM cases WHERE organization_id=? AND is_active=1",
                (request["organization_id"],),
            ).fetchall()
            active_case_ids = {str(row["id"]) for row in active_rows}
            invalid = selected - active_case_ids
            if invalid:
                raise ValueError("선택한 부처의 활성 케이스만 구독할 수 있습니다.")
            existing_rows = connection.execute(
                "SELECT case_id,status FROM signup_request_cases WHERE request_id=?",
                (request_id,),
            ).fetchall()
            existing = {str(row["case_id"]): str(row["status"] or "pending") for row in existing_rows}
            recipient_id = str(request["recipient_id"] or "")
            for case_id in active_case_ids:
                if case_id in selected:
                    if case_id not in existing:
                        connection.execute(
                            "INSERT INTO signup_request_cases(request_id,case_id,status,updated_at) VALUES(?,?, 'pending',?)",
                            (request_id, case_id, now),
                        )
                    status = "approved" if recipient_id else "pending"
                    connection.execute(
                        "UPDATE signup_request_cases SET status=?,decided_at=?,updated_at=? WHERE request_id=? AND case_id=?",
                        (status, now if recipient_id else None, now, request_id, case_id),
                    )
                    if recipient_id:
                        connection.execute(
                            "INSERT OR IGNORE INTO case_recipients(case_id,recipient_id) VALUES(?,?)",
                            (case_id, recipient_id),
                        )
                elif recipient_id or case_id in existing:
                    if recipient_id:
                        connection.execute(
                            "DELETE FROM case_recipients WHERE case_id=? AND recipient_id=?",
                            (case_id, recipient_id),
                        )
                    status = "revoked" if recipient_id or existing.get(case_id) in {"approved", "revoked"} else "rejected"
                    if case_id not in existing:
                        connection.execute(
                            "INSERT INTO signup_request_cases(request_id,case_id,status,decided_at,updated_at) VALUES(?,?,?,?,?)",
                            (request_id, case_id, status, now, now),
                        )
                    else:
                        connection.execute(
                            "UPDATE signup_request_cases SET status=?,decided_at=?,updated_at=? WHERE request_id=? AND case_id=?",
                            (status, now, now, request_id, case_id),
                        )
            if selected_slots is not None:
                connection.execute("DELETE FROM signup_request_magazine_slots WHERE request_id=?", (request_id,))
                connection.executemany(
                    "INSERT INTO signup_request_magazine_slots(request_id,edition_slot) VALUES(?,?)",
                    [(request_id, slot) for slot in sorted(selected_slots)],
                )
            row = self._refresh_signup_request_status(connection, request_id, admin_note)
            self._sync_magazine_subscription(connection, request_id)
            return self._decode_signup_request(connection, row, include_private=True)

    def signup_auto_approve_enabled(self) -> bool:
        return self.get_setting("signup_auto_approve", "0").casefold() in {"1", "true", "on", "yes"}

    def approve_signup_request(self, request_id: str, admin_note: str = "") -> dict:
        self.ensure_magazine_schema()
        now = now_iso()
        with self.connect() as connection:
            request = connection.execute("SELECT * FROM signup_requests WHERE id=?", (request_id,)).fetchone()
            if not request:
                raise ValueError("구독 요청을 찾지 못했습니다.")
            recipient_id = str(request["recipient_id"] or "")
            if not recipient_id:
                raise ValueError("카카오 수신 등록이 완료된 신청만 승인할 수 있습니다.")
            pending = connection.execute(
                "SELECT case_id FROM signup_request_cases WHERE request_id=? AND status='pending'",
                (request_id,),
            ).fetchall()
            for row in pending:
                case_id = str(row["case_id"])
                connection.execute(
                    "UPDATE signup_request_cases SET status='approved',decided_at=?,updated_at=? WHERE request_id=? AND case_id=?",
                    (now, now, request_id, case_id),
                )
                connection.execute(
                    "INSERT OR IGNORE INTO case_recipients(case_id,recipient_id) VALUES(?,?)",
                    (case_id, recipient_id),
                )
            row = self._refresh_signup_request_status(connection, request_id, admin_note)
            self._sync_magazine_subscription(connection, request_id)
            return self._decode_signup_request(connection, row, include_private=True)

    def approve_all_pending_signup_requests(self, admin_note: str = "일괄 승인") -> dict:
        with self.connect() as connection:
            request_ids = [str(row["id"]) for row in connection.execute(
                """SELECT DISTINCT sr.id FROM signup_requests sr
                   JOIN signup_request_cases src ON src.request_id=sr.id AND src.status='pending'
                   WHERE sr.recipient_id IS NOT NULL AND sr.recipient_id<>''
                   ORDER BY sr.created_at"""
            ).fetchall()]
            skipped = int(connection.execute(
                """SELECT COUNT(DISTINCT sr.id) value FROM signup_requests sr
                   JOIN signup_request_cases src ON src.request_id=sr.id AND src.status='pending'
                   WHERE sr.recipient_id IS NULL OR sr.recipient_id=''"""
            ).fetchone()["value"] or 0)
        cases_approved = 0
        for request_id in request_ids:
            with self.connect() as connection:
                cases_approved += int(connection.execute(
                    "SELECT COUNT(*) value FROM signup_request_cases WHERE request_id=? AND status='pending'",
                    (request_id,),
                ).fetchone()["value"] or 0)
            self.approve_signup_request(request_id, admin_note)
        return {"requests_approved": len(request_ids), "cases_approved": cases_approved, "skipped_without_kakao": skipped}

    def get_setting(self, key: str, default: str = "") -> str:
        with self.connect() as connection:
            row = connection.execute("SELECT value FROM app_settings WHERE key=?", (key,)).fetchone()
        return str(row["value"]) if row else default

    def set_setting(self, key: str, value: str) -> None:
        with self.connect() as connection:
            connection.execute("INSERT INTO app_settings(key,value,updated_at) VALUES(?,?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at", (key, str(value), now_iso()))

    def set_settings(self, values: dict[str, Any]) -> None:
        if not values:
            return
        updated_at = now_iso()
        with self.connect() as connection:
            connection.executemany(
                "INSERT INTO app_settings(key,value,updated_at) VALUES(?,?,?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at",
                [(str(key), str(value), updated_at) for key, value in values.items()],
            )

    def claim_provider_quota_probe(self, provider: str, lease_seconds: int = 120) -> bool:
        """Allow one cross-process provider check after a quota lock expires."""
        provider = str(provider or "").strip().lower()
        if not provider:
            return False
        current = datetime.now(KST)
        current_iso = current.isoformat(timespec="seconds")
        lease_until = (current + timedelta(seconds=max(30, int(lease_seconds)))).isoformat(timespec="seconds")
        disabled_key = f"llm_provider_disabled_until:{provider}"
        probe_key = f"llm_provider_probe_until:{provider}"
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            disabled = connection.execute("SELECT value FROM app_settings WHERE key=?", (disabled_key,)).fetchone()
            disabled_until = str(disabled["value"] or "") if disabled else ""
            if not disabled_until:
                return True
            if disabled_until > current_iso:
                return False
            probe = connection.execute("SELECT value FROM app_settings WHERE key=?", (probe_key,)).fetchone()
            if probe and str(probe["value"] or "") > current_iso:
                return False
            connection.execute(
                "INSERT INTO app_settings(key,value,updated_at) VALUES(?,?,?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at",
                (probe_key, lease_until, current_iso),
            )
        return True

    def release_provider_quota_probe(self, provider: str) -> None:
        self.set_setting(f"llm_provider_probe_until:{str(provider or '').strip().lower()}", "")

    def increment_setting_counter(self, key: str, delta: int = 1) -> int:
        with self.connect() as connection:
            row = connection.execute("SELECT value FROM app_settings WHERE key=?", (key,)).fetchone()
            try:
                current = int(row["value"] or 0) if row else 0
            except (TypeError, ValueError):
                current = 0
            updated = current + int(delta)
            connection.execute(
                "INSERT INTO app_settings(key,value,updated_at) VALUES(?,?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at",
                (key, str(updated), now_iso()),
            )
        return updated


    def queue_supabase_outbox(self, table_name: str, rows: list[dict], conflict_key: str = "id") -> int:
        """Durably stage idempotent Supabase writes outside request handling."""
        if not table_name or not rows:
            return 0
        now = now_iso(); queued = 0
        with self.connect() as connection:
            for row in rows:
                item = dict(row or {})
                identifier = str(item.get(conflict_key) or item.get("id") or "")
                if not identifier:
                    continue
                event_id = f"{table_name}:{identifier}"
                payload = json.dumps(item, ensure_ascii=False, default=str, sort_keys=True, separators=(",", ":"))
                existing = connection.execute(
                    "SELECT payload FROM supabase_outbox WHERE id=?", (event_id,)
                ).fetchone()
                # A completed (or retry-delayed) event with identical content must
                # remain untouched. This lets source scans run safely without
                # turning already-sent data back into network work.
                if existing and str(existing["payload"]) == payload:
                    queued += 1
                    continue
                connection.execute(
                    """INSERT INTO supabase_outbox(id,table_name,conflict_key,payload,status,attempts,next_attempt_at,last_error,created_at,updated_at)
                       VALUES(?,?,?,?, 'pending',0,NULL,NULL,?,?)
                       ON CONFLICT(id) DO UPDATE SET table_name=excluded.table_name,conflict_key=excluded.conflict_key,payload=excluded.payload,
                         status='pending',next_attempt_at=NULL,last_error=NULL,updated_at=excluded.updated_at""",
                    (event_id, table_name, conflict_key, payload, now, now),
                )
                queued += 1
        return queued

    def due_supabase_outbox(self, limit: int = 100) -> list[dict]:
        with self.connect() as connection:
            rows = connection.execute(
                """SELECT * FROM supabase_outbox WHERE status='pending' AND COALESCE(next_attempt_at,'')<=?
                   ORDER BY CASE table_name
                       WHEN 'master_press_organizations' THEN 10
                       WHEN 'master_press_cases' THEN 20
                       WHEN 'master_press_articles' THEN 30
                       WHEN 'master_press_article_embeddings' THEN 35
                       WHEN 'master_press_scores' THEN 40
                       WHEN 'master_press_press_releases' THEN 50
                       WHEN 'master_press_press_release_chunks' THEN 60
                       WHEN 'master_press_article_press_matches' THEN 70
                       WHEN 'master_press_daily_metrics' THEN 80
                       WHEN 'master_press_daily_operations' THEN 81
                       WHEN 'master_press_daily_keyword_metrics' THEN 82
                       WHEN 'master_press_daily_model_metrics' THEN 83
                       ELSE 99 END,
                       created_at,id LIMIT ?""", (now_iso(), max(1, min(500, int(limit))))
            ).fetchall()
        return [dict(row) for row in rows]

    def finish_supabase_outbox(self, event_id: str, ok: bool, error: str = "", expected_payload: str | None = None,
                               retryable: bool = True) -> bool:
        """Record a send result, without overwriting a newer queued payload.

        On a confirmed remote write, release and relation source markers are
        advanced in the same local transaction. Other tables are represented
        entirely by the outbox event itself.
        """
        now = now_iso()
        with self.connect() as connection:
            row = connection.execute("SELECT attempts,payload,table_name FROM supabase_outbox WHERE id=?", (event_id,)).fetchone()
            if not row or (expected_payload is not None and str(row["payload"]) != expected_payload):
                return False
            attempts = int(row["attempts"] or 0) + 1
            if ok:
                try:
                    payload = json.loads(str(row["payload"]))
                except (TypeError, ValueError):
                    payload = {}
                if row["table_name"] == "master_press_press_releases" and payload.get("id"):
                    connection.execute("UPDATE press_releases SET supabase_synced_at=? WHERE id=?", (now, payload["id"]))
                elif row["table_name"] == "master_press_article_press_matches" and payload.get("article_id") and payload.get("press_release_id"):
                    connection.execute(
                        "UPDATE article_press_release_matches SET supabase_synced_at=? WHERE article_id=? AND press_release_id=?",
                        (now, payload["article_id"], payload["press_release_id"]),
                    )
                connection.execute("UPDATE supabase_outbox SET status='completed',attempts=?,next_attempt_at=NULL,last_error=NULL,updated_at=? WHERE id=?", (attempts, now, event_id))
            elif retryable:
                delay = min(24 * 60, 5 * (2 ** min(attempts - 1, 8)))
                retry_at = (datetime.now(KST) + timedelta(minutes=delay)).isoformat(timespec="seconds")
                connection.execute("UPDATE supabase_outbox SET status='pending',attempts=?,next_attempt_at=?,last_error=?,updated_at=? WHERE id=?", (attempts, retry_at, error[:1000], now, event_id))
            else:
                connection.execute("UPDATE supabase_outbox SET status='failed',attempts=?,next_attempt_at=NULL,last_error=?,updated_at=? WHERE id=?", (attempts, error[:1000], now, event_id))
        return True

    def recover_stalled_case_evaluation_jobs(self, max_age_seconds: int = 180) -> int:
        """Return abandoned case batches to the queue without restarting web."""
        cutoff = (datetime.now(KST) - timedelta(seconds=max(30, int(max_age_seconds)))).isoformat(timespec="seconds")
        now = now_iso()
        with self.connect() as connection:
            rows = connection.execute(
                """SELECT id,case_evaluation_id FROM case_evaluation_jobs
                   WHERE status='processing'
                     AND ((lease_expires_at IS NOT NULL AND lease_expires_at<=?)
                       OR (lease_expires_at IS NULL AND COALESCE(started_at,'')<=?))""",
                (now, cutoff),
            ).fetchall()
            if not rows:
                return 0
            job_ids = [str(row["id"]) for row in rows]
            evaluation_ids = [str(row["case_evaluation_id"]) for row in rows]
            job_marks = ",".join("?" for _ in job_ids)
            evaluation_marks = ",".join("?" for _ in evaluation_ids)
            connection.execute(
                f"UPDATE case_evaluation_jobs SET status='pending',started_at=NULL,finished_at=NULL,retry_after=NULL,"
                f"error='worker_stalled',lease_owner='',lease_expires_at=NULL WHERE id IN ({job_marks})",
                job_ids,
            )
            connection.execute(
                f"UPDATE case_evaluations SET status='pending',error='worker_stalled',updated_at=? WHERE id IN ({evaluation_marks})",
                (now, *evaluation_ids),
            )
        return len(job_ids)

    def recover_stalled_article_analysis_jobs(self, max_age_seconds: int = 180) -> dict[str, int]:
        """Requeue common-analysis jobs interrupted by a lock or lost worker."""
        cutoff = (datetime.now(KST) - timedelta(seconds=max(30, int(max_age_seconds)))).isoformat(timespec="seconds")
        now = now_iso()
        with self.connect() as connection:
            stalled = connection.execute(
                """UPDATE article_analysis_jobs
                   SET status='pending',started_at=NULL,finished_at=NULL,duration_ms=NULL,retry_after=NULL,
                       error='worker_stalled',lease_owner='',lease_expires_at=NULL
                   WHERE status='processing'
                     AND ((lease_expires_at IS NOT NULL AND lease_expires_at<=?)
                       OR (lease_expires_at IS NULL AND COALESCE(started_at,'')<=?))""",
                (now, cutoff),
            ).rowcount
            locked = connection.execute(
                "UPDATE article_analysis_jobs SET status='pending',started_at=NULL,finished_at=NULL,duration_ms=NULL,retry_after=NULL,error='database_locked_retry' WHERE status='failed' AND error='database is locked' AND attempts<3",
            ).rowcount
            if stalled or locked:
                connection.execute(
                    """UPDATE article_analyses SET status='pending',error=NULL,updated_at=?
                       WHERE id IN (SELECT article_analysis_id FROM article_analysis_jobs
                                    WHERE status='pending' AND error IN ('worker_stalled','database_locked_retry'))
                         AND status<>'completed'""",
                    (now,),
                )
        return {"stalled": int(stalled), "locked": int(locked)}

    def release_article_analysis_retries(self) -> dict[str, int]:
        """Make queued common-analysis work immediately eligible after an admin model switch."""
        now = now_iso()
        with self.connect() as connection:
            pending = connection.execute(
                "UPDATE article_analysis_jobs SET retry_after=NULL,error=NULL "
                "WHERE status='pending' AND (retry_after IS NOT NULL OR error IS NOT NULL)"
            ).rowcount
            failed = connection.execute(
                """UPDATE article_analysis_jobs
                   SET status='pending',attempts=0,started_at=NULL,finished_at=NULL,
                       duration_ms=NULL,retry_after=NULL,error=NULL
                   WHERE status='failed'
                     AND EXISTS (SELECT 1 FROM article_analyses aa
                                 WHERE aa.id=article_analysis_jobs.article_analysis_id
                                   AND aa.status<>'completed')"""
            ).rowcount
            if pending or failed:
                connection.execute(
                    """UPDATE article_analyses SET status='pending',error=NULL,updated_at=?
                       WHERE id IN (SELECT article_analysis_id FROM article_analysis_jobs WHERE status='pending')
                         AND status<>'completed'""",
                    (now,),
                )
        return {"pending_released": int(pending), "failed_requeued": int(failed)}

    def supabase_outbox_status(self) -> dict:
        with self.connect() as connection:
            rows = connection.execute("SELECT status,COUNT(*) value FROM supabase_outbox GROUP BY status").fetchall()
        return {str(row["status"]): int(row["value"] or 0) for row in rows}

    def pipeline_monitor_status(self) -> dict:
        """Small, read-only operational snapshot for the admin monitoring panel."""
        now = now_iso()
        day_start = kst_day_start_iso()
        with self.connect() as connection:
            last_run = connection.execute("SELECT * FROM collection_runs ORDER BY started_at DESC LIMIT 1").fetchone()
            last_success = connection.execute(
                "SELECT * FROM collection_runs WHERE status IN ('completed','completed_with_errors') ORDER BY finished_at DESC LIMIT 1"
            ).fetchone()
            last_article = connection.execute(
                "SELECT id,title,first_seen_at FROM articles ORDER BY first_seen_at DESC LIMIT 1"
            ).fetchone()
            due = connection.execute(
                "SELECT "
                "SUM(CASE WHEN organization_id IS NOT NULL THEN 1 ELSE 0 END) organizations,"
                "SUM(CASE WHEN organization_id IS NULL THEN 1 ELSE 0 END) cases "
                "FROM (SELECT id AS organization_id FROM organizations WHERE is_active=1 AND archived_at IS NULL AND (next_collect_at IS NULL OR next_collect_at<=?) "
                "UNION ALL SELECT NULL FROM cases WHERE is_active=1 AND organization_id IS NULL AND (next_collect_at IS NULL OR next_collect_at<=?))",
                (now, now),
            ).fetchone()
            running = connection.execute("SELECT COUNT(*) value FROM collection_runs WHERE status='running'").fetchone()
            failed = connection.execute("SELECT COUNT(*) value FROM collection_runs WHERE status='failed' AND started_at>=?", (day_start,)).fetchone()
            article_jobs = connection.execute("SELECT status,COUNT(*) value FROM article_analysis_jobs WHERE status IN ('pending','processing','failed') GROUP BY status").fetchall()
            case_jobs = connection.execute("SELECT status,COUNT(*) value FROM case_evaluation_jobs WHERE status IN ('pending','processing','failed') GROUP BY status").fetchall()
            outbox_rows = connection.execute("SELECT status,COUNT(*) value FROM supabase_outbox GROUP BY status").fetchall()

        def as_dict(row):
            return dict(row) if row else None

        def seconds_since(value: str) -> int | None:
            try:
                return max(0, int((datetime.now(KST) - datetime.fromisoformat(value.replace('Z', '+00:00')).astimezone(KST)).total_seconds()))
            except (AttributeError, TypeError, ValueError):
                return None

        def counts(rows):
            return {str(row['status']): int(row['value'] or 0) for row in rows}

        success = as_dict(last_success)
        latest_article = as_dict(last_article)
        return {
            "now": now,
            "last_run": as_dict(last_run),
            "last_success": success,
            "last_article": latest_article,
            "seconds_since_last_success": seconds_since(str((success or {}).get('finished_at') or '')),
            "seconds_since_last_article": seconds_since(str((latest_article or {}).get('first_seen_at') or '')),
            "due_organizations": int((due['organizations'] if due else 0) or 0),
            "due_cases": int((due['cases'] if due else 0) or 0),
            "running_collection_runs": int((running['value'] if running else 0) or 0),
            "failed_collection_runs_today": int((failed['value'] if failed else 0) or 0),
            "article_jobs": counts(article_jobs),
            "case_jobs": counts(case_jobs),
            "outbox": counts(outbox_rows),
        }

    def processing_summary(self, days: int = 7) -> dict:
        """Persist KST daily counts of distinct articles whose case judgments all finished."""
        days = max(7, min(90, int(days)))
        today = datetime.now(KST).date()
        first_day = today - timedelta(days=days - 1)
        with self.connect() as connection:
            rows = connection.execute("""WITH completed_articles AS (
                    SELECT aa.article_id,MAX(COALESCE(ce.completed_at,ce.updated_at)) completed_at
                    FROM article_processing_flags apf
                    JOIN article_analyses aa ON aa.id=apf.analysis_id AND aa.status='completed'
                    JOIN article_case_processing_flags acpf ON acpf.article_id=aa.article_id AND acpf.analysis_id=aa.id
                    JOIN cases c ON c.id=acpf.case_id AND c.is_active=1
                    JOIN case_evaluations ce ON ce.id=acpf.evaluation_id
                    GROUP BY aa.article_id
                    HAVING COUNT(*)>0 AND SUM(CASE WHEN ce.status IN ('completed','excluded') THEN 0 ELSE 1 END)=0
                )
                SELECT substr(completed_at,1,10) day,COUNT(*) article_count
                FROM completed_articles WHERE completed_at>=? GROUP BY substr(completed_at,1,10)""",
                (datetime.combine(first_day, datetime.min.time(), tzinfo=KST).isoformat(timespec="seconds"),)).fetchall()
            now = now_iso()
            counts = {str(row["day"]): int(row["article_count"] or 0) for row in rows if row["day"]}
            connection.executemany("""INSERT INTO processing_daily_stats(day,article_count,recorded_at) VALUES(?,?,?)
                ON CONFLICT(day) DO UPDATE SET article_count=excluded.article_count,recorded_at=excluded.recorded_at""",
                [((first_day + timedelta(days=offset)).isoformat(), counts.get((first_day + timedelta(days=offset)).isoformat(), 0), now) for offset in range(days)])
            saved = {str(row["day"]): int(row["article_count"] or 0) for row in connection.execute(
                "SELECT day,article_count FROM processing_daily_stats WHERE day>=? ORDER BY day", (first_day.isoformat(),)).fetchall()}
            total = int(connection.execute("""WITH completed_articles AS (
                    SELECT aa.article_id
                    FROM article_processing_flags apf
                    JOIN article_analyses aa ON aa.id=apf.analysis_id AND aa.status='completed'
                    JOIN article_case_processing_flags acpf ON acpf.article_id=aa.article_id AND acpf.analysis_id=aa.id
                    JOIN cases c ON c.id=acpf.case_id AND c.is_active=1
                    JOIN case_evaluations ce ON ce.id=acpf.evaluation_id
                    GROUP BY aa.article_id
                    HAVING COUNT(*)>0 AND SUM(CASE WHEN ce.status IN ('completed','excluded') THEN 0 ELSE 1 END)=0
                ) SELECT COUNT(*) value FROM completed_articles""").fetchone()["value"] or 0)
        daily = [{"day": (first_day + timedelta(days=offset)).isoformat(), "article_count": int(saved.get((first_day + timedelta(days=offset)).isoformat(), 0))} for offset in range(days)]
        recent_week = daily[-7:]
        week_total = sum(item["article_count"] for item in recent_week)
        return {"total": total, "week": week_total, "week_average": round(week_total / 7, 1),
                "yesterday": int(saved.get((today - timedelta(days=1)).isoformat(), 0)), "today": int(saved.get(today.isoformat(), 0)), "daily": daily}

    def supabase_outbox_pending_for_tables(self, table_names: list[str]) -> int:
        names = [str(name) for name in table_names if str(name)]
        if not names:
            return 0
        placeholders = ",".join("?" for _ in names)
        with self.connect() as connection:
            row = connection.execute(
                f"SELECT COUNT(*) value FROM supabase_outbox WHERE status='pending' AND table_name IN ({placeholders})", names
            ).fetchone()
        return int(row["value"] or 0)

    def record_llm_api_call(self, provider: str, stage: str, model: str, status: str, duration_ms: int = 0,
                            http_status: int | None = None, request_id: str = "", input_tokens: int = 0,
                            output_tokens: int = 0, usage_units: int = 0, error: str = "") -> None:
        with self.connect() as connection:
            connection.execute(
                """INSERT INTO llm_api_calls(id,provider,stage,model,status,http_status,request_id,input_tokens,output_tokens,usage_units,duration_ms,error,created_at)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (str(uuid.uuid4()), str(provider)[:30], str(stage)[:30], str(model)[:160], str(status)[:30], http_status,
                 str(request_id)[:200] or None, max(0, int(input_tokens)), max(0, int(output_tokens)), max(0, int(usage_units)), max(0, int(duration_ms)),
                 str(error)[:1000] or None, now_iso()),
            )

    def provider_usage_total(self, provider: str, stage: str) -> dict:
        with self.connect() as connection:
            row = connection.execute(
                """SELECT COUNT(*) attempts,
                          SUM(CASE WHEN status='completed' THEN 1 ELSE 0 END) completed,
                          SUM(CASE WHEN status='failed' THEN 1 ELSE 0 END) failed,
                          COALESCE(SUM(input_tokens),0) input_tokens,COALESCE(SUM(output_tokens),0) output_tokens,
                          COALESCE(AVG(CASE WHEN status='completed' THEN duration_ms END),0) average_ms
                   FROM llm_api_calls WHERE provider=? AND stage=?""",
                (str(provider), str(stage)),
            ).fetchone()
        tokens = int(row["input_tokens"] or 0) + int(row["output_tokens"] or 0)
        return {
            "attempts": int(row["attempts"] or 0), "completed": int(row["completed"] or 0),
            "failed": int(row["failed"] or 0), "input_tokens": int(row["input_tokens"] or 0),
            "output_tokens": int(row["output_tokens"] or 0), "tokens": tokens,
            "average_seconds": round(float(row["average_ms"] or 0) / 1000.0, 2), "period": "all",
        }

    def provider_usage_today(self, provider: str, stage: str, request_limit: int, token_limit: int = 0) -> dict:
        day_start = kst_day_start_iso()
        with self.connect() as connection:
            row = connection.execute(
                """SELECT COUNT(*) attempts,
                          SUM(CASE WHEN status='completed' THEN 1 ELSE 0 END) completed,
                          SUM(CASE WHEN status='failed' THEN 1 ELSE 0 END) failed,
                          COALESCE(SUM(input_tokens),0) input_tokens,COALESCE(SUM(output_tokens),0) output_tokens,
                          COALESCE(AVG(CASE WHEN status='completed' THEN duration_ms END),0) average_ms
                   FROM llm_api_calls WHERE provider=? AND stage=? AND created_at>=?""",
                (str(provider), str(stage), day_start),
            ).fetchone()
        attempts = int(row["attempts"] or 0)
        tokens = int(row["input_tokens"] or 0) + int(row["output_tokens"] or 0)
        return {
            "attempts": attempts, "completed": int(row["completed"] or 0), "failed": int(row["failed"] or 0),
            "input_tokens": int(row["input_tokens"] or 0), "output_tokens": int(row["output_tokens"] or 0),
            "tokens": tokens, "average_seconds": round(float(row["average_ms"] or 0) / 1000.0, 2),
            "soft_limit": int(request_limit), "remaining": max(0, int(request_limit) - attempts),
            "token_soft_limit": int(token_limit), "token_remaining": max(0, int(token_limit) - tokens) if token_limit else 0,
            "period": "KST day", "day_start": day_start,
        }

    def provider_usage_last_minute(self, provider: str, stage: str) -> dict:
        since = (datetime.now(KST) - timedelta(seconds=60)).isoformat(timespec="seconds")
        with self.connect() as connection:
            row = connection.execute(
                """SELECT COUNT(*) attempts,COALESCE(SUM(input_tokens),0)+COALESCE(SUM(output_tokens),0) tokens
                   FROM llm_api_calls WHERE provider=? AND stage=? AND created_at>=?""",
                (str(provider), str(stage), since),
            ).fetchone()
        return {"attempts": int(row["attempts"] or 0), "tokens": int(row["tokens"] or 0), "since": since}

    def provider_usage_since(self, provider: str, since: str, request_limit: int = 0, token_limit: int = 0, stage: str = "") -> dict:
        query = """SELECT COUNT(*) attempts,
                          SUM(CASE WHEN status='completed' THEN 1 ELSE 0 END) completed,
                          SUM(CASE WHEN status='failed' THEN 1 ELSE 0 END) failed,
                          COALESCE(SUM(input_tokens),0) input_tokens,COALESCE(SUM(output_tokens),0) output_tokens,COALESCE(SUM(usage_units),0) usage_units,
                          COALESCE(AVG(CASE WHEN status='completed' THEN duration_ms END),0) average_ms
                   FROM llm_api_calls WHERE provider=? AND created_at>=?"""
        params: list[Any] = [str(provider), str(since)]
        if stage:
            query += " AND stage=?"
            params.append(str(stage))
        with self.connect() as connection:
            row = connection.execute(query, tuple(params)).fetchone()
        attempts = int(row["attempts"] or 0)
        tokens = int(row["input_tokens"] or 0) + int(row["output_tokens"] or 0)
        return {
            "attempts": attempts, "completed": int(row["completed"] or 0), "failed": int(row["failed"] or 0),
            "input_tokens": int(row["input_tokens"] or 0), "output_tokens": int(row["output_tokens"] or 0),
            "tokens": tokens, "usage_units": int(row["usage_units"] or 0), "average_seconds": round(float(row["average_ms"] or 0) / 1000.0, 2),
            "soft_limit": int(request_limit or 0), "remaining": max(0, int(request_limit or 0) - attempts) if request_limit else 0,
            "token_soft_limit": int(token_limit or 0), "token_remaining": max(0, int(token_limit or 0) - tokens) if token_limit else 0,
            "period": "custom", "day_start": str(since), "scope": "provider_total" if not stage else "provider_stage",
        }

    def openrouter_usage_today(self, soft_limit: int = 800) -> dict:
        day_start = utc_day_start_kst_iso()
        with self.connect() as connection:
            row = connection.execute(
                """SELECT COUNT(*) attempts,
                          SUM(CASE WHEN status='completed' THEN 1 ELSE 0 END) completed,
                          SUM(CASE WHEN status='failed' THEN 1 ELSE 0 END) failed,
                          COALESCE(SUM(input_tokens),0) input_tokens,COALESCE(SUM(output_tokens),0) output_tokens,
                          COALESCE(AVG(CASE WHEN status='completed' THEN duration_ms END),0) average_ms
                   FROM llm_api_calls WHERE provider='openrouter' AND created_at>=?""",
                (day_start,),
            ).fetchone()
        attempts = int(row["attempts"] or 0)
        tokens = int(row["input_tokens"] or 0) + int(row["output_tokens"] or 0)
        return {
            "attempts": attempts, "completed": int(row["completed"] or 0), "failed": int(row["failed"] or 0),
            "input_tokens": int(row["input_tokens"] or 0), "output_tokens": int(row["output_tokens"] or 0),
            "tokens": tokens, "average_seconds": round(float(row["average_ms"] or 0) / 1000.0, 2),
            "soft_limit": int(soft_limit), "remaining": max(0, int(soft_limit) - attempts),
            "token_soft_limit": 0, "token_remaining": 0,
            "period": "UTC day", "day_start": day_start, "scope": "provider_total",
        }

    def groq_usage_today(self, request_limit: int = 900, token_limit: int = 650000) -> dict:
        return self.provider_usage_today("groq", "common", request_limit, token_limit)


    def list_announcements(self, include_inactive: bool = False) -> list[dict]:
        where = "" if include_inactive else "WHERE is_active=1"
        with self.connect() as connection:
            rows = connection.execute(
                f"SELECT * FROM announcements {where} ORDER BY created_at DESC LIMIT 50"
            ).fetchall()
        return [dict(row) for row in rows]

    def current_announcements(self, reference: datetime | None = None) -> list[dict]:
        now = (reference.astimezone(KST) if reference else datetime.now(KST)).isoformat(timespec="seconds")
        with self.connect() as connection:
            rows = connection.execute(
                """SELECT * FROM announcements
                   WHERE is_active=1 AND (starts_at='' OR starts_at<=?) AND (ends_at='' OR ends_at>=?)
                   ORDER BY created_at DESC LIMIT 3""",
                (now, now),
            ).fetchall()
        return [dict(row) for row in rows]

    def save_announcement(self, payload: dict, announcement_id: str = "") -> dict:
        now = now_iso()
        item_id = str(announcement_id or payload.get("id") or uuid.uuid4())
        title = str(payload.get("title") or "").strip()[:120]
        body = str(payload.get("body") or "").strip()[:2000]
        starts_at = str(payload.get("starts_at") or "").strip()[:40]
        ends_at = str(payload.get("ends_at") or "").strip()[:40]
        if re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$", starts_at):
            starts_at += ":00+09:00"
        if re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$", ends_at):
            ends_at += ":59+09:00"
        is_active = 1 if payload.get("is_active", True) is not False else 0
        if not title and not body:
            raise ValueError("공지 제목 또는 내용을 입력하세요.")
        with self.connect() as connection:
            connection.execute(
                """INSERT INTO announcements(id,title,body,starts_at,ends_at,is_active,created_at,updated_at)
                   VALUES(?,?,?,?,?,?,?,?)
                   ON CONFLICT(id) DO UPDATE SET title=excluded.title,body=excluded.body,starts_at=excluded.starts_at,
                     ends_at=excluded.ends_at,is_active=excluded.is_active,updated_at=excluded.updated_at""",
                (item_id, title, body, starts_at, ends_at, is_active, now, now),
            )
            row = connection.execute("SELECT * FROM announcements WHERE id=?", (item_id,)).fetchone()
        return dict(row)

    def delete_announcement(self, announcement_id: str, hard: bool = False) -> bool:
        with self.connect() as connection:
            if hard:
                return connection.execute("DELETE FROM announcements WHERE id=?", (str(announcement_id),)).rowcount > 0
            return connection.execute("UPDATE announcements SET is_active=0,updated_at=? WHERE id=?", (now_iso(), str(announcement_id))).rowcount > 0

    @staticmethod
    def _case_proposal_terms(value: Any) -> list[str]:
        if isinstance(value, str):
            try:
                loaded = json.loads(value)
                if isinstance(loaded, list):
                    value = loaded
                else:
                    value = re.split(r"[\n,]", value)
            except json.JSONDecodeError:
                value = re.split(r"[\n,]", value)
        return [str(item).strip()[:80] for item in (value or []) if str(item).strip()][:30]

    @staticmethod
    def _case_proposal_password_hash(password: str, salt: str) -> str:
        return hashlib.sha256((str(salt) + ":" + str(password or "")).encode("utf-8")).hexdigest()

    def _decode_case_proposal(self, row: sqlite3.Row | dict, admin: bool = False) -> dict:
        item = dict(row)
        include_terms = self._case_proposal_terms(item.get("include_terms"))
        required_terms = self._case_proposal_terms(item.get("required_terms"))
        flagged = bool(item.get("moderation_flagged")) and not bool(item.get("moderation_exempt"))
        result = {
            "id": item.get("id"),
            "nickname": item.get("nickname") or "익명",
            "title": "클린 AI에 의해서 블라인드 처리되었습니다." if flagged and not admin else item.get("title", ""),
            "prompt": "" if flagged and not admin else item.get("prompt", ""),
            "include_terms": [] if flagged and not admin else include_terms,
            "required_terms": [] if flagged and not admin else required_terms,
            "content_locked": bool(flagged and not admin),
            "moderation_status": item.get("moderation_status") or "pending",
            "moderation_flagged": bool(item.get("moderation_flagged")),
            "moderation_exempt": bool(item.get("moderation_exempt")),
            "created_at": item.get("created_at"),
            "updated_at": item.get("updated_at"),
        }
        if admin:
            result.update({
                "original_title": item.get("title", ""),
                "original_prompt": item.get("prompt", ""),
                "original_include_terms": include_terms,
                "original_required_terms": required_terms,
                "moderation_reason": item.get("moderation_reason") or "",
                "moderation_model": item.get("moderation_model") or "",
                "moderated_at": item.get("moderated_at"),
            })
        return result

    def list_case_proposals(self, admin: bool = False, limit: int = 80) -> list[dict]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM case_proposals ORDER BY created_at DESC LIMIT ?",
                (max(1, min(int(limit), 200)),),
            ).fetchall()
        return [self._decode_case_proposal(row, admin=admin) for row in rows]

    def get_case_proposal(self, proposal_id: str, admin: bool = False) -> dict | None:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM case_proposals WHERE id=?", (str(proposal_id),)).fetchone()
        return self._decode_case_proposal(row, admin=admin) if row else None

    def save_case_proposal(self, payload: dict, proposal_id: str = "", password_required: bool = False) -> dict:
        now = now_iso()
        title = str(payload.get("title") or "").strip()[:120]
        prompt = str(payload.get("prompt") or "").strip()[:4000]
        nickname = str(payload.get("nickname") or "익명").strip()[:40] or "익명"
        include_terms = self._case_proposal_terms(payload.get("include_terms"))
        required_terms = self._case_proposal_terms(payload.get("required_terms"))
        password = str(payload.get("password") or "")
        new_password = str(payload.get("new_password") or "")
        if not title:
            raise ValueError("케이스 제목을 입력하세요.")
        if not prompt:
            raise ValueError("케이스 프롬프트를 입력하세요.")
        if not proposal_id and len(password) < 4:
            raise ValueError("수정·삭제용 암호는 4자 이상 입력하세요.")
        with self.connect() as connection:
            if proposal_id:
                row = connection.execute("SELECT * FROM case_proposals WHERE id=?", (str(proposal_id),)).fetchone()
                if not row:
                    raise ValueError("케이스 신청 글을 찾지 못했습니다.")
                if password_required:
                    expected = self._case_proposal_password_hash(password, row["password_salt"])
                    if not password or not secrets.compare_digest(expected, row["password_hash"]):
                        raise ValueError("암호가 일치하지 않습니다.")
                salt = row["password_salt"]
                password_hash = row["password_hash"]
                if new_password:
                    if len(new_password) < 4:
                        raise ValueError("새 암호는 4자 이상 입력하세요.")
                    salt = secrets.token_hex(8)
                    password_hash = self._case_proposal_password_hash(new_password, salt)
                connection.execute(
                    """UPDATE case_proposals
                       SET nickname=?,title=?,prompt=?,include_terms=?,required_terms=?,password_salt=?,password_hash=?,
                           moderation_status='pending',moderation_flagged=0,moderation_exempt=0,moderation_reason='',moderation_model='',moderated_at=NULL,updated_at=?
                       WHERE id=?""",
                    (nickname, title, prompt, json.dumps(include_terms, ensure_ascii=False), json.dumps(required_terms, ensure_ascii=False), salt, password_hash, now, str(proposal_id)),
                )
                item_id = str(proposal_id)
            else:
                item_id = str(uuid.uuid4())
                salt = secrets.token_hex(8)
                password_hash = self._case_proposal_password_hash(password, salt)
                connection.execute(
                    """INSERT INTO case_proposals(id,nickname,password_salt,password_hash,title,prompt,include_terms,required_terms,created_at,updated_at)
                       VALUES(?,?,?,?,?,?,?,?,?,?)""",
                    (item_id, nickname, salt, password_hash, title, prompt, json.dumps(include_terms, ensure_ascii=False), json.dumps(required_terms, ensure_ascii=False), now, now),
                )
            row = connection.execute("SELECT * FROM case_proposals WHERE id=?", (item_id,)).fetchone()
        return self._decode_case_proposal(row, admin=True)

    def delete_case_proposal(self, proposal_id: str, password: str) -> bool:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM case_proposals WHERE id=?", (str(proposal_id),)).fetchone()
            if not row:
                return False
            expected = self._case_proposal_password_hash(str(password or ""), row["password_salt"])
            if not password or not secrets.compare_digest(expected, row["password_hash"]):
                raise ValueError("암호가 일치하지 않습니다.")
            return connection.execute("DELETE FROM case_proposals WHERE id=?", (str(proposal_id),)).rowcount > 0

    def next_case_proposal_for_moderation(self) -> dict | None:
        with self.connect() as connection:
            row = connection.execute(
                """SELECT * FROM case_proposals
                   WHERE moderation_status='pending' AND moderation_exempt=0
                   ORDER BY updated_at ASC LIMIT 1"""
            ).fetchone()
        return self._decode_case_proposal(row, admin=True) if row else None

    def finish_case_proposal_moderation(self, proposal_id: str, flagged: bool, reason: str = "", model: str = "") -> dict | None:
        status = "blocked" if flagged else "clean"
        with self.connect() as connection:
            connection.execute(
                """UPDATE case_proposals SET moderation_status=?,moderation_flagged=?,moderation_reason=?,moderation_model=?,moderated_at=?,updated_at=?
                   WHERE id=? AND moderation_status='pending' AND moderation_exempt=0""",
                (status, 1 if flagged else 0, str(reason or "")[:500], str(model or "")[:120], now_iso(), now_iso(), str(proposal_id)),
            )
            row = connection.execute("SELECT * FROM case_proposals WHERE id=?", (str(proposal_id),)).fetchone()
        return self._decode_case_proposal(row, admin=True) if row else None

    def allow_case_proposal(self, proposal_id: str) -> dict | None:
        with self.connect() as connection:
            connection.execute(
                """UPDATE case_proposals SET moderation_status='allowed',moderation_flagged=0,moderation_exempt=1,
                   moderation_reason='',moderated_at=?,updated_at=? WHERE id=?""",
                (now_iso(), now_iso(), str(proposal_id)),
            )
            row = connection.execute("SELECT * FROM case_proposals WHERE id=?", (str(proposal_id),)).fetchone()
        return self._decode_case_proposal(row, admin=True) if row else None

    def get_article(self, article_id: str) -> dict | None:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM articles WHERE id=?", (article_id,)).fetchone()
        return dict(row) if row else None

    def get_recipient(self, recipient_id: str, include_tokens: bool = False) -> dict | None:
        fields = "*" if include_tokens else "id,label,kakao_user_id,access_token_expires_at,refresh_token_expires_at,scopes,status,last_error,created_at,updated_at"
        with self.connect() as connection:
            row = connection.execute(f"SELECT {fields} FROM recipients WHERE id=?", (recipient_id,)).fetchone()
        return dict(row) if row else None

    def create_invite(self, label: str, ttl_minutes: int = 60) -> tuple[dict, str]:
        token = secrets.token_urlsafe(32)
        now = datetime.now(KST)
        record = {
            "id": str(uuid.uuid4()),
            "label": str(label or "카카오 수신자").strip()[:80],
            "expires_at": (now + timedelta(minutes=max(5, min(ttl_minutes, 1440)))).isoformat(timespec="seconds"),
            "created_at": now.isoformat(timespec="seconds"),
        }
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO recipient_invites(id,token_hash,label,expires_at,created_at) VALUES(?,?,?,?,?)",
                (record["id"], hashlib.sha256(token.encode()).hexdigest(), record["label"], record["expires_at"], record["created_at"]),
            )
        return record, token

    def valid_invite(self, token: str) -> dict | None:
        token_hash = hashlib.sha256(str(token).encode()).hexdigest()
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM recipient_invites WHERE token_hash=? AND used_at IS NULL AND expires_at>?",
                (token_hash, now_iso()),
            ).fetchone()
        return dict(row) if row else None

    def consume_invite(self, token: str, token_data: dict) -> dict:
        invite = self.valid_invite(token)
        if not invite:
            raise ValueError("수신자 등록 링크가 만료되었거나 이미 사용되었습니다.")
        now = now_iso()
        recipient_id = str(uuid.uuid4())
        with self.connect() as connection:
            connection.execute(
                """INSERT INTO recipients(
                   id,label,kakao_user_id,access_token_ciphertext,refresh_token_ciphertext,
                   access_token_expires_at,refresh_token_expires_at,scopes,status,created_at,updated_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(kakao_user_id) DO UPDATE SET
                   label=CASE
                     WHEN excluded.label IN ('구독 신청자','카카오 수신자','') THEN recipients.label
                     ELSE excluded.label
                   END,
                   access_token_ciphertext=excluded.access_token_ciphertext,
                   refresh_token_ciphertext=excluded.refresh_token_ciphertext,
                   access_token_expires_at=excluded.access_token_expires_at,
                   refresh_token_expires_at=excluded.refresh_token_expires_at,scopes=excluded.scopes,status='active',updated_at=excluded.updated_at""",
                (
                    recipient_id, invite["label"], str(token_data["kakao_user_id"]),
                    token_data["access_token_ciphertext"], token_data["refresh_token_ciphertext"],
                    token_data["access_token_expires_at"], token_data["refresh_token_expires_at"],
                    json.dumps(token_data.get("scopes", []), ensure_ascii=False), "active", now, now,
                ),
            )
            connection.execute("UPDATE recipient_invites SET used_at=? WHERE id=?", (now, invite["id"]))
            row = connection.execute("SELECT id FROM recipients WHERE kakao_user_id=?", (str(token_data["kakao_user_id"]),)).fetchone()
        return self.get_recipient(row["id"]) or {}

    def unsubscribe_recipient_by_kakao_user_id(self, kakao_user_id: str, invite_token: str) -> dict:
        """Remove a verified Kakao recipient while retaining a six-hour audit row."""
        token_hash = hashlib.sha256(str(invite_token).encode()).hexdigest()
        now = now_iso()
        with self.connect() as connection:
            invite = connection.execute(
                """SELECT * FROM recipient_invites
                   WHERE token_hash=? AND label=? AND used_at IS NULL AND expires_at>?""",
                (token_hash, RECIPIENT_UNSUBSCRIBE_INVITE_LABEL, now),
            ).fetchone()
            if not invite:
                raise ValueError("구독 해지 인증이 만료되었거나 이미 사용되었습니다.")
            connection.execute("UPDATE recipient_invites SET used_at=? WHERE id=?", (now, invite["id"]))
            recipient = connection.execute(
                "SELECT id,label FROM recipients WHERE kakao_user_id=? AND status<>'deleted'",
                (str(kakao_user_id or ""),),
            ).fetchone()
            if not recipient:
                return {"deleted": False, "history_count": 0}

            recipient_id = str(recipient["id"])
            applicant_name = str(recipient["label"] or "구독자")
            cases_by_organization: dict[str, set[str]] = {}
            for row in connection.execute(
                """SELECT c.organization_id,cr.case_id FROM case_recipients cr
                   JOIN cases c ON c.id=cr.case_id WHERE cr.recipient_id=?""",
                (recipient_id,),
            ).fetchall():
                cases_by_organization.setdefault(str(row["organization_id"]), set()).add(str(row["case_id"]))
            slots_by_organization: dict[str, set[str]] = {}
            for row in connection.execute(
                "SELECT organization_id,edition_slots,case_ids FROM recipient_magazine_subscriptions WHERE recipient_id=?",
                (recipient_id,),
            ).fetchall():
                organization_id = str(row["organization_id"])
                slots_by_organization[organization_id] = {
                    str(value) for value in json_value(row["edition_slots"], []) if str(value).strip()
                }
                cases_by_organization.setdefault(organization_id, set()).update(
                    str(value) for value in json_value(row["case_ids"], []) if str(value).strip()
                )

            active_requests = connection.execute(
                """SELECT id,organization_id FROM signup_requests
                   WHERE recipient_id=? AND status NOT IN ('rejected','revoked')
                   ORDER BY created_at""",
                (recipient_id,),
            ).fetchall()
            covered_organizations: set[str] = set()
            history_count = 0
            for request in active_requests:
                request_id = str(request["id"])
                organization_id = str(request["organization_id"])
                covered_organizations.add(organization_id)
                connection.executemany(
                    """INSERT OR IGNORE INTO signup_request_cases(
                       request_id,case_id,status,decided_at,updated_at
                       ) VALUES(?,?, 'revoked',?,?)""",
                    [(request_id, case_id, now, now) for case_id in sorted(cases_by_organization.get(organization_id, set()))],
                )
                connection.execute(
                    """UPDATE signup_request_cases SET status='revoked',decided_at=?,updated_at=?
                       WHERE request_id=?""",
                    (now, now, request_id),
                )
                connection.executemany(
                    "INSERT OR IGNORE INTO signup_request_magazine_slots(request_id,edition_slot) VALUES(?,?)",
                    [(request_id, slot) for slot in sorted(slots_by_organization.get(organization_id, set()))],
                )
                connection.execute(
                    """UPDATE signup_requests SET status='revoked',admin_note='사용자 직접 해지',
                       decided_at=?,updated_at=? WHERE id=?""",
                    (now, now, request_id),
                )
                history_count += 1

            current_organizations = set(cases_by_organization) | set(slots_by_organization)
            for organization_id in sorted(current_organizations - covered_organizations):
                request_id = str(uuid.uuid4())
                connection.execute(
                    """INSERT INTO signup_requests(
                       id,invite_id,recipient_id,applicant_name,organization_id,status,admin_note,
                       kakao_registered_at,decided_at,created_at,updated_at
                       ) VALUES(?,?,?,?,?,'revoked','사용자 직접 해지',?,?,?,?)""",
                    (request_id, invite["id"], recipient_id, applicant_name, organization_id, now, now, now, now),
                )
                connection.executemany(
                    """INSERT INTO signup_request_cases(request_id,case_id,status,decided_at,updated_at)
                       VALUES(?,?, 'revoked',?,?)""",
                    [(request_id, case_id, now, now) for case_id in sorted(cases_by_organization.get(organization_id, set()))],
                )
                connection.executemany(
                    "INSERT INTO signup_request_magazine_slots(request_id,edition_slot) VALUES(?,?)",
                    [(request_id, slot) for slot in sorted(slots_by_organization.get(organization_id, set()))],
                )
                history_count += 1

            connection.execute("DELETE FROM case_recipients WHERE recipient_id=?", (recipient_id,))
            connection.execute("DELETE FROM recipient_magazine_subscriptions WHERE recipient_id=?", (recipient_id,))
            connection.execute(
                "DELETE FROM deliveries WHERE recipient_id=? AND status IN ('pending','retry')",
                (recipient_id,),
            )
            connection.execute(
                "DELETE FROM magazine_deliveries WHERE recipient_id=? AND status IN ('pending','retry','sending')",
                (recipient_id,),
            )
            deleted = connection.execute(
                """UPDATE recipients
                   SET label='삭제된 구독자',kakao_user_id=?,access_token_ciphertext='',refresh_token_ciphertext='',
                       access_token_expires_at='',refresh_token_expires_at='',status='deleted',
                       last_error='사용자 직접 해지',updated_at=? WHERE id=?""",
                (f"deleted:{recipient_id}", now, recipient_id),
            ).rowcount > 0
            return {"deleted": deleted, "history_count": history_count, "recipient_id": recipient_id}

    def update_recipient_tokens(self, recipient_id: str, values: dict) -> None:
        allowed = {"access_token_ciphertext", "refresh_token_ciphertext", "access_token_expires_at", "refresh_token_expires_at", "status", "last_error"}
        clean = {key: value for key, value in values.items() if key in allowed}
        if not clean:
            return
        with self.connect() as connection:
            assignments = ",".join(f"{key}=?" for key in clean)
            connection.execute(f"UPDATE recipients SET {assignments},updated_at=? WHERE id=?", (*clean.values(), now_iso(), recipient_id))

    def delete_recipient(self, recipient_id: str) -> bool:
        with self.connect() as connection:
            connection.execute("DELETE FROM signup_requests WHERE recipient_id=?", (recipient_id,))
            connection.execute("DELETE FROM case_recipients WHERE recipient_id=?", (recipient_id,))
            connection.execute("DELETE FROM deliveries WHERE recipient_id=? AND status IN ('pending','retry')", (recipient_id,))
            now = now_iso()
            return connection.execute(
                """UPDATE recipients
                   SET label='삭제된 구독자',kakao_user_id=?,access_token_ciphertext='',refresh_token_ciphertext='',
                       access_token_expires_at='',refresh_token_expires_at='',status='deleted',last_error='관리자 수신 해제',updated_at=?
                   WHERE id=?""",
                (f"deleted:{recipient_id}", now, recipient_id),
            ).rowcount > 0

    def upsert_article(self, article: dict) -> tuple[dict, bool]:
        now = now_iso()
        body_error = str(article.get("body_error") or article.get("error") or "")[:120]
        body_value = str(article.get("body") or "")
        with self.connect() as connection:
            existing = connection.execute("SELECT * FROM articles WHERE canonical_url=?", (article["canonical_url"],)).fetchone()
            if existing:
                connection.execute(
                    """UPDATE articles SET original_url=?,title=?,publisher=?,published_at=?,snippet=?,
                       body=CASE WHEN ?<>'' THEN ? ELSE body END,
                       image_url=CASE WHEN ?<>'' THEN ? ELSE image_url END,
                       body_error=CASE WHEN ?<>'' THEN ? WHEN ?<>'' THEN '' ELSE body_error END,
                       body_expires_at=COALESCE(?,body_expires_at),
                       content_hash=COALESCE(?,content_hash),updated_at=? WHERE id=?""",
                    (
                        article["original_url"], article["title"], article.get("publisher", ""), article.get("published_at"),
                        article.get("snippet", ""), body_value, body_value,
                        article.get("image_url", ""), article.get("image_url", ""), body_error, body_error, body_value,
                        article.get("body_expires_at"), article.get("content_hash"), now, existing["id"],
                    ),
                )
                article_id, created = existing["id"], False
            else:
                article_id, created = str(uuid.uuid4()), True
                connection.execute(
                    """INSERT INTO articles(id,canonical_url,original_url,title,publisher,published_at,snippet,body,
                       image_url,body_error,body_expires_at,content_hash,source_type,first_seen_at,updated_at)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        article_id, article["canonical_url"], article["original_url"], article["title"], article.get("publisher", ""),
                        article.get("published_at"), article.get("snippet", ""), body_value, article.get("image_url", ""), body_error, article.get("body_expires_at"),
                        article.get("content_hash"), article.get("source_type", "naver"), now, now,
                    ),
                )
            row = connection.execute("SELECT * FROM articles WHERE id=?", (article_id,)).fetchone()
        return dict(row), created

    def _analysis_content_key(self, article: dict) -> str:
        value = str(article.get("content_hash") or "").strip()
        if value:
            return value[:128]
        raw = "\n".join(str(article.get(key) or "") for key in ("title", "snippet", "body"))
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def ensure_article_analysis(self, article: dict, organization_id: str | None = None) -> tuple[dict, bool]:
        """Create one automatic common analysis per canonical article, regardless of later body revisions."""
        key, now = self._analysis_content_key(article), now_iso()
        analysis_id = str(uuid.uuid4())
        with self.connect() as connection:
            flag = connection.execute(
                "SELECT analysis_id FROM article_processing_flags WHERE article_id=?",
                (article["id"],),
            ).fetchone()
            if flag:
                row = connection.execute("SELECT * FROM article_analyses WHERE id=?", (flag["analysis_id"],)).fetchone()
                if row:
                    return self._decode_article_analysis(row) or {}, False
            inserted = connection.execute(
                """INSERT OR IGNORE INTO article_analyses(
                   id,article_id,organization_id,content_key,status,created_at,updated_at
                ) VALUES(?,?,?,?,'pending',?,?)""",
                (analysis_id, article["id"], organization_id, key, now, now),
            ).rowcount
            row = connection.execute(
                "SELECT * FROM article_analyses WHERE article_id=? ORDER BY CASE WHEN status='completed' THEN 0 ELSE 1 END,COALESCE(analyzed_at,updated_at) DESC LIMIT 1",
                (article["id"],),
            ).fetchone()
            if not row:
                raise RuntimeError("공통 기사 처리 플래그 생성에 실패했습니다.")
            flag_inserted = connection.execute(
                """INSERT OR IGNORE INTO article_processing_flags(
                       article_id,analysis_id,common_analysis_completed,created_at,updated_at
                   ) VALUES(?,?,?, ?,?)""",
                (article["id"], row["id"], 1 if row["status"] == "completed" else 0, now, now),
            ).rowcount
        return self._decode_article_analysis(row) or {}, bool(inserted and flag_inserted)

    @staticmethod
    def _decode_article_analysis(row: sqlite3.Row | dict | None) -> dict | None:
        if not row:
            return None
        item = dict(row)
        for key in ("classification_tags", "entities", "topic_concepts", "evidence"):
            item[key] = json_value(item.get(key), [])
        item["analysis_report"] = json_value(item.get("analysis_report"), {})
        return item

    @staticmethod
    def _decode_case_evaluation(row: sqlite3.Row | dict | None) -> dict | None:
        if not row:
            return None
        item = dict(row)
        for key in ("reasons", "matched_terms", "low_score_categories"):
            item[key] = json_value(item.get(key), [])
        item["analysis_report"] = json_value(item.get("analysis_report"), {})
        return item

    def queue_article_analysis(self, analysis_id: str, organization_id: str | None = None) -> str:
        job_id, now = str(uuid.uuid4()), now_iso()
        with self.connect() as connection:
            row = connection.execute("SELECT status FROM article_analyses WHERE id=?", (analysis_id,)).fetchone()
            if not row:
                raise ValueError("공통 기사 분석 대상을 찾지 못했습니다.")
            if row["status"] == "completed":
                existing = connection.execute("SELECT id FROM article_analysis_jobs WHERE article_analysis_id=?", (analysis_id,)).fetchone()
                return str(existing["id"]) if existing else ""
            connection.execute(
                """INSERT INTO article_analysis_jobs(id,article_analysis_id,organization_id,status,queued_at)
                   VALUES(?,?,?, 'pending',?) ON CONFLICT(article_analysis_id) DO UPDATE SET
                   organization_id=COALESCE(article_analysis_jobs.organization_id, excluded.organization_id),
                   status=article_analysis_jobs.status,
                   queued_at=article_analysis_jobs.queued_at,
                   started_at=article_analysis_jobs.started_at,
                   finished_at=article_analysis_jobs.finished_at,
                   error=article_analysis_jobs.error""",
                (job_id, analysis_id, organization_id, now),
            )
            connection.execute("UPDATE article_analyses SET status='pending',updated_at=? WHERE id=? AND status<>'completed'", (now, analysis_id))
            current = connection.execute("SELECT id FROM article_analysis_jobs WHERE article_analysis_id=?", (analysis_id,)).fetchone()
        return str(current["id"])

    def next_article_analysis_job(self) -> dict | None:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM article_analysis_jobs WHERE status='pending' AND (retry_after IS NULL OR retry_after<=?) ORDER BY queued_at,rowid LIMIT 1", (now_iso(),)).fetchone()
        return dict(row) if row else None

    def claim_next_article_analysis_job(self, lease_owner: str, provider_lane: str = "primary",
                                        lease_seconds: int = 300) -> dict | None:
        """Claim one common-analysis job in a database transaction shared by all processes."""
        owner = str(lease_owner or "").strip()
        if not owner:
            raise ValueError("lease_owner_required")
        now = now_iso()
        lane = str(provider_lane or "primary")[:30]
        ready_clause = "" if lane == "burst" else " AND (retry_after IS NULL OR retry_after<=?)"
        ready_params = [] if lane == "burst" else [now]
        expires_at = (datetime.now(KST) + timedelta(seconds=max(60, int(lease_seconds)))).isoformat(timespec="seconds")
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT id FROM article_analysis_jobs WHERE status='pending'" + ready_clause +
                " ORDER BY queued_at,rowid LIMIT 1",
                ready_params,
            ).fetchone()
            if not row:
                return None
            job_id = str(row["id"])
            changed = connection.execute(
                """UPDATE article_analysis_jobs
                   SET status='processing',started_at=?,finished_at=NULL,duration_ms=NULL,error=NULL,
                       retry_after=NULL,attempts=attempts+1,lease_owner=?,lease_expires_at=?,provider_lane=?
                   WHERE id=? AND status='pending'""" + ready_clause,
                (now, owner, expires_at, lane, job_id, *ready_params),
            ).rowcount
            if not changed:
                return None
            connection.execute(
                "UPDATE article_analyses SET status='processing',updated_at=? "
                "WHERE id=(SELECT article_analysis_id FROM article_analysis_jobs WHERE id=?)",
                (now, job_id),
            )
            claimed = connection.execute(
                "SELECT * FROM article_analysis_jobs WHERE id=? AND status='processing' AND lease_owner=?",
                (job_id, owner),
            ).fetchone()
        return dict(claimed) if claimed else None

    def start_article_analysis_job(self, job_id: str) -> bool:
        now = now_iso()
        with self.connect() as connection:
            cursor = connection.execute("UPDATE article_analysis_jobs SET status='processing',started_at=?,finished_at=NULL,duration_ms=NULL,error=NULL,retry_after=NULL,attempts=attempts+1 WHERE id=? AND status='pending' AND (retry_after IS NULL OR retry_after<=?)", (now, job_id, now))
            if cursor.rowcount:
                connection.execute("UPDATE article_analyses SET status='processing',updated_at=? WHERE id=(SELECT article_analysis_id FROM article_analysis_jobs WHERE id=?)", (now, job_id))
        return cursor.rowcount > 0

    def save_article_analysis(self, analysis_id: str, result: dict, model: str,
                              job_id: str = "", lease_owner: str = "") -> dict:
        now = now_iso()
        with self.connect() as connection:
            if job_id and lease_owner:
                owned = connection.execute(
                    "SELECT 1 FROM article_analysis_jobs WHERE id=? AND article_analysis_id=? "
                    "AND status='processing' AND lease_owner=?",
                    (job_id, analysis_id, lease_owner),
                ).fetchone()
                if not owned:
                    return {}
            connection.execute(
                """UPDATE article_analyses SET status='completed',model=?,summary=?,publisher_name=?,reporter_name=?,article_type=?,tone=?,classification_tags=?,entities=?,topic_concepts=?,evidence=?,analysis_report=?,error=NULL,analyzed_at=?,updated_at=? WHERE id=?""",
                (str(model)[:120], result.get("summary", ""), result.get("publisher_name", ""), result.get("reporter_name", ""), result.get("article_type", "기타"), result.get("tone", "사실전달"),
                 json.dumps(result.get("classification_tags", []), ensure_ascii=False), json.dumps(result.get("entities", []), ensure_ascii=False),
                 json.dumps(result.get("topic_concepts", []), ensure_ascii=False), json.dumps(result.get("evidence", []), ensure_ascii=False),
                 json.dumps(result.get("analysis_report", {}), ensure_ascii=False), now, now, analysis_id),
            )
            row = connection.execute("SELECT * FROM article_analyses WHERE id=?", (analysis_id,)).fetchone()
            connection.execute(
                "UPDATE article_processing_flags SET analysis_id=?,common_analysis_completed=1,updated_at=? WHERE article_id=(SELECT article_id FROM article_analyses WHERE id=?)",
                (analysis_id, now, analysis_id),
            )
        return self._decode_article_analysis(row) or {}

    def finish_article_analysis_job(self, job_id: str, ok: bool, duration_ms: int, error: str = "",
                                    retryable: bool = False, retry_after: str | None = None,
                                    keep_pending: bool = False, lease_owner: str = "") -> bool:
        now = now_iso()
        with self.connect() as connection:
            row = connection.execute("SELECT attempts FROM article_analysis_jobs WHERE id=?", (job_id,)).fetchone()
            attempts = int(row["attempts"] or 0) if row else 0
            should_retry = bool(not ok and retryable and (keep_pending or attempts < 3))
            if should_retry and not retry_after:
                delay = 1 if attempts <= 1 else 5
                retry_after = (datetime.now(KST) + timedelta(minutes=delay)).isoformat(timespec="seconds")
            status = "completed" if ok else ("pending" if should_retry else "failed")
            owner_clause = " AND lease_owner=?" if lease_owner else ""
            values: list[Any] = [status, status, now, max(0, int(duration_ms)), retry_after if should_retry else None, error[:1000] or None, job_id]
            if lease_owner:
                values.append(lease_owner)
            changed = connection.execute(
                "UPDATE article_analysis_jobs SET status=?,started_at=CASE WHEN ?='pending' THEN NULL ELSE started_at END,"
                "finished_at=?,duration_ms=?,retry_after=?,error=?,lease_owner='',lease_expires_at=NULL "
                f"WHERE id=?{owner_clause}",
                values,
            ).rowcount
            if not changed:
                return False
            if not ok:
                analysis_status = "pending" if should_retry else "failed"
                connection.execute("UPDATE article_analyses SET status=?,error=?,updated_at=? WHERE id=(SELECT article_analysis_id FROM article_analysis_jobs WHERE id=?)", (analysis_status, error[:1000] or None, now, job_id))
        return True

    def get_article_analysis(self, analysis_id: str) -> dict | None:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM article_analyses WHERE id=?", (analysis_id,)).fetchone()
        return self._decode_article_analysis(row)
    def get_current_article_analysis(self, article_id: str) -> dict | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT aa.* FROM article_processing_flags apf JOIN article_analyses aa ON aa.id=apf.analysis_id WHERE apf.article_id=?",
                (article_id,),
            ).fetchone()
        return self._decode_article_analysis(row)


    def create_case_evaluation(self, analysis_id: str, article_id: str, case: dict, candidate: bool,
                               semantic_raw: float = 0.0, semantic_score: float = 0.0,
                               exclusion_reason: str = "") -> tuple[dict, bool]:
        """Create at most one automatic second-stage evaluation per article analysis and case."""
        now, evaluation_id = now_iso(), str(uuid.uuid4())
        status, decision = ("pending", "pending") if candidate else ("excluded", "excluded")
        case_id, case_version = str(case["id"]), int(case.get("version", 1))
        with self.connect() as connection:
            flag = connection.execute(
                "SELECT evaluation_id FROM article_case_processing_flags WHERE article_id=? AND case_id=?",
                (article_id, case_id),
            ).fetchone()
            if flag:
                row = connection.execute("SELECT * FROM case_evaluations WHERE id=?", (flag["evaluation_id"],)).fetchone()
                if not row:
                    row = connection.execute(
                        "SELECT * FROM case_evaluations WHERE article_analysis_id=? AND case_id=? ORDER BY case_version DESC,updated_at DESC LIMIT 1",
                        (analysis_id, case_id),
                    ).fetchone()
                return self._decode_case_evaluation(row) or {}, False

            reason = str(exclusion_reason or "")[:160]
            reasons = [] if candidate or not reason else [candidate_exclusion_message(reason)]
            categories = [] if candidate or not reason else [reason]
            inserted = connection.execute(
                """INSERT OR IGNORE INTO case_evaluations(
                   id,article_analysis_id,article_id,case_id,case_version,candidate_status,status,semantic_raw,semantic_score,reasons,low_score_categories,decision,error,created_at,updated_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (evaluation_id, analysis_id, article_id, case_id, case_version, "candidate" if candidate else "excluded", status,
                 float(semantic_raw), float(semantic_score), json.dumps(reasons, ensure_ascii=False),
                 json.dumps(categories, ensure_ascii=False), decision, reason or None, now, now),
            ).rowcount
            row = connection.execute(
                "SELECT * FROM case_evaluations WHERE article_analysis_id=? AND case_id=? ORDER BY case_version DESC,updated_at DESC LIMIT 1",
                (analysis_id, case_id),
            ).fetchone()
            if not row:
                raise RuntimeError("케이스 평가 플래그 생성에 실패했습니다.")
            flag_inserted = connection.execute(
                """INSERT OR IGNORE INTO article_case_processing_flags(
                       article_id,case_id,analysis_id,evaluation_id,case_version,
                       common_analysis_completed,case_evaluation_completed,delivery_classified,created_at,updated_at
                   ) VALUES(?,?,?,?,?,1,?,?,?,?)""",
                (article_id, case_id, analysis_id, row["id"], int(row["case_version"]),
                 0 if candidate else 1, 0 if candidate else 1, now, now),
            ).rowcount
        return self._decode_case_evaluation(row) or {}, bool(inserted and flag_inserted)

    def reset_case_evaluation_for_requeue(self, analysis_id: str, article_id: str, case: dict, candidate: bool,
                                          semantic_raw: float = 0.0, semantic_score: float = 0.0,
                                          exclusion_reason: str = "") -> tuple[dict, bool]:
        """Reset the current article/case evaluation so the normal case worker overwrites it with fresh results."""
        case_id, case_version = str(case["id"]), int(case.get("version", 1))
        status, decision = ("pending", "pending") if candidate else ("excluded", "excluded")
        reason = str(exclusion_reason or "")[:160]
        reasons = [] if candidate or not reason else [candidate_exclusion_message(reason)]
        categories = [] if candidate or not reason else [reason]
        now = now_iso()
        with self.connect() as connection:
            flag = connection.execute(
                "SELECT evaluation_id FROM article_case_processing_flags WHERE article_id=? AND case_id=?",
                (article_id, case_id),
            ).fetchone()
            if not flag:
                return self.create_case_evaluation(analysis_id, article_id, case, candidate, semantic_raw, semantic_score, reason)
            evaluation_id = str(flag["evaluation_id"])
            connection.execute("DELETE FROM case_evaluation_jobs WHERE case_evaluation_id=?", (evaluation_id,))
            connection.execute(
                "DELETE FROM deliveries WHERE article_id=? AND case_id=? AND status IN ('pending','retry','failed')",
                (article_id, case_id),
            )
            connection.execute("DELETE FROM article_scores WHERE article_id=? AND case_id=?", (article_id, case_id))
            updated = connection.execute(
                """UPDATE case_evaluations SET article_analysis_id=?,case_version=?,candidate_status=?,status=?,decision=?,
                   keyword_score=0,semantic_raw=?,semantic_score=?,llm_score=0,final_score=0,evidence_status='',
                   reasons=?,matched_terms='[]',low_score_categories=?,analysis_report='{}',error=?,completed_at=NULL,updated_at=?
                   WHERE id=?""",
                (analysis_id, case_version, "candidate" if candidate else "excluded", status, decision,
                 float(semantic_raw), float(semantic_score), json.dumps(reasons, ensure_ascii=False),
                 json.dumps(categories, ensure_ascii=False), reason or None, now, evaluation_id),
            ).rowcount
            if not updated:
                return self.create_case_evaluation(analysis_id, article_id, case, candidate, semantic_raw, semantic_score, reason)
            connection.execute(
                """UPDATE article_case_processing_flags SET analysis_id=?,evaluation_id=?,case_version=?,
                   common_analysis_completed=1,case_evaluation_completed=?,delivery_classified=?,updated_at=?
                   WHERE article_id=? AND case_id=?""",
                (analysis_id, evaluation_id, case_version, 0 if candidate else 1, 0 if candidate else 1, now, article_id, case_id),
            )
            row = connection.execute("SELECT * FROM case_evaluations WHERE id=?", (evaluation_id,)).fetchone()
        return self._decode_case_evaluation(row) or {}, False

    def queue_case_evaluation(self, evaluation_id: str, ready_at: str | None = None) -> str:
        job_id, now = str(uuid.uuid4()), now_iso()
        ready_at = ready_at or now
        with self.connect() as connection:
            row = connection.execute("SELECT status FROM case_evaluations WHERE id=?", (evaluation_id,)).fetchone()
            if not row or row["status"] in {"completed", "excluded"}:
                return ""
            connection.execute(
                """INSERT INTO case_evaluation_jobs(id,case_evaluation_id,status,queued_at,retry_after) VALUES(?,?, 'pending',?,?)
                   ON CONFLICT(case_evaluation_id) DO UPDATE SET
                   status=CASE WHEN case_evaluation_jobs.status='failed' THEN 'pending' ELSE case_evaluation_jobs.status END,
                   queued_at=CASE WHEN case_evaluation_jobs.status='failed' THEN excluded.queued_at ELSE case_evaluation_jobs.queued_at END,
                   started_at=CASE WHEN case_evaluation_jobs.status='failed' THEN NULL ELSE case_evaluation_jobs.started_at END,
                   finished_at=CASE WHEN case_evaluation_jobs.status='failed' THEN NULL ELSE case_evaluation_jobs.finished_at END,
                   error=CASE WHEN case_evaluation_jobs.status='failed' THEN NULL ELSE case_evaluation_jobs.error END""",
                (job_id, evaluation_id, now, ready_at),
            )
            connection.execute("UPDATE case_evaluations SET status='pending',updated_at=? WHERE id=? AND status NOT IN ('completed','excluded')", (now, evaluation_id))
            current = connection.execute("SELECT id FROM case_evaluation_jobs WHERE case_evaluation_id=?", (evaluation_id,)).fetchone()
        return str(current["id"])

    def next_case_evaluation_job(self) -> dict | None:
        with self.connect() as connection:
            row = connection.execute(
                """SELECT j.* FROM case_evaluation_jobs j
                   JOIN case_evaluations ce ON ce.id=j.case_evaluation_id
                   JOIN cases c ON c.id=ce.case_id JOIN articles a ON a.id=ce.article_id
                   WHERE j.status='pending' AND (j.retry_after IS NULL OR j.retry_after<=?)
                     AND a.first_seen_at>=COALESCE(NULLIF(c.monitor_from,''),c.created_at)
                   ORDER BY j.queued_at,j.rowid LIMIT 1""",
                (now_iso(),),
            ).fetchone()
        return dict(row) if row else None

    def next_case_evaluation_batch(self, limit: int = 10, provider: str = "openrouter",
                                   lease_owner: str = "", provider_lane: str = "primary",
                                   lease_seconds: int = 300) -> list[dict]:
        """Atomically lease up to ten case jobs sharing one article analysis."""
        limit, now = max(1, min(10, int(limit))), now_iso()
        batch_id = str(uuid.uuid4())
        owner = str(lease_owner or f"legacy:{batch_id}").strip()
        lane = str(provider_lane or "primary")[:30]
        ready_clause = "" if lane == "burst" else " AND (j.retry_after IS NULL OR j.retry_after<=?)"
        ready_params = [] if lane == "burst" else [now]
        expires_at = (datetime.now(KST) + timedelta(seconds=max(60, int(lease_seconds)))).isoformat(timespec="seconds")
        with self.connect() as connection:
            # BEGIN IMMEDIATE serializes the read-and-claim sequence across
            # independent primary and burst worker processes.
            connection.execute("BEGIN IMMEDIATE")
            first = connection.execute(
                "SELECT ce.article_analysis_id,MIN(j.queued_at) first_queued,COUNT(*) pending_count "
                "FROM case_evaluation_jobs j "
                "JOIN case_evaluations ce ON ce.id=j.case_evaluation_id "
                "JOIN cases c ON c.id=ce.case_id JOIN articles a ON a.id=ce.article_id "
                "WHERE j.status='pending'" + ready_clause + " "
                "AND a.first_seen_at>=COALESCE(NULLIF(c.monitor_from,''),c.created_at) "
                "GROUP BY ce.article_analysis_id "
                "ORDER BY pending_count DESC,first_queued,ce.article_analysis_id LIMIT 1", ready_params,
            ).fetchone()
            if not first:
                return []
            rows = connection.execute(
                "SELECT j.*,ce.article_analysis_id,ce.article_id,ce.case_id FROM case_evaluation_jobs j "
                "JOIN case_evaluations ce ON ce.id=j.case_evaluation_id "
                "JOIN cases c ON c.id=ce.case_id JOIN articles a ON a.id=ce.article_id "
                "WHERE j.status='pending'" + ready_clause + " "
                "AND a.first_seen_at>=COALESCE(NULLIF(c.monitor_from,''),c.created_at) "
                "AND ce.article_analysis_id=? ORDER BY j.queued_at,j.rowid LIMIT ?",
                (*ready_params, first["article_analysis_id"], limit),
            ).fetchall()
            if not rows:
                return []
            job_ids = [str(row["id"]) for row in rows]
            marks = ",".join("?" for _ in job_ids)
            connection.execute(
                f"UPDATE case_evaluation_jobs SET status='processing',provider=?,started_at=?,finished_at=NULL,"
                f"duration_ms=NULL,error=NULL,retry_after=NULL,attempts=attempts+1,batch_id=?,batch_size=?,"
                f"lease_owner=?,lease_expires_at=?,provider_lane=? "
                f"WHERE id IN ({marks}) AND status='pending'" + ("" if lane == "burst" else " AND (retry_after IS NULL OR retry_after<=?)"),
                (provider, now, batch_id, len(job_ids), owner, expires_at,
                 lane, *job_ids, *ready_params),
            )
            claimed = connection.execute(
                "SELECT j.*,ce.article_analysis_id,ce.article_id,ce.case_id "
                "FROM case_evaluation_jobs j JOIN case_evaluations ce ON ce.id=j.case_evaluation_id "
                "WHERE j.batch_id=? AND j.status='processing' AND j.lease_owner=? ORDER BY j.queued_at,j.rowid",
                (batch_id, owner),
            ).fetchall()
            if not claimed:
                return []
            claimed_ids = [str(row["id"]) for row in claimed]
            claimed_marks = ",".join("?" for _ in claimed_ids)
            connection.execute(
                f"UPDATE case_evaluations SET status='processing',updated_at=? "
                f"WHERE id IN (SELECT case_evaluation_id FROM case_evaluation_jobs WHERE id IN ({claimed_marks}))",
                (now, *claimed_ids),
            )
        return [{**dict(row), "batch_id": batch_id, "batch_size": len(claimed)} for row in claimed]

    def pending_case_evaluation_jobs(self, include_deferred: bool = False) -> int:
        ready_clause = "" if include_deferred else " AND (retry_after IS NULL OR retry_after<=?)"
        params = [] if include_deferred else [now_iso()]
        with self.connect() as connection:
            row = connection.execute("SELECT COUNT(*) value FROM case_evaluation_jobs WHERE status='pending'" + ready_clause, params).fetchone()
        return int(row["value"] or 0)

    def pending_case_evaluation_bundles(self, include_deferred: bool = False) -> int:
        """Count article-level batches, optionally including provider-deferred work."""
        ready_clause = "" if include_deferred else " AND (j.retry_after IS NULL OR j.retry_after<=?)"
        params = [] if include_deferred else [now_iso()]
        with self.connect() as connection:
            row = connection.execute(
                """SELECT COUNT(DISTINCT ce.article_analysis_id) value
                   FROM case_evaluation_jobs j
                   JOIN case_evaluations ce ON ce.id=j.case_evaluation_id
                   JOIN cases c ON c.id=ce.case_id JOIN articles a ON a.id=ce.article_id
                   WHERE j.status='pending'""" + ready_clause + """
                     AND a.first_seen_at>=COALESCE(NULLIF(c.monitor_from,''),c.created_at)""",
                params,
            ).fetchone()
        return int(row["value"] or 0)

    def pending_article_analysis_jobs(self, include_deferred: bool = False) -> int:
        ready_clause = "" if include_deferred else " AND (retry_after IS NULL OR retry_after<=?)"
        params = [] if include_deferred else [now_iso()]
        with self.connect() as connection:
            row = connection.execute(
                "SELECT COUNT(*) value FROM article_analysis_jobs WHERE status='pending'" + ready_clause,
                params,
            ).fetchone()
        return int(row["value"] or 0)

    def start_case_evaluation_job(self, job_id: str, provider: str = "openrouter") -> bool:
        now = now_iso()
        with self.connect() as connection:
            cursor = connection.execute("UPDATE case_evaluation_jobs SET status='processing',provider=?,started_at=?,finished_at=NULL,duration_ms=NULL,error=NULL,retry_after=NULL,attempts=attempts+1 WHERE id=? AND status='pending' AND (retry_after IS NULL OR retry_after<=?)", (provider, now, job_id, now))
            if cursor.rowcount:
                connection.execute("UPDATE case_evaluations SET status='processing',updated_at=? WHERE id=(SELECT case_evaluation_id FROM case_evaluation_jobs WHERE id=?)", (now, job_id))
        return cursor.rowcount > 0

    def save_case_evaluation(self, evaluation_id: str, result: dict, model: str,
                             job_id: str = "", lease_owner: str = "") -> dict:
        now = now_iso()
        with self.connect() as connection:
            if job_id and lease_owner:
                owned = connection.execute(
                    "SELECT 1 FROM case_evaluation_jobs WHERE id=? AND case_evaluation_id=? "
                    "AND status='processing' AND lease_owner=?",
                    (job_id, evaluation_id, lease_owner),
                ).fetchone()
                if not owned:
                    return {}
            connection.execute(
                """UPDATE case_evaluations SET status='completed',model=?,keyword_score=?,semantic_raw=?,semantic_score=?,llm_score=?,final_score=?,evidence_status=?,reasons=?,matched_terms=?,low_score_categories=?,analysis_report=?,decision=?,error=NULL,completed_at=?,updated_at=? WHERE id=?""",
                (str(model)[:120], result.get("keyword_score", 0), result.get("semantic_raw", 0), result.get("semantic_score", 0), result.get("llm_score", 0), result.get("final_score", 0), result.get("evidence_status", ""),
                 json.dumps(result.get("reasons", []), ensure_ascii=False), json.dumps(result.get("matched_terms", []), ensure_ascii=False), json.dumps(result.get("low_score_categories", []), ensure_ascii=False),
                 json.dumps(result.get("analysis_report", {}), ensure_ascii=False), result.get("decision", "low"), now, now, evaluation_id),
            )
            row = connection.execute("SELECT * FROM case_evaluations WHERE id=?", (evaluation_id,)).fetchone()
            connection.execute(
                """UPDATE article_case_processing_flags
                   SET evaluation_id=?,case_version=?,common_analysis_completed=1,
                       case_evaluation_completed=1,delivery_classified=?,updated_at=?
                   WHERE article_id=(SELECT article_id FROM case_evaluations WHERE id=?)
                     AND case_id=(SELECT case_id FROM case_evaluations WHERE id=?)""",
                (evaluation_id, int(row["case_version"]) if row else 1,
                 1 if result.get("decision") in {"send", "low", "excluded"} else 0,
                 now, evaluation_id, evaluation_id),
            )
        return self._decode_case_evaluation(row) or {}

    def finish_case_evaluation_job(self, job_id: str, ok: bool, duration_ms: int, error: str = "", retryable: bool = False,
                                   retry_after: str | None = None, keep_pending: bool = False,
                                   lease_owner: str = "") -> bool:
        now = now_iso()
        with self.connect() as connection:
            row = connection.execute("SELECT attempts FROM case_evaluation_jobs WHERE id=?", (job_id,)).fetchone()
            attempts = int(row["attempts"] or 0) if row else 0
            should_retry = bool(not ok and retryable and (keep_pending or attempts < 4))
            status = "completed" if ok else ("pending" if should_retry else "failed")
            if should_retry and not retry_after:
                delay = 1 if attempts <= 1 else (2 if attempts == 2 else 5)
                retry_after = (datetime.now(KST) + timedelta(minutes=delay)).isoformat(timespec="seconds")
            owner_clause = " AND lease_owner=?" if lease_owner else ""
            values: list[Any] = [status, status, now, max(0, int(duration_ms)), retry_after if should_retry else None, error[:1000] or None, job_id]
            if lease_owner:
                values.append(lease_owner)
            changed = connection.execute(
                "UPDATE case_evaluation_jobs SET status=?,started_at=CASE WHEN ?='pending' THEN NULL ELSE started_at END,"
                "finished_at=?,duration_ms=?,retry_after=?,error=?,lease_owner='',lease_expires_at=NULL "
                f"WHERE id=?{owner_clause}",
                values,
            ).rowcount
            if not changed:
                return False
            if not ok:
                evaluation_status = "pending" if should_retry else "failed"
                connection.execute("UPDATE case_evaluations SET status=?,error=?,updated_at=? WHERE id=(SELECT case_evaluation_id FROM case_evaluation_jobs WHERE id=?)", (evaluation_status, error[:1000] or None, now, job_id))
        return True

    def get_case_evaluation(self, evaluation_id: str) -> dict | None:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM case_evaluations WHERE id=?", (evaluation_id,)).fetchone()
        return self._decode_case_evaluation(row)

    def get_current_case_evaluation(self, article_id: str, case_id: str) -> dict | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT ce.* FROM article_case_processing_flags flag JOIN case_evaluations ce ON ce.id=flag.evaluation_id WHERE flag.article_id=? AND flag.case_id=?",
                (article_id, case_id),
            ).fetchone()
        return self._decode_case_evaluation(row)

    def activate_worker_session(self, session_id: str) -> int:
        """A changed web-process session means any processing job was interrupted and is safe to retry."""
        key = "master_press_worker_session"
        with self.connect() as connection:
            row = connection.execute("SELECT value FROM app_settings WHERE key=?", (key,)).fetchone()
            if row and str(row["value"]) == str(session_id):
                return 0
            cursor = connection.execute(
                """UPDATE llm_jobs SET status='pending',started_at=NULL,finished_at=NULL,
                   error=COALESCE(error,'worker_restarted') WHERE status='processing'"""
            )
            recovered_common = connection.execute("UPDATE article_analysis_jobs SET status='pending',started_at=NULL,finished_at=NULL,error=COALESCE(error,'worker_restarted') WHERE status='processing'").rowcount
            recovered_cases = connection.execute("UPDATE case_evaluation_jobs SET status='pending',started_at=NULL,finished_at=NULL,error=COALESCE(error,'worker_restarted') WHERE status='processing'").rowcount
            connection.execute(
                """INSERT INTO app_settings(key,value,updated_at) VALUES(?,?,?)
                   ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at""",
                (key, str(session_id), now_iso()),
            )
        return cursor.rowcount + recovered_common + recovered_cases

    def recover_incomplete_pipeline_jobs(self) -> dict:
        """Requeue bounded failures whose prerequisites now exist."""
        with self.connect() as connection:
            common = connection.execute(
                """UPDATE article_analysis_jobs SET status='pending',started_at=NULL,finished_at=NULL,retry_after=NULL
                   WHERE status='failed' AND attempts<3"""
            ).rowcount
            connection.execute(
                """UPDATE article_analyses SET status='pending',error=NULL,updated_at=?
                   WHERE id IN (SELECT article_analysis_id FROM article_analysis_jobs WHERE status='pending')""",
                (now_iso(),),
            )
            cases = connection.execute(
                """UPDATE case_evaluation_jobs SET status='pending',started_at=NULL,finished_at=NULL,retry_after=NULL
                   WHERE status='failed' AND error='article_case_or_common_analysis_missing'
                     AND EXISTS (SELECT 1 FROM case_evaluations ce JOIN article_analyses aa ON aa.id=ce.article_analysis_id
                                 WHERE ce.id=case_evaluation_jobs.case_evaluation_id AND aa.status='completed')"""
            ).rowcount
            connection.execute(
                """UPDATE case_evaluations SET status='pending',error=NULL,updated_at=?
                   WHERE id IN (SELECT case_evaluation_id FROM case_evaluation_jobs WHERE status='pending')""",
                (now_iso(),),
            )
        return {"common": int(common), "cases": int(cases)}

    def queue_llm_job(self, article_id: str, case_id: str, case_version: int, organization_id: str | None = None) -> str:
        job_id = str(uuid.uuid4())
        now = now_iso()
        with self.connect() as connection:
            connection.execute(
                """INSERT INTO llm_jobs(id,article_id,case_id,case_version,organization_id,status,queued_at)
                   VALUES(?,?,?,?,?,'pending',?)
                   ON CONFLICT(article_id,case_id,case_version) DO UPDATE SET
                     organization_id=excluded.organization_id,
                     status=CASE WHEN llm_jobs.status='failed' THEN 'pending' ELSE llm_jobs.status END,
                     queued_at=CASE WHEN llm_jobs.status='failed' THEN excluded.queued_at ELSE llm_jobs.queued_at END,
                     started_at=CASE WHEN llm_jobs.status='failed' THEN NULL ELSE llm_jobs.started_at END,
                     finished_at=CASE WHEN llm_jobs.status='failed' THEN NULL ELSE llm_jobs.finished_at END,
                     duration_ms=CASE WHEN llm_jobs.status='failed' THEN NULL ELSE llm_jobs.duration_ms END,
                     error=CASE WHEN llm_jobs.status='failed' THEN NULL ELSE llm_jobs.error END""",
                (job_id, article_id, case_id, case_version, organization_id, now),
            )
            row = connection.execute(
                "SELECT id FROM llm_jobs WHERE article_id=? AND case_id=? AND case_version=?",
                (article_id, case_id, case_version),
            ).fetchone()
        return str(row["id"])

    def next_llm_job(self) -> dict | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM llm_jobs WHERE status='pending' ORDER BY queued_at,rowid LIMIT 1"
            ).fetchone()
        return dict(row) if row else None

    def start_llm_job(self, job_id: str) -> bool:
        with self.connect() as connection:
            cursor = connection.execute(
                """UPDATE llm_jobs SET status='processing',started_at=?,finished_at=NULL,error=NULL
                   WHERE id=? AND status='pending'""",
                (now_iso(), job_id),
            )
        return cursor.rowcount > 0

    def finish_llm_job(self, job_id: str, ok: bool, duration_ms: int, error: str = "") -> None:
        with self.connect() as connection:
            connection.execute(
                "UPDATE llm_jobs SET status=?,finished_at=?,duration_ms=?,error=? WHERE id=?",
                ("completed" if ok else "failed", now_iso(), max(0, int(duration_ms)), str(error)[:1000] or None, job_id),
            )

    def llm_processing_stats(self, case_id: str | None = None, organization_id: str | None = None) -> dict:
        today = datetime.now(KST).replace(hour=0, minute=0, second=0, microsecond=0).isoformat(timespec="seconds")
        condition = ""
        params: list[Any] = [today, today, today, today, today]
        if case_id:
            condition = " AND case_id=?"
            params.append(case_id)
        elif organization_id:
            condition = " AND case_id IN (SELECT id FROM cases WHERE organization_id=?)"
            params.append(organization_id)
        with self.connect() as connection:
            row = connection.execute(
                f"""SELECT
                    COALESCE(SUM(CASE WHEN status='pending' AND queued_at>=? THEN 1 ELSE 0 END),0) pending,
                    COALESCE(SUM(CASE WHEN status='processing' AND started_at>=? THEN 1 ELSE 0 END),0) processing,
                    COALESCE(SUM(CASE WHEN status='completed' AND finished_at>=? THEN 1 ELSE 0 END),0) completed,
                    COALESCE(SUM(CASE WHEN status='failed' AND finished_at>=? THEN 1 ELSE 0 END),0) failed,
                    COALESCE(ROUND(AVG(CASE WHEN status='completed' AND finished_at>=? THEN duration_ms END)/1000.0,2),0) average_seconds,
                    COUNT(*) total
                    FROM llm_jobs WHERE 1=1{condition}""",
                params,
            ).fetchone()
        data = dict(row) if row else {"pending": 0, "processing": 0, "completed": 0, "failed": 0, "average_seconds": 0, "total": 0}
        job_filter, job_params = "", []
        if case_id:
            job_filter, job_params = " AND j.case_id=?", [case_id]
        elif organization_id:
            job_filter, job_params = " AND j.organization_id=?", [organization_id]
        with self.connect() as connection:
            title_row = connection.execute(
                "SELECT a.title FROM llm_jobs j JOIN articles a ON a.id=j.article_id "
                "WHERE j.status='processing'" + job_filter + " ORDER BY j.started_at DESC LIMIT 1",
                job_params,
            ).fetchone()
            if not title_row:
                title_row = connection.execute("SELECT a.title FROM reanalysis_jobs j JOIN articles a ON a.id=j.article_id WHERE j.status='processing' ORDER BY j.started_at DESC LIMIT 1").fetchone()
        data["processing_title"] = str(title_row["title"]) if title_row else ""
        return data


    def score_exists(self, article_id: str, case_id: str, case_version: int | None = None) -> bool:
        """Completed send/low decisions are final until an operator requests reanalysis."""
        with self.connect() as connection:
            row = connection.execute(
                """SELECT 1 FROM article_scores
                   WHERE article_id=? AND case_id=? AND analysis_completed=1 AND delivery_classified=1""",
                (article_id, case_id),
            ).fetchone()
        return row is not None

    def save_score(self, article_id: str, case_id: str, case_version: int, result: dict) -> dict:
        now = now_iso()
        score_id = str(uuid.uuid4())
        with self.connect() as connection:
            connection.execute(
                """INSERT INTO article_scores(
                   id,article_id,case_id,case_version,keyword_score,semantic_score,llm_score,final_score,
                   summary,organization_tag,article_type,tone,evidence_status,classification_tags,reasons,matched_terms,low_score_categories,analysis_report,decision,analysis_completed,delivery_classified,finalized_at,created_at,updated_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(article_id,case_id) DO UPDATE SET
                   case_version=excluded.case_version,keyword_score=excluded.keyword_score,
                   semantic_score=excluded.semantic_score,llm_score=excluded.llm_score,
                   final_score=excluded.final_score,summary=excluded.summary,organization_tag=excluded.organization_tag,
                   article_type=excluded.article_type,tone=excluded.tone,evidence_status=excluded.evidence_status,
                   classification_tags=excluded.classification_tags,reasons=excluded.reasons,
                   matched_terms=excluded.matched_terms,low_score_categories=excluded.low_score_categories,
                   analysis_report=excluded.analysis_report,
                   decision=excluded.decision,analysis_completed=excluded.analysis_completed,
                   delivery_classified=excluded.delivery_classified,finalized_at=excluded.finalized_at,updated_at=excluded.updated_at""",
                (
                    score_id, article_id, case_id, case_version, result["keyword_score"], result["semantic_score"],
                    result["llm_score"], result["final_score"], result.get("summary", ""),
                    result.get("organization_tag", ""),
                    result.get("article_type", "기타"), result.get("tone", "사실전달"),
                    result.get("evidence_status", "not_recorded"),
                    json.dumps(result.get("classification_tags", []), ensure_ascii=False),
                    json.dumps(result.get("reasons", []), ensure_ascii=False),
                    json.dumps(result.get("matched_terms", []), ensure_ascii=False),
                    json.dumps(result.get("low_score_categories", []), ensure_ascii=False),
                    json.dumps(result.get("analysis_report", {}), ensure_ascii=False),
                    result["decision"], 1, 1 if result["decision"] in {"send", "low"} else 0,
                    now if result["decision"] in {"send", "low"} else None, now, now,
                ),
            )
            row = connection.execute("SELECT * FROM article_scores WHERE article_id=? AND case_id=?", (article_id, case_id)).fetchone()
        return dict(row)

    def save_analysis_feedback(self, article_id: str, case_id: str, reason: str, comment: str = "") -> dict:
        reason = str(reason or "").strip()[:120]
        comment = str(comment or "").strip()[:1000]
        if not reason:
            raise ValueError("피드백 사유를 입력하세요.")
        now = now_iso()
        feedback_id = str(uuid.uuid4())
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO analysis_feedback(id,article_id,case_id,reason,comment,created_at) VALUES(?,?,?,?,?,?)",
                (feedback_id, article_id, case_id, reason, comment, now),
            )
        return {"id": feedback_id, "article_id": article_id, "case_id": case_id, "reason": reason, "comment": comment, "created_at": now}

    def analysis_feedback_summary(self, article_id: str | None, case_id: str, days: int = 30, limit: int = 5) -> dict:
        days = max(1, min(365, int(days)))
        since = (datetime.now(KST) - timedelta(days=days)).isoformat(timespec="seconds")
        article_filter = "AND article_id=?" if article_id else ""
        params = (case_id, article_id, since) if article_id else (case_id, since)
        comment_params = (case_id, article_id, limit) if article_id else (case_id, limit)
        with self.connect() as connection:
            rows = connection.execute(
                f"SELECT reason,COUNT(*) value FROM analysis_feedback WHERE case_id=? {article_filter} AND created_at>=? GROUP BY reason ORDER BY value DESC",
                params,
            ).fetchall()
            comments = connection.execute(
                f"SELECT comment,created_at FROM analysis_feedback WHERE case_id=? {article_filter} AND comment<>'' ORDER BY created_at DESC LIMIT ?",
                comment_params,
            ).fetchall()
        breakdown = [{"reason": str(row["reason"] or ""), "count": int(row["value"] or 0)} for row in rows]
        guidance_map = {
            "expected_send": "실제로 포함해야 한다는 평가입니다. 누락 원인이 임계치인지 대상·주제 근거 규칙인지 함께 점검하세요.",
            "expected_exclude": "실제로 제외해야 한다는 평가입니다. 과대 매칭된 표현과 맥락을 제외 기준에 반영하세요.",
            "topic_or_target_error": "케이스가 찾는 주제와 대상을 프롬프트에서 더 명확하게 구분하세요.",
            "condition_or_keyword_error": "필수 조건·키워드와 동의어 범위가 실제 케이스 의도와 맞는지 점검하세요.",
            "context_or_subject_error": "단순 언급과 핵심 주체를 구분하는 기사 맥락 판정 기준을 조정하세요.",
            "stance_error": "긍정·부정·사실 전달 어조를 구분하는 근거와 예외를 프롬프트에 보강하세요.",
            "evidence_or_body_error": "본문 확보 상태와 근거 문장 판정이 결과에 미친 영향을 점검하세요.",
            "required_terms_missing": "필수 키워드를 case.required_terms에 명확히 추가하거나, 케이스 주제 설명에 핵심 표현을 보강하세요.",
            "include_terms_missing": "include_terms에 더 많은 핵심 표현을 포함하고, 검색 프롬프트를 보다 구체적으로 만드세요.",
            "negative_signal_missing": "부정 어조 요청 케이스는 기사 본문에 명확한 부정 신호가 포함되도록 프롬프트를 다듬으세요.",
            "topic_target_not_verified": "대상 기관·인물이 기사 본문에서 핵심 주체로 확인되도록 케이스 키워드와 설명을 조정하세요.",
            "topic_stance_not_verified": "요구한 어조가 본문 근거와 일치하도록 케이스 프롬프트를 보완하세요.",
            "body_unavailable": "본문을 확보하지 못하는 기사에도 대응할 수 있도록 검색 요약문과 키워드를 보강하세요.",
            "llm_insufficient_relevance": "LLM 판정이 낮다면 케이스 주제 설명을 구체화하고 일반 용어는 줄여주세요.",
            "llm_topic_mismatch": "기사 주제가 케이스 주제와 어긋날 때는 핵심 대상·행위·맥락을 더 선명히 표현하세요.",
            "llm_different_context": "비슷한 표현이 다른 맥락일 경우, 케이스 프롬프트에서 맥락을 보다 명확히 설명하세요.",
            "llm_body_insufficient": "본문 근거가 부족할 때는 검색어와 핵심 문장을 보완하여 충분한 근거를 확보하세요.",
            "required_topic_not_verified": "필수 주제를 본문에서 검증 가능한 근거와 연결하도록 케이스 설정을 보강하세요.",
            "excluded_term": "제외 키워드가 너무 넓거나 애매할 수 있습니다. 제외 기준을 다시 검토하세요.",
            "other": "추가 의견을 통해 케이스 프롬프트와 필수 조건을 세밀히 점검하세요.",
        }
        guidance = []
        for item in breakdown:
            text = guidance_map.get(item["reason"])
            if text and text not in guidance:
                guidance.append(text)
        return {
            "days": days,
            "total": sum(item["count"] for item in breakdown),
            "breakdown": breakdown,
            "guidance": guidance,
            "recent_comments": [{"comment": str(row["comment"] or ""), "created_at": str(row["created_at"] or "")} for row in comments],
        }

    def analysis_report(self, article_id: str, case_id: str) -> dict:
        with self.connect() as connection:
            score = connection.execute("SELECT analysis_report FROM article_scores WHERE article_id=? AND case_id=?", (article_id, case_id)).fetchone()
            if not score:
                score = connection.execute(
                    """SELECT ce.analysis_report FROM article_case_processing_flags flag
                       JOIN case_evaluations ce ON ce.id=flag.evaluation_id
                       WHERE flag.article_id=? AND flag.case_id=?""",
                    (article_id, case_id),
                ).fetchone()
            job = connection.execute("SELECT * FROM reanalysis_jobs WHERE article_id=? AND case_id=? ORDER BY queued_at DESC LIMIT 1", (article_id, case_id)).fetchone()
        return {"current": json_value(score["analysis_report"], {}) if score else {}, "reanalysis": self._decode_reanalysis(job) if job else None}

    @staticmethod
    def _decode_reanalysis(row: sqlite3.Row | dict) -> dict:
        item = dict(row)
        item["result"] = json_value(item.get("result"), {})
        return item

    def queue_reanalysis(self, article_id: str, case_id: str, model: str) -> dict:
        job = {"id": str(uuid.uuid4()), "article_id": article_id, "case_id": case_id, "model": str(model)[:120], "queued_at": now_iso()}
        with self.connect() as connection:
            connection.execute("INSERT INTO reanalysis_jobs(id,article_id,case_id,model,status,queued_at) VALUES(?,?,?,?, 'pending',?)", (job["id"], job["article_id"], job["case_id"], job["model"], job["queued_at"]))
        return {**job, "status": "pending"}

    def next_reanalysis_job(self) -> dict | None:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM reanalysis_jobs WHERE status='pending' ORDER BY queued_at,id LIMIT 1").fetchone()
        return self._decode_reanalysis(row) if row else None

    def get_reanalysis(self, job_id: str) -> dict | None:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM reanalysis_jobs WHERE id=?", (job_id,)).fetchone()
        return self._decode_reanalysis(row) if row else None

    def start_reanalysis(self, job_id: str) -> None:
        with self.connect() as connection:
            connection.execute("UPDATE reanalysis_jobs SET status='processing',started_at=?,error=NULL WHERE id=?", (now_iso(), job_id))

    def finish_reanalysis(self, job_id: str, result: dict | None, duration_ms: int, error: str = "") -> None:
        with self.connect() as connection:
            connection.execute("UPDATE reanalysis_jobs SET status=?,finished_at=?,duration_ms=?,error=?,result=? WHERE id=?", ("completed" if not error else "failed", now_iso(), max(0, int(duration_ms)), error[:1000] or None, json.dumps(result or {}, ensure_ascii=False), job_id))

    def queue_delivery(self, article_id: str, case_id: str, recipient_id: str, scheduled_at: str) -> None:
        now = now_iso()
        with self.connect() as connection:
            connection.execute(
                """INSERT OR IGNORE INTO deliveries(id,article_id,case_id,recipient_id,scheduled_at,created_at,updated_at)
                   VALUES(?,?,?,?,?,?,?)""",
                (str(uuid.uuid4()), article_id, case_id, recipient_id, scheduled_at, now, now),
            )

    def due_deliveries(self, limit: int = 20) -> list[dict]:
        with self.connect() as connection:
            rows = connection.execute(
                """SELECT d.*,a.title,a.original_url,a.image_url,a.publisher,a.published_at,
                          COALESCE(aa.summary,s.summary,a.snippet,'') summary,
                          COALESCE(ce.final_score,s.final_score,0) similarity_score,
                          COALESCE(ce.final_score,s.final_score,0) final_score,
                          COALESCE(o.name,s.organization_tag,'') organization_tag,
                          COALESCE(aa.article_type,s.article_type,'기타') article_type,
                          COALESCE(aa.classification_tags,s.classification_tags,'[]') classification_tags,
                          c.name AS case_name
                   FROM deliveries d JOIN articles a ON a.id=d.article_id
                   JOIN cases c ON c.id=d.case_id
                   JOIN recipients r ON r.id=d.recipient_id AND r.status='active'
                   LEFT JOIN article_scores s ON s.article_id=d.article_id AND s.case_id=d.case_id
                   LEFT JOIN case_evaluations ce ON ce.id=(
                     SELECT ce2.id FROM case_evaluations ce2
                     WHERE ce2.article_id=d.article_id AND ce2.case_id=d.case_id AND ce2.decision='send'
                     ORDER BY ce2.case_version DESC,ce2.completed_at DESC LIMIT 1
                   )
                   LEFT JOIN article_analyses aa ON aa.id=ce.article_analysis_id
                   LEFT JOIN organizations o ON o.id=c.organization_id
                   WHERE d.status IN ('pending','retry') AND d.scheduled_at<=? AND d.attempts<3
                     AND (ce.id IS NOT NULL OR s.article_id IS NOT NULL)
                   ORDER BY d.scheduled_at LIMIT ?""",
                (now_iso(), limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def fail_delivery_permanently(self, delivery_id: str, response_code: int | None = None, error: str = "") -> None:
        now = now_iso()
        with self.connect() as connection:
            connection.execute(
                """UPDATE deliveries SET status='failed',attempts=3,response_code=?,last_error=?,sent_at=NULL,updated_at=? WHERE id=?""",
                (response_code, str(error)[:1000], now, delivery_id),
            )

    def finish_delivery(self, delivery_id: str, ok: bool, response_code: int | None = None, error: str = "") -> None:
        now = now_iso()
        with self.connect() as connection:
            row = connection.execute("SELECT attempts FROM deliveries WHERE id=?", (delivery_id,)).fetchone()
            attempts = int(row["attempts"] or 0) + 1 if row else 1
            status = "sent" if ok else ("failed" if attempts >= 3 else "retry")
            connection.execute(
                """UPDATE deliveries SET status=?,attempts=?,response_code=?,last_error=?,sent_at=?,updated_at=? WHERE id=?""",
                (status, attempts, response_code, error[:1000], now if ok else None, now, delivery_id),
            )

    def queue_magazine_deliveries(self, edition: dict) -> int:
        self.ensure_magazine_schema()
        now, queued = now_iso(), 0
        with self.connect() as connection:
            rows = connection.execute("SELECT s.recipient_id,s.edition_slots,s.case_ids FROM recipient_magazine_subscriptions s JOIN recipients r ON r.id=s.recipient_id AND r.status='active' WHERE s.organization_id=?", (edition["organization_id"],)).fetchall()
            for row in rows:
                slots, case_ids = json_value(row["edition_slots"], []), json_value(row["case_ids"], [])
                if edition.get("edition_slot") not in slots or not case_ids:
                    continue
                connection.execute("INSERT OR IGNORE INTO magazine_deliveries(id,edition_id,recipient_id,selected_case_ids,scheduled_at,created_at,updated_at) VALUES(?,?,?,?,?,?,?)", (str(uuid.uuid4()), edition["id"], row["recipient_id"], json.dumps(case_ids), now, now, now))
                queued += int(connection.execute("SELECT changes()").fetchone()[0] or 0)
        return queued

    def magazine_edition_exists(self, organization_id: str, edition_date: str, slot: str) -> bool:
        self.ensure_magazine_schema()
        with self.connect() as connection:
            row = connection.execute(
                "SELECT 1 FROM magazine_editions WHERE organization_id=? AND edition_date=? AND edition_slot=? LIMIT 1",
                (organization_id, edition_date, slot),
            ).fetchone()
        return bool(row)

    def requeue_magazine_deliveries(self, edition: dict) -> int:
        """Queue the selected edition again for every currently eligible subscriber."""
        self.ensure_magazine_schema()
        now, queued = now_iso(), 0
        with self.connect() as connection:
            rows = connection.execute(
                """SELECT s.recipient_id,s.edition_slots,s.case_ids
                   FROM recipient_magazine_subscriptions s
                   JOIN recipients r ON r.id=s.recipient_id AND r.status='active'
                   WHERE s.organization_id=?""", (edition["organization_id"],),
            ).fetchall()
            for row in rows:
                slots, case_ids = json_value(row["edition_slots"], []), json_value(row["case_ids"], [])
                if edition.get("edition_slot") not in slots or not case_ids:
                    continue
                connection.execute(
                    """INSERT INTO magazine_deliveries(id,edition_id,recipient_id,selected_case_ids,scheduled_at,status,attempts,response_code,last_error,created_at,updated_at,sent_at)
                       VALUES(?,?,?,?,?,'pending',0,NULL,NULL,?,?,NULL)
                       ON CONFLICT(edition_id,recipient_id) DO UPDATE SET
                         selected_case_ids=excluded.selected_case_ids,scheduled_at=excluded.scheduled_at,
                         status='pending',attempts=0,response_code=NULL,last_error=NULL,updated_at=excluded.updated_at,sent_at=NULL""",
                    (str(uuid.uuid4()), edition["id"], row["recipient_id"], json.dumps(case_ids), now, now, now),
                )
                queued += 1
        return queued

    def magazine_window_readiness(self, organization_id: str, window_start: str, window_end: str) -> dict:
        """Return whether every known article in an edition window has finalized."""
        with self.connect() as connection:
            row = connection.execute(
                """SELECT COUNT(*) total,
                          COALESCE(SUM(analysis_status<>'completed'),0) pending_common,
                          COALESCE(SUM(analysis_status='completed' AND embedding_done=0),0) pending_embedding,
                          COALESCE(SUM(case_route_pending>0 OR pending_cases>0),0) pending_case_articles,
                          COALESCE(SUM(analysis_status='completed' AND embedding_done=1 AND similarity_ready=0),0) pending_similarity
                   FROM (
                     SELECT aa.article_id,aa.status analysis_status,
                            CASE WHEN ae.status='completed' THEN 1 ELSE 0 END embedding_done,
                            CASE WHEN sg.article_id IS NOT NULL AND sg.computed_at>=ae.updated_at THEN 1 ELSE 0 END similarity_ready,
                            CASE WHEN aa.case_routed_at IS NULL THEN 1 ELSE 0 END case_route_pending,
                            (SELECT COUNT(*) FROM article_case_processing_flags acpf
                              JOIN cases c ON c.id=acpf.case_id AND c.is_active=1
                              JOIN case_evaluations ce ON ce.id=acpf.evaluation_id
                             WHERE acpf.article_id=aa.article_id AND acpf.analysis_id=aa.id
                               AND ce.status NOT IN ('completed','excluded')) pending_cases
                       FROM article_processing_flags apf
                       JOIN article_analyses aa ON aa.id=apf.analysis_id
                       JOIN articles a ON a.id=aa.article_id
                       LEFT JOIN article_embeddings ae ON ae.article_analysis_id=aa.id
                       LEFT JOIN article_similarity_groups sg ON sg.article_id=aa.article_id
                      WHERE aa.organization_id=? AND COALESCE(a.published_at,a.first_seen_at)>=?
                        AND COALESCE(a.published_at,a.first_seen_at)<?
                   ) scoped""", (organization_id, window_start, window_end),
            ).fetchone()
        result = {key: int(row[key] or 0) for key in ("total", "pending_common", "pending_embedding", "pending_case_articles", "pending_similarity")}
        result["ready"] = not any(result[key] for key in ("pending_common", "pending_embedding", "pending_case_articles", "pending_similarity"))
        return result

    def recent_magazines_for_recipient(self, recipient_id: str, limit: int = 3) -> list[dict]:
        self.ensure_magazine_schema()
        with self.connect() as connection:
            subscriptions = [dict(row) for row in connection.execute(
                "SELECT organization_id,edition_slots,case_ids FROM recipient_magazine_subscriptions WHERE recipient_id=?",
                (str(recipient_id),),
            ).fetchall()]
            if not subscriptions:
                return []
            organization_ids = [str(row["organization_id"]) for row in subscriptions]
            marks = ",".join("?" for _ in organization_ids)
            editions = [dict(row) for row in connection.execute(
                f"""SELECT * FROM magazine_editions
                    WHERE status='published' AND edition_slot<>'daily' AND organization_id IN ({marks})
                    ORDER BY window_end_at DESC,generated_at DESC LIMIT 60""",
                organization_ids,
            ).fetchall()]
        by_organization = {str(row["organization_id"]): row for row in subscriptions}
        selected = []
        for edition in editions:
            subscription = by_organization.get(str(edition["organization_id"])) or {}
            slots = json_value(subscription.get("edition_slots"), [])
            case_ids = json_value(subscription.get("case_ids"), [])
            if edition.get("edition_slot") not in slots or not case_ids:
                continue
            edition["selected_case_ids"] = [str(value) for value in case_ids]
            selected.append(edition)
            if len(selected) >= max(1, min(10, int(limit))):
                break
        return selected

    def due_magazine_deliveries(self, limit: int = 20) -> list[dict]:
        self.ensure_magazine_schema()
        now = now_iso()
        stale_before = (datetime.now(KST) - timedelta(minutes=10)).isoformat(timespec="seconds")
        with self.connect() as connection:
            # A timer and the long-running worker can wake up together. Recover a
            # stale claim, then atomically claim each delivery before Kakao I/O so
            # only one process can send the same edition to the same recipient.
            connection.execute(
                """UPDATE magazine_deliveries
                   SET status=CASE WHEN attempts>=3 THEN 'failed' ELSE 'retry' END,
                       last_error=CASE WHEN COALESCE(last_error,'')='' THEN '발송 작업 중단 후 자동 복구' ELSE last_error END,
                       updated_at=?
                   WHERE status='sending' AND updated_at<?""",
                (now, stale_before),
            )
            candidate_ids = [str(row["id"]) for row in connection.execute(
                """SELECT d.id FROM magazine_deliveries d
                   JOIN recipients r ON r.id=d.recipient_id AND r.status='active'
                   WHERE d.status IN ('pending','retry') AND d.scheduled_at<=? AND d.attempts<3
                   ORDER BY d.scheduled_at LIMIT ?""",
                (now, max(1, int(limit))),
            ).fetchall()]
            claimed = []
            for delivery_id in candidate_ids:
                changed = connection.execute(
                    """UPDATE magazine_deliveries
                       SET status='sending',attempts=attempts+1,updated_at=?
                       WHERE id=? AND status IN ('pending','retry') AND attempts<3""",
                    (now, delivery_id),
                ).rowcount
                if not changed:
                    continue
                row = connection.execute(
                    """SELECT d.*,e.organization_name,e.edition_date,e.edition_slot
                       FROM magazine_deliveries d JOIN magazine_editions e ON e.id=d.edition_id
                       WHERE d.id=?""",
                    (delivery_id,),
                ).fetchone()
                if row:
                    claimed.append(dict(row))
        return claimed

    def finish_magazine_delivery(self, delivery_id: str, ok: bool, response_code: int | None = None, error: str = "") -> None:
        now = now_iso()
        with self.connect() as connection:
            row = connection.execute("SELECT attempts FROM magazine_deliveries WHERE id=?", (delivery_id,)).fetchone()
            attempts = max(1, int(row["attempts"] or 0)) if row else 1
            status = "sent" if ok else ("failed" if attempts >= 3 else "retry")
            connection.execute(
                "UPDATE magazine_deliveries SET status=?,attempts=?,response_code=?,last_error=?,sent_at=?,updated_at=? WHERE id=?",
                (status, attempts, response_code, str(error)[:1000], now if ok else None, now, delivery_id),
            )

    def start_run(self, case_id: str | None = None, organization_id: str | None = None) -> str:
        run_id = str(uuid.uuid4())
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO collection_runs(id,case_id,organization_id,started_at,status) VALUES(?,?,?,?,'running')",
                (run_id, case_id, organization_id, now_iso()),
            )
        return run_id

    def finish_run(self, run_id: str, status: str, counts: dict | None = None, error: str = "") -> None:
        counts = counts or {}
        with self.connect() as connection:
            connection.execute(
                """UPDATE collection_runs SET finished_at=?,status=?,collected_count=?,new_count=?,scored_count=?,queued_count=?,error=? WHERE id=?""",
                (now_iso(), status, counts.get("collected", 0), counts.get("new", 0), counts.get("scored", 0), counts.get("queued", 0), error[:2000], run_id),
            )

    def set_case_schedule(self, case_id: str, next_collect_at: str, collected: bool = False) -> None:
        with self.connect() as connection:
            if collected:
                connection.execute("UPDATE cases SET next_collect_at=?,last_collected_at=?,updated_at=? WHERE id=?", (next_collect_at, now_iso(), now_iso(), case_id))
            else:
                connection.execute("UPDATE cases SET next_collect_at=?,updated_at=? WHERE id=?", (next_collect_at, now_iso(), case_id))

    def list_due_cases(self) -> list[dict]:
        with self.connect() as connection:
            rows = connection.execute("SELECT * FROM cases WHERE is_active=1 AND organization_id IS NULL AND (next_collect_at IS NULL OR next_collect_at<=?) ORDER BY next_collect_at", (now_iso(),)).fetchall()
        return [self.decode_case(row) for row in rows]

    def set_organization_schedule(self, organization_id: str, next_collect_at: str, collected: bool = False) -> None:
        with self.connect() as connection:
            if collected:
                connection.execute("UPDATE organizations SET next_collect_at=?,last_collected_at=?,updated_at=? WHERE id=?", (next_collect_at, now_iso(), now_iso(), organization_id))
            else:
                connection.execute("UPDATE organizations SET next_collect_at=?,updated_at=? WHERE id=?", (next_collect_at, now_iso(), organization_id))

    def list_due_organizations(self) -> list[dict]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM organizations WHERE is_active=1 AND archived_at IS NULL AND (next_collect_at IS NULL OR next_collect_at<=?) ORDER BY next_collect_at",
                (now_iso(),),
            ).fetchall()
        return [self.decode_organization(row) for row in rows]

    def list_articles_missing_body(self, retry_before: str, first_seen_after: str, limit: int = 1) -> list[dict]:
        """Return recent, due recovery candidates newest-first; never select robots bans."""
        with self.connect() as connection:
            rows = connection.execute(
                """SELECT * FROM articles
                   WHERE COALESCE(body,'')='' AND COALESCE(original_url,'')<>''
                     AND COALESCE(NULLIF(published_at,''),first_seen_at)>=?
                     AND COALESCE(body_retryable,1)=1
                     AND COALESCE(body_error,'') NOT IN ('robots_disallowed','http_401','http_403','http_404','http_410','http_451')
                     AND COALESCE(body_attempts,0)<3
                     AND COALESCE(body_next_attempt_at,updated_at)<=?
                   ORDER BY COALESCE(NULLIF(published_at,''),first_seen_at) DESC,COALESCE(body_next_attempt_at,updated_at) ASC,id
                   LIMIT ?""", (first_seen_after, retry_before, max(1, min(200, int(limit))))).fetchall()
        return [dict(row) for row in rows]

    def missing_body_status(self, retry_before: str, first_seen_after: str) -> dict:
        with self.connect() as connection:
            overall = connection.execute("""SELECT COUNT(*) total_articles,
                COALESCE(SUM(CASE WHEN COALESCE(body,'')='' THEN 1 ELSE 0 END),0) missing_total,
                COALESCE(SUM(CASE WHEN COALESCE(body,'')='' AND body_error='robots_disallowed' THEN 1 ELSE 0 END),0) blocked_total,
                COALESCE(SUM(CASE WHEN COALESCE(body,'')='' AND COALESCE(body_error,'')<>'robots_disallowed' THEN 1 ELSE 0 END),0) non_blocked_total,
                COALESCE(SUM(CASE WHEN COALESCE(body,'')='' AND COALESCE(NULLIF(published_at,''),first_seen_at)>=? THEN 1 ELSE 0 END),0) recent_missing_total,
                COALESCE(SUM(CASE WHEN COALESCE(body,'')='' AND COALESCE(NULLIF(published_at,''),first_seen_at)<? THEN 1 ELSE 0 END),0) historical_missing_total
                FROM articles""", (first_seen_after, first_seen_after)).fetchone()
            recollectable = connection.execute("""SELECT COUNT(*) value FROM articles WHERE COALESCE(body,'')='' AND COALESCE(original_url,'')<>'' AND COALESCE(NULLIF(published_at,''),first_seen_at)>=?
                AND COALESCE(body_retryable,1)=1 AND COALESCE(body_error,'') NOT IN ('robots_disallowed','http_401','http_403','http_404','http_410','http_451')
                AND COALESCE(body_attempts,0)<3""", (first_seen_after,)).fetchone()
            due = connection.execute("""SELECT COUNT(*) value FROM articles WHERE COALESCE(body,'')='' AND COALESCE(original_url,'')<>'' AND COALESCE(NULLIF(published_at,''),first_seen_at)>=?
                AND COALESCE(body_retryable,1)=1 AND COALESCE(body_error,'') NOT IN ('robots_disallowed','http_401','http_403','http_404','http_410','http_451')
                AND COALESCE(body_attempts,0)<3 AND COALESCE(body_next_attempt_at,updated_at)<=?""", (first_seen_after, retry_before)).fetchone()
            latest = connection.execute("""SELECT id,title,original_url,first_seen_at,updated_at,snippet FROM articles WHERE COALESCE(body,'')='' AND COALESCE(original_url,'')<>'' AND COALESCE(NULLIF(published_at,''),first_seen_at)>=?
                AND COALESCE(body_retryable,1)=1 AND COALESCE(body_next_attempt_at,updated_at)<=?
                ORDER BY COALESCE(NULLIF(published_at,''),first_seen_at) DESC,COALESCE(body_next_attempt_at,updated_at) ASC,id LIMIT 1""", (first_seen_after, retry_before)).fetchone()
        return {"total_articles": int(overall["total_articles"]), "missing_total": int(overall["missing_total"]), "blocked_total": int(overall["blocked_total"]), "non_blocked_total": int(overall["non_blocked_total"]), "recent_missing_total": int(overall["recent_missing_total"]), "historical_missing_total": int(overall["historical_missing_total"]), "recollectable_total": int(recollectable["value"]), "retry_due": int(due["value"]), "cooling_down": 0, "latest": dict(latest) if latest else None}

    def save_body_backfill_result(self, article_id: str, fetched: dict, retryable: bool, next_attempt_at: str = "") -> None:
        now = now_iso(); body = str(fetched.get("body") or ""); error = str(fetched.get("error") or "")[:120]
        with self.connect() as connection:
            connection.execute("""UPDATE articles SET body=CASE WHEN ?<>'' THEN ? ELSE body END,
                image_url=CASE WHEN ?<>'' THEN ? ELSE image_url END, content_hash=COALESCE(?,content_hash),
                body_error=?, body_attempts=body_attempts+1, body_last_attempt_at=?, body_next_attempt_at=?,
                body_retryable=?, body_http_status=?, body_expires_at=CASE WHEN ?<>'' THEN ? ELSE body_expires_at END, updated_at=? WHERE id=?""",
                (body,body,str(fetched.get("image_url") or ""),str(fetched.get("image_url") or ""),fetched.get("content_hash"),error,now,next_attempt_at or None,1 if retryable else 0,fetched.get("http_status"),body,str(fetched.get("body_expires_at") or ""),now,article_id))

    def next_embedding_analysis(self) -> dict | None:
        """Low-priority backfill: one local embedding per completed common analysis."""
        with self.connect() as connection:
            row = connection.execute(
                """SELECT aa.*,a.title,a.snippet,a.body FROM article_analyses aa JOIN articles a ON a.id=aa.article_id
                   LEFT JOIN article_embeddings e ON e.article_analysis_id=aa.id
                   WHERE aa.status='completed' AND (e.article_analysis_id IS NULL OR e.status='failed')
                   ORDER BY COALESCE(aa.analyzed_at,aa.updated_at) ASC LIMIT 1"""
            ).fetchone()
        return self._decode_article_analysis(row) if row else None

    def save_article_embedding(self, analysis_id: str, model: str, vector: list[float], error: str = "") -> None:
        now, status = now_iso(), "failed" if error else "completed"
        with self.connect() as connection:
            connection.execute(
                """INSERT INTO article_embeddings(article_analysis_id,model,dimensions,vector,status,error,created_at,updated_at)
                   VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(article_analysis_id) DO UPDATE SET
                   model=excluded.model,dimensions=excluded.dimensions,vector=excluded.vector,status=excluded.status,error=excluded.error,updated_at=excluded.updated_at""",
                (analysis_id, str(model)[:120], len(vector), json.dumps(vector), status, error[:1000] or None, now, now),
            )

    def get_article_embedding(self, analysis_id: str) -> dict | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM article_embeddings WHERE article_analysis_id=? AND status='completed'",
                (analysis_id,),
            ).fetchone()
        return {**dict(row), "vector": json_value(row["vector"], [])} if row else None

    def mark_article_cases_routed(self, analysis_id: str) -> None:
        with self.connect() as connection:
            connection.execute("UPDATE article_analyses SET case_routed_at=?,updated_at=? WHERE id=?", (now_iso(), now_iso(), analysis_id))

    def save_article_similarity_groups(self, articles: list[dict]) -> int:
        now, rows = now_iso(), []
        for article in articles:
            article_id = str(article.get("id") or "")
            if not article_id:
                continue
            rows.append((article_id, str(article.get("similar_group_id") or ""), int(article.get("similar_group_size") or 1), str(article.get("similar_group_basis") or ""), str(article.get("similar_group_status") or ""), float(article.get("similar_group_score") or 0), float(article.get("similar_group_semantic_score") or 0), float(article.get("similar_group_noun_score") or 0), json.dumps(article.get("similar_group_topics") or [], ensure_ascii=False), json.dumps(article.get("similar_group_concepts") or [], ensure_ascii=False), now))
        if rows:
            with self.connect() as connection:
                connection.executemany("""INSERT INTO article_similarity_groups(article_id,group_id,group_size,basis,status,score,semantic_score,noun_score,topics,concepts,computed_at) VALUES(?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(article_id) DO UPDATE SET group_id=excluded.group_id,group_size=excluded.group_size,basis=excluded.basis,status=excluded.status,score=excluded.score,semantic_score=excluded.semantic_score,noun_score=excluded.noun_score,topics=excluded.topics,concepts=excluded.concepts,computed_at=excluded.computed_at""", rows)
        return len(rows)

    def article_similarity_groups(self, article_ids: list[str]) -> dict[str, dict]:
        clean = list(dict.fromkeys(str(value) for value in article_ids if str(value)))
        if not clean:
            return {}
        rows = []
        with self.connect() as connection:
            for index in range(0, len(clean), 500):
                chunk = clean[index:index + 500]
                rows.extend(connection.execute(
                    "SELECT * FROM article_similarity_groups WHERE article_id IN (" + ",".join("?" for _ in chunk) + ")",
                    chunk,
                ).fetchall())
        return {str(row["article_id"]): {"group_id": row["group_id"], "size": int(row["group_size"] or 1), "basis": row["basis"], "status": row["status"], "score": float(row["score"] or 0), "semantic_score": float(row["semantic_score"] or 0), "noun_score": float(row["noun_score"] or 0), "topics": json_value(row["topics"], []), "concepts": json_value(row["concepts"], [])} for row in rows}

    def article_similarity_group_members(self, group_ids: list[str]) -> dict[str, dict]:
        """Read every stored member of selected groups without recalculating similarity."""
        clean = list(dict.fromkeys(str(value) for value in group_ids if str(value)))
        if not clean:
            return {}
        rows = []
        with self.connect() as connection:
            for index in range(0, len(clean), 500):
                chunk = clean[index:index + 500]
                rows.extend(connection.execute(
                    "SELECT * FROM article_similarity_groups WHERE group_size>1 AND group_id IN (" + ",".join("?" for _ in chunk) + ")",
                    chunk,
                ).fetchall())
        return {str(row["article_id"]): {"group_id": row["group_id"], "size": int(row["group_size"] or 1), "basis": row["basis"], "status": row["status"], "score": float(row["score"] or 0), "semantic_score": float(row["semantic_score"] or 0), "noun_score": float(row["noun_score"] or 0), "topics": json_value(row["topics"], []), "concepts": json_value(row["concepts"], [])} for row in rows}

    def similarity_groups_stale(self) -> bool:
        cutoff = (datetime.now(KST) - timedelta(hours=self.SIMILARITY_GROUP_LOOKBACK_HOURS)).isoformat(timespec="seconds")
        with self.connect() as connection:
            latest_embedding = connection.execute("SELECT MAX(ae.updated_at) FROM article_embeddings ae JOIN article_analyses aa ON aa.id=ae.article_analysis_id JOIN articles a ON a.id=aa.article_id WHERE ae.status='completed' AND COALESCE(a.published_at,a.first_seen_at)>=?", (cutoff,)).fetchone()[0]
            latest_groups = connection.execute("SELECT MAX(computed_at) FROM article_similarity_groups").fetchone()[0]
            expected = connection.execute("SELECT COUNT(*) FROM article_processing_flags apf JOIN article_analyses aa ON aa.id=apf.analysis_id JOIN articles a ON a.id=aa.article_id WHERE aa.status='completed' AND COALESCE(a.published_at,a.first_seen_at)>=?", (cutoff,)).fetchone()[0]
            current = connection.execute("SELECT COUNT(*) FROM article_similarity_groups").fetchone()[0]
        stored_version = self.get_setting("similarity_groups_algorithm_version", "")
        # Rows naturally age out of the rolling window between rebuilds. Having a
        # few extra older rows is harmless; rebuild immediately only when new
        # in-window articles/embeddings are missing.
        return bool(stored_version != SIMILARITY_GROUPING_VERSION or int(current or 0) < int(expected or 0) or (latest_embedding and (not latest_groups or str(latest_embedding) > str(latest_groups))))

    def similarity_groups_status(self) -> dict:
        """Return the persisted related-article map health for the admin monitor."""
        keys = (
            "similarity_groups_last_status", "similarity_groups_last_at",
            "similarity_groups_last_articles", "similarity_groups_last_duration_ms",
            "similarity_groups_last_error",
            "similarity_groups_algorithm_version",
        )
        cutoff = (datetime.now(KST) - timedelta(hours=self.SIMILARITY_GROUP_LOOKBACK_HOURS)).isoformat(timespec="seconds")
        with self.connect() as connection:
            latest_embedding = connection.execute("SELECT MAX(ae.updated_at) FROM article_embeddings ae JOIN article_analyses aa ON aa.id=ae.article_analysis_id JOIN articles a ON a.id=aa.article_id WHERE ae.status='completed' AND COALESCE(a.published_at,a.first_seen_at)>=?", (cutoff,)).fetchone()[0]
            latest_groups = connection.execute("SELECT MAX(computed_at) FROM article_similarity_groups").fetchone()[0]
            expected = connection.execute("SELECT COUNT(*) FROM article_processing_flags apf JOIN article_analyses aa ON aa.id=apf.analysis_id JOIN articles a ON a.id=aa.article_id WHERE aa.status='completed' AND COALESCE(a.published_at,a.first_seen_at)>=?", (cutoff,)).fetchone()[0]
            current = connection.execute("SELECT COUNT(*) FROM article_similarity_groups").fetchone()[0]
            rows = connection.execute("SELECT key,value FROM app_settings WHERE key IN (" + ",".join("?" for _ in keys) + ")", keys).fetchall()
        settings = {str(row["key"]): str(row["value"] or "") for row in rows}
        return {
            "status": settings.get("similarity_groups_last_status", "rebuilt" if latest_groups else "not_run"),
            "last_at": settings.get("similarity_groups_last_at", str(latest_groups or "")),
            "last_articles": int(settings.get("similarity_groups_last_articles", str(current or 0)) or 0),
            "last_duration_ms": float(settings.get("similarity_groups_last_duration_ms", "0") or 0),
            "last_error": settings.get("similarity_groups_last_error", ""),
            "stored": int(current or 0), "expected": int(expected or 0),
            "version": settings.get("similarity_groups_algorithm_version", ""),
            "window_hours": self.SIMILARITY_GROUP_LOOKBACK_HOURS,
            "stale": bool(settings.get("similarity_groups_algorithm_version", "") != SIMILARITY_GROUPING_VERSION or int(current or 0) < int(expected or 0) or (latest_embedding and (not latest_groups or str(latest_embedding) > str(latest_groups)))),
            "computed_at": str(latest_groups or ""),
        }

    def rebuild_article_similarity_groups(self, limit: int | None = None) -> int:
        """Rebuild the rolling time-window map outside the dashboard request path."""
        cutoff = (datetime.now(KST) - timedelta(hours=self.SIMILARITY_GROUP_LOOKBACK_HOURS)).isoformat(timespec="seconds")
        with self.connect() as connection:
            sql = "SELECT a.id,a.title,a.snippet,a.body,a.published_at,a.first_seen_at,aa.summary,aa.entities,aa.topic_concepts,ae.vector article_vector FROM article_processing_flags apf JOIN article_analyses aa ON aa.id=apf.analysis_id JOIN articles a ON a.id=aa.article_id LEFT JOIN article_embeddings ae ON ae.article_analysis_id=aa.id AND ae.status='completed' WHERE aa.status='completed' AND COALESCE(a.published_at,a.first_seen_at)>=? ORDER BY COALESCE(a.published_at,a.first_seen_at) DESC,COALESCE(aa.analyzed_at,aa.updated_at) DESC"
            params: list[Any] = [cutoff]
            if limit is not None:
                sql += " LIMIT ?"
                params.append(max(2, int(limit)))
            rows = connection.execute(sql, params).fetchall()
        articles = []
        for row in rows:
            item = dict(row)
            articles.append({
                "id": item["id"], "title": item["title"], "summary": item.get("summary") or "",
                "entities": json_value(item.get("entities"), []), "topic_concepts": json_value(item.get("topic_concepts"), []),
                "semantic_vector": json_value(item.get("article_vector"), []), "published_at": item.get("published_at"),
                "first_seen_at": item.get("first_seen_at"),
                "_group_text": " ".join(str(item.get(key) or "") for key in ("title", "snippet", "body", "summary"))[:12000],
            })
        groups = self._dashboard_article_groups(articles)
        for article in articles:
            group = groups.get(str(article["id"]), {})
            article.update({
                "similar_group_id": group.get("group_id", ""), "similar_group_size": int(group.get("size") or 1),
                "similar_group_basis": group.get("basis", ""), "similar_group_status": group.get("status", ""),
                "similar_group_score": float(group.get("score") or 0), "similar_group_semantic_score": float(group.get("semantic_score") or 0),
                "similar_group_noun_score": float(group.get("noun_score") or 0), "similar_group_topics": group.get("topics", []),
                "similar_group_concepts": group.get("concepts", []),
            })
        # Publish the snapshot atomically. Concurrent readers keep seeing the
        # previous complete map until this transaction commits; there is no empty
        # or half-written interval.
        computed_at = now_iso()
        snapshot_rows = []
        for article in articles:
            snapshot_rows.append((
                str(article.get("id") or ""), str(article.get("similar_group_id") or ""),
                int(article.get("similar_group_size") or 1), str(article.get("similar_group_basis") or ""),
                str(article.get("similar_group_status") or ""), float(article.get("similar_group_score") or 0),
                float(article.get("similar_group_semantic_score") or 0), float(article.get("similar_group_noun_score") or 0),
                json.dumps(article.get("similar_group_topics") or [], ensure_ascii=False),
                json.dumps(article.get("similar_group_concepts") or [], ensure_ascii=False), computed_at,
            ))
        with self.connect() as connection:
            connection.execute("DELETE FROM article_similarity_groups")
            connection.executemany(
                """INSERT INTO article_similarity_groups(article_id,group_id,group_size,basis,status,score,semantic_score,noun_score,topics,concepts,computed_at)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?)""", snapshot_rows,
            )
            connection.execute(
                """INSERT INTO app_settings(key,value,updated_at) VALUES('similarity_groups_algorithm_version',?,?)
                   ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at""",
                (SIMILARITY_GROUPING_VERSION, computed_at),
            )
        return len(snapshot_rows)

    def list_article_embedding_vectors(self, model: str) -> list[list[float]]:
        with self.connect() as connection:
            rows = connection.execute("SELECT vector FROM article_embeddings WHERE status='completed' AND model=?", (model,)).fetchall()
        return [json_value(row["vector"], []) for row in rows]

    def get_case_embedding(self, case_id: str, case_version: int, model: str) -> dict | None:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM case_embeddings WHERE case_id=? AND case_version=? AND model=?", (case_id, int(case_version), model)).fetchone()
        if not row:
            return None
        item = dict(row)
        item["vector"] = json_value(item.get("vector"), [])
        item["calibration"] = json_value(item.get("calibration"), {})
        return item

    def save_case_embedding(self, case: dict, model: str, retrieval_text: str, vector: list[float], calibration: dict, error: str = "") -> dict | None:
        now, status = now_iso(), "failed" if error else "completed"
        with self.connect() as connection:
            connection.execute(
                """INSERT INTO case_embeddings(case_id,case_version,model,retrieval_text,dimensions,vector,calibration,status,error,created_at,updated_at)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(case_id,case_version,model) DO UPDATE SET retrieval_text=excluded.retrieval_text,dimensions=excluded.dimensions,vector=excluded.vector,calibration=excluded.calibration,status=excluded.status,error=excluded.error,updated_at=excluded.updated_at""",
                (case["id"], int(case.get("version", 1)), model, retrieval_text[:5000], len(vector), json.dumps(vector), json.dumps(calibration), status, error[:1000] or None, now, now),
            )
        return self.get_case_embedding(case["id"], int(case.get("version", 1)), model)

    def reset_embedding_indexes(self) -> dict:
        """Remove only derived vectors/matches so a new embedding model can rebuild them safely."""
        now = now_iso()
        with self.connect() as connection:
            counts = {
                "article_embeddings": int(connection.execute("SELECT COUNT(*) FROM article_embeddings").fetchone()[0]),
                "case_embeddings": int(connection.execute("SELECT COUNT(*) FROM case_embeddings").fetchone()[0]),
                "press_release_chunks": int(connection.execute("SELECT COUNT(*) FROM press_release_chunks").fetchone()[0]),
                "matches": int(connection.execute("SELECT COUNT(*) FROM article_press_release_matches").fetchone()[0]),
            }
            connection.execute("DELETE FROM article_press_release_matches")
            connection.execute("DELETE FROM press_release_match_jobs")
            connection.execute("DELETE FROM article_embeddings")
            connection.execute("DELETE FROM case_embeddings")
            connection.execute("DELETE FROM press_release_chunks")
            connection.execute(
                """UPDATE press_releases SET embedding_status='pending',embedding_model='',
                   last_error=NULL,supabase_synced_at=NULL,updated_at=?""",
                (now,),
            )
        return counts

    def analysis_insights(self, case_id: str | None = None, organization_id: str | None = None, days: int = 7, sent_only: bool = False, delivery_only: bool = False, article_limit: int = 60, include_detail: bool = False, period_start: str | None = None, period_end: str | None = None, article_ids: list[str] | None = None) -> dict:
        days = max(1, min(90, int(days)))
        since = str(period_start or (datetime.now(KST) - timedelta(days=days)).isoformat(timespec="seconds"))
        article_limit = max(1, min(5000, int(article_limit)))
        join_params: list[Any] = []
        case_join = "LEFT JOIN case_evaluations ce ON ce.article_analysis_id=aa.id"
        # Dashboard periods follow news time, regardless of analysis queue delay.
        period_column = "COALESCE(a.published_at,a.first_seen_at)"
        where = ["aa.status='completed'", period_column + ">=?"]
        params: list[Any] = [since]
        if period_end:
            where.append(period_column + "<?")
            params.append(str(period_end))
        if case_id:
            # Each common analysis receives an evaluation row for every case. Only
            # candidate rows are related to this case; excluded rows previously made
            # the graph and word cloud identical across cases.
            case_join = "JOIN case_evaluations ce ON ce.article_analysis_id=aa.id AND ce.case_id=? AND ce.candidate_status='candidate'"
            join_params.append(case_id)
        if organization_id:
            where.append("aa.organization_id=?"); params.append(organization_id)
        if article_ids is not None:
            selected_article_ids = list(dict.fromkeys(str(article_id) for article_id in article_ids if str(article_id)))
            if selected_article_ids:
                where.append("a.id IN (" + ",".join("?" for _ in selected_article_ids) + ")")
                params.extend(selected_article_ids)
            else:
                where.append("1=0")
        if sent_only:
            # 신경망은 해당 케이스에 최근 기간 안에 실제 발송 성공한 기사만 사용한다.
            where.append("EXISTS (SELECT 1 FROM deliveries d WHERE d.article_id=aa.article_id AND d.case_id=ce.case_id AND d.status='sent' AND COALESCE(d.sent_at,d.updated_at)>=?)")
            params.append(since)
        if delivery_only:
            # 대시보드 화두는 발송 대상(send)으로 확정된 기사만 사용한다.
            where.append("EXISTS (SELECT 1 FROM case_evaluations delivery_case WHERE delivery_case.article_analysis_id=aa.id AND delivery_case.decision='send')")
        detail_fields = "a.body,MAX(e.vector) vector," if include_detail else "'' body,'' vector,"
        detail_join = "LEFT JOIN article_embeddings e ON e.article_analysis_id=aa.id AND e.status='completed'" if include_detail else ""
        sql = f"""SELECT aa.id,a.id article_id,aa.summary,aa.article_type,aa.tone,aa.classification_tags,aa.entities,aa.topic_concepts,aa.analyzed_at,
                         a.title,a.snippet,{detail_fields}a.publisher,a.published_at,a.original_url,a.image_url,
                         MAX(COALESCE(ce.final_score,0)) score,
                         MAX(CASE WHEN ce.decision='send' THEN 1 ELSE 0 END) matched
                  FROM article_analyses aa JOIN articles a ON a.id=aa.article_id
                  {detail_join}
                  {case_join}
                  WHERE {' AND '.join(where)} GROUP BY aa.id ORDER BY COALESCE(aa.analyzed_at,aa.updated_at) DESC LIMIT ?"""
        selected_case = self.get_case(case_id) if case_id else None
        selected_organization = self.get_organization(organization_id or (selected_case or {}).get("organization_id", "")) if (organization_id or (selected_case or {}).get("organization_id")) else None
        with self.connect() as connection:
            rows = connection.execute(sql, (*join_params, *params, article_limit)).fetchall()
        insight_items = [dict(row) for row in rows]
        # Keep the newest seed set, but place every in-scope member of each seed
        # bundle beside it. A plain first-60 slice left almost every counterpart
        # outside the graph and made valid stored groups look disconnected.
        seed_article_ids = [str(item.get("article_id") or "") for item in insight_items[:60]]
        graph_groups = self.article_similarity_groups(seed_article_ids)
        seed_group_ids = [
            str(group.get("group_id") or "") for group in graph_groups.values()
            if group.get("group_id") and int(group.get("size") or 1) > 1
        ]
        graph_groups.update(self.article_similarity_group_members(seed_group_ids))
        insight_buckets: list[list[dict]] = []
        insight_bucket_by_key: dict[str, list[dict]] = {}
        for item in insight_items:
            article_id = str(item.get("article_id") or "")
            group = graph_groups.get(article_id, {})
            group_id = str(group.get("group_id") or "")
            key = "group:" + group_id if group_id and int(group.get("size") or 1) > 1 else "article:" + article_id
            if key not in insight_bucket_by_key:
                insight_bucket_by_key[key] = []
                insight_buckets.append(insight_bucket_by_key[key])
            insight_bucket_by_key[key].append(item)
        ordered_insight_items = [item for bucket in insight_buckets for item in bucket]
        # The cloud remains strict: only source-verifiable noun/proper-noun phrases are counted.
        stop = {"기사","보도","관련","대한","통해","위해","이번","정부","기관","정책","발표","지원","추진","확대","강화","현장","오늘","최근","관계자","있다","있어","있으며","했다","한다","된다","위한","위해","것으로","따라","대해","에서","으로","까지","또한","사실전달","부정적","긍정적","분류대기","정책행정","정치입법","경제산업","사회안전","재난환경","과학기술","디지털","기타"}
        identity_terms = [str((selected_organization or {}).get("name") or ""), *((selected_organization or {}).get("abbreviations") or []), *((selected_organization or {}).get("former_names") or []), *((selected_organization or {}).get("people") or [])]
        for value in identity_terms:
            clean = str(value).strip()
            if clean:
                stop.add(clean)
        words: dict[str, float] = {}; word_sources: dict[str, dict[str, Any]] = {}; word_tones: dict[str, dict[str, int]] = {}
        nodes, topic_terms_by_id, concepts_by_id, vectors_by_id = [], {}, {}, {}
        for item in ordered_insight_items:
            entities = json_value(item.get("entities"), [])
            text = " ".join([str(item.get("title") or ""), str(item.get("snippet") or ""), str(item.get("body") or "")])
            weight = 1.0 + min(1.0, float(item.get("score") or 0) / 100.0) + (0.35 if item.get("matched") else 0)
            concept_source = " ".join([str(item.get("title") or ""), str(item.get("snippet") or "")])
            topic_terms = verified_content_nouns(entities, text, stop, identity_terms)
            if not topic_terms:
                topic_terms = inferred_content_nouns(concept_source, stop, identity_terms)
            stored_concepts = [str(value).strip()[:60] for value in json_value(item.get("topic_concepts"), []) if str(value).strip()]
            # Historical body extraction can contain unrelated recommendation/footer text.
            # Use title + search snippet for deterministic backfill; new analyses use stored LLM concepts.
            concepts = list(dict.fromkeys(stored_concepts))[:4] or inferred_topic_concepts(concept_source)
            vector = json_value(item.get("vector"), [])
            if isinstance(vector, list) and vector and all(isinstance(value, (int, float)) for value in vector):
                vectors_by_id[str(item["id"])] = [float(value) for value in vector]
            for clean in topic_terms:
                words[clean] = words.get(clean, 0) + 1
                tone_counts = word_tones.setdefault(clean, {"negative": 0, "positive": 0, "neutral": 0})
                tone = str(item.get("tone") or "사실전달")
                tone_key = "negative" if tone == "부정적" else ("positive" if tone == "긍정적" else "neutral")
                tone_counts[tone_key] += 1
                image_url = str(item.get("image_url") or "").strip()
                title = str(item.get("title") or "").strip()
                source_priority = (2.0 if image_url else 0.0) + (1.0 if clean.casefold() in title.casefold() else 0.0) + min(1.0, float(item.get("score") or 0) / 100.0)
                previous = word_sources.get(clean)
                if previous is None or source_priority > float(previous.get("priority") or 0):
                    word_sources[clean] = {
                        "priority": source_priority,
                        "image_url": image_url,
                        "article_title": title[:160],
                        "article_url": str(item.get("original_url") or "").strip(),
                    }
            if len(nodes) >= 60:
                continue
            topic_terms_by_id[str(item["id"])] = set(topic_terms)
            concepts_by_id[str(item["id"])] = set(concepts)
            nodes.append({"id": str(item["id"]), "article_id": str(item.get("article_id") or ""), "label": str(item.get("title") or "")[:42], "summary": str(item.get("summary") or "")[:500], "entities": entities, "topics": topic_terms, "topic_concepts": concepts, "semantic_vector": vectors_by_id.get(str(item["id"]), []), "published_at": item.get("published_at") or "", "article_type": item.get("article_type") or "기타", "tone": item.get("tone") or "사실전달", "score": round(float(item.get("score") or 0), 1), "matched": bool(item.get("matched"))})
        topic_frequency: dict[str, int] = {}
        for terms in topic_terms_by_id.values():
            for term in terms:
                topic_frequency[term] = topic_frequency.get(term, 0) + 1
        dimensions = {len(vector) for vector in vectors_by_id.values()}
        semantic_vectors = vectors_by_id if len(dimensions) == 1 and len(vectors_by_id) >= 3 else {}
        centroid = []
        if semantic_vectors:
            vector_length = next(iter(dimensions))
            centroid = [sum(vector[index] for vector in semantic_vectors.values()) / len(semantic_vectors) for index in range(vector_length)]
        candidate_edges = []
        topic_items = list(topic_terms_by_id.items())
        node_count = len(topic_items)
        # As the graph grows, weak common-context similarities create one giant blob.
        # Keep edges only when article-to-article similarity is strong enough.
        semantic_min = max(0.0, min(1.0, float(self.get_setting("similar_article_threshold", "65")) / 100.0))
        concept_semantic_min = max(0.48, semantic_min - 0.08)
        direct_noun_min = 0.42 if node_count >= 35 else 0.36
        fallback_noun_min = 0.58 if node_count >= 35 else 0.50
        # Similarity is precomputed by the background snapshot worker. Build the
        # lighter cross-bundle topic network from inverted indexes instead of an
        # O(n²) embedding scan on every user request.
        node_by_id = {str(node["id"]): node for node in nodes}
        article_id_by_node = {str(node["id"]): str(node.get("article_id") or node["id"]) for node in nodes}
        indexed_edges: dict[tuple[str, str], dict] = {}

        def add_indexed_edge(left_id: str, right_id: str, term: str, relation_level: str, weight: float) -> None:
            if left_id == right_id:
                return
            left_group = str(graph_groups.get(article_id_by_node.get(left_id, left_id), {}).get("group_id") or "")
            right_group = str(graph_groups.get(article_id_by_node.get(right_id, right_id), {}).get("group_id") or "")
            if left_group and left_group == right_group:
                return
            source, target = sorted((left_id, right_id))
            key = (source, target)
            edge = indexed_edges.setdefault(key, {
                "source": source, "target": target, "weight": weight,
                "relation_level": relation_level, "noun_similarity": weight if relation_level == "direct_topic" else 0.0,
                "semantic_similarity": 0.0, "shared_topics": [], "shared_concepts": [], "rank_score": weight,
            })
            edge["weight"] = max(float(edge["weight"]), weight)
            edge["rank_score"] = max(float(edge["rank_score"]), weight)
            if relation_level == "direct_topic":
                edge["relation_level"] = "direct_topic"
                edge["noun_similarity"] = max(float(edge["noun_similarity"]), weight)
                if term not in edge["shared_topics"]:
                    edge["shared_topics"].append(term)
            elif term not in edge["shared_concepts"]:
                edge["shared_concepts"].append(term)

        concept_index: dict[str, list[str]] = {}
        topic_index: dict[str, list[str]] = {}
        for node_id, concepts in concepts_by_id.items():
            for concept in concepts:
                concept_index.setdefault(concept, []).append(node_id)
        for node_id, topics in topic_terms_by_id.items():
            for topic in topics:
                topic_index.setdefault(topic, []).append(node_id)
        for term, member_ids in concept_index.items():
            unique_ids = list(dict.fromkeys(member_ids))
            if not 2 <= len(unique_ids) <= 8:
                continue
            ordered_ids = sorted(unique_ids, key=lambda node_id: (-float(node_by_id.get(node_id, {}).get("score") or 0), node_id))
            for member_id in ordered_ids[1:6]:
                add_indexed_edge(ordered_ids[0], member_id, term, "abstract_topic", 0.68)
        for term, member_ids in topic_index.items():
            unique_ids = list(dict.fromkeys(member_ids))
            if len(str(term).strip()) < 3 or not 2 <= len(unique_ids) <= 5:
                continue
            ordered_ids = sorted(unique_ids, key=lambda node_id: (-float(node_by_id.get(node_id, {}).get("score") or 0), node_id))
            for member_id in ordered_ids[1:5]:
                add_indexed_edge(ordered_ids[0], member_id, term, "direct_topic", 0.64)
        candidate_edges = list(indexed_edges.values())
        # Avoid a fully connected hairball: each abstract concept uses its most semantically
        # central real article as the hub. No synthetic node is introduced.
        edge_lookup = {tuple(sorted((edge["source"], edge["target"]))): edge for edge in candidate_edges}
        selected_keys = {key for key, edge in edge_lookup.items() if edge["relation_level"] == "direct_topic"}
        concept_groups: dict[str, set[str]] = {}
        for article_id, concepts in concepts_by_id.items():
            for concept in concepts:
                concept_groups.setdefault(concept, set()).add(article_id)
        for article_ids in concept_groups.values():
            if len(article_ids) < 2:
                continue
            candidates = []
            for article_id in sorted(article_ids):
                scores = [edge_lookup[key]["rank_score"] for other_id in article_ids if other_id != article_id
                          if (key := tuple(sorted((article_id, other_id)))) in edge_lookup]
                candidates.append((sum(scores) / max(1, len(scores)), article_id))
            hub_id = max(candidates, key=lambda item: (item[0], item[1]))[1]
            for article_id in article_ids:
                if article_id != hub_id:
                    key = tuple(sorted((hub_id, article_id)))
                    if key in edge_lookup:
                        selected_keys.add(key)
        # For concept-free semantic relations retain only the two strongest neighbors per node.
        semantic_only = [edge for edge in candidate_edges if not edge["shared_concepts"] and edge["relation_level"] == "abstract_topic" and edge["semantic_similarity"] >= semantic_min]
        for article_id in topic_terms_by_id:
            neighbors = sorted((edge for edge in semantic_only if article_id in (edge["source"], edge["target"])),
                               key=lambda edge: (-edge["rank_score"], edge["source"], edge["target"]))[:1]
            selected_keys.update(tuple(sorted((edge["source"], edge["target"]))) for edge in neighbors)
        # Final pruning: keep only the strongest local article similarities.
        # This prevents one weak bridge from pulling unrelated topics into a single mass.
        parent = {node["id"]: node["id"] for node in nodes}
        component_size = {node["id"]: 1 for node in nodes}

        def find(value: str) -> str:
            while parent[value] != value:
                parent[value] = parent[parent[value]]
                value = parent[value]
            return value

        def union(left: str, right: str) -> None:
            left_root, right_root = find(left), find(right)
            if left_root == right_root:
                return
            if component_size[left_root] < component_size[right_root]:
                left_root, right_root = right_root, left_root
            parent[right_root] = left_root
            component_size[left_root] += component_size[right_root]

        max_component = 14 if len(nodes) >= 45 else (12 if len(nodes) >= 25 else 10)
        degree_limit = 2 if len(nodes) >= 25 else 3
        edge_limit = min(70, max(16, int(len(nodes) * 1.15)))
        edges = []
        degree: dict[str, int] = {}
        proposed_edges = sorted((edge_lookup[key] for key in selected_keys),
                                key=lambda item: (-item["weight"], -item.get("semantic_similarity", 0), -item.get("noun_similarity", 0), item["source"], item["target"]))
        for edge in proposed_edges:
            source, target = edge["source"], edge["target"]
            strong_duplicate = float(edge.get("weight") or 0) >= 0.94 and float(edge.get("semantic_similarity") or 0) >= 0.70
            current_degree_limit = degree_limit + (1 if strong_duplicate else 0)
            if degree.get(source, 0) >= current_degree_limit or degree.get(target, 0) >= current_degree_limit:
                continue
            source_root, target_root = find(source), find(target)
            merged_size = component_size[source_root] if source_root == target_root else component_size[source_root] + component_size[target_root]
            if source_root != target_root and merged_size > max_component and not strong_duplicate:
                continue
            item = dict(edge)
            item.pop("rank_score", None)
            edges.append(item)
            degree[source] = degree.get(source, 0) + 1
            degree[target] = degree.get(target, 0) + 1
            union(source, target)
            if len(edges) >= edge_limit:
                break
        # Read the last complete snapshot. New articles remain temporarily ungrouped
        # until the background worker atomically publishes the next snapshot.
        shared_groups = graph_groups
        bundles: dict[str, list[str]] = {}
        for node in nodes:
            group = shared_groups.get(node.get("article_id") or node["id"], {})
            node["similar_group_id"] = group.get("group_id", "")
            node["similar_group_size"] = int(group.get("size") or 1)
            node["similar_group_basis"] = group.get("basis", "")
            node["similar_group_topics"] = group.get("topics", [])
            node["similar_group_concepts"] = group.get("concepts", [])
            node["similar_group_score"] = float(group.get("score") or 0)
            node.pop("semantic_vector", None)
            node.pop("published_at", None)
            if node["similar_group_id"] and node["similar_group_size"] > 1:
                bundles.setdefault(node["similar_group_id"], []).append(node["id"])
        network_parent = {node["id"]: node["id"] for node in nodes}
        def network_find(value: str) -> str:
            while network_parent[value] != value:
                network_parent[value] = network_parent[network_parent[value]]
                value = network_parent[value]
            return value
        def network_union(left: str, right: str) -> None:
            left_root, right_root = network_find(left), network_find(right)
            if left_root != right_root:
                network_parent[right_root] = left_root
        for edge in edges:
            network_union(edge["source"], edge["target"])
        known_pairs = {tuple(sorted((edge["source"], edge["target"]))) for edge in edges}
        bridge_edges = []
        article_id_by_node = {node["id"]: str(node.get("article_id") or node["id"]) for node in nodes}
        for members in bundles.values():
            head = members[0]
            for member in members[1:]:
                key = tuple(sorted((head, member)))
                if key in known_pairs or network_find(head) == network_find(member):
                    continue
                group = shared_groups.get(article_id_by_node.get(member, member), {})
                bridge_edges.append({"source": head, "target": member,
                                     "weight": round(float(group.get("score") or 0) / 100, 4),
                                     "relation_level": "bundle_bridge",
                                     "noun_similarity": round(float(group.get("noun_score") or 0) / 100, 4),
                                     "semantic_similarity": round(float(group.get("semantic_score") or 0) / 100, 4),
                                     "shared_topics": group.get("topics", []),
                                     "shared_concepts": group.get("concepts", [])})
                known_pairs.add(key)
                network_union(head, member)
        edges = sorted(edges + bridge_edges, key=lambda item: (-item["weight"], item["source"], item["target"]))
        all_concepts = sorted({concept for concepts in concepts_by_id.values() for concept in concepts})
        return {"period_days": days, "sent_only": bool(sent_only), "delivery_only": bool(delivery_only), "similarity_basis": "strict_article_similarity",
                "edge_thresholds": {"semantic_min": round(semantic_min, 2), "raw_evidence_min": round(max(0.86, semantic_min), 2), "concept_semantic_min": round(concept_semantic_min, 2), "direct_noun_min": round(direct_noun_min, 2), "degree_limit": degree_limit, "max_component": max_component},
                "article_count": len(rows), "graph_article_count": len(nodes), "group_count": len(bundles), "grouped_article_count": sum(len(members) for members in bundles.values()), "grouping_version": SIMILARITY_GROUPING_VERSION,
                "topic_node_count": sum(bool(terms) for terms in topic_terms_by_id.values()), "abstract_topic_count": len(all_concepts), "semantic_vector_count": len(semantic_vectors),
                "words": [{"label": key, "value": round(value, 1),
                           "image_url": word_sources.get(key, {}).get("image_url", ""),
                           "article_title": word_sources.get(key, {}).get("article_title", ""),
                           "article_url": word_sources.get(key, {}).get("article_url", ""),
                           "tone_counts": word_tones.get(key, {"negative": 0, "positive": 0, "neutral": 0})}
                          for key, value in sorted(words.items(), key=lambda pair: (-pair[1], pair[0]))[:35]],
                "nodes": nodes, "edges": edges, "delivery_trends": self.case_delivery_trends((selected_organization or {}).get("id") or None, 14)}

    def case_delivery_trends(self, organization_id: str | None = None, days: int = 14) -> dict:
        days = max(1, min(31, int(days)))
        today = datetime.now(KST).date()
        dates = [today - timedelta(days=days - index - 1) for index in range(days)]
        since = datetime.combine(dates[0], datetime.min.time(), tzinfo=KST).isoformat(timespec="seconds")
        case_where, case_params = ["c.is_active=1"], []
        delivery_where, delivery_params = ["d.status='sent'", "COALESCE(d.sent_at,d.updated_at,d.created_at)>=?"], [since]
        if organization_id:
            case_where.append("c.organization_id=?"); case_params.append(organization_id)
            delivery_where.append("c.organization_id=?"); delivery_params.append(organization_id)
        with self.connect() as connection:
            cases = connection.execute("SELECT c.id,c.name FROM cases c WHERE " + " AND ".join(case_where) + " ORDER BY c.sort_order,c.name", case_params).fetchall()
            rows = connection.execute(
                """SELECT d.case_id,SUBSTR(COALESCE(d.sent_at,d.updated_at,d.created_at),1,10) day,
                          COUNT(DISTINCT d.article_id) article_count
                   FROM deliveries d JOIN cases c ON c.id=d.case_id
                   WHERE """ + " AND ".join(delivery_where) + " GROUP BY d.case_id,day",
                delivery_params).fetchall()
        values = {(str(row["case_id"]), str(row["day"])): int(row["article_count"] or 0) for row in rows}
        series = []
        for item in cases:
            case_id = str(item["id"])
            points = [values.get((case_id, day.isoformat()), 0) for day in dates]
            series.append({"id": case_id, "name": str(item["name"]), "values": points, "total": sum(points)})
        return {"period_days": days, "dates": [day.isoformat() for day in dates], "series": series}

    def pipeline_stats(self, case_id: str | None = None, organization_id: str | None = None) -> dict:
        """Current queue plus today's completed/failed counts, reset at 00:00 KST."""
        day_start = kst_day_start_iso()
        cache_key = ("pipeline_stats_v1", str(case_id or ""), str(organization_id or ""), day_start)
        cache_marker = self._database_change_marker()
        cached_stats = self._pipeline_summary_cache_get(cache_key, cache_marker)
        if cached_stats is not None:
            return cached_stats
        speed_reset_at = str(self.get_setting("pipeline_speed_reset_at", "") or "")
        speed_start = speed_reset_at if speed_reset_at and speed_reset_at > day_start else day_start
        error_reset_at = str(self.get_setting("pipeline_error_reset_at", "") or "")
        error_start = error_reset_at if error_reset_at and error_reset_at > day_start else day_start
        latest_case = "ce.id IN (SELECT evaluation_id FROM article_case_processing_flags) AND EXISTS (SELECT 1 FROM cases active_case WHERE active_case.id=ce.case_id AND active_case.is_active=1)"
        common_scope, common_params = "", []
        if organization_id:
            common_scope, common_params = " AND aa.organization_id=?", [organization_id]
        case_scope, case_params = "", []
        if case_id:
            case_scope, case_params = " AND ce.case_id=?", [case_id]
        elif organization_id:
            case_scope, case_params = " AND aa.organization_id=?", [organization_id]
        with self.connect() as connection:
            common = connection.execute(
                "SELECT aa.status,COUNT(*) value FROM article_analyses aa JOIN article_processing_flags apf ON apf.analysis_id=aa.id "
                "WHERE (aa.status IN ('pending','processing') OR COALESCE(aa.analyzed_at,aa.updated_at)>=?)" +
                common_scope + " GROUP BY aa.status",
                [day_start, *common_params],
            ).fetchall()
            cases = connection.execute(
                "SELECT ce.status,COUNT(*) value FROM case_evaluations ce "
                "JOIN article_analyses aa ON aa.id=ce.article_analysis_id "
                "WHERE " + latest_case +
                " AND (ce.status IN ('pending','processing') OR COALESCE(ce.completed_at,ce.updated_at)>=?)" +
                case_scope + " GROUP BY ce.status",
                [day_start, *case_params],
            ).fetchall()
            jobs = connection.execute(
                "SELECT j.status,COUNT(*) value FROM article_analysis_jobs j "
                "JOIN article_analyses aa ON aa.id=j.article_analysis_id JOIN article_processing_flags apf ON apf.analysis_id=aa.id "
                "WHERE (j.status IN ('pending','processing') OR COALESCE(j.finished_at,j.queued_at)>=?)" +
                common_scope + " GROUP BY j.status",
                [day_start, *common_params],
            ).fetchall()
            case_jobs = connection.execute(
                "SELECT j.status,COUNT(*) value FROM case_evaluation_jobs j "
                "JOIN case_evaluations ce ON ce.id=j.case_evaluation_id "
                "JOIN article_analyses aa ON aa.id=ce.article_analysis_id "
                "WHERE " + latest_case +
                " AND (j.status IN ('pending','processing') OR COALESCE(j.finished_at,j.queued_at)>=?)" +
                case_scope + " GROUP BY j.status",
                [day_start, *case_params],
            ).fetchall()
            common_error_row = connection.execute(
                "SELECT "
                "COALESCE(SUM(CASE WHEN j.status IN ('pending','failed') AND COALESCE(j.error,'') NOT IN ('','worker_restarted') THEN 1 ELSE 0 END),0) current_errors "
                "FROM article_analysis_jobs j "
                "JOIN article_analyses aa ON aa.id=j.article_analysis_id JOIN article_processing_flags apf ON apf.analysis_id=aa.id "
                "WHERE (j.status IN ('pending','processing') OR COALESCE(j.finished_at,j.started_at,j.queued_at)>=?)" + common_scope,
                [day_start, *common_params],
            ).fetchone()
            case_error_row = connection.execute(
                "SELECT "
                "COALESCE(SUM(CASE WHEN j.status IN ('pending','failed') AND COALESCE(j.error,'') NOT IN ('','worker_restarted') THEN 1 ELSE 0 END),0) current_errors "
                "FROM case_evaluation_jobs j "
                "JOIN case_evaluations ce ON ce.id=j.case_evaluation_id "
                "JOIN article_analyses aa ON aa.id=ce.article_analysis_id "
                "WHERE " + latest_case +
                " AND (j.status IN ('pending','processing') OR COALESCE(j.finished_at,j.started_at,j.queued_at)>=?)" + case_scope,
                [day_start, *case_params],
            ).fetchone()
            common_api_error_row = connection.execute(
                "SELECT COUNT(*) total_errors FROM llm_api_calls WHERE provider='groq' AND stage='common' AND status='failed' AND created_at>=?",
                (error_start,),
            ).fetchone()
            case_api_error_row = connection.execute(
                "SELECT COUNT(*) total_errors FROM llm_api_calls WHERE provider='openrouter' AND stage='case' AND status='failed' AND created_at>=?",
                (error_start,),
            ).fetchone()
            embedding_error_row = connection.execute(
                "SELECT COUNT(*) total_errors FROM llm_api_calls WHERE provider='ollama' AND stage='embedding' AND status='failed' AND created_at>=?",
                (error_start,),
            ).fetchone()
            embedding = connection.execute(
                "SELECT COALESCE(SUM(CASE WHEN e.article_analysis_id IS NULL THEN 1 ELSE 0 END),0) pending,"
                " 0 processing,COALESCE(SUM(CASE WHEN e.status='completed' AND e.updated_at>=? THEN 1 ELSE 0 END),0) completed,"
                " COALESCE(SUM(CASE WHEN e.status='failed' AND e.updated_at>=? THEN 1 ELSE 0 END),0) failed "
                "FROM article_analyses aa JOIN article_processing_flags apf ON apf.analysis_id=aa.id "
                "LEFT JOIN article_embeddings e ON e.article_analysis_id=aa.id WHERE aa.status='completed'" + common_scope,
                [day_start, day_start, *common_params],
            ).fetchone()
            flow = connection.execute(
                """WITH article_flow AS (
                     SELECT aa.id,aj.queued_at,e.updated_at embedding_at,
                            MAX(COALESCE(ce.completed_at,ce.updated_at)) case_at,
                            COUNT(ce.id) case_count,
                            SUM(CASE WHEN ce.status IN ('pending','processing') THEN 1 ELSE 0 END) unfinished
                     FROM article_processing_flags apf JOIN article_analyses aa ON aa.id=apf.analysis_id
                     JOIN article_analysis_jobs aj ON aj.article_analysis_id=aa.id
                     JOIN article_embeddings e ON e.article_analysis_id=aa.id
                     LEFT JOIN article_case_processing_flags acpf ON acpf.article_id=aa.article_id
                     LEFT JOIN cases flow_case ON flow_case.id=acpf.case_id AND flow_case.is_active=1
                     LEFT JOIN case_evaluations ce ON ce.id=acpf.evaluation_id AND flow_case.id IS NOT NULL
                     WHERE aj.status='completed' AND e.status='completed'
                       AND aj.queued_at>=?
                       AND (?='' OR ce.case_id=?) AND (?='' OR aa.organization_id=?)
                     GROUP BY aa.id,aj.queued_at,e.updated_at
                   ), completed_flow AS (
                     SELECT queued_at,CASE WHEN case_at>embedding_at THEN case_at ELSE embedding_at END finalized_at
                     FROM article_flow WHERE case_count>0 AND unfinished=0
                   )
                   SELECT COUNT(*) processed_articles,
                          COALESCE(AVG(MAX(0,(julianday(finalized_at)-julianday(queued_at))*86400.0)),0) average_seconds
                   FROM completed_flow WHERE finalized_at>=?""",
                (speed_start, str(case_id or ""), str(case_id or ""), str(organization_id or ""), str(organization_id or ""), speed_start),
            ).fetchone()
            title = connection.execute(
                """SELECT a.title FROM article_analysis_jobs j JOIN article_analyses aa ON aa.id=j.article_analysis_id JOIN articles a ON a.id=aa.article_id WHERE j.status='processing'
                   UNION ALL SELECT a.title FROM case_evaluation_jobs j JOIN case_evaluations ce ON ce.id=j.case_evaluation_id JOIN articles a ON a.id=ce.article_id WHERE j.status='processing' LIMIT 1"""
            ).fetchone()
        def counts(rows): return {str(row["status"]): int(row["value"]) for row in rows}
        common_counts, case_counts, job_counts, case_job_counts = counts(common), counts(cases), counts(jobs), counts(case_jobs)
        def error_counts(row, api_row=None, current_fallback=0):
            data = dict(row) if row else {}
            api_data = dict(api_row) if api_row else {}
            return {
                "failed_current": int(data.get("current_errors") or current_fallback or 0),
                "failed_total": int(api_data.get("total_errors") or 0),
            }
        common_job_errors = error_counts(common_error_row, common_api_error_row, job_counts.get("failed", 0))
        case_job_errors = error_counts(case_error_row, case_api_error_row, case_job_counts.get("failed", 0))
        embedding_counts = {key: int(embedding[key] or 0) for key in ("pending", "processing", "completed", "failed")}
        embedding_counts["failed_current"] = embedding_counts.get("failed", 0)
        embedding_counts["failed_total"] = max(embedding_counts.get("failed", 0), int(embedding_error_row["total_errors"] or 0) if embedding_error_row else 0)
        job_counts.update(common_job_errors)
        case_job_counts.update(case_job_errors)
        result = {"common": common_counts, "cases": case_counts, "article_jobs": job_counts, "embedding": embedding_counts, "case_jobs": case_job_counts,
            "pending": job_counts.get("pending", 0) + case_job_counts.get("pending", 0),
            "processing": job_counts.get("processing", 0) + case_job_counts.get("processing", 0),
            "completed": job_counts.get("completed", 0) + case_job_counts.get("completed", 0),
            "failed": job_counts.get("failed", 0) + case_job_counts.get("failed", 0),
            "total": int(flow["processed_articles"] or 0), "processed_articles": int(flow["processed_articles"] or 0),
            "average_seconds": round(float(flow["average_seconds"] or 0), 2),
            "processing_title": str(title["title"]) if title else "", "period": "KST day",
            "day_start": day_start, "speed_start": speed_start, "speed_reset_at": speed_reset_at,
            "error_start": error_start, "error_reset_at": error_reset_at}
        self._pipeline_summary_cache_set(cache_key, self._database_change_marker(), result)
        return result

    def _hydrate_dashboard_group_scope(self, articles: list[dict]) -> None:
        """Load group-only body/vector data for the bounded new-article fallback."""
        analysis_ids = [str(article.get("analysis_id") or "") for article in articles if str(article.get("analysis_id") or "")]
        if not analysis_ids:
            return
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT aa.id analysis_id,a.title,a.snippet,substr(a.body,1,1800) source_body,aa.summary,ae.vector article_vector "
                "FROM article_analyses aa JOIN articles a ON a.id=aa.article_id "
                "LEFT JOIN article_embeddings ae ON ae.article_analysis_id=aa.id AND ae.status='completed' "
                "WHERE aa.id IN (" + ",".join("?" for _ in analysis_ids) + ")",
                analysis_ids,
            ).fetchall()
        source = {str(row["analysis_id"]): dict(row) for row in rows}
        for article in articles:
            row = source.get(str(article.get("analysis_id") or ""), {})
            article["semantic_vector"] = json_value(row.get("article_vector"), [])
            article["_group_text"] = " ".join(
                str(row.get(key) or "") for key in ("title", "snippet", "source_body", "summary")
            )[:12000]

    def editorial_article_groups(self, articles: list[dict], organization_id: str | None = None) -> dict[str, dict]:
        """Conservative, explainable groups used by user-facing article lists."""
        if len(articles) < 2:
            return {}
        generic = {"정부", "정책", "발표", "지원", "추진", "확대", "강화", "관련", "기사", "보도", "안전", "관리", "현장", "사업", "지역", "행정안전부", "행안부", "윤호중"}
        evidence: dict[str, set[str]] = {}
        titles: dict[str, str] = {}
        order: dict[str, int] = {}
        for index, article in enumerate(articles):
            article_id = str(article.get("id") or "")
            if not article_id:
                continue
            values = [*(article.get("entities") or []), *(article.get("topic_concepts") or [])]
            evidence[article_id] = {str(value).strip().casefold() for value in values if len(str(value).strip()) >= 3 and str(value).strip().casefold() not in generic}
            titles[article_id] = "".join(character for character in str(article.get("title") or "").casefold() if not character.isspace() and not character.isdigit())
            order[article_id] = index
        parent = {article_id: article_id for article_id in order}
        def find(value: str) -> str:
            while parent[value] != value:
                parent[value] = parent[parent[value]]
                value = parent[value]
            return value
        def union(left: str, right: str) -> None:
            left_root, right_root = find(left), find(right)
            if left_root != right_root:
                parent[right_root] = left_root
        article_ids = list(order)
        for index, left_id in enumerate(article_ids):
            for right_id in article_ids[index + 1:]:
                shared = evidence.get(left_id, set()) & evidence.get(right_id, set())
                if len(shared) >= 2 or (len(titles.get(left_id, "")) >= 6 and titles[left_id] == titles.get(right_id, "")):
                    union(left_id, right_id)
        components: dict[str, list[str]] = {}
        for article_id in article_ids:
            components.setdefault(find(article_id), []).append(article_id)
        result: dict[str, dict] = {}
        for members in components.values():
            if len(members) < 2:
                continue
            representative = min(members, key=lambda article_id: order[article_id])
            common = set.intersection(*(evidence[article_id] for article_id in members)) if all(evidence[article_id] for article_id in members) else set()
            for article_id in members:
                result[article_id] = {"group_id": representative, "size": len(members), "basis": "editorial", "status": "finalized", "score": 100.0 if titles.get(article_id) == titles.get(representative) else 90.0, "semantic_score": 0.0, "noun_score": 90.0, "topics": sorted(common)[:5], "concepts": sorted(common)[:4]}
        return result

    def _dashboard_article_groups(self, articles: list[dict], organization_id: str | None = None, case_id: str | None = None, threshold_override: float | None = None) -> dict[str, dict]:
        """Use the shared similarity engine for dashboard, neural graph and magazine."""
        if len(articles) < 2:
            return {}
        if threshold_override is None:
            try:
                threshold = float(self.get_setting("similar_article_threshold", "65")) / 100.0
            except (TypeError, ValueError):
                threshold = 0.65
        else:
            threshold = float(threshold_override)
        selected_case = self.get_case(case_id) if case_id else None
        organization_key = organization_id or (selected_case or {}).get("organization_id", "")
        selected_organization = self.get_organization(organization_key) if organization_key else None
        identity_terms = [
            str((selected_organization or {}).get("name") or ""),
            *((selected_organization or {}).get("abbreviations") or []),
            *((selected_organization or {}).get("former_names") or []),
            *((selected_organization or {}).get("people") or []),
        ]
        stop = {"기사","보도","관련","대한","통해","위해","이번","정부","기관","정책","발표","지원","추진","확대","강화","현장","오늘","최근","관계자","있다","있어","있으며","했다","한다","된다","위한","것으로","따라","대해","에서","으로","까지","또한","사실전달","부정적","긍정적","분류대기","정책행정","정치입법","경제산업","사회안전","재난환경","과학기술","디지털","기타","행정안전부","행안부"}
        return build_article_similarity_groups(
            articles,
            threshold=threshold,
            identity_terms=identity_terms,
            stopwords=stop,
            noun_extractor=verified_content_nouns,
            concept_inferer=inferred_topic_concepts,
            noun_similarity_fn=topic_noun_similarity,
            centered_similarity_fn=centered_semantic_similarity,
        )

    def _legacy_dashboard_article_groups(self, articles: list[dict], organization_id: str | None = None, case_id: str | None = None) -> dict[str, dict]:
        """Build dashboard article bundles with the same strictness used by the neural graph.

        The first pass works with verified nouns/topic concepts. When article embeddings are
        available, centered semantic similarity upgrades the temporary keyword bundle into a
        finalized hybrid/semantic bundle. No remote LLM call is made here.
        """
        if len(articles) < 2:
            return {}
        try:
            threshold = max(0.0, min(1.0, float(self.get_setting("similar_article_threshold", "65")) / 100.0))
        except Exception:
            threshold = 0.65
        selected_case = self.get_case(case_id) if case_id else None
        selected_organization = self.get_organization(organization_id or (selected_case or {}).get("organization_id", "")) if (organization_id or (selected_case or {}).get("organization_id")) else None
        stop = {"기사","보도","관련","대한","통해","위해","이번","정부","기관","정책","발표","지원","추진","확대","강화","현장","오늘","최근","관계자","있다","있어","있으며","했다","한다","된다","위한","것으로","따라","대해","에서","으로","까지","또한","사실전달","부정적","긍정적","분류대기","정책행정","정치입법","경제산업","사회안전","재난환경","과학기술","디지털","기타","행정안전부","행안부"}
        identity_terms = [str((selected_organization or {}).get("name") or ""), *((selected_organization or {}).get("abbreviations") or []), *((selected_organization or {}).get("former_names") or []), *((selected_organization or {}).get("people") or [])]
        for value in identity_terms:
            clean = str(value).strip()
            if clean:
                stop.add(clean)
        topic_terms_by_id: dict[str, set[str]] = {}
        concepts_by_id: dict[str, set[str]] = {}
        vectors_by_id: dict[str, list[float]] = {}
        order = {str(article.get("id")): index for index, article in enumerate(articles)}
        published_days: dict[str, object] = {}
        for article in articles:
            article_id = str(article.get("id") or "")
            if not article_id:
                continue
            try:
                published_days[article_id] = datetime.fromisoformat(str(article.get("published_at") or article.get("first_seen_at") or "").replace("Z", "+00:00")).date()
            except (TypeError, ValueError):
                pass
            text = str(article.get("_group_text") or " ".join([str(article.get("title") or ""), str(article.get("summary") or "")]))
            entities = article.get("entities") if isinstance(article.get("entities"), list) else []
            topic_terms_by_id[article_id] = set(verified_content_nouns(entities, text, stop, identity_terms))
            stored_concepts = [str(value).strip()[:60] for value in article.get("topic_concepts", []) if str(value).strip()] if isinstance(article.get("topic_concepts"), list) else []
            concept_source = " ".join([str(article.get("title") or ""), str(article.get("summary") or "")])
            concepts_by_id[article_id] = set(list(dict.fromkeys(stored_concepts))[:4] or inferred_topic_concepts(concept_source))
            vector = article.get("semantic_vector") if isinstance(article.get("semantic_vector"), list) else []
            if vector and all(isinstance(value, (int, float)) for value in vector):
                vectors_by_id[article_id] = [float(value) for value in vector]
        topic_frequency: dict[str, int] = {}
        for terms in topic_terms_by_id.values():
            for term in terms:
                topic_frequency[term] = topic_frequency.get(term, 0) + 1
        dimensions = {len(vector) for vector in vectors_by_id.values()}
        semantic_vectors = vectors_by_id if len(dimensions) == 1 and len(vectors_by_id) >= 3 else {}
        centroid: list[float] = []
        if semantic_vectors:
            vector_length = next(iter(dimensions))
            centroid = [sum(vector[index] for vector in semantic_vectors.values()) / len(semantic_vectors) for index in range(vector_length)]
        ids = [str(article.get("id")) for article in articles if article.get("id")]
        node_count = len(ids)
        semantic_min = threshold
        concept_semantic_min = max(0.48, semantic_min - 0.08)
        direct_noun_min = 0.42 if node_count >= 35 else 0.36
        fallback_noun_min = 0.58 if node_count >= 35 else 0.50
        candidate_edges: list[dict] = []
        for index, left_id in enumerate(ids):
            left_topics = topic_terms_by_id.get(left_id, set())
            for right_id in ids[index + 1:]:
                right_topics = topic_terms_by_id.get(right_id, set())
                shared_topics = left_topics & right_topics
                shared_concepts = concepts_by_id.get(left_id, set()) & concepts_by_id.get(right_id, set())
                noun_similarity = topic_noun_similarity(left_topics, right_topics, topic_frequency, max(1, node_count))
                semantic_similarity = 0.0
                has_semantic = bool(centroid and left_id in semantic_vectors and right_id in semantic_vectors)
                if has_semantic:
                    semantic_similarity = centered_semantic_similarity(semantic_vectors[left_id], semantic_vectors[right_id], centroid)
                left_day, right_day = published_days.get(left_id), published_days.get(right_id)
                if left_day and right_day and abs((left_day - right_day).days) > 14 and semantic_similarity < 0.88:
                    continue
                semantic_strong = has_semantic and semantic_similarity >= semantic_min
                concept_supported = bool(shared_concepts) and ((has_semantic and semantic_similarity >= concept_semantic_min) or noun_similarity >= direct_noun_min)
                direct_supported = bool(shared_topics) and (
                    (has_semantic and semantic_similarity >= max(0.34, semantic_min - 0.18) and noun_similarity >= 0.22)
                    or (not has_semantic and noun_similarity >= fallback_noun_min)
                    or noun_similarity >= max(0.50, direct_noun_min + 0.10)
                )
                if not (semantic_strong or concept_supported or direct_supported):
                    continue
                if semantic_strong and not (shared_topics or shared_concepts):
                    basis = "semantic"
                elif has_semantic:
                    basis = "hybrid"
                else:
                    basis = "keyword"
                weight = max(noun_similarity, 0.62 if concept_supported else 0.0, semantic_similarity if has_semantic else 0.0)
                candidate_edges.append({"source": left_id, "target": right_id, "weight": round(weight, 4), "basis": basis,
                                        "status": "finalized" if has_semantic else "temporary",
                                        "noun_similarity": round(noun_similarity, 4), "semantic_similarity": round(semantic_similarity, 4),
                                        "shared_topics": sorted(shared_topics, key=lambda term: (-len(term), term))[:5],
                                        "shared_concepts": sorted(shared_concepts)[:4],
                                        "rank_score": round(max(0.0, semantic_similarity if has_semantic else 0.0) + noun_similarity * 0.25 + (0.08 if concept_supported else 0.0), 4),
                                        "relation_level": "abstract_topic" if semantic_strong or concept_supported else "direct_topic"})
        if not candidate_edges:
            return {}
        edge_lookup = {tuple(sorted((edge["source"], edge["target"]))): edge for edge in candidate_edges}
        selected_keys = {key for key, edge in edge_lookup.items() if edge["relation_level"] == "direct_topic"}
        concept_groups: dict[str, set[str]] = {}
        for article_id, concepts in concepts_by_id.items():
            for concept in concepts:
                concept_groups.setdefault(concept, set()).add(article_id)
        for article_ids in concept_groups.values():
            if len(article_ids) < 2:
                continue
            candidates = []
            for article_id in sorted(article_ids):
                scores = [edge_lookup[key]["rank_score"] for other_id in article_ids if other_id != article_id
                          if (key := tuple(sorted((article_id, other_id)))) in edge_lookup]
                candidates.append((sum(scores) / max(1, len(scores)), article_id))
            hub_id = max(candidates, key=lambda item: (item[0], -order.get(item[1], 999999)))[1]
            for article_id in article_ids:
                key = tuple(sorted((hub_id, article_id)))
                if article_id != hub_id and key in edge_lookup:
                    selected_keys.add(key)
        semantic_only = [edge for edge in candidate_edges if not edge["shared_concepts"] and edge["relation_level"] == "abstract_topic" and edge["semantic_similarity"] >= semantic_min]
        for article_id in ids:
            neighbors = sorted((edge for edge in semantic_only if article_id in (edge["source"], edge["target"])),
                               key=lambda edge: (-edge["rank_score"], edge["source"], edge["target"]))[:1]
            selected_keys.update(tuple(sorted((edge["source"], edge["target"]))) for edge in neighbors)
        parent = {article_id: article_id for article_id in ids}
        component_size = {article_id: 1 for article_id in ids}
        group_edges: list[dict] = []
        degree: dict[str, int] = {}

        def find(value: str) -> str:
            while parent[value] != value:
                parent[value] = parent[parent[value]]
                value = parent[value]
            return value

        def union(left: str, right: str) -> None:
            left_root, right_root = find(left), find(right)
            if left_root == right_root:
                return
            if component_size[left_root] < component_size[right_root]:
                left_root, right_root = right_root, left_root
            parent[right_root] = left_root
            component_size[left_root] += component_size[right_root]

        max_component = 14 if node_count >= 45 else (12 if node_count >= 25 else 10)
        degree_limit = 2 if node_count >= 25 else 3
        edge_limit = min(70, max(16, int(node_count * 1.15)))
        proposed_edges = sorted((edge_lookup[key] for key in selected_keys),
                                key=lambda item: (-item["weight"], -item.get("semantic_similarity", 0), -item.get("noun_similarity", 0), order.get(item["source"], 999999), order.get(item["target"], 999999)))
        for edge in proposed_edges:
            source, target = edge["source"], edge["target"]
            strong_duplicate = float(edge.get("weight") or 0) >= 0.94 and float(edge.get("semantic_similarity") or 0) >= 0.70
            current_degree_limit = degree_limit + (1 if strong_duplicate else 0)
            if degree.get(source, 0) >= current_degree_limit or degree.get(target, 0) >= current_degree_limit:
                continue
            source_root, target_root = find(source), find(target)
            merged_size = component_size[source_root] if source_root == target_root else component_size[source_root] + component_size[target_root]
            if source_root != target_root and merged_size > max_component and not strong_duplicate:
                continue
            group_edges.append(edge)
            degree[source] = degree.get(source, 0) + 1
            degree[target] = degree.get(target, 0) + 1
            union(source, target)
            if len(group_edges) >= edge_limit:
                break
        components: dict[str, list[str]] = {}
        for article_id in ids:
            components.setdefault(find(article_id), []).append(article_id)
        # The edge pass above is deliberately conservative: it limits node degree and
        # component size so a broad subject cannot turn into one giant bundle. That
        # can leave a small, genuinely related bundle (or a single article) beside the
        # main bundle. Compare those bundles once more, using their combined evidence,
        # and attach only when both the semantic signal and topic evidence agree.
        attachment_max_component = min(18, max_component + 4)

        def component_profile(members: list[str]) -> dict[str, object]:
            topics: set[str] = set()
            concepts: set[str] = set()
            vectors: list[list[float]] = []
            dates = []
            for member in members:
                topics.update(topic_terms_by_id.get(member, set()))
                concepts.update(concepts_by_id.get(member, set()))
                if member in semantic_vectors:
                    vectors.append(semantic_vectors[member])
                if member in published_days:
                    dates.append(published_days[member])
            vector: list[float] = []
            if vectors and len(vectors) == len(members) and len({len(value) for value in vectors}) == 1:
                vector = [sum(value[index] for value in vectors) / len(vectors) for index in range(len(vectors[0]))]
            return {"members": members, "topics": topics, "concepts": concepts, "vector": vector, "dates": dates}

        profiles = [(root, component_profile(members)) for root, members in components.items()]
        attachment_candidates: list[dict] = []
        attachment_semantic_min = max(0.72, semantic_min + 0.08)
        attachment_noun_min = max(0.42, direct_noun_min + 0.08)
        for left_index, (left_root, left_profile) in enumerate(profiles):
            left_members = left_profile["members"]
            for right_root, right_profile in profiles[left_index + 1:]:
                right_members = right_profile["members"]
                if min(len(left_members), len(right_members)) > 3 or len(left_members) + len(right_members) > attachment_max_component:
                    continue
                left_vector, right_vector = left_profile["vector"], right_profile["vector"]
                if not centroid or not left_vector or not right_vector:
                    continue
                semantic_similarity = centered_semantic_similarity(left_vector, right_vector, centroid)
                if semantic_similarity < attachment_semantic_min:
                    continue
                shared_topics = left_profile["topics"] & right_profile["topics"]
                shared_concepts = left_profile["concepts"] & right_profile["concepts"]
                noun_similarity = topic_noun_similarity(left_profile["topics"], right_profile["topics"], topic_frequency, max(1, node_count))
                supported = bool(shared_concepts) or len(shared_topics) >= 2 or noun_similarity >= attachment_noun_min
                if not supported:
                    continue
                left_dates, right_dates = left_profile["dates"], right_profile["dates"]
                if left_dates and right_dates and min(abs((left_day - right_day).days) for left_day in left_dates for right_day in right_dates) > 14 and semantic_similarity < 0.90:
                    continue
                if len(left_members) <= len(right_members):
                    small_root, large_root = left_root, right_root
                else:
                    small_root, large_root = right_root, left_root
                attachment_candidates.append({
                    "source": min(left_members, key=lambda article_id: order.get(article_id, 999999)),
                    "target": min(right_members, key=lambda article_id: order.get(article_id, 999999)),
                    "small_root": small_root, "large_root": large_root,
                    "weight": round(max(semantic_similarity, noun_similarity), 4), "basis": "hybrid", "status": "finalized",
                    "noun_similarity": round(noun_similarity, 4), "semantic_similarity": round(semantic_similarity, 4),
                    "shared_topics": sorted(shared_topics, key=lambda term: (-len(term), term))[:5],
                    "shared_concepts": sorted(shared_concepts)[:4],
                })
        attached_component_roots: set[str] = set()
        for edge in sorted(attachment_candidates, key=lambda item: (-item["weight"], -item["semantic_similarity"], -item["noun_similarity"], order.get(item["source"], 999999), order.get(item["target"], 999999))):
            small_root = edge["small_root"]
            if small_root in attached_component_roots or edge["large_root"] in attached_component_roots:
                continue
            source_root, target_root = find(edge["source"]), find(edge["target"])
            if source_root == target_root:
                continue
            if component_size[source_root] + component_size[target_root] > attachment_max_component:
                continue
            group_edges.append(edge)
            union(edge["source"], edge["target"])
            attached_component_roots.update((small_root, edge["large_root"]))
        components = {}
        for article_id in ids:
            components.setdefault(find(article_id), []).append(article_id)
        result: dict[str, dict] = {}
        edges_by_node: dict[str, list[dict]] = {}
        for edge in group_edges:
            edges_by_node.setdefault(edge["source"], []).append(edge)
            edges_by_node.setdefault(edge["target"], []).append(edge)
        for members in components.values():
            if len(members) < 2:
                continue
            representative = min(members, key=lambda article_id: order.get(article_id, 999999))
            member_edges = [edge for edge in group_edges if edge["source"] in members and edge["target"] in members]
            best = max(member_edges, key=lambda edge: (edge["weight"], edge.get("semantic_similarity", 0), edge.get("noun_similarity", 0))) if member_edges else {}
            basis_order = {"semantic": 3, "hybrid": 2, "keyword": 1}
            basis = max((edge.get("basis", "keyword") for edge in member_edges), key=lambda value: basis_order.get(value, 0), default="keyword")
            finalized = bool(member_edges) and all(edge.get("status") == "finalized" for edge in member_edges) and all(member in semantic_vectors for member in members)
            for member in members:
                nearest = max(edges_by_node.get(member, []), key=lambda edge: edge["weight"], default=best)
                result[member] = {"group_id": representative, "size": len(members), "basis": basis,
                                  "status": "finalized" if finalized else "temporary",
                                  "score": round(float((nearest or best).get("weight") or 0) * 100, 1),
                                  "semantic_score": round(float((nearest or best).get("semantic_similarity") or 0) * 100, 1),
                                  "noun_score": round(float((nearest or best).get("noun_similarity") or 0) * 100, 1),
                                  "topics": (nearest or best).get("shared_topics", []), "concepts": (nearest or best).get("shared_concepts", [])}
        return result

    def pipeline_dashboard(
        self,
        case_id: str | None = None,
        organization_id: str | None = None,
        tags: list[str] | None = None,
        limit: int = 100,
        offset: int = 0,
        search: str = "",
        include_groups: bool = True,
        delivery_filter: str = "all",
        days: int = 3650,
        include_press_stats: bool = True,
    ) -> dict:
        day_start = kst_day_start_iso()
        limit = min(10000, max(1, int(limit)))
        offset = max(0, int(offset))
        days = max(1, min(3650, int(days)))
        delivery_filter = delivery_filter if delivery_filter in {"all", "sent", "unsent"} else "all"
        where, params = [], []
        if organization_id:
            where.append("aa.organization_id=?"); params.append(organization_id)
        if case_id:
            where.append("ce.case_id=?"); params.append(case_id)
        where.append("COALESCE(a.published_at,a.first_seen_at)>=?")
        params.append((datetime.now(KST) - timedelta(days=days)).isoformat(timespec="seconds"))
        if delivery_filter != "all":
            delivery_where = "EXISTS (SELECT 1 FROM deliveries df WHERE df.article_id=a.id AND df.status='sent')"
            delivery_params: list[Any] = []
            if case_id:
                delivery_where = "EXISTS (SELECT 1 FROM deliveries df WHERE df.article_id=a.id AND df.case_id=? AND df.status='sent')"
                delivery_params.append(case_id)
            elif organization_id:
                delivery_where = "EXISTS (SELECT 1 FROM deliveries df JOIN cases dc ON dc.id=df.case_id WHERE df.article_id=a.id AND dc.organization_id=? AND df.status='sent')"
                delivery_params.append(organization_id)
            where.append(delivery_where if delivery_filter == "sent" else "NOT " + delivery_where)
            params.extend(delivery_params)
        for tag in tags or []:
            where.append("(aa.classification_tags LIKE ? OR aa.article_type=? OR aa.tone=?)")
            params.extend([f'%"{tag}"%', tag, tag])
        article_where, article_params = list(where), list(params)
        search = str(search or "").strip()[:100]
        if search:
            article_where.append(
                "(instr(lower(COALESCE(a.title,'')),lower(?))>0 "
                "OR instr(lower(COALESCE(a.publisher,'')),lower(?))>0 "
                "OR instr(lower(COALESCE(aa.publisher_name,'')),lower(?))>0 "
                "OR instr(lower(COALESCE(aa.reporter_name,'')),lower(?))>0 "
                "OR instr(lower(COALESCE(a.snippet,'')),lower(?))>0 "
                "OR instr(lower(COALESCE(a.body,'')),lower(?))>0 "
                "OR instr(lower(COALESCE(aa.summary,'')),lower(?))>0)"
            )
            article_params.extend([search] * 7)
        # The persisted map serves completed articles. Keep the broad dashboard
        # query lean; only the small missing fallback scope is hydrated below.
        source_body_expr = "''"
        press_stats_fields = "0 related_press_count,0 press_match_checked_count,0 press_match_total_count,"
        sql = f"""SELECT aa.id analysis_id,aa.status analysis_status,aa.summary,aa.publisher_name,aa.reporter_name,aa.article_type,aa.tone,aa.classification_tags,aa.entities,aa.topic_concepts,aa.evidence,aa.model,aa.error analysis_error,aa.analyzed_at,
                                    a.id,a.title,a.original_url,a.publisher source_publisher,a.published_at,a.first_seen_at,a.snippet source_snippet,a.image_url,{source_body_expr} source_body,'' article_vector,
                                    CASE WHEN EXISTS (
                                      SELECT 1 FROM article_analysis_jobs turbo_common
                                      WHERE turbo_common.article_analysis_id=aa.id AND turbo_common.provider_lane='burst'
                                    ) OR EXISTS (
                                      SELECT 1 FROM case_evaluation_jobs turbo_case_job
                                      JOIN case_evaluations turbo_case ON turbo_case.id=turbo_case_job.case_evaluation_id
                                      WHERE turbo_case.article_analysis_id=aa.id AND turbo_case_job.provider_lane='burst'
                                    ) THEN 1 ELSE 0 END turbo_used,
                                    {press_stats_fields}
                                    ce.id evaluation_id,ce.case_id,ce.status evaluation_status,ce.candidate_status,ce.keyword_score,ce.semantic_raw,ce.semantic_score,ce.llm_score,ce.final_score,ce.evidence_status,ce.reasons,ce.low_score_categories,ce.analysis_report evaluation_report,ce.error evaluation_error,ce.decision,ce.completed_at,ce.updated_at evaluation_updated_at,
                                    c.name case_name,o.name organization_name
                                    FROM article_processing_flags apf
                                    JOIN article_analyses aa ON aa.id=apf.analysis_id JOIN articles a ON a.id=aa.article_id
                                    LEFT JOIN article_case_processing_flags acpf ON acpf.article_id=a.id AND EXISTS (SELECT 1 FROM cases active_case WHERE active_case.id=acpf.case_id AND active_case.is_active=1)
                                    LEFT JOIN case_evaluations ce ON ce.id=acpf.evaluation_id
                                    LEFT JOIN cases c ON c.id=ce.case_id LEFT JOIN organizations o ON o.id=aa.organization_id"""
        if article_where: sql += " WHERE " + " AND ".join(article_where)
        article_sql_base = sql
        article_order_sql = " ORDER BY COALESCE(a.published_at,a.first_seen_at) DESC,COALESCE(aa.analyzed_at,aa.updated_at) DESC,COALESCE(c.sort_order,999999),COALESCE(c.created_at,''),COALESCE(ce.updated_at,aa.updated_at) DESC LIMIT ?"
        sql = article_sql_base + article_order_sql
        delivery_scope, delivery_params = "", []
        completion_scope, completion_params = "", []
        if case_id:
            delivery_scope, delivery_params = " AND d.case_id=?", [case_id]
            completion_scope, completion_params = " AND c.id=?", [case_id]
        elif organization_id:
            delivery_scope, delivery_params = " AND c.organization_id=?", [organization_id]
            completion_scope, completion_params = " AND c.organization_id=?", [organization_id]
        with self.connect() as connection:
            # One article can have several case-evaluation rows. Fetch enough rows
            # to build this page plus one article for the has_more marker.
            row_limit = min(10000, max(120, (offset + limit + 31) * 12))
            rows = list(connection.execute(sql, (*article_params, row_limit)).fetchall())
            snapshot_groups: dict[str, dict] = {}
            if include_groups and rows:
                seed_article_ids = list(dict.fromkeys(str(row["id"]) for row in rows if row["id"]))
                snapshot_groups = self.article_similarity_groups(seed_article_ids)
                seed_group_ids = [
                    str(group.get("group_id") or "") for group in snapshot_groups.values()
                    if group.get("group_id") and int(group.get("size") or 1) > 1
                ]
                member_groups = self.article_similarity_group_members(seed_group_ids)
                snapshot_groups.update(member_groups)
                missing_member_ids = [article_id for article_id in member_groups if article_id not in set(seed_article_ids)]
                if missing_member_ids:
                    marks = ",".join("?" for _ in missing_member_ids)
                    member_sql = article_sql_base + (" AND " if article_where else " WHERE ") + f"a.id IN ({marks})" + article_order_sql
                    member_row_limit = min(10000, max(120, len(missing_member_ids) * 20))
                    extra_rows = connection.execute(
                        member_sql, (*article_params, *missing_member_ids, member_row_limit)
                    ).fetchall()
                    known_rows = {(str(row["analysis_id"]), str(row["evaluation_id"] or "")) for row in rows}
                    for row in extra_rows:
                        key = (str(row["analysis_id"]), str(row["evaluation_id"] or ""))
                        if key not in known_rows:
                            rows.append(row)
                            known_rows.add(key)
            daily_sql = """SELECT
                    COUNT(DISTINCT CASE WHEN aa.analyzed_at>=? OR COALESCE(ce.completed_at,ce.updated_at)>=? THEN a.id END) total,
                    COALESCE(SUM(CASE WHEN COALESCE(ce.completed_at,ce.updated_at)>=? AND ce.decision='send' THEN 1 ELSE 0 END),0) sent_candidates,
                    COALESCE(SUM(CASE WHEN COALESCE(ce.completed_at,ce.updated_at)>=? AND ce.decision IN ('low','excluded') THEN 1 ELSE 0 END),0) low,
                    COALESCE(AVG(CASE WHEN ce.completed_at>=? AND ce.status='completed' THEN ce.final_score END),0) average_score
                  FROM article_processing_flags apf
                  JOIN article_analyses aa ON aa.id=apf.analysis_id JOIN articles a ON a.id=aa.article_id
                  LEFT JOIN article_case_processing_flags acpf ON acpf.article_id=a.id AND EXISTS (SELECT 1 FROM cases active_case WHERE active_case.id=acpf.case_id AND active_case.is_active=1)
                  LEFT JOIN case_evaluations ce ON ce.id=acpf.evaluation_id
                  LEFT JOIN cases c ON c.id=ce.case_id LEFT JOIN organizations o ON o.id=aa.organization_id"""
            if where:
                daily_sql += " WHERE " + " AND ".join(where)
            daily_stats_row = connection.execute(
                daily_sql, (day_start, day_start, day_start, day_start, day_start, *params)
            ).fetchone()
            delivery_rows = connection.execute(
                "SELECT d.article_id,d.case_id,d.status,COUNT(*) value FROM deliveries d JOIN cases c ON c.id=d.case_id WHERE 1=1"
                + delivery_scope + " GROUP BY d.article_id,d.case_id,d.status",
                delivery_params,
            ).fetchall()
            delivery_total_rows = connection.execute(
                "SELECT d.status,COUNT(*) value FROM deliveries d JOIN cases c ON c.id=d.case_id "
                "WHERE (d.status IN ('pending','retry') OR COALESCE(d.sent_at,d.updated_at)>=?)"
                + delivery_scope + " GROUP BY d.status",
                [day_start, *delivery_params],
            ).fetchall()
            completed_article_daily_row = connection.execute(
                """WITH completed_articles AS (
                       SELECT aa.article_id,MAX(COALESCE(ce.completed_at,ce.updated_at)) completed_at
                       FROM article_processing_flags apf
                       JOIN article_analyses aa ON aa.id=apf.analysis_id AND aa.status='completed'
                       JOIN article_case_processing_flags acpf ON acpf.article_id=aa.article_id AND acpf.analysis_id=aa.id
                       JOIN cases c ON c.id=acpf.case_id AND c.is_active=1
                       JOIN case_evaluations ce ON ce.id=acpf.evaluation_id
                       WHERE 1=1""" + completion_scope + """
                       GROUP BY aa.article_id
                       HAVING COUNT(*)>0 AND SUM(CASE WHEN ce.status IN ('completed','excluded') THEN 0 ELSE 1 END)=0
                   ) SELECT COUNT(*) value FROM completed_articles WHERE completed_at>=?""",
                [*completion_params, day_start],
            ).fetchone()
            delivery_error_row = connection.execute(
                "SELECT "
                "COALESCE(SUM(CASE WHEN d.status IN ('retry','failed') AND COALESCE(d.last_error,'')<>'' THEN 1 ELSE 0 END),0) current_errors,"
                "COALESCE(SUM(CASE "
                "WHEN d.status='sent' THEN MAX(d.attempts-1,0) "
                "WHEN d.status IN ('retry','failed') THEN MAX(d.attempts,0) "
                "ELSE 0 END),0) total_errors "
                "FROM deliveries d JOIN cases c ON c.id=d.case_id "
                "WHERE (d.status IN ('pending','retry') OR COALESCE(d.sent_at,d.updated_at)>=?)"
                + delivery_scope,
                [day_start, *delivery_params],
            ).fetchone()
            recent_sent_rows = connection.execute(
                """SELECT a.id,a.title,a.original_url,MAX(d.sent_at) sent_at,
                          c.name AS case_name,o.name AS organization_name
                   FROM deliveries d JOIN articles a ON a.id=d.article_id
                   JOIN cases c ON c.id=d.case_id LEFT JOIN organizations o ON o.id=c.organization_id
                   WHERE d.status='sent'""" + delivery_scope +
                " GROUP BY a.id,d.case_id ORDER BY sent_at DESC LIMIT 6",
                delivery_params,
            ).fetchall()
        deliveries: dict[tuple[str, str], dict[str, int]] = {}
        delivery_totals = {str(row["status"]): int(row["value"]) for row in delivery_total_rows}
        delivery_error_data = dict(delivery_error_row) if delivery_error_row else {}
        delivery_totals["failed_current"] = int(delivery_error_data.get("current_errors") or delivery_totals.get("failed", 0) or 0)
        delivery_totals["failed_total"] = int(delivery_error_data.get("total_errors") or 0)
        for row in delivery_rows:
            status, value = str(row["status"]), int(row["value"])
            deliveries.setdefault((str(row["article_id"]), str(row["case_id"])), {})[status] = value
        grouped: dict[str, dict] = {}
        for row in rows:
            item = dict(row); analysis_id = item["analysis_id"]
            tags_value = json_value(item.get("classification_tags"), [])
            if tags and not all(tag in tags_value or tag == item.get("article_type") or tag == item.get("tone") for tag in tags):
                continue
            article = grouped.setdefault(analysis_id, {
                "id": item["id"], "analysis_id": analysis_id, "title": item["title"], "original_url": item["original_url"], "image_url": item.get("image_url") or "", "publisher": item.get("publisher_name") or item.get("source_publisher") or "", "source_publisher": item.get("source_publisher") or "", "reporter_name": item.get("reporter_name") or "", "published_at": item["published_at"], "first_seen_at": item["first_seen_at"], "turbo_used": bool(item.get("turbo_used")), "related_press_count": int(item.get("related_press_count") or 0),
                "press_match_checked_count": int(item.get("press_match_checked_count") or 0),
                "press_match_total_count": int(item.get("press_match_total_count") or 0),
                "semantic_vector": json_value(item.get("article_vector"), []),
                "topic_concepts": json_value(item.get("topic_concepts"), []),
                "_group_text": " ".join([str(item.get("title") or ""), str(item.get("source_snippet") or ""), str(item.get("source_body") or ""), str(item.get("summary") or "")])[:12000],
                "status": item["analysis_status"], "analyzed_at": item["analyzed_at"], "summary": item["summary"], "article_type": item["article_type"], "tone": item["tone"], "classification_tags": tags_value, "entities": json_value(item.get("entities"), []), "evidence": json_value(item.get("evidence"), []), "model": item["model"], "error": item["analysis_error"], "case_results": []})
            if item.get("evaluation_id"):
                result = {key: item.get(key) for key in ("evaluation_id", "case_id", "case_name", "organization_name", "evaluation_status", "candidate_status", "keyword_score", "semantic_raw", "semantic_score", "llm_score", "final_score", "evidence_status", "evaluation_error", "decision", "completed_at", "evaluation_updated_at")}
                report = json_value(item.get("evaluation_report"), {})
                categories = json_value(item.get("low_score_categories"), [])
                llm_error = bool(result.get("evaluation_status") == "failed" or result.get("evidence_status") in {"case_llm_unavailable", "llm_unavailable"} or "case_llm_unavailable" in categories or "llm_unavailable" in categories or (report.get("components") or {}).get("llm_error"))
                result["similarity_score"] = float(item.get("final_score") or 0)
                result["llm_status"] = "unavailable" if llm_error else str(result.get("evaluation_status") or "pending")
                result["llm_retry_needed"] = bool(llm_error or result.get("evaluation_status") in {"failed", "pending", "processing"})
                result["reasons"] = json_value(item.get("reasons"), [])
                result["low_score_categories"] = categories
                result["deliveries"] = deliveries.get((str(item["id"]), str(item["case_id"])), {})
                article["case_results"].append(result)
        # Grouping a single dashboard page made the result depend on scroll position:
        # two related articles on pages 1 and 2 were never compared. Build one bounded
        # scope first, then paginate whole bundles below.
        all_articles = list(grouped.values())
        for article in all_articles:
            results = article["case_results"]
            article["case_summary"] = {
                "total": len(results), "pending": sum(value.get("evaluation_status") in {"pending", "processing"} for value in results),
                "matched": sum(value.get("decision") == "send" for value in results),
                "candidate_excluded": sum(value.get("decision") == "excluded" or value.get("evaluation_status") == "excluded" for value in results),
                "delivery_excluded": sum(value.get("decision") == "low" for value in results), "excluded": sum(value.get("decision") in {"low", "excluded"} for value in results),
                "sent": sum(sum(value.get("deliveries", {}).get(status, 0) for status in ("sent",)) for value in results),
                "scheduled": sum(sum(value.get("deliveries", {}).get(status, 0) for status in ("pending", "retry")) for value in results),
            }
        similar_groups: dict[str, dict] = {}
        if include_groups:
            # DB-only snapshot read: no embedding hydration or similarity work is
            # allowed in the request path.
            similar_groups = snapshot_groups

        scoped_group_sizes: dict[str, int] = {}
        for article in all_articles:
            group = similar_groups.get(str(article.get("id") or ""), {})
            group_id = str(group.get("group_id") or "")
            if group_id and int(group.get("size") or 1) > 1:
                scoped_group_sizes[group_id] = scoped_group_sizes.get(group_id, 0) + 1

        for article in all_articles:
            group = similar_groups.get(str(article.get("id") or ""), {})
            group_id = str(group.get("group_id") or "")
            scoped_size = int(scoped_group_sizes.get(group_id, 0))
            article["similar_group_id"] = group_id if scoped_size > 1 else ""
            article["similar_group_size"] = scoped_size if scoped_size > 1 else 1
            article["similar_group_basis"] = group.get("basis", "")
            article["similar_group_status"] = group.get("status", "")
            article["similar_group_score"] = float(group.get("score") or 0)
            article["similar_group_topics"] = group.get("topics", [])
            article["similar_group_concepts"] = group.get("concepts", [])
            article.pop("_group_text", None)
        # Keep every bundle intact in the response. The client advances its offset by
        # the returned count, so its next request starts on a bundle boundary.
        buckets: list[list[dict]] = []
        bucket_by_key: dict[str, list[dict]] = {}
        for article in all_articles:
            article_id = str(article.get("id") or "")
            group_id = str(article.get("similar_group_id") or "")
            key = group_id if group_id and int(article.get("similar_group_size") or 1) > 1 else article_id
            if key not in bucket_by_key:
                bucket_by_key[key] = []
                buckets.append(bucket_by_key[key])
            bucket_by_key[key].append(article)
        page_buckets, consumed = [], 0
        for bucket in buckets:
            if consumed < offset:
                consumed += len(bucket)
                continue
            if page_buckets and sum(len(item) for item in page_buckets) >= limit:
                break
            page_buckets.append(bucket)
        articles = [article for bucket in page_buckets for article in bucket]
        if include_press_stats and articles:
            article_ids = [str(article["id"]) for article in articles]
            marks = ",".join("?" for _ in article_ids)
            try: threshold = float(self.get_setting("press_release_match_threshold", "65") or 65)
            except (TypeError, ValueError): threshold = 65.0
            version = self.get_setting("press_release_matcher_migration_version", "press-rag-v4-lite") or "press-rag-v4-lite"
            with self.connect() as connection:
                match_rows = connection.execute(f"""SELECT article_id,COALESCE(SUM(CASE WHEN is_related=1 AND similarity_score>=? AND matcher_version=? THEN 1 ELSE 0 END),0) related_count,COALESCE(SUM(CASE WHEN matcher_version=? THEN 1 ELSE 0 END),0) checked_count FROM article_press_release_matches WHERE article_id IN ({marks}) GROUP BY article_id""", (threshold, version, version, *article_ids)).fetchall()
                job_rows = connection.execute(f"SELECT article_id,COUNT(*) total_count FROM press_release_match_jobs WHERE article_id IN ({marks}) GROUP BY article_id", article_ids).fetchall()
            press_stats = {str(row["article_id"]): (int(row["related_count"] or 0), int(row["checked_count"] or 0)) for row in match_rows}
            press_totals = {str(row["article_id"]): int(row["total_count"] or 0) for row in job_rows}
            for article in articles:
                related_count, checked_count = press_stats.get(str(article["id"]), (0, 0))
                article["related_press_count"], article["press_match_checked_count"], article["press_match_total_count"] = related_count, checked_count, press_totals.get(str(article["id"]), 0)
        next_offset = offset + len(articles)
        has_more = next_offset < len(all_articles)
        stats = {"total": int(completed_article_daily_row["value"] or 0) if completed_article_daily_row else 0,
                 "sent_candidates": int(daily_stats_row["sent_candidates"] or 0),
                 "low": int(daily_stats_row["low"] or 0),
                 "average_score": round(float(daily_stats_row["average_score"] or 0), 1),
                 "period": "KST day", "day_start": day_start}
        publishers: dict[str, int] = {}; categories: dict[str, dict[str, int]] = {}; tag_counts: dict[str, int] = {}
        for item in articles:
            publishers[item.get("publisher") or "미확인"] = publishers.get(item.get("publisher") or "미확인", 0) + 1
            category = item.get("article_type") or "기타"; category_data = categories.setdefault(category, {"article_count": 0, "sent_count": 0}); category_data["article_count"] += 1; category_data["sent_count"] += item["case_summary"]["sent"]
            # The filter taxonomy must stay finite: one canonical topic plus one exclusive tone.
            # Free-form LLM detail tags and pending labels remain on articles but never grow this filter.
            topic, tone = item.get("article_type"), item.get("tone")
            filter_tags = [topic] if topic in DASHBOARD_TOPIC_TYPES else []
            if tone in DASHBOARD_TONES:
                filter_tags.append(tone)
            for tag in filter_tags:
                tag_counts[str(tag)] = tag_counts.get(str(tag), 0) + 1
        similar_article_threshold = max(0.0, min(100.0, float(self.get_setting("similar_article_threshold", "65"))))
        pipeline_stats = self.pipeline_stats(case_id, organization_id)
        return {"stats": stats, "articles": articles, "offset": offset, "next_offset": next_offset, "limit": limit, "has_more": has_more, "similar_article_threshold": similar_article_threshold,
            "publishers": [{"label": key, "value": value} for key, value in sorted(publishers.items(), key=lambda pair: -pair[1])[:10]],
            "categories": [{"label": key, **value} for key, value in sorted(categories.items(), key=lambda pair: -pair[1]["article_count"])],
            "tags": [{"label": key, "value": value} for key, value in sorted(tag_counts.items(), key=lambda pair: -pair[1])],
            "deliveries": [{"status": key, "value": value} for key, value in sorted(delivery_totals.items()) if key not in {"failed_current", "failed_total"}],
            "delivery_errors": {"failed_current": delivery_totals.get("failed_current", 0), "failed_total": delivery_totals.get("failed_total", 0)},
            "recent_sent": [dict(row) for row in recent_sent_rows], "recent_runs": [],
            "llm": pipeline_stats, "pipeline": pipeline_stats}

    def dashboard(
        self,
        case_id: str | None = None,
        organization_id: str | None = None,
        limit: int = 20,
        tags: list[str] | None = None,
    ) -> dict:
        filters, params = "", []
        if case_id:
            filters, params = "WHERE s.case_id=?", [case_id]
        elif organization_id:
            filters, params = (
                "WHERE s.case_id IN (SELECT id FROM cases WHERE organization_id=?)",
                [organization_id],
            )
        for tag in tags or []:
            filters += (" AND " if filters else "WHERE ") + "(s.classification_tags LIKE ? OR s.tone=?)"
            clean_tag = str(tag).replace("%", "")
            params.extend(["%" + clean_tag + "%", clean_tag])

        delivery_filter, delivery_params = "", []
        if case_id:
            delivery_filter, delivery_params = "WHERE d.case_id=?", [case_id]
        elif organization_id:
            delivery_filter, delivery_params = (
                "WHERE d.case_id IN (SELECT id FROM cases WHERE organization_id=?)",
                [organization_id],
            )
        recent_sent_filter = "WHERE d.status='sent'"
        recent_sent_params: list[Any] = []
        if case_id:
            recent_sent_filter += " AND d.case_id=?"
            recent_sent_params.append(case_id)
        elif organization_id:
            recent_sent_filter += " AND d.case_id IN (SELECT id FROM cases WHERE organization_id=?)"
            recent_sent_params.append(organization_id)

        with self.connect() as connection:
            articles = connection.execute(
                f"""SELECT a.id,a.title,a.original_url,a.publisher,a.published_at,a.first_seen_at,
                    s.case_id,s.keyword_score,s.semantic_score,s.llm_score,s.final_score,s.summary,
                    s.organization_tag,s.article_type,s.tone,s.evidence_status,s.classification_tags,s.reasons,s.low_score_categories,
                    s.decision,c.name AS case_name,o.name AS organization_name
                    FROM article_scores s JOIN articles a ON a.id=s.article_id
                    JOIN cases c ON c.id=s.case_id LEFT JOIN organizations o ON o.id=c.organization_id
                    {filters} ORDER BY s.created_at DESC,COALESCE(a.published_at,a.first_seen_at) DESC LIMIT ?""",
                (*params, min(10000, max(1, int(limit)))),
            ).fetchall()
            stats = connection.execute(
                f"""SELECT COUNT(*) total,
                    COALESCE(SUM(CASE WHEN decision='send' THEN 1 ELSE 0 END),0) sent_candidates,
                    COALESCE(SUM(CASE WHEN decision='hold' THEN 1 ELSE 0 END),0) held,
                    COALESCE(SUM(CASE WHEN decision='low' THEN 1 ELSE 0 END),0) low,
                    COALESCE(ROUND(AVG(final_score),1),0) average_score
                    FROM article_scores s {filters}""",
                params,
            ).fetchone()
            publishers = connection.execute(
                f"""SELECT a.publisher label,COUNT(*) value FROM article_scores s
                    JOIN articles a ON a.id=s.article_id {filters}
                    GROUP BY a.publisher ORDER BY value DESC LIMIT 10""",
                params,
            ).fetchall()
            categories = connection.execute(
                f"""SELECT COALESCE(NULLIF(s.article_type,''),'기타') label,COUNT(*) article_count,
                    COALESCE(SUM(CASE WHEN EXISTS(
                        SELECT 1 FROM deliveries d
                        WHERE d.article_id=s.article_id AND d.case_id=s.case_id AND d.status='sent'
                    ) THEN 1 ELSE 0 END),0) sent_count
                    FROM article_scores s {filters}
                    GROUP BY COALESCE(NULLIF(s.article_type,''),'기타')
                    ORDER BY article_count DESC,label LIMIT 15""",
                params,
            ).fetchall()
            tag_records = connection.execute(
                f"SELECT classification_tags,tone FROM article_scores s {filters}", params
            ).fetchall()
            deliveries = connection.execute(
                f"SELECT status,COUNT(*) value FROM deliveries d {delivery_filter} GROUP BY status",
                delivery_params,
            ).fetchall()
            recent_sent = connection.execute(
                f"""SELECT a.id,a.title,a.original_url,MAX(d.sent_at) sent_at,c.name AS case_name,
                    o.name AS organization_name,s.organization_tag,s.article_type
                    FROM deliveries d JOIN articles a ON a.id=d.article_id
                    JOIN cases c ON c.id=d.case_id LEFT JOIN organizations o ON o.id=c.organization_id
                    LEFT JOIN article_scores s ON s.article_id=d.article_id AND s.case_id=d.case_id
                    {recent_sent_filter}
                    GROUP BY a.id,d.case_id ORDER BY sent_at DESC LIMIT 6""",
                recent_sent_params,
            ).fetchall()
            recent_runs = connection.execute(
                "SELECT * FROM collection_runs ORDER BY started_at DESC LIMIT 10"
            ).fetchall()

        decoded = []
        for row in articles:
            item = dict(row)
            item["reasons"] = json_value(item["reasons"], [])
            item["low_score_categories"] = json_value(item["low_score_categories"], [])
            item["classification_tags"] = json_value(item["classification_tags"], [])
            decoded.append(item)
        tag_counts: dict[str, int] = {}
        for row in tag_records:
            values = list(dict.fromkeys([*json_value(row["classification_tags"], []), row["tone"]]))
            for tag in values:
                tag = str(tag).strip()
                if tag:
                    tag_counts[tag] = tag_counts.get(tag, 0) + 1
        return {
            "stats": dict(stats) if stats else {},
            "articles": decoded,
            "publishers": [dict(row) for row in publishers],
            "categories": [dict(row) for row in categories],
            "tags": [
                {"label": tag, "value": count}
                for tag, count in sorted(
                    tag_counts.items(),
                    key=lambda item: (
                        1,
                        {"사실전달": 0, "부정적": 1, "긍정적": 2}[item[0]],
                    )
                    if item[0] in {"사실전달", "부정적", "긍정적"}
                    else (0, -item[1], item[0]),
                )
            ],
            "deliveries": [dict(row) for row in deliveries],
            "recent_sent": [dict(row) for row in recent_sent],
            "recent_runs": [dict(row) for row in recent_runs],
            "llm": self.llm_processing_stats(case_id, organization_id),
        }

    def case_sent_keyword_suggestions(self, case_id: str, days: int = 30, limit: int = 5) -> dict:
        """Rank source-verifiable nouns in sent articles, excluding configured and common terms."""
        days = max(1, min(365, int(days)))
        limit = max(1, min(20, int(limit)))
        case = self.get_case(case_id)
        if not case:
            return {"days": days, "sent_articles": 0, "keywords": []}
        organization = self.get_organization(str(case.get("organization_id") or "")) if case.get("organization_id") else None
        identity_terms = [
            str((organization or {}).get("name") or ""),
            *((organization or {}).get("abbreviations") or []),
            *((organization or {}).get("former_names") or []),
            *((organization or {}).get("people") or []),
        ]
        configured_terms = [
            str(value).strip()
            for value in [*case.get("include_terms", []), *case.get("required_terms", [])]
            if str(value).strip()
        ]
        synonyms = case.get("synonym_terms") if isinstance(case.get("synonym_terms"), dict) else {}
        for values in synonyms.values():
            if isinstance(values, list):
                configured_terms.extend(str(value).strip() for value in values if str(value).strip())
        stopwords = {
            "기사", "보도", "관련", "대한", "통해", "위해", "이번", "정부", "기관", "정책", "발표",
            "지원", "추진", "확대", "강화", "현장", "오늘", "최근", "관계자", "사실전달", "부정적",
            "긍정적", "분류대기", "비판", "부정", "논란", "문제", "기타",
            *DASHBOARD_TOPIC_TYPES, *DASHBOARD_TONES, *configured_terms,
        }
        since = (datetime.now(KST) - timedelta(days=days)).isoformat(timespec="seconds")
        with self.connect() as connection:
            # Existing installations predate this index. Creating it is
            # idempotent and much cheaper than repeatedly scanning article
            # bodies while an administrator is viewing settings.
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_deliveries_case_status_sent_at "
                "ON deliveries(case_id, status, sent_at DESC, article_id)"
            )
            # A keyword preview does not need every historical sent article.
            # First select a bounded, newest-first delivery set, then fetch
            # the comparatively large article body only for that sample.
            rows = connection.execute(
                """WITH recent_sent AS (
                       SELECT article_id, MAX(sent_at) AS sent_at
                       FROM deliveries
                       WHERE case_id=? AND status='sent' AND sent_at>=?
                       GROUP BY article_id
                       ORDER BY sent_at DESC
                       LIMIT 80
                   )
                   SELECT a.id,a.title,a.snippet,a.body,aa.summary,aa.entities,recent_sent.sent_at
                   FROM recent_sent
                   JOIN articles a ON a.id=recent_sent.article_id
                   JOIN case_evaluations ce ON ce.article_id=recent_sent.article_id AND ce.case_id=?
                     AND ce.status='completed' AND ce.decision='send'
                   JOIN article_analyses aa ON aa.id=ce.article_analysis_id AND aa.status='completed'
                   ORDER BY recent_sent.sent_at DESC""",
                (case_id, since, case_id),
            ).fetchall()
        counts: dict[str, int] = {}
        configured_compact = [re.sub(r"\s+", "", value).casefold() for value in configured_terms]
        for row in rows:
            item = dict(row)
            article_text = " ".join([
                str(item.get("title") or ""), str(item.get("snippet") or ""),
                str(item.get("body") or ""), str(item.get("summary") or ""),
            ])
            terms = verified_content_nouns(json_value(item.get("entities"), []), article_text, stopwords, identity_terms)
            for term in set(terms):
                compact = re.sub(r"\s+", "", term).casefold()
                if any(value in compact or compact in value for value in configured_compact):
                    continue
                counts[term] = counts.get(term, 0) + 1
        keywords = [
            {"keyword": keyword, "count": count, "coverage_pct": round(count / max(1, len(rows)) * 100, 1)}
            for keyword, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:limit]
        ]
        return {"days": days, "sent_articles": len(rows), "keywords": keywords}

    @staticmethod
    def _operation_error_reason(error: str) -> str:
        lowered = str(error or "").casefold()
        if not lowered:
            return "오류 상세가 기록되지 않았습니다."
        if any(marker in lowered for marker in ("quota", "daily_soft_limit", "free-models-per-day", "token_soft_limit", "resource_exhausted", "allocation")):
            return "무료 사용량 또는 토큰 한도에 도달했습니다."
        if any(marker in lowered for marker in ("rate limit", "429", "too many requests")):
            return "제공자 요청 제한(rate limit)이 발생했습니다."
        if any(marker in lowered for marker in ("timeout", "timed out", "read timed")):
            return "모델 또는 외부 API 응답 시간이 초과되었습니다."
        if any(marker in lowered for marker in ("json", "parse", "schema")):
            return "모델 응답 형식이 기대한 JSON 구조와 맞지 않았습니다."
        if any(marker in lowered for marker in ("401", "403", "scope", "token", "reauthorize")):
            return "인증 권한 또는 토큰 상태 확인이 필요합니다."
        if any(marker in lowered for marker in ("connection", "network", "urlopen", "502", "503", "504")):
            return "외부 서비스 연결 또는 일시 장애가 발생했습니다."
        return str(error or "")[:180]

    @staticmethod
    def _operation_stage_label(stage: str) -> str:
        return {
            "common": "공통분석", "case": "케이스판정", "embedding": "임베딩",
            "moderation": "클린 AI", "delivery": "카카오 발송", "provider": "모델 전환",
            "collection": "기사 수집",
        }.get(str(stage or ""), str(stage or "기타"))

    @staticmethod
    def _operation_provider_label(provider: str) -> str:
        return {
            "groq": "Groq", "openrouter": "OpenRouter", "cloudflare": "Cloudflare Workers AI",
            "gemini": "Gemini", "ollama": "Ollama", "kakao": "Kakao",
        }.get(str(provider or ""), str(provider or ""))

    def operation_logs(self, days: int = 7, limit: int = 200) -> dict:
        days = max(1, min(30, int(days)))
        limit = max(1, min(1000, int(limit)))
        since = (datetime.now(KST) - timedelta(days=days)).isoformat(timespec="seconds")
        now = now_iso()
        events: list[dict[str, Any]] = []

        def append_event(kind: str, stage: str, title: str, message: str, occurred_at: str, **extra: Any) -> None:
            events.append({
                "kind": kind,
                "stage": stage,
                "stage_label": self._operation_stage_label(stage),
                "title": title,
                "message": str(message or "")[:1000],
                "occurred_at": occurred_at,
                "severity": extra.pop("severity", "warning"),
                **extra,
            })

        with self.connect() as connection:
            disabled_rows = connection.execute(
                "SELECT key,value,updated_at FROM app_settings WHERE key LIKE 'llm_provider_disabled_until:%' ORDER BY updated_at DESC"
            ).fetchall()
            disabled_reasons = {
                str(row["key"]).split(":", 1)[1]: str(row["value"] or "")
                for row in connection.execute("SELECT key,value FROM app_settings WHERE key LIKE 'llm_provider_disabled_reason:%'").fetchall()
            }
            quota_lock_meta: dict[str, dict[str, str]] = {}
            for row in connection.execute(
                "SELECT key,value FROM app_settings WHERE key LIKE 'llm_provider_lock_%:%'"
            ).fetchall():
                key, provider = str(row["key"]).split(":", 1)
                field = key.removeprefix("llm_provider_lock_")
                quota_lock_meta.setdefault(provider, {})[field] = str(row["value"] or "")
            api_rows = connection.execute(
                """SELECT failed.*,MIN(succeeded.created_at) resolved_at
                   FROM llm_api_calls failed
                   LEFT JOIN llm_api_calls succeeded
                     ON succeeded.provider=failed.provider AND succeeded.stage=failed.stage
                    AND succeeded.status='completed' AND succeeded.created_at>failed.created_at
                   WHERE failed.status='failed' AND failed.created_at>=?
                   GROUP BY failed.id
                   ORDER BY failed.created_at DESC LIMIT ?""",
                (since, limit),
            ).fetchall()
            case_rows = connection.execute(
                """SELECT j.id,j.status,j.provider,j.error,j.queued_at,j.started_at,j.finished_at,j.retry_after,j.attempts,
                          a.title article_title,c.name case_name
                   FROM case_evaluation_jobs j
                   JOIN case_evaluations ce ON ce.id=j.case_evaluation_id
                   JOIN articles a ON a.id=ce.article_id
                   JOIN cases c ON c.id=ce.case_id
                   WHERE COALESCE(j.error,'')<>'' AND COALESCE(j.finished_at,j.started_at,j.queued_at)>=?
                   ORDER BY COALESCE(j.finished_at,j.started_at,j.queued_at) DESC LIMIT ?""",
                (since, limit),
            ).fetchall()
            common_rows = connection.execute(
                """SELECT j.id,j.status,j.error,j.queued_at,j.started_at,j.finished_at,j.retry_after,j.attempts,a.title article_title
                   FROM article_analysis_jobs j
                   JOIN article_analyses aa ON aa.id=j.article_analysis_id
                   JOIN articles a ON a.id=aa.article_id
                   WHERE COALESCE(j.error,'')<>'' AND COALESCE(j.finished_at,j.started_at,j.queued_at)>=?
                   ORDER BY COALESCE(j.finished_at,j.started_at,j.queued_at) DESC LIMIT ?""",
                (since, limit),
            ).fetchall()
            delivery_rows = connection.execute(
                """SELECT d.id,d.status,d.last_error,d.response_code,d.updated_at,d.sent_at,d.attempts,a.title article_title,c.name case_name
                   FROM deliveries d JOIN articles a ON a.id=d.article_id JOIN cases c ON c.id=d.case_id
                   WHERE COALESCE(d.last_error,'')<>'' AND COALESCE(d.updated_at,d.created_at)>=?
                   ORDER BY COALESCE(d.updated_at,d.created_at) DESC LIMIT ?""",
                (since, limit),
            ).fetchall()

            for row in disabled_rows:
                provider = str(row["key"]).split(":", 1)[1]
                disabled_until = str(row["value"] or "")
                reason = disabled_reasons.get(provider, "")
                lock_meta = quota_lock_meta.get(provider, {})
                lock_mode = lock_meta.get("mode", "")
                if not disabled_until and not reason:
                    continue
                active = bool(disabled_until and disabled_until > now)
                occurred_at = str(row["updated_at"] or disabled_until or now)
                if not active and occurred_at < since:
                    continue
                append_event(
                    "provider_failover", "provider",
                    f"{self._operation_provider_label(provider)} 무료 사용량/토큰 소진 감지",
                    (("정확한 초기화 예측 시각까지 잠그고 예비 모델 체인으로 전환했습니다. " if lock_mode == "exact_reset" else "초기화 시각이 불확실해 1시간 잠그고 예비 모델 체인으로 전환했습니다. ") if active else "잠금 시각이 지나 공급자 사용량 재확인이 가능한 상태입니다. ")
                    + (f"원인: {self._operation_error_reason(reason)}" if reason else "원인 상세는 제공자 응답에 기록되지 않았습니다."),
                    occurred_at,
                    provider=provider, provider_label=self._operation_provider_label(provider),
                    status="active" if active else "resolved", resolved_at="" if active else disabled_until,
                    disabled_until=disabled_until, lock_mode=lock_mode,
                    lock_confidence=lock_meta.get("confidence", ""),
                    lock_reset_source=lock_meta.get("reset_source", ""),
                    raw_error=reason[:500], severity="critical" if active else "info",
                )

            for row in api_rows:
                item = dict(row)
                provider, stage, model = str(item.get("provider") or ""), str(item.get("stage") or ""), str(item.get("model") or "")
                resolved_at = str(item.get("resolved_at") or "")
                resolved = bool(resolved_at)
                reason = self._operation_error_reason(str(item.get("error") or ""))
                append_event(
                    "api_error", stage,
                    f"{self._operation_stage_label(stage)} API 호출 실패",
                    f"{self._operation_provider_label(provider)} {model} 호출에서 오류가 발생했습니다. 원인: {reason}"
                    + (" 이후 같은 단계 호출이 성공해 해소된 것으로 보입니다." if resolved else " 현재 로그상 후속 성공 기록은 아직 없습니다."),
                    str(item.get("created_at") or ""),
                    provider=provider, provider_label=self._operation_provider_label(provider), model=model,
                    status="resolved" if resolved else "open", resolved_at=resolved_at,
                    raw_error=str(item.get("error") or "")[:500], http_status=item.get("http_status"),
                    severity="warning" if resolved else "critical",
                )

        for row in case_rows:
            item = dict(row); error = str(item.get("error") or "")
            retry_after = str(item.get("retry_after") or "")
            resolved = item.get("status") == "completed"
            retrying = item.get("status") == "pending" and bool(retry_after)
            append_event(
                "case_job_error", "case", "케이스판정 작업 오류",
                f"'{item.get('case_name') or '케이스'}' 판정 중 '{str(item.get('article_title') or '')[:80]}' 기사에서 오류가 발생했습니다. 원인: {self._operation_error_reason(error)}"
                + (f" 재시도 예정: {retry_after}" if retrying else (" 완료 상태로 정리됐습니다." if resolved else " 확인 또는 재시도가 필요합니다.")),
                str(item.get("finished_at") or item.get("started_at") or item.get("queued_at") or ""),
                provider=str(item.get("provider") or ""), provider_label=self._operation_provider_label(str(item.get("provider") or "")),
                status="resolved" if resolved else ("retrying" if retrying else str(item.get("status") or "open")),
                resolved_at=str(item.get("finished_at") or "") if resolved else "", raw_error=error[:500], severity="warning" if retrying or resolved else "critical",
            )

        for row in common_rows:
            item = dict(row); error = str(item.get("error") or "")
            retry_after = str(item.get("retry_after") or "")
            retrying = item.get("status") == "pending" and bool(retry_after)
            append_event(
                "common_job_error", "common", "공통분석 작업 오류",
                f"'{str(item.get('article_title') or '')[:80]}' 기사 공통분석 중 오류가 발생했습니다. 원인: {self._operation_error_reason(error)}"
                + (f" 재시도 예정: {retry_after}" if retrying else " 확인 또는 재시도가 필요합니다."),
                str(item.get("finished_at") or item.get("started_at") or item.get("queued_at") or ""),
                status="retrying" if retrying else str(item.get("status") or "open"), raw_error=error[:500], severity="warning" if retrying else "critical",
            )

        for row in delivery_rows:
            item = dict(row); error = str(item.get("last_error") or "")
            sent = item.get("status") == "sent"
            append_event(
                "delivery_error", "delivery", "카카오 발송 오류",
                f"'{str(item.get('article_title') or '')[:80]}' 기사 발송 중 오류가 발생했습니다. 원인: {self._operation_error_reason(error)}"
                + (" 이후 발송 완료 상태입니다." if sent else " 재시도 또는 재동의가 필요할 수 있습니다."),
                str(item.get("updated_at") or item.get("sent_at") or ""),
                status="resolved" if sent else str(item.get("status") or "open"), raw_error=error[:500], http_status=item.get("response_code"),
                resolved_at=str(item.get("sent_at") or "") if sent else "", severity="warning" if sent else "critical",
            )

        events = sorted(events, key=lambda item: str(item.get("occurred_at") or ""), reverse=True)[:limit]
        summary: dict[str, int] = {"total": len(events), "open": 0, "retrying": 0, "resolved": 0, "critical": 0}
        for event in events:
            status = str(event.get("status") or "open")
            if status in summary:
                summary[status] += 1
            elif status == "active":
                summary["open"] += 1
            elif status not in {"resolved", "sent"}:
                summary["open"] += 1
            if event.get("severity") == "critical":
                summary["critical"] += 1
        return {"days": days, "limit": limit, "since": since, "summary": summary, "items": events}

    def low_score_analysis(self, case_id: str, days: int = 7) -> dict:
        since = (datetime.now(KST) - timedelta(days=days)).isoformat(timespec="seconds")
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT final_score,low_score_categories FROM article_scores WHERE case_id=? AND decision<>'send' AND created_at>=?",
                (case_id, since),
            ).fetchall()
        categories: dict[str, int] = {}
        for row in rows:
            for category in json_value(row["low_score_categories"], []):
                categories[category] = categories.get(category, 0) + 1
        average = sum(float(row["final_score"]) for row in rows) / len(rows) if rows else 0
        suggestions = []
        mapping = {
            "required_term_missing": "필수 키워드가 지나치게 제한적인지 확인하세요.",
            "excluded_term": "제외 키워드가 적절히 오탐을 제거하는지 사례를 검토하세요.",
            "title_only_match": "제목에만 등장하는 키워드의 본문 일치 조건을 강화하세요.",
            "low_semantic_similarity": "주제 설명에 구체적인 대상·행위·지역 표현을 추가하세요.",
            "body_unavailable": "본문 접근 제한 언론사는 검색 요약문 기준 별도 임계점을 고려하세요.",
        }
        for key, _count in sorted(categories.items(), key=lambda item: item[1], reverse=True)[:5]:
            if key in mapping:
                suggestions.append(mapping[key])
        return {
            "sample_count": len(rows), "average_score": round(average, 1),
            "categories": categories, "suggestions": suggestions,
            "sent_keyword_suggestions": self.case_sent_keyword_suggestions(case_id, days=30, limit=5),
        }

    def cleanup(self, raw_days: int, metadata_days: int) -> dict:
        raw_cutoff = (datetime.now(KST) - timedelta(days=raw_days)).isoformat(timespec="seconds")
        metadata_cutoff = (datetime.now(KST) - timedelta(days=metadata_days)).isoformat(timespec="seconds")
        with self.connect() as connection:
            raw = connection.execute("UPDATE articles SET body='',body_expires_at=NULL WHERE body<>'' AND first_seen_at<?", (raw_cutoff,)).rowcount
            meta = connection.execute(
                "DELETE FROM articles WHERE first_seen_at<? AND id NOT IN (SELECT article_id FROM deliveries WHERE status IN ('pending','retry'))",
                (metadata_cutoff,),
            ).rowcount
            connection.execute("DELETE FROM recipient_invites WHERE expires_at<?", (now_iso(),))
        return {"cleared_bodies": raw, "deleted_articles": meta}

    def cleanup_short_retention(self, analysis_days: int, source_days: int, article_limit: int,
                                press_limit: int, press_markdown_root: str | Path) -> dict:
        """Bounded cleanup for the 7-day analysis / 8-day source policy."""
        now = datetime.now(KST)
        analysis_cutoff = (now - timedelta(days=max(1, int(analysis_days)))).isoformat(timespec="seconds")
        source_cutoff = (now - timedelta(days=max(int(analysis_days), int(source_days)))).isoformat(timespec="seconds")
        article_limit = max(1, min(500, int(article_limit)))
        press_limit = max(1, min(100, int(press_limit)))
        root = Path(press_markdown_root)
        result: dict[str, Any] = {"analysis_cutoff": analysis_cutoff, "source_cutoff": source_cutoff}
        removed_paths: list[str] = []
        with self.connect() as connection:
            eligible = """first_seen_at<? AND id NOT IN (SELECT article_id FROM deliveries WHERE status IN ('pending','retry'))"""
            result["analysis_candidates"] = int(connection.execute(f"SELECT COUNT(*) FROM articles WHERE {eligible}", (analysis_cutoff,)).fetchone()[0])
            result["source_candidates"] = int(connection.execute(f"SELECT COUNT(*) FROM articles WHERE {eligible}", (source_cutoff,)).fetchone()[0])
            analysis_ids = [str(row[0]) for row in connection.execute(
                f"SELECT id FROM articles WHERE {eligible} ORDER BY first_seen_at,id LIMIT ?", (analysis_cutoff, article_limit)
            ).fetchall()]
            source_ids = [str(row[0]) for row in connection.execute(
                f"SELECT id FROM articles WHERE {eligible} ORDER BY first_seen_at,id LIMIT ?", (source_cutoff, article_limit)
            ).fetchall()]
            if analysis_ids:
                marks = ",".join("?" for _ in analysis_ids)
                for table in ("article_scores", "article_press_release_matches", "press_release_match_jobs", "reanalysis_jobs", "llm_jobs", "analysis_feedback", "article_case_processing_flags", "article_processing_flags"):
                    connection.execute(f"DELETE FROM {table} WHERE article_id IN ({marks})", analysis_ids)
                analysis_deleted = connection.execute(f"DELETE FROM article_analyses WHERE article_id IN ({marks})", analysis_ids).rowcount
            else:
                analysis_deleted = 0
            if source_ids:
                marks = ",".join("?" for _ in source_ids)
                source_deleted = connection.execute(f"DELETE FROM articles WHERE id IN ({marks})", source_ids).rowcount
            else:
                source_deleted = 0
            press_eligible = "COALESCE(published_at,created_at)<?"
            result["press_analysis_candidates"] = int(connection.execute(f"SELECT COUNT(*) FROM press_releases WHERE {press_eligible}", (analysis_cutoff,)).fetchone()[0])
            result["press_source_candidates"] = int(connection.execute(f"SELECT COUNT(*) FROM press_releases WHERE {press_eligible}", (source_cutoff,)).fetchone()[0])
            press_analysis_ids = [str(row[0]) for row in connection.execute(
                f"SELECT id FROM press_releases WHERE {press_eligible} ORDER BY COALESCE(published_at,created_at),id LIMIT ?", (analysis_cutoff, press_limit)
            ).fetchall()]
            if press_analysis_ids:
                marks = ",".join("?" for _ in press_analysis_ids)
                connection.execute(f"DELETE FROM article_press_release_matches WHERE press_release_id IN ({marks})", press_analysis_ids)
                connection.execute(f"DELETE FROM press_release_match_jobs WHERE press_release_id IN ({marks})", press_analysis_ids)
                press_chunks_deleted = connection.execute(f"DELETE FROM press_release_chunks WHERE press_release_id IN ({marks})", press_analysis_ids).rowcount
            else:
                press_chunks_deleted = 0
            source_press_rows = connection.execute(
                f"SELECT id,markdown_path FROM press_releases WHERE {press_eligible} ORDER BY COALESCE(published_at,created_at),id LIMIT ?", (source_cutoff, press_limit)
            ).fetchall()
            source_press_ids = [str(row["id"]) for row in source_press_rows]
            if source_press_ids:
                marks = ",".join("?" for _ in source_press_ids)
                press_deleted = connection.execute(f"DELETE FROM press_releases WHERE id IN ({marks})", source_press_ids).rowcount
                removed_paths = [str(row["markdown_path"] or "") for row in source_press_rows]
            else:
                press_deleted = 0
        deleted_files = file_errors = 0
        try:
            root_resolved = root.resolve()
        except OSError:
            root_resolved = root
        for raw_path in removed_paths:
            try:
                path = Path(raw_path)
                path.resolve().relative_to(root_resolved)
                if path.is_file():
                    path.unlink()
                    deleted_files += 1
            except (OSError, ValueError):
                file_errors += 1
        result.update({
            "analysis_pruned_articles": analysis_deleted, "source_deleted_articles": source_deleted,
            "press_pruned_chunks": press_chunks_deleted, "source_deleted_press_releases": press_deleted,
            "deleted_markdown_files": deleted_files, "markdown_file_errors": file_errors,
        })
        return result
