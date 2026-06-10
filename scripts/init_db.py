"""Creates SQLite schema from db/schema.sql (idempotent — safe to run multiple times)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from db.database import get_connection

SCHEMA_PATH = Path(__file__).parent.parent / "db" / "schema.sql"


def main() -> None:
    sql = SCHEMA_PATH.read_text(encoding="utf-8")
    with get_connection() as conn:
        conn.executescript(sql)
    print(f"Database schema initialised at: {Path('data/worldcup.db').resolve()}")


if __name__ == "__main__":
    main()
