from app.operations import OperationsStore


def test_history_is_opt_in_and_can_be_deleted(tmp_path):
    store = OperationsStore(str(tmp_path / "ops.sqlite3"))
    user_id = 123
    store.save_prompt(user_id, "not saved by default", "natural", "English")
    assert store.get_history(user_id) == []

    store.set_history(user_id, True)
    store.save_prompt(user_id, "a detailed prompt", "natural", "English")
    rows = store.get_history(user_id)
    assert len(rows) == 1
    assert rows[0]["prompt"] == "a detailed prompt"

    store.set_history(user_id, False)
    assert store.get_history(user_id) == []
    assert not store.history_enabled(user_id)


def test_history_keeps_only_latest_twenty(tmp_path):
    store = OperationsStore(str(tmp_path / "ops.sqlite3"))
    store.set_history(7, True)
    for i in range(25):
        store.save_prompt(7, f"prompt-{i}", "tags", "English")
    rows = store.get_history(7, 20)
    assert len(rows) == 20
    assert rows[0]["prompt"] == "prompt-24"
    assert rows[-1]["prompt"] == "prompt-5"


def test_user_and_global_limits_are_enforced(tmp_path):
    store = OperationsStore(str(tmp_path / "ops.sqlite3"))
    ok, _ = store.allow_request(1, cooldown_seconds=0, user_daily_limit=2, global_daily_limit=3)
    assert ok
    ok, _ = store.allow_request(1, cooldown_seconds=0, user_daily_limit=2, global_daily_limit=3)
    assert ok
    ok, reason = store.allow_request(1, cooldown_seconds=0, user_daily_limit=2, global_daily_limit=3)
    assert not ok and "today's limit" in reason
    ok, _ = store.allow_request(2, cooldown_seconds=0, user_daily_limit=2, global_daily_limit=3)
    assert ok
    ok, reason = store.allow_request(3, cooldown_seconds=0, user_daily_limit=2, global_daily_limit=3)
    assert not ok and "daily processing capacity" in reason


def test_cooldown_and_admin_stats(tmp_path):
    store = OperationsStore(str(tmp_path / "ops.sqlite3"))
    ok, _ = store.allow_request(42, cooldown_seconds=60, user_daily_limit=10, global_daily_limit=0)
    assert ok
    ok, reason = store.allow_request(42, cooldown_seconds=60, user_daily_limit=10, global_daily_limit=0)
    assert not ok and "wait" in reason
    store.record_event(42, "failed")
    stats = store.admin_stats()
    assert stats["requests_today"] == 1
    assert stats["failures_today"] == 1
    assert stats["active_users_today"] == 1


def test_registered_users_can_be_listed_for_admin_tools(tmp_path):
    store = OperationsStore(str(tmp_path / "ops.sqlite3"))
    store.register_user(101, "anime_fan", "Anime", "Fan")
    store.register_user(202, first_name="New User")
    users = store.list_users()
    assert {item["user_id"] for item in users} == {101, 202}
    first = next(item for item in users if item["user_id"] == 101)
    assert first["username"] == "anime_fan"
    assert first["first_name"] == "Anime"


def test_registered_and_monthly_user_counts_in_sqlite_fallback(tmp_path):
    store = OperationsStore(str(tmp_path / "ops.sqlite3"))
    store.register_user(111, "active", "Active")
    store.register_user(222, "also_active", "Also")
    assert store.total_users_count() == 2
    assert store.monthly_active_users_count() == 2


def test_sleep_mode_persists_across_store_recreation(tmp_path):
    database = str(tmp_path / "state.sqlite3")
    first = OperationsStore(database)
    assert first.is_sleeping() is False
    first.set_sleeping(True)
    assert OperationsStore(database).is_sleeping() is True
    OperationsStore(database).set_sleeping(False)
    assert OperationsStore(database).is_sleeping() is False
