import asyncio
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from unittest.mock import AsyncMock, MagicMock, patch

from telegram.error import Forbidden

import pipeline

URL = "https://a.example/rss"


def make_items(n, title="bitcoin news", published_at=None, guid="guid"):
    # Без даты публикации доставка сравнивает fetched_at: обе отметки ставит часы БД
    return [
        {
            "guid": f"{guid}-{i}",
            "title": f"{title} {i}",
            "url": f"https://a.example/{i}",
            "summary": "text",
            "published_at": published_at and published_at + timedelta(minutes=i),
        }
        for i in range(n)
    ]


def subscribe(db, telegram_id, keyword="bitcoin", url=URL):
    if not db.get_user(telegram_id):
        db.add_user(telegram_id)
    db.add_keyword(telegram_id, keyword)
    db.add_source(telegram_id, url=url, name="A", source_type="rss")


def make_due():
    """Делает все источники готовыми к опросу, не дожидаясь интервала."""
    import database
    from sqlalchemy import text

    with database.engine.begin() as conn:
        conn.execute(text("UPDATE news_sources SET next_fetch_at = now() - interval '1 second'"))


def collect(items):
    make_due()
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


def test_posts_published_before_subscription_are_not_delivered(db):
    # Первый подписчик нового источника не получает старые посты ленты
    subscribe(db, 1)
    collect(make_items(30, published_at=datetime(2025, 1, 1, tzinfo=timezone.utc), guid="old"))
    bot = make_bot()

    assert deliver(bot) == 0

    # Запас в час, чтобы не зависеть от расхождения часов с БД
    collect(make_items(1, title="bitcoin fresh", published_at=datetime.now(timezone.utc) + timedelta(hours=1)))
    assert deliver(bot) == 1
    [(_, text)] = sent(bot)
    assert "bitcoin fresh 0" in text


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
    from config import FETCH_INTERVAL_MINUTES

    assert set(pipeline.FETCHERS) == {"rss", "binance", "telegram", "rsshub"}
    assert set(FETCH_INTERVAL_MINUTES) == set(pipeline.FETCHERS)


def source_state(db):
    """error_count и задержка до следующего опроса в минутах по часам БД."""
    import database
    from sqlalchemy import text

    with database.engine.connect() as conn:
        return conn.execute(text(
            "SELECT error_count, extract(epoch FROM next_fetch_at - now()) / 60 FROM news_sources"
        )).one()


def add_channel(db, telegram_id, url="https://t.me/examplechannel"):
    if not db.get_user(telegram_id):
        db.add_user(telegram_id)
    db.add_keyword(telegram_id, "bitcoin")
    db.add_source(telegram_id, url=url, name="@examplechannel", source_type="telegram")


def test_source_is_not_fetched_before_next_fetch_at(db):
    subscribe(db, 1)
    collect(make_items(1))

    fetch = AsyncMock(return_value=[])
    with patch.dict(pipeline.FETCHERS, {"rss": fetch}):
        asyncio.run(pipeline.collect())

    fetch.assert_not_awaited()
    # Обычный RSS опрашивается не чаще раза в 10 минут
    _, delay = source_state(db)
    assert 9 < delay <= 10


def test_429_backs_off_and_success_resets(db, fake_http):
    from conftest import sample

    add_channel(db, 1)
    fake_http.status = 429
    fake_http.body = "Too Many Requests"

    make_due()
    asyncio.run(pipeline.collect())
    errors, first_delay = source_state(db)
    assert errors == 1
    assert 59 < first_delay <= 60  # 30 минут для telegram, удвоено

    make_due()
    asyncio.run(pipeline.collect())
    errors, second_delay = source_state(db)
    assert errors == 2
    assert 119 < second_delay <= 120

    fake_http.status = 200
    fake_http.body = sample("tme_s_durov.html")
    make_due()
    assert asyncio.run(pipeline.collect()) == 20
    errors, delay = source_state(db)
    assert errors == 0
    assert 29 < delay <= 30


def test_backoff_is_capped_at_24_hours(db, fake_http):
    import database

    add_channel(db, 1)
    with db.Session() as session:
        session.query(database.NewsSource).update({"error_count": 50})
        session.commit()
    fake_http.status = 503

    make_due()
    asyncio.run(pipeline.collect())

    errors, delay = source_state(db)
    assert errors == 51
    assert 24 * 60 - 1 < delay <= 24 * 60


def test_channel_page_without_posts_counts_as_error(db, fake_http):
    from conftest import sample

    add_channel(db, 1)
    fake_http.body = sample("tme_s_no_posts.html")

    make_due()
    asyncio.run(pipeline.collect())

    assert source_state(db)[0] == 1


def test_rsshub_base_url_change_needs_no_db_change(db, fake_http, monkeypatch):
    import database
    from conftest import VALID_RSS, sample

    add_channel(db, 1)
    db.add_source(1, url="/youtube/channel/UC1", name="YT", source_type="rsshub")
    fake_http.body = lambda url: sample("tme_s_durov.html") if url.startswith("https://t.me/") else VALID_RSS
    with db.Session() as session:
        before = sorted((s.url, s.type) for s in session.query(database.NewsSource))

    for base in ("https://rsshub.example.com", "https://rss.example.org"):
        monkeypatch.setattr("config.RSSHUB_BASE_URL", base)
        make_due()
        asyncio.run(pipeline.collect())

    # Канал читается с t.me независимо от RSSHub, маршрут — с текущего экземпляра RSSHub
    assert sorted(fake_http.urls) == [
        "https://rss.example.org/youtube/channel/UC1",
        "https://rsshub.example.com/youtube/channel/UC1",
        "https://t.me/s/examplechannel",
        "https://t.me/s/examplechannel",
    ]
    with db.Session() as session:
        assert sorted((s.url, s.type) for s in session.query(database.NewsSource)) == before
    assert before == [("/youtube/channel/UC1", "rsshub"), ("https://t.me/examplechannel", "telegram")]


def test_telegram_post_link_points_to_telegram(db, fake_http):
    from conftest import sample

    add_channel(db, 1, url="https://t.me/durov")
    db.add_keyword(1, "designers")
    # Посты образца опубликованы до подписки: делаем подписку старше них
    with db.Session() as session:
        from sqlalchemy import text
        session.execute(text("UPDATE user_sources SET created_at = '2025-01-01'"))
        session.commit()
    fake_http.body = sample("tme_s_durov.html")
    make_due()
    asyncio.run(pipeline.collect())
    bot = make_bot()

    deliver(bot)

    [(_, message)] = sent(bot)
    assert "href='https://t.me/durov/552'" in message
    assert "<b>✨ Designers × AI" in message
