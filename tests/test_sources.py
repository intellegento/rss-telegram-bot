import asyncio
from datetime import datetime, timezone

import pytest

from config import HTTP_TIMEOUT
from conftest import VALID_RSS, sample
from news_sources import binance_handler, rss_handler, rsshub, telegram_handler

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


def test_rsshub_route_detection_without_base_url(monkeypatch):
    monkeypatch.setattr("config.RSSHUB_BASE_URL", "")

    # Адрес публичного RSSHub по-прежнему распознаётся, чтобы бот мог объяснить отказ
    assert rsshub.route_path("https://rsshub.app/youtube/channel/UC1") == "/youtube/channel/UC1"
    assert rsshub.route_path("https://a.example/rss") is None
    assert rsshub.route_path("/youtube/channel/UC1") is None


def test_route_feed_url_follows_rsshub_base_url(monkeypatch, fake_http):
    fake_http.body = VALID_RSS

    for base in ("https://rsshub.example.com", "https://rss.example.org"):
        monkeypatch.setattr("config.RSSHUB_BASE_URL", base)
        asyncio.run(rsshub.fetch_route("/youtube/channel/UC1"))

    assert fake_http.urls == [
        "https://rsshub.example.com/youtube/channel/UC1",
        "https://rss.example.org/youtube/channel/UC1",
    ]


def test_route_is_not_fetched_without_rsshub_base_url(monkeypatch, fake_http):
    monkeypatch.setattr("config.RSSHUB_BASE_URL", "")

    with pytest.raises(Exception, match="RSSHUB_BASE_URL"):
        asyncio.run(rsshub.fetch_route("/youtube/channel/UC1"))
    assert fake_http.urls == []


def fetch_durov(fake_http):
    fake_http.body = sample("tme_s_durov.html")
    return asyncio.run(telegram_handler.fetch("https://t.me/durov"))


def test_channel_is_read_from_public_web_page(monkeypatch, fake_http):
    # RSSHub для каналов не нужен
    monkeypatch.setattr("config.RSSHUB_BASE_URL", "")

    items = fetch_durov(fake_http)

    assert fake_http.urls == ["https://t.me/s/durov"]
    assert fake_http.timeouts == [HTTP_TIMEOUT]
    assert len(items) == 20
    assert all(set(item) == RECORD_KEYS for item in items)


def test_channel_posts_are_normalized(fake_http):
    items = fetch_durov(fake_http)
    first, last = items[0], items[-1]

    assert first["guid"] == "531"
    assert first["url"] == "https://t.me/durov/531"
    assert last["guid"] == "552"
    # Ссылка ведёт на пост в Telegram
    assert last["url"] == "https://t.me/durov/552"
    assert last["published_at"] == datetime(2026, 10, 11, 14, 52, 40, tzinfo=timezone.utc)
    # Заголовка у постов нет: берётся начало текста без HTML, не длиннее 100 символов
    assert last["title"].startswith("✨ Designers × AI 🆕 The mockup era is over.")
    assert len(last["title"]) <= 100
    assert len(last["summary"]) <= 203
    assert "superpower:" in last["summary"]
    for item in items:
        assert item["title"] and "<" not in item["title"] and "<" not in item["summary"]
        assert item["published_at"].tzinfo is not None
    assert len({item["guid"] for item in items}) == 20


def test_channel_without_posts_raises(fake_http):
    # Так t.me отвечает на закрытый или несуществующий канал после перенаправления с /s/
    fake_http.body = sample("tme_s_no_posts.html")

    with pytest.raises(ValueError):
        asyncio.run(telegram_handler.fetch("https://t.me/nosuchchannel_zq7x91"))


def test_channel_http_error_raises(fake_http):
    fake_http.status = 429
    fake_http.body = "Too Many Requests"

    with pytest.raises(Exception):
        asyncio.run(telegram_handler.fetch("https://t.me/durov"))


@pytest.mark.parametrize("path, expected", [
    ("/telegram/channel/ExampleChannel", "examplechannel"),
    ("/telegram/channel/examplechannel/showLinkPreview=0", "examplechannel"),
    ("/telegram/channel/examplechannel?limit=5", "examplechannel"),
    ("/telegram/stickerpack/examplechannel", None),
    ("/github/release/DIYgod/RSSHub", None),
])
def test_route_channel_name(path, expected):
    assert rsshub.route_channel_name(path) == expected
