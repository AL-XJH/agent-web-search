from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

from ..errors import exception_error, http_error
from ..models import ProviderResponse, SearchRequest, SearchResult
from .base import Provider

ENDPOINT = "https://open.feedcoopapi.com/search_api/global_search"

# The API returns snippet blocks, not one description string.
EXCERPT_CHARS = 600
SNIPPET_CHARS = 500


class FeedCoopProvider(Provider):
    """Volcengine FeedCoop global_search (open.feedcoopapi.com).

    POST with a Bearer key and a JSON body of ``Query`` / ``DocCount`` /
    ``MaxSnippetLength`` / ``MaxImageCountPerDoc``. Each document carries a
    ``Snippet`` array mixing text and image blocks, so the text blocks are
    joined into the description; images are not requested at all.
    """

    name = "feedcoop"

    def __init__(self, api_key: str | None = None, timeout: float = 60):
        self.api_key = (
            api_key
            if api_key is not None
            else os.getenv("FEEDCOOP_API_KEY", "")
        )
        self.endpoint = os.getenv("AGENT_WEB_SEARCH_FEEDCOOP_ENDPOINT", ENDPOINT)
        self.timeout = timeout

    @staticmethod
    def _text_of(document: dict) -> str:
        parts = []
        for block in document.get("Snippet") or []:
            if not isinstance(block, dict) or block.get("Type") != "text":
                continue
            # Snippets keep the source document's markdown headings; the
            # leading hashes are noise inside a one-line description.
            text = (block.get("Text") or "").lstrip("#").strip()
            if text:
                parts.append(text)
        collapsed = " ".join(" ".join(parts).split())
        if len(collapsed) <= EXCERPT_CHARS:
            return collapsed
        return collapsed[:EXCERPT_CHARS].rstrip() + "…"

    @classmethod
    def parse(cls, data: dict, limit: int | None = None) -> ProviderResponse:
        result = data.get("Result") or {}
        code = result.get("ErrorCode")
        if code not in (0, None):
            # Upstream ErrorMsg is not surfaced: callers get a stable code.
            return ProviderResponse(
                provider="feedcoop", error=f"feedcoop API code {code}"
            )
        results = []
        seen_titles: set[str] = set()
        for document in result.get("Documents") or []:
            if not isinstance(document, dict) or not document.get("Url"):
                continue
            title = (document.get("Title") or "").strip()
            # The same page often comes back twice under locale-specific URLs
            # (e.g. /en-au/pages/x and /pages/x); keep the first.
            key = title.casefold()
            if key and key in seen_titles:
                continue
            if key:
                seen_titles.add(key)
            info = document.get("DocumentInfo") or {}
            host = document.get("HostInfo") or {}
            results.append(
                SearchResult(
                    title=title,
                    url=(document.get("Url") or "").strip(),
                    description=cls._text_of(document),
                    provider="feedcoop",
                    published_at=(info.get("PublishTime") or "").strip() or None,
                    author=(host.get("Hostname") or "").strip() or None,
                )
            )
        if limit is not None:
            results = results[: max(1, limit)]
        return ProviderResponse(
            provider="feedcoop", results=results, searched=bool(results)
        )

    def search(self, request: SearchRequest) -> ProviderResponse:
        if not self.api_key:
            return ProviderResponse(
                provider=self.name, error="FEEDCOOP_API_KEY is not set"
            )
        payload = {
            "Query": request.query,
            "DocCount": max(1, min(50, request.max_results)),
            "MaxSnippetLength": SNIPPET_CHARS,
            "MaxImageCountPerDoc": 0,
        }
        req = urllib.request.Request(
            self.endpoint,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
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
