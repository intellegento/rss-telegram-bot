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


SAMPLES = os.path.join(ROOT, "tests", "samples")


def sample(name):
    with open(os.path.join(SAMPLES, name), encoding="utf-8") as f:
        return f.read()


VALID_RSS = """<?xml version="1.0"?>
<rss version="2.0"><channel><title>t</title>
<item><title>bitcoin</title><link>https://a.example/1</link></item>
</channel></rss>"""


class FakeHTTP:
    """Подменяет aiohttp.ClientSession: отдаёт заданный ответ и запоминает запросы.

    body может быть функцией от url, чтобы разные адреса получали разные ответы.
    """

    def __init__(self):
        self.status = 200
        self.body = ""
        self.urls = []
        self.timeouts = []

    def __call__(self, timeout=None, **kwargs):
        self.timeouts.append(timeout.total)
        return _FakeSession(self)


class _FakeSession:
    def __init__(self, http):
        self.http = http

    def get(self, url, **kwargs):
        self.http.urls.append(url)
        body = self.http.body(url) if callable(self.http.body) else self.http.body
        return _FakeResponse(self.http.status, body)

    post = get

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False


class _FakeResponse:
    def __init__(self, status, body):
        self.status = status
        self.body = body

    def raise_for_status(self):
        if self.status >= 400:
            raise RuntimeError(f"HTTP {self.status}")

    async def text(self):
        return self.body

    async def json(self):
        return self.body

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False


@pytest.fixture
def fake_http(monkeypatch):
    import aiohttp

    http = FakeHTTP()
    monkeypatch.setattr(aiohttp, "ClientSession", http)
    return http
