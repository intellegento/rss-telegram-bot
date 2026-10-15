import asyncio
from unittest.mock import AsyncMock, MagicMock

import main


def make_update(user_id, text):
    update = MagicMock()
    update.effective_user.id = user_id
    update.message.text = text
    update.message.reply_text = AsyncMock()
    return update


def test_adding_existing_keyword_via_bot_is_skipped(db):
    db.add_user(1)
    bot = main.NewsBot()

    asyncio.run(bot.process_new_keyword(make_update(1, "bitcoin"), MagicMock()))
    update = make_update(1, "Bitcoin, eth")
    asyncio.run(bot.process_new_keyword(update, MagicMock()))

    reply = update.message.reply_text.await_args.args[0]
    assert "Добавлены ключевые слова: eth" in reply
    assert "Уже существуют: Bitcoin" in reply
    assert sorted(db.get_keywords(1)) == ["bitcoin", "eth"]
