import asyncio
from datetime import datetime, timezone

import pytest

from config import HTTP_TIMEOUT
from conftest import sample
from news_sources import binance_handler, rss_handler, rsshub

FEED = """<?xml version="1.0"?>
<rss version="2.0"><channel><title>t</title>
<item><title>dated</title><link>https://a.example/1</link><guid>id-1</guid>
<description>&lt;p&gt;some &lt;b&gt;text&lt;/b&gt;&lt;/p&gt;</description>
<pubDate>Wed, 01 Jan 2025 12:00:00 GMT</pubDate></item>
<item><title>undated</title><link>https://a.example/2</link></item>
</channel></rss>"""

RECORD_KEYS = {"guid", "title", "url", "summary", "published_at"}


def test_rss_records_are_normalized(fake_http):
    fake_http.body = FEED

    dated, undated = asyncio.run(rss_handler.fetch("https://a.example/rss"))

    assert set(dated) == RECORD_KEYS
    assert dated["guid"] == "id-1"
    assert dated["title"] == "dated"
    assert dated["url"] == "https://a.example/1"
    assert dated["summary"] == "some text"
    assert dated["published_at"] == datetime(2025, 1, 1, 12, 0, tzinfo=timezone.utc)
    # Без guid в ленте идентификатором служит ссылка, без даты — None
    assert undated["guid"] == "https://a.example/2"
    assert undated["published_at"] is None
    assert fake_http.timeouts == [HTTP_TIMEOUT]


def test_binance_records_are_normalized(fake_http):
    fake_http.body = {"code": "000000", "data": {"catalogs": [
        {"title": "b", "code": "c1", "description": "d", "releaseDate": 1735732800000},
    ]}}

    [item] = asyncio.run(binance_handler.fetch("https://binance.example"))

    assert item == {
        "guid": "c1",
        "title": "b",
        "url": "https://www.binance.com/en/support/announcement/c1",
        "summary": "d",
        "published_at": datetime(2025, 1, 1, 12, 0, tzinfo=timezone.utc),
    }
    assert fake_http.timeouts == [HTTP_TIMEOUT]


@pytest.mark.parametrize("status, body", [
    (200, "<html><body>not a feed</body></html>"),
    (200, ""),
    (503, sample("rsshub_error.html")),
    (429, "Too Many Requests"),
])
def test_invalid_feed_raises(fake_http, status, body):
    fake_http.status = status
    fake_http.body = body

    with pytest.raises(Exception):
        asyncio.run(rss_handler.fetch("https://a.example/rss"))


@pytest.mark.parametrize("text", [
    "@ExampleChannel",
    "examplechannel",
    "t.me/examplechannel",
    "https://t.me/examplechannel",
    "https://t.me/s/examplechannel",
    "https://t.me/examplechannel/101",
    "https://t.me/s/examplechannel/101",
    "http://telegram.me/examplechannel/",
    "  https://t.me/examplechannel?single  ",
])
def test_channel_inputs_give_same_name(text):
    assert rsshub.channel_name(text) == "examplechannel"
    assert rsshub.channel_url(rsshub.channel_name(text)) == "https://t.me/examplechannel"


@pytest.mark.parametrize("text", [
    "", "@abc", "https://t.me/+AbCdEf123", "https://t.me/joinchat/AbCd", "https://example.com/examplechannel",
    "examplechannel/extra", "@example channel",
])
def test_not_a_channel(text):
    assert rsshub.channel_name(text) is None


def test_rsshub_route_detection(monkeypatch):
    monkeypatch.setattr("config.RSSHUB_BASE_URL", "https://rss.example.org")

    assert rsshub.route_path("https://rss.example.org/youtube/channel/UC1") == "/youtube/channel/UC1"
    assert rsshub.route_path("https://rsshub.app/youtube/channel/UC1?limit=5") == "/youtube/channel/UC1?limit=5"
    assert rsshub.route_path("https://a.example/rss") is None
    assert rsshub.route_path("https://rsshub.app.evil.example/x") is None


def test_feed_urls_follow_rsshub_base_url(monkeypatch, fake_http):
    fake_http.body = sample("rsshub_telegram_channel.xml")

    for base in ("https://rsshub.app", "https://rss.example.org"):
        monkeypatch.setattr("config.RSSHUB_BASE_URL", base)
        asyncio.run(rsshub.fetch_telegram("https://t.me/examplechannel"))
        asyncio.run(rsshub.fetch_route("/youtube/channel/UC1"))

    assert fake_http.urls == [
        "https://rsshub.app/telegram/channel/examplechannel",
        "https://rsshub.app/youtube/channel/UC1",
        "https://rss.example.org/telegram/channel/examplechannel",
        "https://rss.example.org/youtube/channel/UC1",
    ]


def test_telegram_channel_sample_is_parsed(fake_http):
    fake_http.body = sample("rsshub_telegram_channel.xml")

    titled, untitled = asyncio.run(rsshub.fetch_telegram("https://t.me/examplechannel"))

    # Ссылка ведёт на пост в Telegram
    assert titled["url"] == "https://t.me/examplechannel/101"
    assert titled["guid"] == "https://t.me/examplechannel/101"
    assert titled["title"] == "Bitcoin update & market <notes>"
    assert titled["published_at"] == datetime(2025, 10, 8, 10, 0, tzinfo=timezone.utc)
    # Пустой заголовок заменяется началом текста поста без HTML, не длиннее 100 символов
    assert untitled["title"].startswith("Это очень длинный пост про bitcoin без заголовка")
    assert len(untitled["title"]) <= 100
    assert "<" not in untitled["title"] and "div" not in untitled["title"]
    assert untitled["url"] == "https://t.me/examplechannel/102"


@pytest.mark.parametrize("path, expected", [
    ("/telegram/channel/ExampleChannel", "examplechannel"),
    ("/telegram/channel/examplechannel/showLinkPreview=0", "examplechannel"),
    ("/telegram/channel/examplechannel?limit=5", "examplechannel"),
    ("/telegram/stickerpack/examplechannel", None),
    ("/github/release/DIYgod/RSSHub", None),
])
def test_route_channel_name(path, expected):
    assert rsshub.route_channel_name(path) == expected
