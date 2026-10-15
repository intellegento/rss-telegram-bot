import asyncio
from datetime import datetime, timezone
from unittest.mock import patch

from config import HTTP_TIMEOUT
from news_sources import binance_handler, rss_handler

FEED = """<?xml version="1.0"?>
<rss version="2.0"><channel><title>t</title>
<item><title>dated</title><link>https://a.example/1</link><guid>id-1</guid>
<description>&lt;p&gt;some &lt;b&gt;text&lt;/b&gt;&lt;/p&gt;</description>
<pubDate>Wed, 01 Jan 2025 12:00:00 GMT</pubDate></item>
<item><title>undated</title><link>https://a.example/2</link></item>
</channel></rss>"""

RECORD_KEYS = {"guid", "title", "url", "summary", "published_at"}


class FakeResponse:
    status = 200

    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        pass

    async def json(self):
        return self.payload

    async def text(self):
        return self.payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False


class FakeSession:
    """Подменяет aiohttp.ClientSession и запоминает таймаут."""

    timeouts = []

    def __init__(self, payload, timeout=None):
        self.payload = payload
        FakeSession.timeouts.append(timeout.total)

    def get(self, url, **kwargs):
        return FakeResponse(self.payload)

    post = get

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False


def fetch(module, payload):
    FakeSession.timeouts = []
    with patch.object(module.aiohttp, "ClientSession", lambda **kw: FakeSession(payload, **kw)):
        return asyncio.run(module.fetch("https://a.example/rss"))


def test_rss_records_are_normalized():
    dated, undated = fetch(rss_handler, FEED)

    assert set(dated) == RECORD_KEYS
    assert dated["guid"] == "id-1"
    assert dated["title"] == "dated"
    assert dated["url"] == "https://a.example/1"
    assert dated["summary"] == "some text"
    assert dated["published_at"] == datetime(2025, 1, 1, 12, 0, tzinfo=timezone.utc)
    # Без guid в ленте идентификатором служит ссылка, без даты — None
    assert undated["guid"] == "https://a.example/2"
    assert undated["published_at"] is None
    assert FakeSession.timeouts == [HTTP_TIMEOUT]


def test_binance_records_are_normalized():
    payload = {"code": "000000", "data": {"catalogs": [
        {"title": "b", "code": "c1", "description": "d", "releaseDate": 1735732800000},
    ]}}

    [item] = fetch(binance_handler, payload)

    assert item == {
        "guid": "c1",
        "title": "b",
        "url": "https://www.binance.com/en/support/announcement/c1",
        "summary": "d",
        "published_at": datetime(2025, 1, 1, 12, 0, tzinfo=timezone.utc),
    }
    assert FakeSession.timeouts == [HTTP_TIMEOUT]
