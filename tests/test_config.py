import importlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENV_VARS = ["TELEGRAM_TOKEN", "DATABASE_URL", "BINANCE_API_KEY", "BINANCE_API_SECRET"]


def test_config_reads_values_from_env(monkeypatch, capsys):
    import config

    monkeypatch.setenv("TELEGRAM_TOKEN", "token-from-env")
    monkeypatch.setenv("DATABASE_URL", "sqlite:///from-env.db")
    importlib.reload(config)

    # Сравнение без вывода значений, чтобы при падении не напечатать секрет
    token_from_env = config.TELEGRAM_TOKEN == "token-from-env"
    assert token_from_env, "TELEGRAM_TOKEN не читается из окружения"
    assert config.DATABASE_URL == "sqlite:///from-env.db"
    assert "token-from-env" not in capsys.readouterr().out, "токен печатается в stdout"


def test_env_example_lists_all_vars_without_values():
    lines = (ROOT / ".env.example").read_text().splitlines()
    entries = dict(line.split("=", 1) for line in lines if line and not line.startswith("#"))
    assert sorted(entries) == sorted(ENV_VARS)
    assert all(value == "" for value in entries.values())
