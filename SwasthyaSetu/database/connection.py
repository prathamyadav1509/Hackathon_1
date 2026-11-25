import os
import socket
import sqlite3
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(dotenv_path=BASE_DIR / ".env")

try:
    import psycopg2
except ImportError:
    psycopg2 = None

_DETECTED_AUTO_BACKEND = None
_INITIALIZED_DBS = set()


class _CompatCursor:
    """Wraps sqlite3.Cursor to accept PostgreSQL-style %s placeholders."""

    def __init__(self, cursor):
        self._cursor = cursor

    def execute(self, query, params=None):
        sqlite_query = query.replace("%s", "?")
        if params is None:
            return self._cursor.execute(sqlite_query)
        return self._cursor.execute(sqlite_query, params)

    def fetchall(self):
        return self._cursor.fetchall()

    def fetchone(self):
        return self._cursor.fetchone()

    def close(self):
        self._cursor.close()

    def __getattr__(self, name):
        return getattr(self._cursor, name)


class _CompatSQLiteConnection:
    """SQLite connection wrapper compatible with psycopg2 call patterns."""

    backend = "sqlite"

    def __init__(self, db_path):
        self._conn = sqlite3.connect(db_path, check_same_thread=False)

    def cursor(self):
        return _CompatCursor(self._conn.cursor())

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def close(self):
        self._conn.close()


def _get_sqlite_path():
    raw_path = os.getenv("SQLITE_DB_PATH", "database/swasthyasetu.db")
    path = Path(raw_path)
    if not path.is_absolute():
        path = BASE_DIR / path
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _is_postgres_reachable():
    if psycopg2 is None:
        return False
    host = os.getenv("DB_HOST", "localhost")
    port = int(os.getenv("DB_PORT", "5432"))
    try:
        with socket.create_connection((host, port), timeout=0.3):
            return True
    except OSError:
        return False


def _connect_postgres():
    if psycopg2 is None:
        raise RuntimeError("psycopg2 is not installed.")

    return psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=os.getenv("DB_PORT", "5432"),
        database=os.getenv("DB_NAME", "swasthyasetu"),
        user=os.getenv("DB_USER", "postgres"),
        password=os.getenv("DB_PASSWORD", "2005"),
        connect_timeout=2,
    )


def get_connection():
    """
    Returns a database connection.
    Uses PostgreSQL when DB_BACKEND=postgres or when PostgreSQL is reachable in auto mode;
    otherwise falls back to a local SQLite database so the app runs out-of-the-box.
    """
    global _DETECTED_AUTO_BACKEND

    backend = os.getenv("DB_BACKEND", "auto").strip().lower()

    if backend == "sqlite":
        return _CompatSQLiteConnection(_get_sqlite_path())

    if backend == "postgres":
        return _connect_postgres()

    if _DETECTED_AUTO_BACKEND is None:
        if _is_postgres_reachable():
            try:
                conn = _connect_postgres()
                _DETECTED_AUTO_BACKEND = "postgres"
                return conn
            except Exception:
                _DETECTED_AUTO_BACKEND = "sqlite"
        else:
            _DETECTED_AUTO_BACKEND = "sqlite"

    if _DETECTED_AUTO_BACKEND == "postgres":
        try:
            return _connect_postgres()
        except Exception:
            _DETECTED_AUTO_BACKEND = "sqlite"

    return _CompatSQLiteConnection(_get_sqlite_path())


def ensure_tables():
    """Creates required tables if they do not exist yet."""
    sqlite_key = str(_get_sqlite_path())
    backend = os.getenv("DB_BACKEND", "auto").strip().lower()
    cache_key = (backend, sqlite_key)
    if cache_key in _INITIALIZED_DBS and Path(sqlite_key).exists():
        return

    connection = get_connection()
    cursor = connection.cursor()
    is_sqlite = getattr(connection, "backend", "postgres") == "sqlite"

    try:
        if is_sqlite:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS health_assessments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    age INTEGER NOT NULL,
                    symptoms TEXT NOT NULL,
                    duration VARCHAR(50) NOT NULL,
                    risk_level VARCHAR(20) NOT NULL,
                    recommended_specialist TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
        else:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS health_assessments (
                    id SERIAL PRIMARY KEY,
                    age INTEGER NOT NULL,
                    symptoms TEXT NOT NULL,
                    duration VARCHAR(50) NOT NULL,
                    risk_level VARCHAR(20) NOT NULL,
                    recommended_specialist TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
        connection.commit()
        _INITIALIZED_DBS.add(cache_key)
    finally:
        cursor.close()
        connection.close()


if __name__ == "__main__":
    ensure_tables()
    conn = get_connection()
    backend_name = getattr(conn, "backend", "postgresql")
    print(f"Database connected successfully! (backend: {backend_name})")
    conn.close()
