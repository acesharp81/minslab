from __future__ import annotations

import email.utils
import hashlib
import html
import json
import re
import time
import urllib.parse
import urllib.request
import urllib.robotparser
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timedelta
from html.parser import HTMLParser
from typing import Iterable

from .config import Settings
from .matching import article_topic_fields, expanded_case_terms, term_in_text
from .storage import KST


TAG_RE = re.compile(r"<[^>]+>")
SPACE_RE = re.compile(r"\s+")
TRACKING_KEYS = {"fbclid", "gclid", "ref", "source", "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content"}
ARTICLE_SELECTORS = ("article", "main")


def plain_text(value: str) -> str:
    return SPACE_RE.sub(" ", html.unescape(TAG_RE.sub(" ", str(value or "")))).strip()


def canonicalize_url(value: str) -> str:
    parsed = urllib.parse.urlsplit(str(value or "").strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    query = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
    query = [(key, item) for key, item in query if key.lower() not in TRACKING_KEYS and not key.lower().startswith("utm_")]
    path = re.sub(r"/+$", "", parsed.path) or "/"
    return urllib.parse.urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), path, urllib.parse.urlencode(query), ""))


def publisher_from_url(value: str) -> str:
    hostname = urllib.parse.urlsplit(value).hostname or ""
    return hostname.lower().removeprefix("www.")


def parse_published_at(value: str) -> str | None:
    if not value:
        return None
    try:
        parsed = email.utils.parsedate_to_datetime(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=KST)
        return parsed.astimezone(KST).isoformat(timespec="seconds")
    except (TypeError, ValueError, OverflowError):
        return None


class TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts: list[str] = []
        self.hidden_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag.lower() in {"script", "style", "noscript", "svg", "nav", "footer", "aside"}:
            self.hidden_depth += 1

    def handle_endtag(self, tag):
        if tag.lower() in {"script", "style", "noscript", "svg", "nav", "footer", "aside"} and self.hidden_depth:
            self.hidden_depth -= 1
        if tag.lower() in {"p", "div", "article", "main", "section", "br", "li"}:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.hidden_depth:
            self.parts.append(data)

    def text(self) -> str:
        lines = [SPACE_RE.sub(" ", line).strip() for line in "".join(self.parts).splitlines()]
        return "\n".join(line for line in lines if len(line) > 1)


@dataclass
class Candidate:
    canonical_url: str
    original_url: str
    title: str
    publisher: str
    published_at: str | None
    snippet: str
    source_type: str

    def as_dict(self) -> dict:
        return self.__dict__.copy()


class HttpClient:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.last_domain_request: dict[str, float] = {}
        self.robots: dict[str, urllib.robotparser.RobotFileParser] = {}

    def request(self, url: str, headers: dict | None = None, data: bytes | None = None, method: str = "GET") -> bytes:
        parsed = urllib.parse.urlsplit(str(url or ""))
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("HTTP(S) 주소만 수집할 수 있습니다.")
        request_headers = {"User-Agent": self.settings.user_agent, "Accept": "*/*"}
        request_headers.update(headers or {})
        request = urllib.request.Request(url, headers=request_headers, data=data, method=method)
        with urllib.request.urlopen(request, timeout=self.settings.request_timeout_seconds) as response:
            return response.read(2_000_000)

    def allowed(self, url: str) -> bool:
        parsed = urllib.parse.urlsplit(url)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        if origin not in self.robots:
            parser = urllib.robotparser.RobotFileParser()
            parser.set_url(f"{origin}/robots.txt")
            try:
                parser.read()
            except Exception:
                parser = urllib.robotparser.RobotFileParser()
                parser.parse([])
            self.robots[origin] = parser
        return self.robots[origin].can_fetch(self.settings.user_agent, url)

    def throttle(self, url: str, minimum_seconds: float = 1.0) -> None:
        domain = urllib.parse.urlsplit(url).netloc
        wait = minimum_seconds - (time.monotonic() - self.last_domain_request.get(domain, 0))
        if wait > 0:
            time.sleep(wait)
        self.last_domain_request[domain] = time.monotonic()


class NewsCollector:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.http = HttpClient(settings)

    @staticmethod
    def query_for_case(case: dict) -> str:
        required = [str(term).strip() for term in case.get("required_terms", []) if str(term).strip()]
        included = [str(term).strip() for term in case.get("include_terms", []) if str(term).strip()]
        if required:
            return " ".join(required + included[:4])
        if included:
            return " ".join(included[:8])
        return str(case.get("topic_description") or case.get("name") or "").strip()[:200]

    def collect_naver_query(self, query: str) -> list[Candidate]:
        if not (self.settings.naver_client_id and self.settings.naver_client_secret):
            return []
        query = str(query or "").strip()[:200]
        if not query:
            return []
        params = urllib.parse.urlencode({"query": query, "display": 100, "start": 1, "sort": "date"})
        payload = self.http.request(
            f"https://openapi.naver.com/v1/search/news.json?{params}",
            headers={
                "X-Naver-Client-Id": self.settings.naver_client_id,
                "X-Naver-Client-Secret": self.settings.naver_client_secret,
                "Accept": "application/json",
            },
        )
        data = json.loads(payload.decode("utf-8"))
        results = []
        for item in data.get("items", []):
            original_url = canonicalize_url(item.get("originallink") or item.get("link"))
            canonical_url = canonicalize_url(original_url)
            title = plain_text(item.get("title"))
            if not canonical_url or not title:
                continue
            results.append(Candidate(
                canonical_url=canonical_url,
                original_url=original_url,
                title=title[:500],
                publisher=publisher_from_url(original_url),
                published_at=parse_published_at(item.get("pubDate", "")),
                snippet=plain_text(item.get("description"))[:2000],
                source_type="naver",
            ))
        return results

    def collect_naver(self, case: dict) -> list[Candidate]:
        return self.collect_naver_query(self.query_for_case(case))

    def collect_rss(self, urls: Iterable[str]) -> list[Candidate]:
        results = []
        for feed_url in dict.fromkeys(str(url).strip() for url in urls if str(url).strip()):
            try:
                payload = self.http.request(feed_url, headers={"Accept": "application/rss+xml, application/atom+xml, text/xml"})
                root = ET.fromstring(payload)
            except Exception:
                continue
            items = list(root.findall(".//item"))
            if not items:
                items = list(root.findall(".//{*}entry"))
            for item in items[:100]:
                def value(*names: str) -> str:
                    for name in names:
                        node = item.find(name) or item.find(f"{{*}}{name}")
                        if node is not None:
                            if node.text:
                                return node.text
                            if node.attrib.get("href"):
                                return node.attrib["href"]
                    return ""
                original_url = canonicalize_url(value("link", "guid"))
                title = plain_text(value("title"))
                if not original_url or not title:
                    continue
                results.append(Candidate(
                    canonical_url=original_url,
                    original_url=original_url,
                    title=title[:500],
                    publisher=plain_text(value("author", "source"))[:200] or publisher_from_url(original_url),
                    published_at=parse_published_at(value("pubDate", "published", "updated")),
                    snippet=plain_text(value("description", "summary", "content"))[:2000],
                    source_type="rss",
                ))
        return results

    def collect(self, case: dict) -> list[dict]:
        candidates = []
        errors = []
        try:
            candidates.extend(self.collect_naver(case))
        except Exception as error:
            errors.append(f"naver: {error}")
        rss_urls = [*self.settings.rss_feeds, *case.get("rss_urls", [])]
        candidates.extend(self.collect_rss(rss_urls))
        deduped: dict[str, Candidate] = {}
        for candidate in candidates:
            deduped.setdefault(candidate.canonical_url, candidate)
        results = [candidate.as_dict() for candidate in deduped.values()]
        for item in results:
            item["collector_errors"] = errors
        return results

    def collect_organization(self, organization: dict) -> list[dict]:
        search_terms = [
            organization.get("name", ""),
            *organization.get("abbreviations", []),
            *organization.get("former_names", []),
            *organization.get("people", []),
        ]
        queries = list(dict.fromkeys(str(term).strip() for term in search_terms if str(term).strip()))
        queries = queries[: max(1, int(organization.get("max_search_queries", 8)))]
        candidates: list[Candidate] = []
        errors: list[str] = []
        for query in queries:
            try:
                candidates.extend(self.collect_naver_query(query))
            except Exception as error:
                errors.append(f"naver({query[:30]}): {error}")
        # 기관 수집은 전역 RSS를 절대 합치지 않습니다. 기관이 직접 등록한 RSS만 허용합니다.
        rss_urls = list(organization.get("rss_urls", []))
        candidates.extend(self.collect_rss(rss_urls))
        deduped: dict[str, Candidate] = {}
        for candidate in candidates:
            deduped.setdefault(candidate.canonical_url, candidate)
        results = [candidate.as_dict() for candidate in deduped.values()]
        for item in results:
            item["collector_errors"] = errors
        return results


    def fetch_body(self, url: str) -> dict:
        if not self.http.allowed(url):
            return {"body": "", "error": "robots_disallowed"}
        try:
            self.http.throttle(url)
            payload = self.http.request(url, headers={"Accept": "text/html,application/xhtml+xml"})
            raw_html = payload.decode("utf-8", errors="replace")
            body = ""
            try:
                import trafilatura
                body = trafilatura.extract(raw_html, include_comments=False, include_tables=False, favor_precision=True) or ""
            except (ImportError, RuntimeError):
                parser = TextExtractor()
                parser.feed(raw_html)
                body = parser.text()
            body = body.strip()[: self.settings.article_body_limit]
            return {
                "body": body,
                "content_hash": hashlib.sha256(body.encode("utf-8")).hexdigest() if body else None,
                "body_expires_at": (datetime.now(KST) + timedelta(days=self.settings.raw_retention_days)).isoformat(timespec="seconds"),
                "error": "" if body else "body_unavailable",
            }
        except Exception as error:
            return {"body": "", "error": f"fetch_error:{type(error).__name__}"}


def quick_candidate_match(case: dict, candidate: dict) -> bool:
    fields = article_topic_fields(candidate)
    expanded = expanded_case_terms(case)
    search_groups = list(expanded.values())
    return not search_groups or any(
        any(term_in_text(variant, field) for variant in variants for field in fields)
        for variants in search_groups
    )


def organization_candidate_match(organization: dict, candidate: dict) -> bool:
    text = f"{candidate.get('title', '')} {candidate.get('snippet', '')} {candidate.get('body', '')}".casefold()
    excluded = [str(term).strip().casefold() for term in organization.get("exclude_terms", []) if str(term).strip()]
    if any(term in text for term in excluded):
        return False
    identity_terms = [
        organization.get("name", ""),
        *organization.get("abbreviations", []),
        *organization.get("former_names", []),
        *organization.get("people", []),
    ]
    identity_terms = [str(term).strip().casefold() for term in identity_terms if str(term).strip()]
    url = str(candidate.get("original_url") or candidate.get("canonical_url") or "").casefold()
    domains = [str(domain).strip().casefold().removeprefix("https://").removeprefix("http://").strip("/") for domain in organization.get("domains", []) if str(domain).strip()]
    return (not identity_terms and not domains) or any(term in text for term in identity_terms) or any(domain in url for domain in domains)
