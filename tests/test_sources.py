import asyncio
from datetime import datetime, timezone
from unittest.mock import MagicMock

from news_sources.binance_handler import BinanceHandler
from news_sources.rss_handler import RSSHandler

FEED = """<?xml version="1.0"?>
<rss version="2.0"><channel><title>t</title>
<item><title>dated</title><link>https://a.example/1</link>
<pubDate>Wed, 01 Jan 2025 12:00:00 GMT</pubDate></item>
<item><title>undated</title><link>https://a.example/2</link></item>
</channel></rss>"""


def test_rss_dates_are_utc_aware():
    items = asyncio.run(RSSHandler().parse_feed(FEED))
    dated, undated = items

    assert dated["published"] == datetime(2025, 1, 1, 12, 0, tzinfo=timezone.utc)
    assert dated["published"].utcoffset().total_seconds() == 0
    assert undated["published"].tzinfo is not None


class FakeResponse:
    status = 200

    def __init__(self, payload):
        self.payload = payload

    async def json(self):
        return self.payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False


def test_binance_dates_are_utc_aware_and_sortable_with_rss():
    payload = {"code": "000000", "data": {"catalogs": [
        {"title": "b", "code": "c1", "description": "", "releaseDate": 1735732800000},
    ]}}
    handler = BinanceHandler()
    handler.session = MagicMock()
    handler.session.post = MagicMock(return_value=FakeResponse(payload))

    [item] = asyncio.run(handler.get_announcements())

    assert item["published"] == datetime(2025, 1, 1, 12, 0, tzinfo=timezone.utc)
    rss_items = asyncio.run(RSSHandler().parse_feed(FEED))
    sorted(rss_items + [item], key=lambda x: x["published"])


def session_timeout(handler):
    async def run():
        await handler.init_session()
        timeout = handler.session.timeout.total
        await handler.close_session()
        return timeout

    return asyncio.run(run())


def test_http_sessions_have_timeout():
    from config import HTTP_TIMEOUT

    assert HTTP_TIMEOUT > 0
    assert session_timeout(RSSHandler()) == HTTP_TIMEOUT
    assert session_timeout(BinanceHandler()) == HTTP_TIMEOUT
