import importlib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
ENV_VARS = ["TELEGRAM_TOKEN", "DATABASE_URL", "BINANCE_API_KEY", "BINANCE_API_SECRET", "TEST_DATABASE_URL",
            "RSSHUB_BASE_URL"]


def test_config_reads_values_from_env(monkeypatch, capsys):
    import config

    monkeypatch.setenv("TELEGRAM_TOKEN", "token-from-env")
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u@h/from-env")
    importlib.reload(config)

    # Сравнение без вывода значений, чтобы при падении не напечатать секрет
    token_from_env = config.TELEGRAM_TOKEN == "token-from-env"
    assert token_from_env, "TELEGRAM_TOKEN не читается из окружения"
    assert config.DATABASE_URL == "postgresql+psycopg://u@h/from-env"
    assert "token-from-env" not in capsys.readouterr().out, "токен печатается в stdout"


def test_env_example_lists_all_vars_without_values():
    lines = (ROOT / ".env.example").read_text().splitlines()
    entries = dict(line.split("=", 1) for line in lines if line and not line.startswith("#"))
    assert sorted(entries) == sorted(ENV_VARS)
    assert all(value == "" for value in entries.values())


@pytest.mark.parametrize("value", ["", None])
def test_missing_database_url_exits_with_message(monkeypatch, value):
    import config

    # .env не подгружаем, чтобы проверить именно отсутствие переменной
    monkeypatch.setattr("dotenv.load_dotenv", lambda *a, **k: None)
    if value is None:
        monkeypatch.delenv("DATABASE_URL")
    else:
        monkeypatch.setenv("DATABASE_URL", value)

    with pytest.raises(SystemExit) as exc:
        importlib.reload(config)
    assert "DATABASE_URL" in str(exc.value.code)

    monkeypatch.undo()
    importlib.reload(config)


@pytest.mark.parametrize("url", [
    "postgresql://u@h/db",
    "postgres://u@h/db",
    "postgresql+psycopg://u@h/db",
])
def test_database_url_scheme_is_normalized_to_psycopg(monkeypatch, url):
    import config

    # Интеграция Neon в Vercel отдаёт postgresql:// или postgres://
    monkeypatch.setenv("DATABASE_URL", url)
    importlib.reload(config)
    assert config.DATABASE_URL == "postgresql+psycopg://u@h/db"

    monkeypatch.undo()
    importlib.reload(config)


@pytest.mark.parametrize("value, expected", [
    (None, "https://rsshub.app"),
    ("", "https://rsshub.app"),
    ("https://rsshub.example.com/", "https://rsshub.example.com"),
])
def test_rsshub_base_url(monkeypatch, value, expected):
    import config

    monkeypatch.setattr("dotenv.load_dotenv", lambda *a, **k: None)
    if value is None:
        monkeypatch.delenv("RSSHUB_BASE_URL", raising=False)
    else:
        monkeypatch.setenv("RSSHUB_BASE_URL", value)
    importlib.reload(config)
    assert config.RSSHUB_BASE_URL == expected

    monkeypatch.undo()
    importlib.reload(config)
