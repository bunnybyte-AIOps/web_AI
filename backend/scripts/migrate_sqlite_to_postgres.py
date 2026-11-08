import argparse
import sqlite3
import sys
from pathlib import Path

from app.core.config import settings
from app.core.database import get_db, initialize_database


TABLE_ORDER = (
    "users",
    "projects",
    "seasons",
    "episodes",
    "stories",
    "story_bibles",
    "characters",
    "worlds",
    "scenes",
    "assets",
    "ai_generations",
    "analytics",
    "ai_recommendations",
    "video_renders",
    "auth_otps",
    "social_connections",
    "social_oauth_states",
)


def migrate(source_path: Path) -> dict[str, int]:
    if not source_path.is_file():
        raise FileNotFoundError(f"SQLite source does not exist: {source_path}")
    if not settings.DATABASE_URL.startswith(("postgresql://", "postgres://", "postgresql+")):
        raise ValueError("DATABASE_URL must point to the PostgreSQL destination.")

    source = sqlite3.connect(source_path)
    source.row_factory = sqlite3.Row
    try:
        source_tables = {
            row["name"]
            for row in source.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        initialize_database()
        with get_db() as destination:
            for table in TABLE_ORDER:
                exists = destination.execute(
                    "SELECT to_regclass(?)", (f"public.{table}",)
                ).fetchone()[0]
                if exists:
                    count = destination.execute(
                        f'SELECT COUNT(*) FROM "{table}"'
                    ).fetchone()[0]
                    if count:
                        raise RuntimeError(
                            f"PostgreSQL table {table} is not empty. "
                            "Migration stopped to prevent overwriting existing data."
                        )

        copied: dict[str, int] = {}
        with get_db() as destination:
            for table in TABLE_ORDER:
                if table not in source_tables:
                    continue
                source_columns = {
                    row["name"]
                    for row in source.execute(f'PRAGMA table_info("{table}")').fetchall()
                }
                target_columns = {
                    row["column_name"]
                    for row in destination.execute(
                        """
                        SELECT column_name FROM information_schema.columns
                        WHERE table_schema = current_schema() AND table_name = ?
                        """,
                        (table,),
                    ).fetchall()
                }
                columns = sorted(source_columns & target_columns)
                if not columns:
                    continue
                quoted_columns = ", ".join(f'"{column}"' for column in columns)
                placeholders = ", ".join("?" for _ in columns)
                rows = source.execute(
                    f'SELECT {quoted_columns} FROM "{table}"'
                ).fetchall()
                for row in rows:
                    values = tuple(row[column] for column in columns)
                    destination.execute(
                        f'INSERT INTO "{table}" ({quoted_columns}) '
                        f"VALUES ({placeholders})",
                        values,
                    )
                copied[table] = len(rows)

            for table in TABLE_ORDER:
                if table not in copied or "id" not in {
                    row["column_name"]
                    for row in destination.execute(
                        """
                        SELECT column_name FROM information_schema.columns
                        WHERE table_schema = current_schema() AND table_name = ?
                        """,
                        (table,),
                    ).fetchall()
                }:
                    continue
                destination.execute(
                    f"""
                    SELECT setval(
                        pg_get_serial_sequence('{table}', 'id'),
                        COALESCE(MAX(id), 1),
                        MAX(id) IS NOT NULL
                    ) FROM "{table}"
                    """
                )
        return copied
    finally:
        source.close()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Copy existing CINAI SQLite rows to an empty PostgreSQL database."
    )
    parser.add_argument(
        "--sqlite-path",
        required=True,
        type=Path,
        help="Path to the existing SQLite database file.",
    )
    args = parser.parse_args()
    try:
        copied = migrate(args.sqlite_path)
    except (OSError, sqlite3.Error, RuntimeError, ValueError) as exc:
        print(f"Migration failed: {exc}", file=sys.stderr)
        return 1
    total = sum(copied.values())
    print(f"Migration complete: copied {total} rows across {len(copied)} tables.")
    for table, count in copied.items():
        print(f"  {table}: {count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
