from app.key_store import GeminiKeyStore


def test_add_list_remove_admin_keys(tmp_path):
    store = GeminiKeyStore(str(tmp_path / "keys.json"))
    assert store.list_keys() == []
    assert store.add(" key-one ") is True
    assert store.add("key-one") is False
    assert store.add("key-two") is True
    assert store.list_keys() == ["key-one", "key-two"]
    assert store.remove(2) == "key-two"
    assert store.remove(9) is None
    assert store.list_keys() == ["key-one"]


def test_empty_key_rejected(tmp_path):
    store = GeminiKeyStore(str(tmp_path / "keys.json"))
    try:
        store.add("  ")
    except ValueError:
        pass
    else:
        raise AssertionError("empty API key should be rejected")
