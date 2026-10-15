def test_add_duplicate_source_returns_false(db):
    assert db.add_source(url="https://a.example/rss", name="A", source_type="rss")
    # Раньше падало с NameError: logger не определён
    assert db.add_source(url="https://a.example/rss", name="A", source_type="rss") is False


def test_removed_source_can_be_added_again(db):
    assert db.add_source(url="https://a.example/rss", name="A", source_type="rss")
    [source] = db.get_sources()
    assert db.remove_source(source["id"])
    assert db.get_sources() == []

    assert db.add_source(url="https://a.example/rss", name="A2", source_type="rss")

    [restored] = db.get_sources()
    assert restored["id"] == source["id"]
    assert restored["name"] == "A2"


def test_large_telegram_id_is_stored_and_read(db):
    # ID в Telegram не помещаются в 32 бита
    db.add_user(7000000000)

    user = db.get_user(7000000000)

    assert user is not None
    assert user.telegram_id == 7000000000
