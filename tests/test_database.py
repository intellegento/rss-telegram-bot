from datetime import datetime, timedelta, timezone

import pytest

from config import FREE_KEYWORDS_LIMIT, FREE_SOURCES_LIMIT


def set_premium_until(db, telegram_id, value):
    import database

    with db.Session() as session:
        session.query(database.User).filter_by(telegram_id=telegram_id).update({"premium_until": value})
        session.commit()


def test_large_telegram_id_is_stored_and_read(db):
    # ID в Telegram не помещаются в 32 бита
    db.add_user(7000000000)

    user = db.get_user(7000000000)

    assert user is not None
    assert user.telegram_id == 7000000000


def test_adding_same_keyword_twice_does_not_fail_or_duplicate(db):
    import database

    db.add_user(1)

    assert db.add_keyword(1, "bitcoin") == database.ADDED
    assert db.add_keyword(1, "Bitcoin") == database.DUPLICATE

    assert db.get_keywords(1) == ["bitcoin"]


def test_add_keyword_without_user_is_reported(db):
    import database

    assert db.add_keyword(1, "bitcoin") == database.NO_USER


def test_free_user_cannot_add_keyword_over_limit(db):
    import database

    db.add_user(1)
    for i in range(FREE_KEYWORDS_LIMIT):
        assert db.add_keyword(1, f"word{i}") == database.ADDED

    assert db.add_keyword(1, "extra") == database.LIMIT
    # Дубль на лимите остаётся дублем, а не превышением лимита
    assert db.add_keyword(1, "word0") == database.DUPLICATE
    assert len(db.get_keywords(1)) == FREE_KEYWORDS_LIMIT


def test_premium_user_can_add_keyword_over_limit(db):
    import database

    db.add_user(1)
    set_premium_until(db, 1, datetime.now(timezone.utc) + timedelta(days=1))
    for i in range(FREE_KEYWORDS_LIMIT + 1):
        assert db.add_keyword(1, f"word{i}") == database.ADDED


def test_is_premium():
    from database import User, is_premium

    now = datetime.now(timezone.utc)
    assert not is_premium(User(premium_until=None))
    assert not is_premium(User(premium_until=now - timedelta(seconds=1)))
    assert is_premium(User(premium_until=now + timedelta(days=1)))


def test_source_is_shared_and_subscription_is_personal(db):
    import database

    db.add_user(1)
    db.add_user(2)

    assert db.add_source(1, url="https://a.example/rss", name="A", source_type="rss") == database.ADDED
    assert db.add_source(1, url="https://a.example/rss", name="A", source_type="rss") == database.DUPLICATE
    assert db.add_source(2, url="https://a.example/rss", name="A2", source_type="rss") == database.ADDED

    with db.Session() as session:
        assert session.query(database.NewsSource).count() == 1
    assert db.get_sources(1)[0]["id"] == db.get_sources(2)[0]["id"]


def test_add_source_without_user_is_reported(db):
    import database

    assert db.add_source(1, url="https://a.example/rss", name="A", source_type="rss") == database.NO_USER


def test_user_does_not_see_and_cannot_remove_other_users_sources(db):
    db.add_user(1)
    db.add_user(2)
    db.add_source(1, url="https://a.example/rss", name="A", source_type="rss")
    db.add_source(2, url="https://b.example/rss", name="B", source_type="rss")
    [source_b] = db.get_sources(2)

    assert [src["name"] for src in db.get_sources(1)] == ["A"]
    assert db.remove_source(1, source_b["id"]) is False
    assert db.get_sources(2) == [source_b]


def test_removing_source_removes_only_subscription(db):
    import database

    db.add_user(1)
    db.add_user(2)
    db.add_source(1, url="https://a.example/rss", name="A", source_type="rss")
    db.add_source(2, url="https://a.example/rss", name="A", source_type="rss")
    [source] = db.get_sources(1)

    assert db.remove_source(1, source["id"]) is True

    assert db.get_sources(1) == []
    assert len(db.get_sources(2)) == 1
    with db.Session() as session:
        assert session.get(database.NewsSource, source["id"]).is_active


def test_free_user_cannot_add_source_over_limit(db):
    import database

    db.add_user(1)
    for i in range(FREE_SOURCES_LIMIT):
        assert db.add_source(1, url=f"https://{i}.example/rss", name=str(i), source_type="rss") == database.ADDED

    assert db.add_source(1, url="https://extra.example/rss", name="x", source_type="rss") == database.LIMIT
    assert db.add_source(1, url="https://0.example/rss", name="0", source_type="rss") == database.DUPLICATE
    assert len(db.get_sources(1)) == FREE_SOURCES_LIMIT


def test_premium_user_can_add_source_over_limit(db):
    import database

    db.add_user(1)
    set_premium_until(db, 1, datetime.now(timezone.utc) + timedelta(days=1))
    for i in range(FREE_SOURCES_LIMIT + 1):
        assert db.add_source(1, url=f"https://{i}.example/rss", name=str(i), source_type="rss") == database.ADDED


@pytest.mark.parametrize("statement", [
    "INSERT INTO users (telegram_id) VALUES (NULL)",
    "INSERT INTO keywords (user_id, word) VALUES (NULL, 'x')",
    "INSERT INTO news_sources (url) VALUES (NULL)",
])
def test_required_columns_are_not_null(db, statement):
    from sqlalchemy import text
    from sqlalchemy.exc import IntegrityError

    import database

    with pytest.raises(IntegrityError):
        with database.engine.begin() as conn:
            conn.execute(text(statement))
