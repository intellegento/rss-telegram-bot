from unittest.mock import patch

from telegram.ext import Application, ChatMemberHandler, MessageHandler

import main


def test_main_starts_without_exceptions():
    # Сеть не трогаем: run_polling подменён
    with patch.object(Application, "run_polling", autospec=True) as run_polling:
        main.main()
    run_polling.assert_called_once()

    # Мониторинга групп больше нет: ни MY_CHAT_MEMBER, ни обработчиков вне ConversationHandler
    application = run_polling.call_args.args[0]
    handlers = [h for group in application.handlers.values() for h in group]
    assert not any(isinstance(h, (ChatMemberHandler, MessageHandler)) for h in handlers)


def test_telegram_token_is_not_logged(caplog):
    import logging

    from config import TELEGRAM_TOKEN

    # Под pytest basicConfig в main ничего не меняет; уровень INFO как при реальном запуске
    caplog.set_level(logging.INFO)
    with patch.object(Application, "run_polling"):
        main.main()
    # Так httpx логирует каждый запрос к Bot API: токен входит в URL
    for name in ("httpx", "httpcore"):
        logging.getLogger(name).info(f"HTTP Request: POST https://api.telegram.org/bot{TELEGRAM_TOKEN}/getMe")

    leaked = any(TELEGRAM_TOKEN in record.getMessage() for record in caplog.records)
    assert not leaked, "токен бота попал в логи"
