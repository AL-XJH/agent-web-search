import json

from agent_web_search.models import SearchRequest
from agent_web_search.providers.feedcoop import FeedCoopProvider

SAMPLE = {
    "ResponseMetadata": {"RequestId": "abc"},
    "Result": {
        "TotalDocCount": 2,
        "ErrorCode": 0,
        "ErrorMsg": "",
        "Documents": [
            {
                "Rank": 0,
                "Url": "https://example.com/a",
                "Title": "天安門",
                "Snippet": [
                    {"Type": "image", "Image": {"ImageUrl": "https://cdn/x.jpg"}},
                    {"Type": "text", "Text": "天安门造型威严庄重。"},
                    {"Type": "text", "Text": "1969 年 12 月重建天安门城楼。"},
                ],
                "DocumentInfo": {"Filetype": "pdf", "PublishTime": "2019-05-01"},
                "HostInfo": {"Hostname": "中国国家图书馆", "AuthorityLevel": "high"},
            },
            {
                "Rank": 1,
                "Url": "https://example.com/b",
                "Title": "无文本块",
                "Snippet": [{"Type": "image", "Image": {}}],
                "DocumentInfo": {"PublishTime": ""},
                "HostInfo": {},
            },
            {"Rank": 2, "Title": "缺 Url", "Snippet": []},
        ],
    },
}


def test_parse_joins_text_blocks_and_drops_documents_without_url():
    response = FeedCoopProvider.parse(SAMPLE)

    assert response.searched is True
    assert response.error is None
    assert [row.url for row in response.results] == [
        "https://example.com/a",
        "https://example.com/b",
    ]
    first, second = response.results
    assert first.provider == "feedcoop"
    assert first.author == "中国国家图书馆"
    assert first.published_at == "2019-05-01"
    assert first.description == "天安门造型威严庄重。 1969 年 12 月重建天安门城楼。"
    # An image-only document still yields a row, with an empty description.
    assert second.description == ""
    assert second.published_at is None
    assert second.author is None


def test_parse_applies_limit():
    assert len(FeedCoopProvider.parse(SAMPLE, limit=1).results) == 1


def test_error_code_is_stable_and_hides_upstream_message():
    response = FeedCoopProvider.parse(
        {"Result": {"ErrorCode": 100013, "ErrorMsg": "invalid api key"}}
    )
    assert response.searched is False
    assert response.error == "feedcoop API code 100013"
    assert "invalid api key" not in response.error


def test_missing_key_is_an_explicit_error(monkeypatch):
    monkeypatch.delenv("FEEDCOOP_API_KEY", raising=False)
    response = FeedCoopProvider(api_key="").search(SearchRequest(query="天安门"))
    assert response.error == "FEEDCOOP_API_KEY is not set"


def test_request_body_and_headers(monkeypatch):
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
        captured["body"] = json.loads(request.data.decode("utf-8"))
        captured["headers"] = {k.lower(): v for k, v in request.header_items()}
        return _Response()

    monkeypatch.setattr(
        "agent_web_search.providers.feedcoop.urllib.request.urlopen", fake_urlopen
    )
    FeedCoopProvider(api_key="secret").search(
        SearchRequest(query="天安门城楼", max_results=4)
    )

    assert captured["body"]["Query"] == "天安门城楼"
    assert captured["body"]["DocCount"] == 4
    assert captured["body"]["MaxImageCountPerDoc"] == 0
    assert captured["headers"]["authorization"] == "Bearer secret"
