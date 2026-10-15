import os
import sys

# Тесты не должны трогать реальную БД и реальный Telegram
os.environ["DATABASE_URL"] = "sqlite://"
os.environ["TELEGRAM_TOKEN"] = "test-token"
os.environ["BINANCE_API_KEY"] = ""
os.environ["BINANCE_API_SECRET"] = ""

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest


@pytest.fixture
def db():
    import database

    database.Base.metadata.drop_all(database.engine)
    database.Base.metadata.create_all(database.engine)
    return database.DatabaseManager()
