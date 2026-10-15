import asyncio
from unittest.mock import AsyncMock, MagicMock

import main
from config import FREE_KEYWORDS_LIMIT, FREE_SOURCES_LIMIT


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
