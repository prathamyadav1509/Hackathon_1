import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from database.connection import ensure_tables, get_connection


def create_tables():
    ensure_tables()
    conn = get_connection()
    backend_name = getattr(conn, "backend", "postgresql")
    conn.close()
    print(f"health_assessments table ready! (backend: {backend_name})")


if __name__ == "__main__":
    create_tables()
