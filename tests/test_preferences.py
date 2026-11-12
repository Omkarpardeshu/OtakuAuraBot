from app.preferences import PreferenceStore, DEFAULT_PREFERENCES


def test_defaults_are_returned_for_new_user(tmp_path):
    store = PreferenceStore(str(tmp_path / "prefs.sqlite3"))
    assert store.get(123) == DEFAULT_PREFERENCES


def test_preferences_persist_after_store_reopen(tmp_path):
    db = str(tmp_path / "prefs.sqlite3")
    first = PreferenceStore(db)
    first.update(123, output_mode="tags", detail_level="maximum", language="Hindi")

    second = PreferenceStore(db)
    assert second.get(123) == {
        "output_mode": "tags",
        "detail_level": "maximum",
        "language": "Hindi",
    }


def test_unknown_fields_do_not_change_preferences(tmp_path):
    store = PreferenceStore(str(tmp_path / "prefs.sqlite3"))
    result = store.update(123, not_a_setting="oops", language="Hinglish")
    assert result["language"] == "Hinglish"
    assert "not_a_setting" not in result


def test_new_users_default_to_anime_tags(tmp_path):
    store = PreferenceStore(str(tmp_path / "prefs.sqlite3"))
    assert store.get(12345)["output_mode"] == "tags"


def test_existing_natural_mode_is_migrated_to_tags(tmp_path):
    import sqlite3
    db = tmp_path / "prefs.sqlite3"
    connection = sqlite3.connect(db)
    connection.execute("CREATE TABLE user_preferences (user_id INTEGER PRIMARY KEY, output_mode TEXT NOT NULL DEFAULT 'natural', detail_level TEXT NOT NULL DEFAULT 'standard', language TEXT NOT NULL DEFAULT 'English', updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)")
    connection.execute("INSERT INTO user_preferences (user_id, output_mode, detail_level, language) VALUES (1, 'natural', 'standard', 'English')")
    connection.commit(); connection.close()
    store = PreferenceStore(str(db))
    assert store.get(1)["output_mode"] == "tags"
