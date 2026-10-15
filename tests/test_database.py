def test_add_duplicate_source_returns_false(db):
    assert db.add_source(url="https://a.example/rss", name="A", source_type="rss")
    # Раньше падало с NameError: logger не определён
    assert db.add_source(url="https://a.example/rss", name="A", source_type="rss") is False
