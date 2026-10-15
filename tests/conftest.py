import os
import sys

import pytest
from dotenv import dotenv_values

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

# Тесты с БД работают только с отдельной базой TEST_DATABASE_URL (из окружения или .env)
_dotenv = dotenv_values(os.path.join(ROOT, ".env"))
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL") or _dotenv.get("TEST_DATABASE_URL")
SKIP_DB_REASON = "TEST_DATABASE_URL не задан"
if TEST_DATABASE_URL and TEST_DATABASE_URL == (os.environ.get("DATABASE_URL") or _dotenv.get("DATABASE_URL")):
    # Тесты очищают таблицы, поэтому рабочую базу не трогаем
    TEST_DATABASE_URL = None
    SKIP_DB_REASON = "TEST_DATABASE_URL совпадает с DATABASE_URL"

# Тесты не должны трогать реальную БД и реальный Telegram
os.environ["DATABASE_URL"] = TEST_DATABASE_URL or "postgresql+psycopg://unused@localhost/unused"
os.environ["TELEGRAM_TOKEN"] = "test-token"
os.environ["BINANCE_API_KEY"] = ""
os.environ["BINANCE_API_SECRET"] = ""


def _truncate_all():
    from sqlalchemy import text

    import database

    tables = ", ".join(table.name for table in database.Base.metadata.sorted_tables)
    with database.engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))


@pytest.fixture(scope="session")
def migrated_db():
    if not TEST_DATABASE_URL:
        pytest.skip(SKIP_DB_REASON)
    from alembic import command
    from alembic.config import Config

    config = Config()
    config.set_main_option("script_location", os.path.join(ROOT, "alembic"))
    command.upgrade(config, "head")


@pytest.fixture
def db(migrated_db):
    import database

    _truncate_all()
    yield database.DatabaseManager()
    _truncate_all()
