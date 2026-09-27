import os
import json
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncGenerator
import aiosqlite


class Database:
    """Async SQLite storage implementing ROADMAP.md specifications."""

    def __init__(self, db_path: str = "./data/assistant.db"):
        self.db_path = db_path
        self._shared_conn: aiosqlite.Connection | None = None

    async def _ensure_dir_exists(self) -> None:
        if self.db_path != ":memory:" and not self.db_path.startswith("file:"):
            db_dir = Path(self.db_path).parent
            db_dir.mkdir(parents=True, exist_ok=True)

    @asynccontextmanager
    async def connection(self) -> AsyncGenerator[aiosqlite.Connection, None]:
        await self._ensure_dir_exists()
        if self.db_path == ":memory:":
            if self._shared_conn is None:
                self._shared_conn = await aiosqlite.connect(":memory:")
                self._shared_conn.row_factory = aiosqlite.Row
                await self._shared_conn.execute("PRAGMA foreign_keys = ON;")
            yield self._shared_conn
        else:
            async with aiosqlite.connect(self.db_path) as conn:
                conn.row_factory = aiosqlite.Row
                await conn.execute("PRAGMA foreign_keys = ON;")
                yield conn

    async def close(self) -> None:
        if self._shared_conn is not None:
            await self._shared_conn.close()
            self._shared_conn = None

    async def init_db(self) -> None:
        """Create all tables defined in ROADMAP.md if they do not exist."""
        async with self.connection() as conn:
            await conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS monitored_sources (
                    id TEXT PRIMARY KEY,
                    source_type TEXT NOT NULL,
                    display_name TEXT NOT NULL,
                    config_json TEXT NOT NULL,
                    last_checked_at TIMESTAMP,
                    is_active BOOLEAN DEFAULT TRUE
                );

                CREATE TABLE IF NOT EXISTS content_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_id TEXT NOT NULL REFERENCES monitored_sources(id),
                    content_hash TEXT NOT NULL,
                    raw_payload TEXT NOT NULL,
                    captured_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS calendar_sync_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_event_id TEXT NOT NULL UNIQUE,
                    google_event_id TEXT NOT NULL UNIQUE,
                    calendar_id TEXT NOT NULL,
                    event_start TIMESTAMP NOT NULL,
                    event_end TIMESTAMP NOT NULL,
                    summary TEXT NOT NULL,
                    last_synced_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    status TEXT DEFAULT 'active'
                );

                CREATE TABLE IF NOT EXISTS action_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_type TEXT NOT NULL,
                    priority_score INTEGER NOT NULL,
                    summary_text TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    status TEXT DEFAULT 'pending',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE INDEX IF NOT EXISTS idx_snapshots_source_id ON content_snapshots(source_id);
                CREATE INDEX IF NOT EXISTS idx_snapshots_content_hash ON content_snapshots(content_hash);
                CREATE INDEX IF NOT EXISTS idx_sync_records_source_event_id ON calendar_sync_records(source_event_id);
                """
            )
            await conn.commit()

    async def upsert_monitored_source(
        self,
        source_id: str,
        source_type: str,
        display_name: str,
        config: dict[str, Any] | str,
        is_active: bool = True,
    ) -> None:
        config_str = config if isinstance(config, str) else json.dumps(config, ensure_ascii=False)
        async with self.connection() as conn:
            await conn.execute(
                """
                INSERT INTO monitored_sources (id, source_type, display_name, config_json, is_active)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    source_type = excluded.source_type,
                    display_name = excluded.display_name,
                    config_json = excluded.config_json,
                    is_active = excluded.is_active;
                """,
                (source_id, source_type, display_name, config_str, is_active),
            )
            await conn.commit()

    async def save_snapshot(
        self,
        source_id: str,
        content_hash: str,
        raw_payload: str,
    ) -> int:
        """Save a content snapshot and update source last_checked_at."""
        now_iso = datetime.now(timezone.utc).isoformat()
        async with self.connection() as conn:
            cursor = await conn.execute(
                """
                INSERT INTO content_snapshots (source_id, content_hash, raw_payload, captured_at)
                VALUES (?, ?, ?, ?);
                """,
                (source_id, content_hash, raw_payload, now_iso),
            )
            snapshot_id = cursor.lastrowid

            await conn.execute(
                """
                UPDATE monitored_sources
                SET last_checked_at = ?
                WHERE id = ?;
                """,
                (now_iso, source_id),
            )
            await conn.commit()
            return snapshot_id

    async def get_latest_snapshot(self, source_id: str) -> dict[str, Any] | None:
        """Retrieve the most recent snapshot for a source."""
        async with self.connection() as conn:
            cursor = await conn.execute(
                """
                SELECT id, source_id, content_hash, raw_payload, captured_at
                FROM content_snapshots
                WHERE source_id = ?
                ORDER BY id DESC
                LIMIT 1;
                """,
                (source_id,),
            )
            row = await cursor.fetchone()
            if row:
                return dict(row)
            return None

    async def record_calendar_sync(
        self,
        source_event_id: str,
        google_event_id: str,
        calendar_id: str,
        event_start: datetime | str,
        event_end: datetime | str,
        summary: str,
        status: str = "active",
    ) -> int:
        start_str = event_start.isoformat() if isinstance(event_start, datetime) else str(event_start)
        end_str = event_end.isoformat() if isinstance(event_end, datetime) else str(event_end)

        async with self.connection() as conn:
            cursor = await conn.execute(
                """
                INSERT INTO calendar_sync_records
                    (source_event_id, google_event_id, calendar_id, event_start, event_end, summary, status)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(source_event_id) DO UPDATE SET
                    google_event_id = excluded.google_event_id,
                    event_start = excluded.event_start,
                    event_end = excluded.event_end,
                    summary = excluded.summary,
                    status = excluded.status,
                    last_synced_at = CURRENT_TIMESTAMP;
                """,
                (source_event_id, google_event_id, calendar_id, start_str, end_str, summary, status),
            )
            await conn.commit()
            return cursor.lastrowid

    async def get_calendar_sync_record(self, source_event_id: str) -> dict[str, Any] | None:
        async with self.connection() as conn:
            cursor = await conn.execute(
                """
                SELECT * FROM calendar_sync_records WHERE source_event_id = ?;
                """,
                (source_event_id,),
            )
            row = await cursor.fetchone()
            return dict(row) if row else None
