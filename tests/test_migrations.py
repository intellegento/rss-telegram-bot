import os

from sqlalchemy import text

from conftest import ROOT, _truncate_all

INITIAL_REVISION = "0f407fd44174"


def alembic_config():
    from alembic.config import Config

    config = Config()
    config.set_main_option("script_location", os.path.join(ROOT, "alembic"))
    return config


def test_migration_deactivates_telegram_group_sources(migrated_db):
    from alembic import command

    import database

    _truncate_all()
    command.downgrade(alembic_config(), INITIAL_REVISION)
    try:
        with database.engine.begin() as conn:
            conn.execute(text(
                "INSERT INTO news_sources (url, name, type, is_active) VALUES "
                "('-100123', 'group', 'telegram', true), ('https://a.example/rss', 'A', 'rss', true)"
            ))
    finally:
        command.upgrade(alembic_config(), "head")

    with database.engine.connect() as conn:
        rows = dict(conn.execute(text("SELECT type, is_active FROM news_sources")).all())
    _truncate_all()

    assert rows == {"telegram": False, "rss": True}
