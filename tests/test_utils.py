from datetime import datetime, timezone
from html.parser import HTMLParser

import pytest

from utils import format_message, matches_keywords


def links(text):
    hrefs = []

    class Collector(HTMLParser):
        def handle_starttag(self, tag, attrs):
            if tag == "a":
                hrefs.append(dict(attrs).get("href"))

    Collector().feed(text)
    return hrefs


def make_post(url):
    return {
        "title": "t",
        "url": url,
        "summary": "s",
        "published_at": datetime(2025, 1, 1, tzinfo=timezone.utc),
        "source": "rss",
    }


def test_link_with_quotes_is_escaped_in_href():
    url = "https://a.example/?q=\"x'y\"&a=<b>"

    text = format_message(make_post(url))

    assert links(text) == [url]
    assert "<b>" not in text.split("href")[1]


@pytest.mark.parametrize("url", ["javascript:alert(1)", "JavaScript:alert(1)", "data:text/html,x", "", None])
def test_non_http_link_is_not_put_into_href(url):
    text = format_message(make_post(url))

    assert links(text) == []
    assert "javascript" not in text.lower()


def test_message_without_date():
    post = make_post("https://a.example/1")
    post["published_at"] = None

    assert "Дата не указана" in format_message(post)


@pytest.mark.parametrize("title, summary, keywords, expected", [
    ("Bitcoin rises", "", ["bitcoin"], True),
    ("news", "about ETH", ["eth"], True),
    ("news", "about eth", ["ETH"], True),
    ("news", None, ["eth"], False),
    ("news", "text", [], False),
])
def test_matches_keywords(title, summary, keywords, expected):
    assert matches_keywords(title, summary, keywords) is expected


def test_telegram_post_is_shown_with_text_start(fake_http):
    import asyncio

    from conftest import sample
    from news_sources import telegram_handler

    fake_http.body = sample("tme_s_durov.html")
    post = asyncio.run(telegram_handler.fetch("https://t.me/durov"))[-1]
    post["source"] = "telegram"

    text = format_message(post)

    assert "<b>✨ Designers × AI 🆕 The mockup era is over." in text
    assert links(text) == ["https://t.me/durov/552"]
    assert "💰" not in text
