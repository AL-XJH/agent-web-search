from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request

from ..errors import exception_error, http_error
from ..models import ProviderResponse, SearchRequest, SearchResult
from .base import Provider

ENDPOINT = "https://api.search.tinyfish.ai"

# TinyFish takes a recency window in minutes, not named buckets.
RECENCY_MINUTES = {"d": 1440, "w": 10080, "m": 43200, "y": 525600}


class TinyFishProvider(Provider):
    """TinyFish Search API provider (agent-facing search over its own index)."""

    name = "tinyfish"

    def __init__(self, api_key: str | None = None, timeout: float = 60):
        if api_key is not None:
            self.api_key = api_key
        else:
            # Hermes stores the key under MCP_TINYFISH_API_KEY (written by the
            # TinyFish installer); TINYFISH_API_KEY is accepted as an override.
            self.api_key = os.getenv("TINYFISH_API_KEY", "") or os.getenv(
                "MCP_TINYFISH_API_KEY", ""
            )
        self.endpoint = os.getenv("AGENT_WEB_SEARCH_TINYFISH_ENDPOINT", ENDPOINT)
        self.timeout = timeout

    @staticmethod
    def parse(data: dict, limit: int | None = None) -> ProviderResponse:
        results = [
            SearchResult(
                title=(item.get("title") or "").strip(),
                url=(item.get("url") or "").strip(),
                description=(item.get("snippet") or "").strip(),
                provider="tinyfish",
                published_at=item.get("date") or None,
            )
            for item in data.get("results") or []
            if isinstance(item, dict) and item.get("url")
        ]
        # TinyFish has no result-count parameter, so the limit is applied here.
        if limit is not None:
            results = results[: max(1, limit)]
        return ProviderResponse(
            provider="tinyfish", results=results, searched=bool(results)
        )

    def search(self, request: SearchRequest) -> ProviderResponse:
        if not self.api_key:
            return ProviderResponse(
                provider=self.name, error="TINYFISH_API_KEY is not set"
            )
        params: dict[str, str] = {"query": request.query}
        if request.time_range in RECENCY_MINUTES:
            params["recency_minutes"] = str(RECENCY_MINUTES[request.time_range])
        req = urllib.request.Request(
            f"{self.endpoint}?{urllib.parse.urlencode(params)}",
            headers={
                "Accept": "application/json",
                "X-API-Key": self.api_key,
                "X-TF-Client-Name": "hermes",
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
