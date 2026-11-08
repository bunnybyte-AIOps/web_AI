import sqlite3
import re
from contextlib import contextmanager
from typing import Any, Generator

from app.core.config import settings

try:
    import psycopg2

    INTEGRITY_ERRORS = (sqlite3.IntegrityError, psycopg2.IntegrityError)
except ImportError:
    INTEGRITY_ERRORS = (sqlite3.IntegrityError,)


class _PostgresRow(dict):
    def __getitem__(self, key):
        if isinstance(key, int):
            return tuple(self.values())[key]
        return super().__getitem__(key)


class _PostgresCursor:
    def __init__(self, cursor) -> None:
        self._cursor = cursor
        self.lastrowid = None
        self.rowcount = -1

    def execute(self, query: str, parameters: tuple | list = ()):
        normalized = query.strip()
        ignore_insert = normalized.upper().startswith("INSERT OR IGNORE INTO")
        if ignore_insert:
            normalized = normalized.replace("INSERT OR IGNORE INTO", "INSERT INTO", 1)
            normalized = normalized.rstrip().rstrip(";") + " ON CONFLICT DO NOTHING"

        if normalized.lstrip().upper().startswith("INSERT ") and " RETURNING " not in normalized.upper():
            normalized = normalized.rstrip().rstrip(";") + " RETURNING id"
            captures_id = True
        else:
            captures_id = False

        normalized = _postgres_sql(normalized)
        self._cursor.execute(_qmark_to_format(normalized), parameters)
        self.rowcount = self._cursor.rowcount
        if captures_id:
            inserted = self._cursor.fetchone()
            self.lastrowid = inserted["id"] if inserted else None
        return self

    def fetchone(self):
        row = self._cursor.fetchone()
        return _PostgresRow(row) if row is not None else None

    def fetchall(self):
        return [_PostgresRow(row) for row in self._cursor.fetchall()]


class _PostgresConnection:
    def __init__(self, raw_connection) -> None:
        from psycopg2.extras import RealDictCursor

        self._connection = raw_connection
        self._cursor_factory = RealDictCursor

    def cursor(self):
        return _PostgresCursor(self._connection.cursor(cursor_factory=self._cursor_factory))

    def execute(self, query: str, parameters: tuple | list = ()):
        return self.cursor().execute(query, parameters)

    def executescript(self, script: str) -> None:
        for statement in script.split(";"):
            if statement.strip():
                self.execute(statement)

    def commit(self) -> None:
        self._connection.commit()

    def rollback(self) -> None:
        self._connection.rollback()

    def close(self) -> None:
        self._connection.close()


def _qmark_to_format(query: str) -> str:
    result: list[str] = []
    quote: str | None = None
    index = 0
    while index < len(query):
        char = query[index]
        if quote:
            result.append(char)
            if char == quote:
                if index + 1 < len(query) and query[index + 1] == quote:
                    result.append(query[index + 1])
                    index += 1
                else:
                    quote = None
        elif char in {"'", '"'}:
            quote = char
            result.append(char)
        elif char == "?":
            result.append("%s")
        else:
            result.append(char)
        index += 1
    return "".join(result)


def _postgres_sql(query: str) -> str:
    query = re.sub(
        r"\bINTEGER\s+PRIMARY\s+KEY\s+AUTOINCREMENT\b",
        "BIGSERIAL PRIMARY KEY",
        query,
        flags=re.IGNORECASE,
    )
    query = re.sub(
        r"\bDEFAULT\s+CURRENT_TIMESTAMP\b",
        "DEFAULT (CURRENT_TIMESTAMP::text)",
        query,
        flags=re.IGNORECASE,
    )
    return re.sub(
        r"(\bupdated_at\s*=\s*)CURRENT_TIMESTAMP\b",
        r"\1CURRENT_TIMESTAMP::text",
        query,
        flags=re.IGNORECASE,
    )


def _postgres_url() -> str | None:
    url = settings.DATABASE_URL
    if url.startswith("postgresql+psycopg2://"):
        return url.replace("postgresql+psycopg2://", "postgresql://", 1)
    if url.startswith(("postgresql://", "postgres://")):
        return url
    return None


@contextmanager
def get_db() -> Generator[Any, None, None]:
    postgres_url = _postgres_url()
    if postgres_url:
        import psycopg2

        connection = _PostgresConnection(psycopg2.connect(postgres_url))
    else:
        settings.DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(settings.DATABASE_PATH, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def _ensure_columns(
    connection: Any, table: str, columns: dict[str, str]
) -> None:
    if isinstance(connection, _PostgresConnection):
        existing = {
            row["column_name"]
            for row in connection.execute(
                """
                SELECT column_name FROM information_schema.columns
                WHERE table_schema = current_schema() AND table_name = ?
                """,
                (table,),
            ).fetchall()
        }
    else:
        existing = {
            row["name"] for row in connection.execute(f"PRAGMA table_info({table})")
        }
    for name, declaration in columns.items():
        if name not in existing:
            connection.execute(f"ALTER TABLE {table} ADD COLUMN {name} {declaration}")


def initialize_database() -> None:
    with get_db() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                hashed_password TEXT NOT NULL,
                full_name TEXT,
                role TEXT NOT NULL DEFAULT 'creator',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS projects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                title TEXT NOT NULL,
                description TEXT,
                genre TEXT DEFAULT 'Điện ảnh',
                status TEXT DEFAULT 'draft',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS episodes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                season_id INTEGER,
                episode_number INTEGER NOT NULL,
                title TEXT NOT NULL,
                synopsis TEXT,
                status TEXT NOT NULL DEFAULT 'draft',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(project_id, episode_number)
            );
            CREATE TABLE IF NOT EXISTS seasons (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                season_number INTEGER NOT NULL,
                title TEXT NOT NULL,
                synopsis TEXT,
                status TEXT NOT NULL DEFAULT 'draft',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(project_id, season_number)
            );
            CREATE TABLE IF NOT EXISTS story_bibles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                logline TEXT,
                theme TEXT,
                world_setting TEXT,
                character_profiles TEXT,
                data_json TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS stories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                episode_number INTEGER NOT NULL DEFAULT 1,
                generation_id INTEGER,
                fountain_script TEXT,
                data_json TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS scenes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                episode_number INTEGER NOT NULL DEFAULT 1,
                generation_id INTEGER,
                scene_number INTEGER NOT NULL,
                title TEXT,
                visual_prompt TEXT,
                dialogue TEXT,
                camera_angle TEXT DEFAULT 'medium_shot',
                sfx TEXT,
                image_url TEXT,
                audio_url TEXT,
                duration REAL DEFAULT 5,
                status TEXT DEFAULT 'draft',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS characters (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                role_type TEXT DEFAULT 'supporting',
                age INTEGER,
                voice_profile TEXT,
                visual_prompt TEXT,
                personality TEXT,
                backstory TEXT,
                flux_prompt TEXT,
                edge_tts_voice TEXT,
                status TEXT DEFAULT 'draft',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS worlds (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                setting_description TEXT,
                time_period TEXT,
                technology_level TEXT,
                factions TEXT,
                locations TEXT,
                rules TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS assets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                scene_id INTEGER,
                name TEXT NOT NULL,
                asset_type TEXT DEFAULT 'visual',
                file_url TEXT,
                thumbnail_url TEXT,
                file_size_mb REAL DEFAULT 0,
                duration_seconds REAL,
                status TEXT DEFAULT 'draft',
                tags TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS ai_generations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                project_id INTEGER NOT NULL,
                step TEXT NOT NULL,
                input_json TEXT NOT NULL,
                output_json TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'completed',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS analytics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                episode_number INTEGER,
                platform TEXT,
                external_content_id TEXT,
                view_count INTEGER NOT NULL DEFAULT 0,
                unique_viewers INTEGER NOT NULL DEFAULT 0,
                watch_time_avg_sec REAL NOT NULL DEFAULT 0,
                retention_rate REAL NOT NULL DEFAULT 0,
                like_count INTEGER NOT NULL DEFAULT 0,
                comment_count INTEGER NOT NULL DEFAULT 0,
                share_count INTEGER NOT NULL DEFAULT 0,
                recorded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS social_connections (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                platform TEXT NOT NULL,
                account_id TEXT,
                account_name TEXT,
                access_token TEXT NOT NULL,
                refresh_token TEXT,
                expires_at INTEGER,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(project_id, platform, account_id)
            );
            CREATE TABLE IF NOT EXISTS social_oauth_states (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                state TEXT UNIQUE NOT NULL,
                project_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                platform TEXT NOT NULL,
                expires_at INTEGER NOT NULL,
                created_at INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS ai_recommendations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                description TEXT NOT NULL,
                data_json TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS video_renders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                episode_number INTEGER,
                status TEXT NOT NULL DEFAULT 'queued',
                file_url TEXT,
                error_message TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            """
        )

        _ensure_columns(
            connection,
            "users",
            {
                "email": "TEXT",
                "hashed_password": "TEXT",
                "full_name": "TEXT",
                "role": "TEXT NOT NULL DEFAULT 'creator'",
                "created_at": "TEXT",
                "phone": "TEXT",
                "email_verified": "INTEGER NOT NULL DEFAULT 1",
                "phone_verified": "INTEGER NOT NULL DEFAULT 0",
            },
        )
        connection.executescript(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_users_phone
                ON users(phone) WHERE phone IS NOT NULL;
            CREATE TABLE IF NOT EXISTS auth_otps (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                destination TEXT NOT NULL,
                purpose TEXT NOT NULL,
                code_hash TEXT NOT NULL,
                expires_at INTEGER NOT NULL,
                attempts INTEGER NOT NULL DEFAULT 0,
                consumed_at INTEGER,
                created_at INTEGER NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_auth_otps_lookup
                ON auth_otps(destination, purpose, created_at DESC);
            """
        )
        _ensure_columns(
            connection,
            "projects",
            {
                "user_id": "INTEGER",
                "title": "TEXT",
                "description": "TEXT",
                "genre": "TEXT",
                "status": "TEXT DEFAULT 'draft'",
                "view_count": "INTEGER NOT NULL DEFAULT 0",
                "updated_at": "TEXT",
            },
        )
        _ensure_columns(
            connection,
            "story_bibles",
            {
                "logline": "TEXT",
                "theme": "TEXT",
                "world_setting": "TEXT",
                "character_profiles": "TEXT",
                "data_json": "TEXT",
                "created_at": "TEXT",
            },
        )
        _ensure_columns(
            connection,
            "episodes",
            {"season_id": "INTEGER"},
        )
        _ensure_columns(
            connection,
            "scenes",
            {
                "episode_number": "INTEGER NOT NULL DEFAULT 1",
                "generation_id": "INTEGER",
                "camera_angle": "TEXT DEFAULT 'medium_shot'",
                "sfx": "TEXT",
                "image_url": "TEXT",
                "audio_url": "TEXT",
                "duration": "REAL DEFAULT 5",
                "status": "TEXT DEFAULT 'draft'",
                "created_at": "TEXT",
            },
        )
        _ensure_columns(
            connection,
            "assets",
            {
                "scene_id": "INTEGER",
                "error_message": "TEXT",
                "request_json": "TEXT",
                "updated_at": "TEXT",
            },
        )
        _ensure_columns(
            connection,
            "video_renders",
            {
                "episode_number": "INTEGER",
                "error_message": "TEXT",
                "updated_at": "TEXT",
            },
        )
        _ensure_columns(
            connection,
            "analytics",
            {
                "episode_number": "INTEGER",
                "platform": "TEXT",
                "external_content_id": "TEXT",
            },
        )
        _ensure_columns(
            connection,
            "stories",
            {"generation_id": "INTEGER"},
        )
        connection.execute(
            """
            INSERT OR IGNORE INTO seasons (project_id, season_number, title)
            SELECT id, 1, 'Mùa 1' FROM projects
            """
        )
        connection.execute(
            """
            INSERT OR IGNORE INTO episodes (project_id, episode_number, title)
            SELECT project_id, episode_number, 'Tập ' || episode_number
            FROM stories
            GROUP BY project_id, episode_number
            """
        )
        connection.execute(
            """
            INSERT OR IGNORE INTO episodes (project_id, episode_number, title)
            SELECT project_id, episode_number, 'Tập ' || episode_number
            FROM scenes
            GROUP BY project_id, episode_number
            """
        )
        connection.execute(
            """
            UPDATE episodes SET season_id = (
                SELECT id FROM seasons
                WHERE seasons.project_id = episodes.project_id AND season_number = 1
            )
            WHERE season_id IS NULL
            """
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_projects_user_id ON projects(user_id)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_generations_project "
            "ON ai_generations(project_id, created_at DESC)"
        )
        connection.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_analytics_external_content_unique
            ON analytics(project_id, platform, external_content_id)
            """
        )
        try:
            cur = connection.execute("SELECT COUNT(*) FROM scenes")
            cnt = cur.fetchone()[0]
            if cnt == 0:
                import sys
                from pathlib import Path
                backend_dir = Path(__file__).resolve().parents[2]
                if str(backend_dir) not in sys.path:
                    sys.path.insert(0, str(backend_dir))
                from seed_full_database import seed
                seed()
        except Exception:
            pass
