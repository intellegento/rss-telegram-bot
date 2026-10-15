import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

import main
from config import FREE_KEYWORDS_LIMIT, FREE_SOURCES_LIMIT
from conftest import sample


@pytest.fixture(autouse=True)
def valid_feed(fake_http):
    # Проверка ленты при добавлении источника получает записанный ответ RSSHub, без сети
    fake_http.body = sample("rsshub_telegram_channel.xml")
    return fake_http


def make_update(user_id, text):
    update = MagicMock()
    update.effective_user.id = user_id
    update.message.text = text
    update.message.reply_text = AsyncMock()
    return update


def reply(bot_method, user_id, text, context=None):
    update = make_update(user_id, text)
    asyncio.run(bot_method(update, context or MagicMock()))
    return update.message.reply_text.await_args.args[0]


def test_adding_existing_keyword_via_bot_is_skipped(db):
    db.add_user(1)
    bot = main.NewsBot()

    reply(bot.process_new_keyword, 1, "bitcoin")
    text = reply(bot.process_new_keyword, 1, "Bitcoin, eth")

    assert "Добавлены ключевые слова: eth" in text
    assert "Уже существуют: Bitcoin" in text
    assert sorted(db.get_keywords(1)) == ["bitcoin", "eth"]


def test_keyword_limit_message_shows_usage_and_premium(db):
    db.add_user(1)
    bot = main.NewsBot()
    words = ", ".join(f"word{i}" for i in range(FREE_KEYWORDS_LIMIT))
    reply(bot.process_new_keyword, 1, words)

    text = reply(bot.process_new_keyword, 1, "extra")

    assert f"{FREE_KEYWORDS_LIMIT} из {FREE_KEYWORDS_LIMIT}" in text
    assert "ремиум" in text
    assert "Уже существуют" not in text


def test_keyword_for_unknown_user_asks_to_start(db):
    bot = main.NewsBot()

    assert "/start" in reply(bot.process_new_keyword, 1, "bitcoin")


def rss_context():
    context = MagicMock()
    context.user_data = {"source_type": "rss"}
    return context


def test_source_limit_message_shows_usage_and_premium(db):
    db.add_user(1)
    bot = main.NewsBot()
    for i in range(FREE_SOURCES_LIMIT):
        reply(bot.process_add_source, 1, f"S{i} | https://{i}.example/rss", rss_context())

    text = reply(bot.process_add_source, 1, "X | https://x.example/rss", rss_context())

    assert f"{FREE_SOURCES_LIMIT} из {FREE_SOURCES_LIMIT}" in text
    assert "ремиум" in text


def test_duplicate_source_message(db):
    db.add_user(1)
    bot = main.NewsBot()
    reply(bot.process_add_source, 1, "A | https://a.example/rss", rss_context())

    text = reply(bot.process_add_source, 1, "A | https://a.example/rss", rss_context())

    assert "уже есть" in text


def test_user_sees_only_own_sources(db):
    db.add_user(1)
    db.add_user(2)
    db.add_source(1, url="https://a.example/rss", name="Mine", source_type="rss")
    db.add_source(2, url="https://b.example/rss", name="Other", source_type="rss")
    bot = main.NewsBot()

    text = reply(bot.sources_command, 1, "/sources")

    assert "Mine" in text
    assert "Other" not in text


def test_source_name_and_url_with_html_chars_are_escaped(db):
    from html.parser import HTMLParser

    db.add_user(1)
    db.add_source(1, url="https://a.example/rss?a=1&b=<2>", name="A < B & C", source_type="rss")
    bot = main.NewsBot()
    update = make_update(1, "/sources")

    asyncio.run(bot.sources_command(update, MagicMock()))

    text = update.message.reply_text.await_args.args[0]
    assert update.message.reply_text.await_args.kwargs["parse_mode"] == "HTML"
    tags = []

    class Collector(HTMLParser):
        def handle_starttag(self, tag, attrs):
            tags.append(tag)

    Collector().feed(text)
    # Только теги самого бота, название и URL не ломают разметку
    assert set(tags) == {"b"}
    assert "A &lt; B &amp; C" in text
    assert "https://a.example/rss?a=1&amp;b=&lt;2&gt;" in text


def telegram_context():
    context = MagicMock()
    context.user_data = {"source_type": "telegram"}
    return context


def test_same_channel_added_differently_is_one_source(db, valid_feed):
    import database

    db.add_user(1)
    db.add_user(2)
    bot = main.NewsBot()

    reply(bot.process_add_source, 1, "@ExampleChannel", telegram_context())
    reply(bot.process_add_source, 2, "https://t.me/s/examplechannel/101", telegram_context())

    with db.Session() as session:
        sources = session.query(database.NewsSource).all()
    assert [(s.url, s.type) for s in sources] == [("https://t.me/examplechannel", "telegram")]
    assert db.get_sources(1)[0]["id"] == db.get_sources(2)[0]["id"] == sources[0].id
    assert valid_feed.urls == ["https://rsshub.app/telegram/channel/examplechannel"] * 2


def test_invalid_channel_feed_does_not_subscribe(db, valid_feed):
    db.add_user(1)
    bot = main.NewsBot()
    valid_feed.status = 503
    valid_feed.body = sample("rsshub_error.html")

    text = reply(bot.process_add_source, 1, "@privatechannel", telegram_context())

    assert "закрыт" in text and "веб-превью" in text
    assert db.get_sources(1) == []


def test_invalid_rss_feed_does_not_subscribe(db, valid_feed):
    db.add_user(1)
    bot = main.NewsBot()
    valid_feed.body = "<html>not a feed</html>"

    text = reply(bot.process_add_source, 1, "A | https://a.example/page", rss_context())

    assert "RSS" in text
    assert db.get_sources(1) == []


def test_not_a_channel_input_is_rejected(db, valid_feed):
    db.add_user(1)
    bot = main.NewsBot()

    text = reply(bot.process_add_source, 1, "https://example.com/x", telegram_context())

    assert "канал" in text
    assert valid_feed.urls == []
    assert db.get_sources(1) == []


def test_rsshub_url_is_stored_as_route_path(db, valid_feed):
    db.add_user(1)
    bot = main.NewsBot()

    reply(bot.process_add_source, 1, "YT | https://rsshub.app/youtube/channel/UC1", rss_context())
    reply(bot.process_add_source, 1, "Plain | https://a.example/rss", rss_context())

    sources = {src["name"]: (src["url"], src["type"]) for src in db.get_sources(1)}
    assert sources == {
        "YT": ("/youtube/channel/UC1", "rsshub"),
        "Plain": ("https://a.example/rss", "rss"),
    }


def test_source_limit_applies_to_all_types(db, valid_feed):
    db.add_user(1)
    bot = main.NewsBot()
    reply(bot.process_add_source, 1, "A | https://a.example/rss", rss_context())
    reply(bot.process_add_source, 1, "YT | https://rsshub.app/youtube/channel/UC1", rss_context())

    text = reply(bot.process_add_source, 1, "@examplechannel", telegram_context())

    assert f"{FREE_SOURCES_LIMIT} из {FREE_SOURCES_LIMIT}" in text
    assert len(db.get_sources(1)) == FREE_SOURCES_LIMIT


def test_sources_list_shows_all_types(db):
    db.add_user(1)
    db.add_source(1, url="https://t.me/examplechannel", name="@examplechannel", source_type="telegram")
    db.add_source(1, url="/youtube/channel/UC1", name="YT", source_type="rsshub")
    bot = main.NewsBot()

    text = reply(bot.sources_command, 1, "/sources")

    assert "@examplechannel" in text
    assert "YT" in text
