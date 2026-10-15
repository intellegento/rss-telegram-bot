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
