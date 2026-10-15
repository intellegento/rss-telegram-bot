from unittest.mock import patch

from telegram.ext import Application

import main


def test_main_starts_without_exceptions():
    # Сеть не трогаем: run_polling подменён
    with patch.object(Application, "run_polling") as run_polling:
        main.main()
    run_polling.assert_called_once()
