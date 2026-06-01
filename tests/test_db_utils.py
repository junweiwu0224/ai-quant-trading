import sqlite3

from utils.db import get_connection


def test_get_connection_falls_back_when_wal_is_unavailable(monkeypatch, tmp_path):
    db_path = tmp_path / "fallback.db"
    real_connect = sqlite3.connect
    calls = []

    class CursorWrapper:
        def __init__(self, cursor):
            self._cursor = cursor

        def execute(self, sql, *args, **kwargs):
            calls.append(sql)
            if sql == "PRAGMA journal_mode=WAL":
                raise sqlite3.OperationalError("disk I/O error")
            return self._cursor.execute(sql, *args, **kwargs)

        def __getattr__(self, name):
            return getattr(self._cursor, name)

    class ConnectionWrapper:
        def __init__(self, conn):
            self._conn = conn
            self.row_factory = conn.row_factory

        def execute(self, sql, *args, **kwargs):
            calls.append(sql)
            if sql == "PRAGMA journal_mode=WAL":
                raise sqlite3.OperationalError("disk I/O error")
            return self._conn.execute(sql, *args, **kwargs)

        def cursor(self):
            return CursorWrapper(self._conn.cursor())

        def __getattr__(self, name):
            return getattr(self._conn, name)

        def __setattr__(self, name, value):
            if name == "row_factory" and "_conn" in self.__dict__:
                self._conn.row_factory = value
            object.__setattr__(self, name, value)

    def flaky_connect(*args, **kwargs):
        return ConnectionWrapper(real_connect(*args, **kwargs))

    monkeypatch.setattr(sqlite3, "connect", flaky_connect)

    conn = get_connection(db_path)
    try:
        assert "PRAGMA journal_mode=WAL" in calls
        assert "PRAGMA journal_mode=DELETE" in calls
        assert "PRAGMA busy_timeout=5000" in calls
        conn.execute("CREATE TABLE smoke (id INTEGER PRIMARY KEY)")
    finally:
        conn.close()
