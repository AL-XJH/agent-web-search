from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

from ..errors import exception_error, http_error
from ..models import ProviderResponse, SearchRequest, SearchResult
from .base import Provider

ENDPOINT = "https://api.keenable.ai/v1/search"


class KeenableProvider(Provider):
    """Keenable search API provider.

    Uses the authenticated endpoint when KEENABLE_API_KEY is set. The public
    token-less endpoint is intentionally not used here: this provider only runs
    when a key is configured, so a missing key is reported as an error rather
    than silently degrading to the shared anonymous pool.
    """

    name = "keenable"

    def __init__(self, api_key: str | None = None, timeout: float = 60):
        self.api_key = (
            api_key if api_key is not None else os.getenv("KEENABLE_API_KEY", "")
        )
        self.endpoint = os.getenv("AGENT_WEB_SEARCH_KEENABLE_ENDPOINT", ENDPOINT)
        self.timeout = timeout

    @staticmethod
    def parse(data: dict) -> ProviderResponse:
        results = [
            SearchResult(
                title=(item.get("title") or "").strip(),
                url=(item.get("url") or "").strip(),
                description=(
                    item.get("snippet") or item.get("description") or ""
                ).strip(),
                provider="keenable",
                published_at=item.get("published_at") or item.get("date") or None,
            )
            for item in data.get("results") or []
            if isinstance(item, dict) and item.get("url")
        ]
        return ProviderResponse(
            provider="keenable",
            results=results,
            searched=bool(results),
            answer=(data.get("answer") or "").strip(),
        )

    def search(self, request: SearchRequest) -> ProviderResponse:
        if not self.api_key:
            return ProviderResponse(
                provider=self.name, error="KEENABLE_API_KEY is not set"
            )
        payload = {
            "query": request.query,
            "max_results": max(1, min(20, request.max_results)),
        }
        req = urllib.request.Request(
            self.endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                return self.parse(json.loads(response.read().decode("utf-8")))
        except urllib.error.HTTPError as exc:
            return ProviderResponse(
                provider=self.name, error=http_error(self.name, exc.code)
            )
        except Exception as exc:  # noqa: BLE001 - reported as a stable error code
            return ProviderResponse(
                provider=self.name, error=exception_error(self.name, exc)
            )
