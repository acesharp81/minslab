from __future__ import annotations

from datetime import datetime, timezone
from urllib import error as url_error
from urllib import parse as url_parse
from urllib import request as url_request

from .base import AdapterError, SourcePayload
from .contracts import OPEN_API_BASE_URL, get_contract


class NationalAssemblyClient:
    def __init__(self, api_key: str, *, timeout_seconds: float = 15.0):
        if not api_key.strip():
            raise ValueError("National Assembly API key is required")
        self._api_key = api_key.strip()
        self._timeout_seconds = timeout_seconds

    def fetch(
        self,
        source_key: str,
        *,
        page: int = 1,
        page_size: int = 100,
        filters: dict[str, str] | None = None,
    ) -> SourcePayload:
        contract = get_contract(source_key)
        normalized_filters = {
            str(key): str(value).strip()
            for key, value in (filters or {}).items()
            if str(value).strip()
        }
        missing = [name for name in contract.required_parameters if not normalized_filters.get(name)]
        if missing:
            raise AdapterError(f"missing required parameters for {source_key}: {', '.join(missing)}")
        if page < 1:
            raise ValueError("page must be at least 1")
        if not 1 <= page_size <= 1000:
            raise ValueError("page_size must be between 1 and 1000")

        public_query = {
            "Type": "json",
            "pIndex": str(page),
            "pSize": str(page_size),
            **normalized_filters,
        }
        authenticated_query = {"KEY": self._api_key, **public_query}
        endpoint = f"{OPEN_API_BASE_URL}/{contract.resource}"
        request_url = f"{endpoint}?{url_parse.urlencode(authenticated_query)}"
        safe_url = f"{endpoint}?{url_parse.urlencode(public_query)}"

        request = url_request.Request(
            request_url,
            headers={"User-Agent": "POC-07-NationalAssembly/0.1"},
        )
        try:
            with url_request.urlopen(request, timeout=self._timeout_seconds) as response:
                content = response.read()
                status = int(response.status)
                content_type = response.headers.get_content_type()
        except url_error.HTTPError as error:
            raise AdapterError(f"HTTP {error.code} from {source_key}") from error
        except (url_error.URLError, TimeoutError) as error:
            raise AdapterError(f"request failed for {source_key}: {type(error).__name__}") from error

        return SourcePayload(
            source_key=source_key,
            content=content,
            content_type=content_type,
            retrieved_at=datetime.now(timezone.utc),
            source_url=safe_url,
            http_status=status,
        )
