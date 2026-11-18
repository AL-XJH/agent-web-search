from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

from ..errors import exception_error, http_error
from ..models import ProviderResponse, SearchRequest, SearchResult
from .base import Provider

ENDPOINT = "https://developer.zhihu.com/api/v1/content/zhihu_search"

# ContentText is the full article body; keep the payload readable.
EXCERPT_CHARS = 600


class ZhihuProvider(Provider):
    """Zhihu open-platform search (developer.zhihu.com).

    Auth is ``Authorization: Bearer`` plus a seconds-resolution
    ``X-Request-Timestamp`` the server validates against its clock, so the
    timestamp is generated per request rather than cached.
    """

    name = "zhihu"

    def __init__(self, api_key: str | None = None, timeout: float = 60):
        self.api_key = (
            api_key if api_key is not None else os.getenv("ZHIHU_ACCESS_SECRET", "")
        )
        self.endpoint = os.getenv("AGENT_WEB_SEARCH_ZHIHU_ENDPOINT", ENDPOINT)
        self.timeout = timeout

    @staticmethod
    def _excerpt(text: str) -> str:
        collapsed = " ".join((text or "").split())
        if len(collapsed) <= EXCERPT_CHARS:
            return collapsed
        return collapsed[:EXCERPT_CHARS].rstrip() + "…"

    @staticmethod
    def _published(created: object) -> str | None:
        try:
            stamp = int(created)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return None
        if stamp <= 0:
            return None
        return datetime.fromtimestamp(stamp, tz=timezone.utc).strftime("%Y-%m-%d")

    @classmethod
    def parse(cls, data: dict, limit: int | None = None) -> ProviderResponse:
        if data.get("Code") not in (0, None):
            # Upstream message text is not surfaced: callers get a stable code.
            return ProviderResponse(
                provider="zhihu", error=f"zhihu API code {data.get('Code')}"
            )
        payload = data.get("Data") or {}
        results = [
            SearchResult(
                title=(item.get("Title") or "").strip(),
                url=(item.get("Url") or "").strip(),
                description=cls._excerpt(item.get("ContentText") or item.get("Headline") or ""),
                provider="zhihu",
                published_at=cls._published(item.get("CreateTime")),
                author=(item.get("AuthorName") or "").strip() or None,
            )
            for item in payload.get("Items") or []
            if isinstance(item, dict) and item.get("Url")
        ]
        if limit is not None:
            results = results[: max(1, limit)]
        return ProviderResponse(provider="zhihu", results=results, searched=bool(results))

    def search(self, request: SearchRequest) -> ProviderResponse:
        if not self.api_key:
            return ProviderResponse(
                provider=self.name, error="ZHIHU_ACCESS_SECRET is not set"
            )
        query = urllib.parse.urlencode({"Query": request.query})
        req = urllib.request.Request(
            f"{self.endpoint}?{query}",
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
                "X-Request-Timestamp": str(int(time.time())),
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                return self.parse(
                    json.loads(response.read().decode("utf-8")),
                    limit=request.max_results,
                )
        except urllib.error.HTTPError as exc:
            return ProviderResponse(
                provider=self.name, error=http_error(self.name, exc.code)
            )
        except Exception as exc:  # noqa: BLE001 - reported as a stable error code
            return ProviderResponse(
                provider=self.name, error=exception_error(self.name, exc)
            )
