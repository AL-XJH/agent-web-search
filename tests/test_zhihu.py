import json

from agent_web_search.models import SearchRequest
from agent_web_search.providers.zhihu import ZhihuProvider

SAMPLE = {
    "Code": 0,
    "Message": "success",
    "Data": {
        "HasMore": False,
        "Items": [
            {
                "Title": "Rave锐舞文化 - 知乎",
                "Headline": "👗👙",
                "ContentText": "20世纪80年代，随着电子音乐技术快速的发展，Techno、House等音乐在欧美流行起来。",
                "Url": "https://zhuanlan.zhihu.com/p/1",
                "AuthorName": "桔Beautiful",
                "CreateTime": 1791241375,
                "VoteUpCount": 1,
            },
            {
                "Title": "有 Headline 没正文",
                "Headline": "只有摘要",
                "ContentText": "",
                "Url": "https://zhuanlan.zhihu.com/p/2",
                "CreateTime": 0,
            },
            {"Title": "没有 Url 的条目", "ContentText": "会被丢掉"},
        ],
    },
}


def test_parse_maps_items_and_drops_entries_without_url():
    response = ZhihuProvider.parse(SAMPLE)

    assert response.searched is True
    assert response.error is None
    assert [row.url for row in response.results] == [
        "https://zhuanlan.zhihu.com/p/1",
        "https://zhuanlan.zhihu.com/p/2",
    ]
    first, second = response.results
    assert first.provider == "zhihu"
    assert first.author == "桔Beautiful"
    assert first.published_at == "2026-10-05"
    # Empty ContentText falls back to Headline; a zero CreateTime yields no date.
    assert second.description == "只有摘要"
    assert second.published_at is None


def test_parse_applies_limit():
    response = ZhihuProvider.parse(SAMPLE, limit=1)
    assert len(response.results) == 1


def test_parse_reports_non_zero_code_without_upstream_message():
    response = ZhihuProvider.parse({"Code": 40001, "Message": "invalid timestamp"})
    assert response.searched is False
    assert response.error == "zhihu API code 40001"
    assert "invalid timestamp" not in response.error


def test_missing_key_is_an_explicit_error(monkeypatch):
    monkeypatch.delenv("ZHIHU_ACCESS_SECRET", raising=False)
    provider = ZhihuProvider(api_key="")
    response = provider.search(SearchRequest(query="rave"))
    assert response.error == "ZHIHU_ACCESS_SECRET is not set"


def test_request_carries_bearer_and_seconds_timestamp(monkeypatch):
    captured = {}

    class _Response:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self):
            return json.dumps(SAMPLE).encode("utf-8")

    def fake_urlopen(request, timeout=None):
        captured["url"] = request.full_url
        captured["headers"] = {k.lower(): v for k, v in request.header_items()}
        return _Response()

    monkeypatch.setattr(
        "agent_web_search.providers.zhihu.urllib.request.urlopen", fake_urlopen
    )
    provider = ZhihuProvider(api_key="secret", timeout=5)
    provider.search(SearchRequest(query="锐舞文化", max_results=2))

    assert "Query=%E9%94%90%E8%88%9E%E6%96%87%E5%8C%96" in captured["url"]
    assert captured["headers"]["authorization"] == "Bearer secret"
    stamp = captured["headers"]["x-request-timestamp"]
    assert stamp.isdigit() and len(stamp) == 10
