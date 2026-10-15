import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import main

USER_ID = 111


def make_news(n, title="bitcoin news"):
    base = datetime(2025, 1, 1, tzinfo=timezone.utc)
    return [
        {
            "title": f"{title} {i}",
            "link": f"https://a.example/{i}",
            "description": "text",
            "published": base + timedelta(minutes=i),
            "hash": f"hash-{i}",
        }
        for i in range(n)
    ]


@pytest.fixture
def bot(db):
    db.add_user(USER_ID)
    db.add_keyword(USER_ID, "bitcoin")
    db.add_source(url="https://a.example/rss", name="A", source_type="rss")
    news_bot = main.NewsBot()
    news_bot.rss_handler = MagicMock()
    return news_bot


def make_context():
    context = MagicMock()
    context.bot.send_message = AsyncMock()
    return context


def run_cycle(bot, context, news):
    bot.rss_handler.get_news = AsyncMock(return_value=news)
    with patch("main.asyncio.sleep", AsyncMock()):
        asyncio.run(bot.check_news(context))


def sent_texts(context):
    return [call.kwargs["text"] for call in context.bot.send_message.await_args_list]


def test_news_over_limit_are_sent_in_next_cycle(bot):
    news = make_news(15)
    context = make_context()

    run_cycle(bot, context, news)
    first = sent_texts(context)
    assert len(first) == 10

    context.bot.send_message.reset_mock()
    run_cycle(bot, context, news)
    second = sent_texts(context)
    assert len(second) == 5

    assert len(set(first + second)) == 15

    context.bot.send_message.reset_mock()
    run_cycle(bot, context, news)
    assert sent_texts(context) == []


def test_failed_send_does_not_mark_news_as_seen(bot):
    news = make_news(1)
    context = make_context()
    context.bot.send_message.side_effect = Exception("Telegram недоступен")

    run_cycle(bot, context, news)
    assert not bot.db.is_news_seen(USER_ID, "hash-0")

    context.bot.send_message.side_effect = None
    run_cycle(bot, context, news)
    assert context.bot.send_message.await_count == 2
    assert bot.db.is_news_seen(USER_ID, "hash-0")
