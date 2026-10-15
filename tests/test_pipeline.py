import asyncio
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from unittest.mock import AsyncMock, MagicMock, patch

from telegram.error import Forbidden

import pipeline

URL = "https://a.example/rss"


def make_items(n, title="bitcoin news"):
    base = datetime(2025, 1, 1, tzinfo=timezone.utc)
    return [
        {
            "guid": f"guid-{i}",
            "title": f"{title} {i}",
            "url": f"https://a.example/{i}",
            "summary": "text",
            "published_at": base + timedelta(minutes=i),
        }
        for i in range(n)
    ]


def subscribe(db, telegram_id, keyword="bitcoin", url=URL):
    if not db.get_user(telegram_id):
        db.add_user(telegram_id)
    db.add_keyword(telegram_id, keyword)
    db.add_source(telegram_id, url=url, name="A", source_type="rss")


def collect(items):
    fetch = AsyncMock(return_value=items)
    with patch.dict(pipeline.FETCHERS, {"rss": fetch}):
        new = asyncio.run(pipeline.collect())
    return fetch, new


def make_bot():
    bot = MagicMock()
    bot.send_message = AsyncMock()
    return bot


def deliver(bot):
    with patch("pipeline.asyncio.sleep", AsyncMock()):
        return asyncio.run(pipeline.deliver(bot))


def sent(bot):
    return [(call.kwargs["chat_id"], call.kwargs["text"]) for call in bot.send_message.await_args_list]


def count(db, model):
    with db.Session() as session:
        return session.query(model).count()


def test_source_without_subscribers_is_not_fetched(db):
    db.add_user(1)
    db.add_source(1, url=URL, name="A", source_type="rss")
    [source] = db.get_sources(1)
    db.remove_source(1, source["id"])

    fetch, _ = collect(make_items(1))

    fetch.assert_not_awaited()


def test_source_with_two_subscribers_is_fetched_once(db):
    subscribe(db, 1)
    subscribe(db, 2)

    fetch, _ = collect(make_items(1))

    fetch.assert_awaited_once_with(URL)


def test_inactive_source_is_not_fetched(db):
    import database

    subscribe(db, 1)
    with db.Session() as session:
        session.query(database.NewsSource).update({"is_active": False})
        session.commit()

    fetch, _ = collect(make_items(1))

    fetch.assert_not_awaited()


def test_repeated_collect_does_not_duplicate_posts(db):
    import database

    subscribe(db, 1)

    assert collect(make_items(3))[1] == 3
    assert collect(make_items(3))[1] == 0

    assert count(db, database.Post) == 3
    assert db.get_sources(1)[0]["last_fetch"] is not None


def test_failed_fetch_does_not_stop_other_sources(db):
    import database

    subscribe(db, 1, url="https://bad.example/rss")
    subscribe(db, 1, url=URL)

    async def fetch(url):
        if "bad" in url:
            raise RuntimeError("недоступен")
        return make_items(2)

    with patch.dict(pipeline.FETCHERS, {"rss": fetch}):
        asyncio.run(pipeline.collect())

    assert count(db, database.Post) == 2


def test_post_fetched_before_subscription_is_not_delivered(db):
    subscribe(db, 1)
    collect(make_items(1))
    subscribe(db, 2)

    bot = make_bot()
    deliver(bot)

    assert [chat_id for chat_id, _ in sent(bot)] == [1]


def test_only_posts_matching_keywords_are_delivered(db):
    subscribe(db, 1, keyword="ETH")
    items = make_items(3)
    items[1]["summary"] = "About eth today"
    collect(items)

    bot = make_bot()
    deliver(bot)

    [(_, text)] = sent(bot)
    assert "bitcoin news 1" in text


def test_posts_over_limit_are_delivered_in_next_run(db):
    subscribe(db, 1)
    collect(make_items(15))
    bot = make_bot()

    assert deliver(bot) == 10
    first = sent(bot)
    bot.send_message.reset_mock()
    assert deliver(bot) == 5
    second = sent(bot)

    assert len(set(first + second)) == 15
    bot.send_message.reset_mock()
    assert deliver(bot) == 0


def test_failed_send_does_not_create_delivery(db):
    import database

    subscribe(db, 1)
    collect(make_items(1))
    bot = make_bot()
    bot.send_message.side_effect = Exception("Telegram недоступен")

    assert deliver(bot) == 0
    assert count(db, database.Delivery) == 0

    bot.send_message.side_effect = None
    assert deliver(bot) == 1
    assert count(db, database.Delivery) == 1


def test_user_who_blocked_bot_is_deactivated(db):
    subscribe(db, 1)
    subscribe(db, 2)
    collect(make_items(2))
    bot = make_bot()

    async def send_message(chat_id, **kwargs):
        if chat_id == 1:
            raise Forbidden("Forbidden: bot was blocked by the user")

    bot.send_message.side_effect = send_message

    deliver(bot)

    assert db.get_user(1).is_active is False
    assert db.get_user(2).is_active is True
    # После блокировки боту больше не пытаются отправить ни одной новости
    assert [call.kwargs["chat_id"] for call in bot.send_message.await_args_list].count(1) == 1

    collect(make_items(3))
    bot.send_message.reset_mock()
    deliver(bot)
    assert 1 not in [call.kwargs["chat_id"] for call in bot.send_message.await_args_list]


def test_collect_removes_old_posts_with_deliveries(db):
    import database
    from config import POSTS_RETENTION_DAYS

    subscribe(db, 1)
    collect(make_items(2))
    deliver(make_bot())
    with db.Session() as session:
        old = session.query(database.Post).filter_by(guid_hash=pipeline.guid_hash("guid-0")).one()
        old.fetched_at = datetime.now(timezone.utc) - timedelta(days=POSTS_RETENTION_DAYS, minutes=1)
        session.commit()

    collect([])

    with db.Session() as session:
        assert [p.title for p in session.query(database.Post)] == ["bitcoin news 1"]
        assert session.query(database.Delivery).count() == 1


def html_tags(text):
    tags = []

    class Collector(HTMLParser):
        def handle_starttag(self, tag, attrs):
            tags.append(tag)

    Collector().feed(text)
    return tags


def test_title_with_html_special_chars_is_escaped(db):
    subscribe(db, 1)
    items = make_items(1, title="bitcoin <b>2 > 1</b> & <script>")
    items[0]["summary"] = "a < b & c > d"
    collect(items)
    bot = make_bot()

    deliver(bot)

    [(_, text)] = sent(bot)
    # Остаются только теги, которые добавляет сам бот
    assert html_tags(text) == ["b", "a"]
    assert "bitcoin &lt;b&gt;2 &gt; 1&lt;/b&gt; &amp; &lt;script&gt;" in text
    assert "a &lt; b &amp; c &gt; d" in text


def test_fetchers_cover_source_types():
    assert set(pipeline.FETCHERS) == {"rss", "binance"}
