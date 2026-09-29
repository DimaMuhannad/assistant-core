import logging
import os
import json
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncGenerator
import aiosqlite

logger = logging.getLogger(__name__)


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
                    google_event_id TEXT NOT NULL,
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

                CREATE TABLE IF NOT EXISTS email_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    message_id TEXT NOT NULL UNIQUE,
                    account_id TEXT NOT NULL,
                    folder TEXT NOT NULL,
                    sender_name TEXT,
                    sender_email TEXT NOT NULL,
                    recipients_json TEXT,
                    subject TEXT,
                    date_sent TIMESTAMP NOT NULL,
                    body_plain TEXT,
                    body_html TEXT,
                    snippet TEXT,
                    has_attachments BOOLEAN DEFAULT FALSE,
                    attachments_json TEXT,
                    in_reply_to TEXT,
                    references_text TEXT,
                    thread_id TEXT,
                    category TEXT DEFAULT 'general',
                    is_noise BOOLEAN DEFAULT FALSE,
                    requires_action BOOLEAN DEFAULT FALSE,
                    is_read BOOLEAN DEFAULT FALSE,
                    is_answered BOOLEAN DEFAULT FALSE,
                    replied_at TIMESTAMP,
                    reply_message_id TEXT,
                    flags_json TEXT,
                    is_expired BOOLEAN DEFAULT FALSE,
                    deadline_at TIMESTAMP,
                    relevance_score REAL DEFAULT 1.0,
                    ingested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS email_threads (
                    thread_id TEXT PRIMARY KEY,
                    subject TEXT,
                    participant_emails_json TEXT,
                    message_count INTEGER DEFAULT 1,
                    last_message_at TIMESTAMP,
                    category TEXT DEFAULT 'general',
                    summary TEXT,
                    status TEXT DEFAULT 'open',
                    last_sender_email TEXT,
                    last_reply_at TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS email_drafts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    email_id INTEGER NOT NULL REFERENCES email_messages(id),
                    draft_text TEXT NOT NULL,
                    status TEXT DEFAULT 'pending',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS projects (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    area TEXT NOT NULL DEFAULT 'ГУАП',
                    status TEXT NOT NULL DEFAULT 'active',
                    target_date TEXT,
                    key_result TEXT,
                    description TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id INTEGER REFERENCES projects(id) ON DELETE SET NULL,
                    title TEXT NOT NULL,
                    description TEXT,
                    area TEXT NOT NULL DEFAULT 'ГУАП',
                    priority TEXT NOT NULL DEFAULT 'P2',
                    status TEXT NOT NULL DEFAULT 'todo',
                    due_date TEXT,
                    estimated_minutes INTEGER,
                    context_tag TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS reminders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id INTEGER REFERENCES tasks(id) ON DELETE SET NULL,
                    what TEXT NOT NULL,
                    person TEXT,
                    check_date TEXT,
                    context TEXT,
                    source_type TEXT DEFAULT 'manual',
                    status TEXT NOT NULL DEFAULT 'active',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS documents (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id INTEGER REFERENCES projects(id) ON DELETE SET NULL,
                    title TEXT NOT NULL,
                    category TEXT DEFAULT 'general',
                    content_markdown TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS timesheet_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source TEXT NOT NULL DEFAULT 'aadhk',
                    external_record_id TEXT,
                    project_name TEXT NOT NULL DEFAULT 'Тидекс',
                    task_name TEXT,
                    start_time TIMESTAMP NOT NULL,
                    end_time TIMESTAMP NOT NULL,
                    duration_minutes INTEGER NOT NULL,
                    hourly_rate REAL DEFAULT 0.0,
                    amount REAL DEFAULT 0.0,
                    note TEXT,
                    has_guap_conflict BOOLEAN DEFAULT FALSE,
                    conflict_details TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE INDEX IF NOT EXISTS idx_snapshots_source_id ON content_snapshots(source_id);
                CREATE INDEX IF NOT EXISTS idx_snapshots_content_hash ON content_snapshots(content_hash);
                CREATE INDEX IF NOT EXISTS idx_sync_records_source_event_id ON calendar_sync_records(source_event_id);
                CREATE INDEX IF NOT EXISTS idx_email_msg_id ON email_messages(message_id);
                CREATE INDEX IF NOT EXISTS idx_email_account_date ON email_messages(account_id, date_sent);
                CREATE INDEX IF NOT EXISTS idx_email_thread ON email_messages(thread_id);
                CREATE INDEX IF NOT EXISTS idx_email_sender ON email_messages(sender_email);
                CREATE INDEX IF NOT EXISTS idx_email_answered ON email_messages(is_answered);
                CREATE INDEX IF NOT EXISTS idx_email_requires_action ON email_messages(requires_action);
                CREATE INDEX IF NOT EXISTS idx_email_drafts_email_id ON email_drafts(email_id);
                CREATE INDEX IF NOT EXISTS idx_tasks_project_id ON tasks(project_id);
                CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
                CREATE INDEX IF NOT EXISTS idx_tasks_priority ON tasks(priority);
                CREATE INDEX IF NOT EXISTS idx_tasks_due_date ON tasks(due_date);
                CREATE INDEX IF NOT EXISTS idx_reminders_status ON reminders(status);
                CREATE INDEX IF NOT EXISTS idx_documents_project_id ON documents(project_id);
                CREATE INDEX IF NOT EXISTS idx_timesheet_start ON timesheet_records(start_time);
                CREATE INDEX IF NOT EXISTS idx_timesheet_project ON timesheet_records(project_name);
                CREATE INDEX IF NOT EXISTS idx_timesheet_conflict ON timesheet_records(has_guap_conflict);
                """
            )
            await conn.commit()
            await self._seed_initial_data_if_empty(conn)

            # Migrate email_messages columns if missing
            cursor = await conn.execute("PRAGMA table_info(email_messages);")
            existing_cols = {row[1] for row in await cursor.fetchall()}
            new_cols_messages = [
                ("is_answered", "BOOLEAN DEFAULT FALSE"),
                ("replied_at", "TIMESTAMP"),
                ("reply_message_id", "TEXT"),
                ("flags_json", "TEXT"),
                ("is_expired", "BOOLEAN DEFAULT FALSE"),
                ("deadline_at", "TIMESTAMP"),
                ("relevance_score", "REAL DEFAULT 1.0"),
                ("card_message_id", "INTEGER"),
            ]
            for col_name, col_type in new_cols_messages:
                if col_name not in existing_cols:
                    logger.info("Migrating email_messages: adding column %s", col_name)
                    await conn.execute(f"ALTER TABLE email_messages ADD COLUMN {col_name} {col_type};")

            # Migrate email_drafts columns if missing
            cursor = await conn.execute("PRAGMA table_info(email_drafts);")
            existing_draft_cols = {row[1] for row in await cursor.fetchall()}
            if "draft_message_id" not in existing_draft_cols:
                logger.info("Migrating email_drafts: adding column draft_message_id")
                await conn.execute("ALTER TABLE email_drafts ADD COLUMN draft_message_id INTEGER;")

            # Migrate email_threads columns if missing
            cursor = await conn.execute("PRAGMA table_info(email_threads);")
            existing_thread_cols = {row[1] for row in await cursor.fetchall()}
            new_cols_threads = [
                ("last_sender_email", "TEXT"),
                ("last_reply_at", "TIMESTAMP"),
            ]
            for col_name, col_type in new_cols_threads:
                if col_name not in existing_thread_cols:
                    logger.info("Migrating email_threads: adding column %s", col_name)
                    await conn.execute(f"ALTER TABLE email_threads ADD COLUMN {col_name} {col_type};")

            # Migrate calendar_sync_records if it contains UNIQUE constraint on google_event_id
            cursor = await conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='calendar_sync_records';")
            row = await cursor.fetchone()
            sql_text = row[0] if row else ""
            if "google_event_id TEXT NOT NULL UNIQUE" in sql_text:
                logger.info("Migrating calendar_sync_records: removing UNIQUE constraint on google_event_id...")
                await conn.executescript(
                    """
                    CREATE TABLE calendar_sync_records_new (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        source_event_id TEXT NOT NULL UNIQUE,
                        google_event_id TEXT NOT NULL,
                        calendar_id TEXT NOT NULL,
                        event_start TIMESTAMP NOT NULL,
                        event_end TIMESTAMP NOT NULL,
                        summary TEXT NOT NULL,
                        last_synced_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        status TEXT DEFAULT 'active'
                    );
                    INSERT OR IGNORE INTO calendar_sync_records_new SELECT * FROM calendar_sync_records;
                    DROP TABLE calendar_sync_records;
                    ALTER TABLE calendar_sync_records_new RENAME TO calendar_sync_records;
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

    async def get_content_snapshot_by_hash(self, source_id: str, content_hash: str) -> dict[str, Any] | None:
        """Check if a specific content hash already exists for this source."""
        async with self.connection() as conn:
            cursor = await conn.execute(
                """
                SELECT id, source_id, content_hash, raw_payload, captured_at
                FROM content_snapshots
                WHERE source_id = ? AND content_hash = ?
                LIMIT 1;
                """,
                (source_id, content_hash),
            )
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def save_action_item(
        self,
        source_type: str,
        priority_score: int,
        summary_text: str,
        payload: dict[str, Any] | str,
        status: str = "pending",
    ) -> int:
        """Save a new action item to be reviewed or sent in daily brief."""
        payload_str = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False)
        async with self.connection() as conn:
            cursor = await conn.execute(
                """
                INSERT INTO action_items (source_type, priority_score, summary_text, payload_json, status)
                VALUES (?, ?, ?, ?, ?);
                """,
                (source_type, priority_score, summary_text, payload_str, status),
            )
            await conn.commit()
            return cursor.lastrowid

    async def get_pending_action_items(self, limit: int = 50) -> list[dict[str, Any]]:
        """Retrieve pending action items ordered by priority (descending)."""
        async with self.connection() as conn:
            cursor = await conn.execute(
                """
                SELECT id, source_type, priority_score, summary_text, payload_json, status, created_at
                FROM action_items
                WHERE status = 'pending'
                ORDER BY priority_score DESC, id DESC
                LIMIT ?;
                """,
                (limit,),
            )
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

    async def update_action_item_status(self, item_id: int, status: str) -> None:
        """Update status of an action item (e.g. 'processed', 'dismissed', 'confirmed')."""
        async with self.connection() as conn:
            await conn.execute(
                """
                UPDATE action_items
                SET status = ?
                WHERE id = ?;
                """,
                (status, item_id),
            )
            await conn.commit()

    async def list_monitored_sources(self, source_type: str | None = None) -> list[dict[str, Any]]:
        """List active monitored sources."""
        async with self.connection() as conn:
            if source_type:
                cursor = await conn.execute(
                    """
                    SELECT id, source_type, display_name, config_json, last_checked_at, is_active
                    FROM monitored_sources
                    WHERE is_active = TRUE AND source_type = ?
                    ORDER BY display_name;
                    """,
                    (source_type,),
                )
            else:
                cursor = await conn.execute(
                    """
                    SELECT id, source_type, display_name, config_json, last_checked_at, is_active
                    FROM monitored_sources
                    WHERE is_active = TRUE
                    ORDER BY display_name;
                    """,
                )
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

    async def upsert_email_message(
        self,
        message_id: str,
        account_id: str,
        folder: str,
        sender_name: str | None,
        sender_email: str,
        recipients_json: str,
        subject: str | None,
        date_sent: datetime,
        body_plain: str | None,
        body_html: str | None,
        snippet: str | None,
        has_attachments: bool,
        attachments_json: str | None,
        in_reply_to: str | None,
        references_text: str | None,
        thread_id: str,
        category: str = "general",
        is_noise: bool = False,
        requires_action: bool = False,
        is_read: bool = False,
        is_answered: bool = False,
        replied_at: datetime | None = None,
        reply_message_id: str | None = None,
        flags_json: str | None = None,
        is_expired: bool = False,
        deadline_at: datetime | None = None,
        relevance_score: float = 1.0,
    ) -> bool:
        """Insert email message or update flags/answered status. Returns True if inserted, False if updated/duplicate."""
        date_sent_str = date_sent.isoformat() if isinstance(date_sent, datetime) else str(date_sent)
        replied_at_str = replied_at.isoformat() if isinstance(replied_at, datetime) else (str(replied_at) if replied_at else None)
        deadline_str = deadline_at.isoformat() if isinstance(deadline_at, datetime) else (str(deadline_at) if deadline_at else None)

        async with self.connection() as conn:
            cursor = await conn.execute(
                """
                INSERT INTO email_messages (
                    message_id, account_id, folder, sender_name, sender_email,
                    recipients_json, subject, date_sent, body_plain, body_html,
                    snippet, has_attachments, attachments_json, in_reply_to,
                    references_text, thread_id, category, is_noise, requires_action,
                    is_read, is_answered, replied_at, reply_message_id, flags_json,
                    is_expired, deadline_at, relevance_score
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(message_id) DO UPDATE SET
                    flags_json = COALESCE(excluded.flags_json, email_messages.flags_json),
                    is_answered = MAX(email_messages.is_answered, excluded.is_answered),
                    is_read = MAX(email_messages.is_read, excluded.is_read),
                    category = CASE WHEN email_messages.category = 'general' THEN excluded.category ELSE email_messages.category END,
                    relevance_score = excluded.relevance_score,
                    is_expired = excluded.is_expired,
                    deadline_at = COALESCE(excluded.deadline_at, email_messages.deadline_at),
                    replied_at = COALESCE(excluded.replied_at, email_messages.replied_at),
                    reply_message_id = COALESCE(excluded.reply_message_id, email_messages.reply_message_id);
                """,
                (
                    message_id, account_id, folder, sender_name, sender_email,
                    recipients_json, subject, date_sent_str, body_plain, body_html,
                    snippet, has_attachments, attachments_json, in_reply_to,
                    references_text, thread_id, category, is_noise, requires_action,
                    is_read, is_answered, replied_at_str, reply_message_id, flags_json,
                    is_expired, deadline_str, relevance_score,
                ),
            )
            inserted = cursor.rowcount > 0

            # Update or insert thread
            if thread_id:
                initial_status = "answered" if is_answered else ("open" if is_noise else "unanswered")
                await conn.execute(
                    """
                    INSERT INTO email_threads (
                        thread_id, subject, participant_emails_json, message_count,
                        last_message_at, category, status, last_sender_email
                    )
                    VALUES (?, ?, ?, 1, ?, ?, ?, ?)
                    ON CONFLICT(thread_id) DO UPDATE SET
                        message_count = email_threads.message_count + 1,
                        last_message_at = MAX(email_threads.last_message_at, excluded.last_message_at),
                        last_sender_email = excluded.last_sender_email,
                        category = CASE WHEN email_threads.category = 'general' THEN excluded.category ELSE email_threads.category END;
                    """,
                    (thread_id, subject or "Без темы", json.dumps([sender_email]), date_sent_str, category, initial_status, sender_email),
                )
            await conn.commit()
            return inserted

    async def reconcile_replies_and_threads(self, user_emails: list[str]) -> dict[str, int]:
        """Reconcile replied status across email messages and threads.
        
        Marks incoming emails as answered if:
        1. Dmitry has sent a reply referencing the message (In-Reply-To / References).
        2. Dmitry has sent a reply in the same thread later than the incoming message.
        3. The message has IMAP flag \\Answered.
        
        Updates thread status:
        - 'answered': Dmitry sent the most recent message or has replied.
        - 'unanswered': Waiting for Dmitry to reply.
        - 'expired': Deadline passed or older than threshold.
        """
        user_emails_lower = [e.lower().strip() for e in user_emails if e and e.strip()]
        if not user_emails_lower:
            return {"answered_by_reply": 0, "answered_by_flag": 0, "threads_updated": 0}

        stats = {"answered_by_reply": 0, "answered_by_flag": 0, "threads_updated": 0}

        async with self.connection() as conn:
            # 1. Answered by IMAP flag (\Answered in flags_json)
            cursor = await conn.execute(
                """
                UPDATE email_messages
                SET is_answered = 1
                WHERE is_answered = 0 AND flags_json LIKE '%Answered%';
                """
            )
            stats["answered_by_flag"] = cursor.rowcount

            # 2. Outgoing replies: find all messages sent by user
            placeholders = ",".join("?" for _ in user_emails_lower)
            cursor = await conn.execute(
                f"""
                SELECT message_id, in_reply_to, references_text, thread_id, date_sent
                FROM email_messages
                WHERE LOWER(sender_email) IN ({placeholders})
                ORDER BY date_sent ASC;
                """,
                tuple(user_emails_lower),
            )
            outgoing_msgs = await cursor.fetchall()

            for out_msg in outgoing_msgs:
                out_id = out_msg["message_id"]
                in_reply = out_msg["in_reply_to"]
                refs = out_msg["references_text"]
                th_id = out_msg["thread_id"]
                out_date = out_msg["date_sent"]

                # A. Match direct in_reply_to
                if in_reply:
                    c = await conn.execute(
                        """
                        UPDATE email_messages
                        SET is_answered = 1, replied_at = ?, reply_message_id = ?
                        WHERE message_id = ? AND is_answered = 0;
                        """,
                        (out_date, out_id, in_reply),
                    )
                    stats["answered_by_reply"] += c.rowcount

                # B. Match references
                if refs:
                    for ref_id in refs.split():
                        c = await conn.execute(
                            """
                            UPDATE email_messages
                            SET is_answered = 1, replied_at = ?, reply_message_id = ?
                            WHERE message_id = ? AND is_answered = 0;
                            """,
                            (out_date, out_id, ref_id),
                        )
                        stats["answered_by_reply"] += c.rowcount

                # C. Match thread: any incoming message in the same thread with date_sent <= out_date
                if th_id:
                    c = await conn.execute(
                        f"""
                        UPDATE email_messages
                        SET is_answered = 1, replied_at = ?, reply_message_id = ?
                        WHERE thread_id = ? AND date_sent <= ? AND LOWER(sender_email) NOT IN ({placeholders}) AND is_answered = 0;
                        """,
                        (out_date, out_id, th_id, out_date, *user_emails_lower),
                    )
                    stats["answered_by_reply"] += c.rowcount

            # 3. Update thread statuses & last sender
            cursor = await conn.execute(
                """
                SELECT thread_id, sender_email, date_sent, requires_action, is_expired, is_answered
                FROM email_messages
                ORDER BY date_sent ASC;
                """
            )
            all_msgs = await cursor.fetchall()
            thread_latest: dict[str, dict[str, Any]] = {}
            for m in all_msgs:
                th_id = m["thread_id"]
                if not th_id:
                    continue
                thread_latest[th_id] = dict(m)

            for th_id, latest in thread_latest.items():
                sender = (latest["sender_email"] or "").lower()
                is_from_me = sender in user_emails_lower
                if is_from_me:
                    th_status = "answered"
                    last_reply = latest["date_sent"]
                else:
                    if latest.get("is_expired"):
                        th_status = "expired"
                    elif latest.get("is_answered"):
                        th_status = "answered"
                    elif latest.get("requires_action"):
                        th_status = "unanswered"
                    else:
                        th_status = "open"
                    last_reply = None

                c = await conn.execute(
                    """
                    UPDATE email_threads
                    SET status = ?, last_sender_email = ?, last_reply_at = COALESCE(?, last_reply_at)
                    WHERE thread_id = ?;
                    """,
                    (th_status, latest["sender_email"], last_reply, th_id),
                )
                stats["threads_updated"] += c.rowcount

            await conn.commit()
            return stats

    async def update_date_relevance(self, reference_now: datetime | None = None) -> dict[str, int]:
        """Recalculate relevance scores and expiration for non-noise emails."""
        now = reference_now or datetime.now(timezone.utc)
        stats = {"updated": 0, "expired": 0}

        async with self.connection() as conn:
            cursor = await conn.execute(
                """
                SELECT id, date_sent, deadline_at, is_answered, requires_action
                FROM email_messages
                WHERE is_noise = 0;
                """
            )
            rows = await cursor.fetchall()

            for row in rows:
                msg_id = row["id"]
                date_sent_raw = row["date_sent"]
                deadline_raw = row["deadline_at"]

                # Parse date_sent
                if isinstance(date_sent_raw, str):
                    try:
                        date_sent = datetime.fromisoformat(date_sent_raw)
                    except Exception:
                        date_sent = now
                else:
                    date_sent = date_sent_raw

                if date_sent.tzinfo is None:
                    date_sent = date_sent.replace(tzinfo=timezone.utc)

                # Parse deadline
                deadline = None
                if deadline_raw:
                    if isinstance(deadline_raw, str):
                        try:
                            deadline = datetime.fromisoformat(deadline_raw)
                        except Exception:
                            deadline = None
                    else:
                        deadline = deadline_raw
                    if deadline and deadline.tzinfo is None:
                        deadline = deadline.replace(tzinfo=timezone.utc)

                age_days = (now - date_sent).days

                # Determine expiration and score
                is_expired = False
                score = 1.0

                if deadline:
                    if deadline < now:
                        is_expired = True
                        score = 0.05
                    else:
                        days_left = (deadline - now).days
                        if days_left <= 1:
                            score = 1.5
                        elif days_left <= 3:
                            score = 1.3
                        else:
                            score = 1.1
                else:
                    # Aging decay
                    if age_days <= 1:
                        score = 1.0
                    elif age_days <= 3:
                        score = 0.9
                    elif age_days <= 7:
                        score = 0.75
                    elif age_days <= 14:
                        score = 0.5
                    elif age_days <= 30:
                        score = 0.25
                    else:
                        score = 0.05
                        is_expired = True

                if is_expired:
                    stats["expired"] += 1

                await conn.execute(
                    """
                    UPDATE email_messages
                    SET relevance_score = ?, is_expired = ?
                    WHERE id = ?;
                    """,
                    (score, 1 if is_expired else 0, msg_id),
                )
                stats["updated"] += 1

            await conn.commit()
            return stats

    async def list_actionable_emails(self, limit: int = 50) -> list[dict[str, Any]]:
        """List emails that require action: not noise, not answered, not expired."""
        async with self.connection() as conn:
            cursor = await conn.execute(
                """
                SELECT id, message_id, account_id, folder, sender_name, sender_email,
                       subject, date_sent, snippet, has_attachments, category,
                       relevance_score, deadline_at, is_answered, is_expired
                FROM email_messages
                WHERE requires_action = 1 AND is_answered = 0 AND is_noise = 0 AND is_expired = 0
                ORDER BY relevance_score DESC, date_sent DESC
                LIMIT ?;
                """,
                (limit,),
            )
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

    async def get_email_stats(self) -> dict[str, Any]:
        """Get summary statistics about ingested emails."""
        async with self.connection() as conn:
            cursor = await conn.execute(
                """
                SELECT
                    COUNT(*) as total_emails,
                    COUNT(DISTINCT thread_id) as total_threads,
                    SUM(CASE WHEN is_noise = 1 THEN 1 ELSE 0 END) as noise_count,
                    SUM(CASE WHEN requires_action = 1 THEN 1 ELSE 0 END) as action_count,
                    SUM(CASE WHEN is_answered = 1 THEN 1 ELSE 0 END) as answered_count,
                    SUM(CASE WHEN is_expired = 1 THEN 1 ELSE 0 END) as expired_count,
                    SUM(CASE WHEN requires_action = 1 AND is_answered = 0 AND is_expired = 0 AND is_noise = 0 THEN 1 ELSE 0 END) as active_action_count,
                    SUM(CASE WHEN category = 'guap_student' THEN 1 ELSE 0 END) as student_count,
                    SUM(CASE WHEN category = 'guap_dept' THEN 1 ELSE 0 END) as dept_count,
                    SUM(CASE WHEN category = 'service' THEN 1 ELSE 0 END) as service_count,
                    SUM(CASE WHEN category = 'personal' THEN 1 ELSE 0 END) as personal_count,
                    MIN(date_sent) as oldest_date,
                    MAX(date_sent) as newest_date
                FROM email_messages;
                """
            )
            row = await cursor.fetchone()
            stats = dict(row) if row else {}

            cursor2 = await conn.execute(
                """
                SELECT account_id, COUNT(*) as count
                FROM email_messages
                GROUP BY account_id;
                """
            )
            rows2 = await cursor2.fetchall()
            stats["by_account"] = {r["account_id"]: r["count"] for r in rows2}
            return stats

    async def list_recent_emails(
        self,
        limit: int = 50,
        account_id: str | None = None,
        category: str | None = None,
        non_noise_only: bool = True,
    ) -> list[dict[str, Any]]:
        """List recent emails with filters."""
        query = "SELECT * FROM email_messages WHERE 1=1"
        params: list[Any] = []
        if account_id:
            query += " AND account_id = ?"
            params.append(account_id)
        if category:
            query += " AND category = ?"
            params.append(category)
        if non_noise_only:
            query += " AND is_noise = 0"
        query += " ORDER BY date_sent DESC LIMIT ?"
        params.append(limit)

        async with self.connection() as conn:
            cursor = await conn.execute(query, tuple(params))
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

    async def get_email_by_id(self, email_id: int) -> dict[str, Any] | None:
        """Fetch a single email message by primary key id."""
        async with self.connection() as conn:
            cursor = await conn.execute(
                "SELECT * FROM email_messages WHERE id = ? LIMIT 1;",
                (email_id,),
            )
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def get_thread_messages(self, thread_id: str) -> list[dict[str, Any]]:
        """Fetch all messages belonging to a thread in chronological order."""
        if not thread_id:
            return []
        async with self.connection() as conn:
            cursor = await conn.execute(
                """
                SELECT id, message_id, account_id, sender_name, sender_email, subject,
                       date_sent, snippet, body_plain, is_answered, category
                FROM email_messages
                WHERE thread_id = ?
                ORDER BY date_sent ASC;
                """,
                (thread_id,),
            )
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

    async def mark_email_as_answered(
        self,
        email_id: int,
        reply_message_id: str | None = None,
        user_email: str | None = None,
    ) -> bool:
        """Mark email as answered, recording timestamp and updating thread status."""
        now_iso = datetime.now(timezone.utc).isoformat()
        async with self.connection() as conn:
            # 1. Update email_messages
            cursor = await conn.execute(
                """
                UPDATE email_messages
                SET is_answered = 1,
                    requires_action = 0,
                    replied_at = ?,
                    reply_message_id = COALESCE(?, reply_message_id)
                WHERE id = ?;
                """,
                (now_iso, reply_message_id, email_id),
            )
            updated = cursor.rowcount > 0

            # 2. Get thread_id for this email
            cursor = await conn.execute(
                "SELECT thread_id FROM email_messages WHERE id = ?;",
                (email_id,),
            )
            row = await cursor.fetchone()
            if row and row["thread_id"]:
                thread_id = row["thread_id"]
                await conn.execute(
                    """
                    UPDATE email_threads
                    SET status = 'answered',
                        last_sender_email = COALESCE(?, last_sender_email),
                        last_reply_at = ?
                    WHERE thread_id = ?;
                    """,
                    (user_email, now_iso, thread_id),
                )
            await conn.commit()
            return updated

    async def create_email_draft(self, email_id: int, draft_text: str) -> int:
        """Save a new draft reply to the database."""
        now_iso = datetime.now(timezone.utc).isoformat()
        async with self.connection() as conn:
            cursor = await conn.execute(
                """
                INSERT INTO email_drafts (email_id, draft_text, status, created_at, updated_at)
                VALUES (?, ?, 'pending', ?, ?);
                """,
                (email_id, draft_text, now_iso, now_iso),
            )
            await conn.commit()
            return cursor.lastrowid

    async def get_email_draft(self, draft_id: int) -> dict[str, Any] | None:
        """Retrieve draft by ID including linked email info."""
        async with self.connection() as conn:
            cursor = await conn.execute(
                """
                SELECT d.id as draft_id, d.email_id, d.draft_text, d.status as draft_status,
                       d.created_at as draft_created_at, d.updated_at as draft_updated_at,
                       m.message_id, m.account_id, m.sender_name, m.sender_email, m.subject,
                       m.in_reply_to, m.references_text, m.thread_id, m.body_plain, m.category
                FROM email_drafts d
                JOIN email_messages m ON d.email_id = m.id
                WHERE d.id = ? LIMIT 1;
                """,
                (draft_id,),
            )
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def update_email_draft(
        self,
        draft_id: int,
        draft_text: str | None = None,
        status: str | None = None,
    ) -> bool:
        """Update draft reply text and/or status."""
        now_iso = datetime.now(timezone.utc).isoformat()
        fields = ["updated_at = ?"]
        params: list[Any] = [now_iso]

        if draft_text is not None:
            fields.append("draft_text = ?")
            params.append(draft_text)
        if status is not None:
            fields.append("status = ?")
            params.append(status)

        params.append(draft_id)
        query = f"UPDATE email_drafts SET {', '.join(fields)} WHERE id = ?;"

        async with self.connection() as conn:
            cursor = await conn.execute(query, tuple(params))
            await conn.commit()
            return cursor.rowcount > 0

    async def set_email_card_msg_id(self, email_id: int, card_msg_id: int) -> None:
        """Store Telegram message ID of the notification card for an email."""
        async with self.connection() as conn:
            await conn.execute(
                "UPDATE email_messages SET card_message_id = ? WHERE id = ?;",
                (card_msg_id, email_id),
            )
            await conn.commit()

    async def set_draft_msg_id(self, draft_id: int, draft_msg_id: int) -> None:
        """Store Telegram message ID of the draft card."""
        async with self.connection() as conn:
            await conn.execute(
                "UPDATE email_drafts SET draft_message_id = ? WHERE id = ?;",
                (draft_msg_id, draft_id),
            )
            await conn.commit()

    async def get_daily_email_stats(self, target_date: Any) -> dict[str, Any]:
        """Fetch statistics about emails processed and answered on target_date."""
        from datetime import date
        date_iso = target_date.isoformat() if hasattr(target_date, "isoformat") else str(target_date)[:10]

        async with self.connection() as conn:
            # 1. Answered via bot/drafts on this date
            cursor = await conn.execute(
                """
                SELECT d.id as draft_id, d.email_id, d.updated_at, m.subject, m.sender_name,
                       m.sender_email, m.category, m.account_id
                FROM email_drafts d
                JOIN email_messages m ON d.email_id = m.id
                WHERE d.status = 'sent' AND substr(d.updated_at, 1, 10) = ?
                ORDER BY d.updated_at ASC;
                """,
                (date_iso,),
            )
            bot_answered = [dict(r) for r in await cursor.fetchall()]

            # 2. Total answered emails on this date (including external replies)
            cursor = await conn.execute(
                """
                SELECT id, subject, sender_name, sender_email, replied_at, category, account_id
                FROM email_messages
                WHERE is_answered = 1 AND substr(replied_at, 1, 10) = ?
                ORDER BY replied_at ASC;
                """,
                (date_iso,),
            )
            all_answered = [dict(r) for r in await cursor.fetchall()]

            # 3. Remaining unanswered actionable emails
            cursor = await conn.execute(
                """
                SELECT id, subject, sender_name, sender_email, date_sent, category
                FROM email_messages
                WHERE requires_action = 1 AND is_answered = 0 AND is_noise = 0 AND is_expired = 0
                ORDER BY date_sent DESC;
                """,
            )
            pending_actionable = [dict(r) for r in await cursor.fetchall()]

            return {
                "date": date_iso,
                "bot_answered": bot_answered,
                "all_answered": all_answered,
                "pending_actionable": pending_actionable,
                "total_answered_count": len(all_answered),
                "bot_answered_count": len(bot_answered),
                "pending_count": len(pending_actionable),
            }

    async def _seed_initial_data_if_empty(self, conn: aiosqlite.Connection) -> None:
        """Seed initial projects, tasks, reminders and documents if empty."""
        cursor = await conn.execute("SELECT COUNT(*) FROM projects;")
        row = await cursor.fetchone()
        if row and row[0] > 0:
            return

        now_iso = datetime.now(timezone.utc).isoformat()
        
        # 1. Seed Projects
        projects_data = [
            ("ГУАП: Осенний семестр 2026 (Физика и ОПД)", "ГУАП", "active", "2027-01-31", "Проведение лекций, практик, лабораторных работ, прием зачетов и экзаменов", "Учебный процесс на кафедре физики №1 ГУАП (очники и заочники)."),
            ("ГУАП: Эффективный контракт и методическая работа", "ГУАП", "active", "2027-06-30", "Выполнение плановых показателей публикационной активности и методических материалов", "Подготовка учебно-методических пособий и баллы эффективного контракта."),
            ("Тидекс: Сектор приборов (разработка и учет)", "Тидекс", "active", "2026-12-31", "Выполнение R&D задач сектора приборов, разработка ПО и учет смен", "НИОКР в секторе приборов ООО «Тидекс», трекинг смен и задач."),
            ("AI-ассистент: Автономный секретарь и Студия", "AI & Dev Projects", "active", "2026-10-31", "Запуск полного контура ассистента: почта, расписание, ЛК ГУАП, веб-кабинет", "Разработка веб-студии (chat-app) и серверного движка (assistant-core)."),
            ("Научные публикации и исследования", "Наука и статьи", "active", "2027-04-30", "Подготовка и подача статей ВАК/Scopus по оптике и спектроскопии", "Исследования в области терагерцовой оптики и приборостроения."),
        ]
        
        project_ids = {}
        for name, area, status, target_date, key_result, desc in projects_data:
            c = await conn.execute(
                """
                INSERT INTO projects (name, area, status, target_date, key_result, description, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (name, area, status, target_date, key_result, desc, now_iso, now_iso),
            )
            project_ids[name] = c.lastrowid

        # 2. Seed Tasks
        tasks_data = [
            (project_ids.get("ГУАП: Осенний семестр 2026 (Физика и ОПД)"), "Подготовка к занятиям в среду: Гастелло 15, ауд. 31-04а и 32-03 (ФОНТ и Физика)", "3 пары: 09:30 ФОНТ (м431к), 11:10 Физика (м562), 13:00 ФОНТ (м431к)", "ГУАП", "P1", "todo", "2026-09-30", 90, "ГУАП"),
            (project_ids.get("ГУАП: Осенний семестр 2026 (Физика и ОПД)"), "Размещение заданий и дедлайнов в Личном кабинете преподавателя pro.guap.ru", "Опубликовать лабораторные работы и настроить сроки сдачи для учебных групп.", "ГУАП", "P2", "todo", "2026-10-03", 60, "Документы"),
            (project_ids.get("Тидекс: Сектор приборов (разработка и учет)"), "Сверка и учет отработанных часов за сентябрь в секторе приборов Тидекс", "Проверить табель смен в AADHk Time Recording и сопоставить с сеткой занятий.", "Тидекс", "P2", "todo", "2026-10-01", 45, "Тидекс"),
        ]
        for pid, title, desc, area, prio, status, due, est, tag in tasks_data:
            await conn.execute(
                """
                INSERT INTO tasks (project_id, title, description, area, priority, status, due_date, estimated_minutes, context_tag, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (pid, title, desc, area, prio, status, due, est, tag, now_iso, now_iso),
            )

        # 3. Seed Reminders (Waiting For)
        reminders_data = [
            (None, "Назначить дату онлайн-защиты лабораторных работ в Телемосте и отправить ссылку", "Светлана Парфирова (гр. м651ксв)", "2026-10-02", "ГУАП: Осенний семестр 2026 / Почта", "email", "active"),
            (None, "Проверить присланные отчеты по практике 1 от старост групп м531 и м631к", "Старосты групп м531 / м631к", "2026-10-03", "Основы проектной деятельности", "tg_group", "active"),
        ]
        for tid, what, person, check_date, ctx, stype, status in reminders_data:
            await conn.execute(
                """
                INSERT INTO reminders (task_id, what, person, check_date, context, source_type, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (tid, what, person, check_date, ctx, stype, status, now_iso, now_iso),
            )

        # 4. Seed Documents (Markdown notes / plans)
        sample_doc_content = (
            "# План учебной работы: Осенний семестр 2026\n\n"
            "## 1. Дисциплины и аудиторная нагрузка\n"
            "- **Физические основы нанотехнологий (ФОНТ):** гр. м431к (Лекции и Лабораторные работы, ауд. 31-04а, Гастелло 15).\n"
            "- **Физика (общий курс):** гр. м562, м553, 8626, 1632.\n"
            "- **Основы проектной деятельности (ОПД):** гр. м531, м631к.\n\n"
            "## 2. Порядок приема лабораторных работ\n"
            "1. Очники выполняют работы и защищают в аудиториях кафедры физики №1.\n"
            "2. Для студентов очно-заочной формы (проживающих в других регионах):\n"
            "   - Выполнение отчетов дистанционно и отправка по email.\n"
            "   - Рецензирование и проверка замечаний.\n"
            "   - Итоговая защита в онлайн-формате на платформе «Яндекс Телемост».\n"
        )
        await conn.execute(
            """
            INSERT INTO documents (project_id, title, category, content_markdown, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?);
            """,
            (project_ids.get("ГУАП: Осенний семестр 2026 (Физика и ОПД)"), "План учебной работы: Осенний семестр 2026 (Кафедра физики №1)", "plan", sample_doc_content, now_iso, now_iso),
        )
        await conn.commit()

    # --- Projects CRUD ---
    async def list_projects(self, area: str | None = None, status: str | None = None) -> list[dict[str, Any]]:
        async with self.connection() as conn:
            query = "SELECT * FROM projects WHERE 1=1"
            params: list[Any] = []
            if area:
                query += " AND area = ?"
                params.append(area)
            if status:
                query += " AND status = ?"
                params.append(status)
            query += " ORDER BY id ASC;"
            cursor = await conn.execute(query, tuple(params))
            return [dict(r) for r in await cursor.fetchall()]

    async def get_project(self, project_id: int) -> dict[str, Any] | None:
        async with self.connection() as conn:
            cursor = await conn.execute("SELECT * FROM projects WHERE id = ?;", (project_id,))
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def create_project(
        self,
        name: str,
        area: str = "ГУАП",
        status: str = "active",
        target_date: str | None = None,
        key_result: str | None = None,
        description: str | None = None,
    ) -> int:
        now_iso = datetime.now(timezone.utc).isoformat()
        async with self.connection() as conn:
            cursor = await conn.execute(
                """
                INSERT INTO projects (name, area, status, target_date, key_result, description, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (name, area, status, target_date, key_result, description, now_iso, now_iso),
            )
            await conn.commit()
            return cursor.lastrowid

    async def update_project(self, project_id: int, **kwargs: Any) -> bool:
        if not kwargs:
            return False
        kwargs["updated_at"] = datetime.now(timezone.utc).isoformat()
        set_clauses = [f"{k} = ?" for k in kwargs.keys()]
        values = list(kwargs.values()) + [project_id]
        async with self.connection() as conn:
            cursor = await conn.execute(
                f"UPDATE projects SET {', '.join(set_clauses)} WHERE id = ?;",
                tuple(values),
            )
            await conn.commit()
            return cursor.rowcount > 0

    async def delete_project(self, project_id: int) -> bool:
        async with self.connection() as conn:
            cursor = await conn.execute("DELETE FROM projects WHERE id = ?;", (project_id,))
            await conn.commit()
            return cursor.rowcount > 0

    # --- Tasks CRUD ---
    async def list_tasks(
        self,
        status: str | None = None,
        area: str | None = None,
        priority: str | None = None,
        project_id: int | None = None,
    ) -> list[dict[str, Any]]:
        async with self.connection() as conn:
            query = """
                SELECT t.*, p.name as project_name
                FROM tasks t
                LEFT JOIN projects p ON t.project_id = p.id
                WHERE 1=1
            """
            params: list[Any] = []
            if status:
                query += " AND t.status = ?"
                params.append(status)
            if area:
                query += " AND t.area = ?"
                params.append(area)
            if priority:
                query += " AND t.priority = ?"
                params.append(priority)
            if project_id:
                query += " AND t.project_id = ?"
                params.append(project_id)
            query += " ORDER BY CASE t.priority WHEN 'P1' THEN 1 WHEN 'P2' THEN 2 WHEN 'P3' THEN 3 ELSE 4 END, t.due_date ASC, t.id DESC;"
            cursor = await conn.execute(query, tuple(params))
            return [dict(r) for r in await cursor.fetchall()]

    async def get_task(self, task_id: int) -> dict[str, Any] | None:
        async with self.connection() as conn:
            cursor = await conn.execute(
                """
                SELECT t.*, p.name as project_name
                FROM tasks t
                LEFT JOIN projects p ON t.project_id = p.id
                WHERE t.id = ?;
                """,
                (task_id,),
            )
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def create_task(
        self,
        title: str,
        project_id: int | None = None,
        description: str | None = None,
        area: str = "ГУАП",
        priority: str = "P2",
        status: str = "todo",
        due_date: str | None = None,
        estimated_minutes: int | None = None,
        context_tag: str | None = None,
    ) -> int:
        now_iso = datetime.now(timezone.utc).isoformat()
        async with self.connection() as conn:
            cursor = await conn.execute(
                """
                INSERT INTO tasks (project_id, title, description, area, priority, status, due_date, estimated_minutes, context_tag, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (project_id, title, description, area, priority, status, due_date, estimated_minutes, context_tag, now_iso, now_iso),
            )
            await conn.commit()
            return cursor.lastrowid

    async def update_task(self, task_id: int, **kwargs: Any) -> bool:
        if not kwargs:
            return False
        kwargs["updated_at"] = datetime.now(timezone.utc).isoformat()
        set_clauses = [f"{k} = ?" for k in kwargs.keys()]
        values = list(kwargs.values()) + [task_id]
        async with self.connection() as conn:
            cursor = await conn.execute(
                f"UPDATE tasks SET {', '.join(set_clauses)} WHERE id = ?;",
                tuple(values),
            )
            await conn.commit()
            return cursor.rowcount > 0

    async def delete_task(self, task_id: int) -> bool:
        async with self.connection() as conn:
            cursor = await conn.execute("DELETE FROM tasks WHERE id = ?;", (task_id,))
            await conn.commit()
            return cursor.rowcount > 0

    # --- Reminders / Waiting For CRUD ---
    async def list_reminders(self, status: str | None = None) -> list[dict[str, Any]]:
        async with self.connection() as conn:
            query = "SELECT * FROM reminders WHERE 1=1"
            params: list[Any] = []
            if status:
                query += " AND status = ?"
                params.append(status)
            query += " ORDER BY status ASC, check_date ASC, id DESC;"
            cursor = await conn.execute(query, tuple(params))
            return [dict(r) for r in await cursor.fetchall()]

    async def get_reminder(self, reminder_id: int) -> dict[str, Any] | None:
        async with self.connection() as conn:
            cursor = await conn.execute("SELECT * FROM reminders WHERE id = ?;", (reminder_id,))
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def create_reminder(
        self,
        what: str,
        person: str | None = None,
        check_date: str | None = None,
        context: str | None = None,
        source_type: str = "manual",
        task_id: int | None = None,
        status: str = "active",
    ) -> int:
        now_iso = datetime.now(timezone.utc).isoformat()
        async with self.connection() as conn:
            cursor = await conn.execute(
                """
                INSERT INTO reminders (task_id, what, person, check_date, context, source_type, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (task_id, what, person, check_date, context, source_type, status, now_iso, now_iso),
            )
            await conn.commit()
            return cursor.lastrowid

    async def update_reminder(self, reminder_id: int, **kwargs: Any) -> bool:
        if not kwargs:
            return False
        kwargs["updated_at"] = datetime.now(timezone.utc).isoformat()
        set_clauses = [f"{k} = ?" for k in kwargs.keys()]
        values = list(kwargs.values()) + [reminder_id]
        async with self.connection() as conn:
            cursor = await conn.execute(
                f"UPDATE reminders SET {', '.join(set_clauses)} WHERE id = ?;",
                tuple(values),
            )
            await conn.commit()
            return cursor.rowcount > 0

    async def delete_reminder(self, reminder_id: int) -> bool:
        async with self.connection() as conn:
            cursor = await conn.execute("DELETE FROM reminders WHERE id = ?;", (reminder_id,))
            await conn.commit()
            return cursor.rowcount > 0

    # --- Documents CRUD ---
    async def list_documents(self, project_id: int | None = None) -> list[dict[str, Any]]:
        async with self.connection() as conn:
            query = """
                SELECT d.id, d.project_id, d.title, d.category, d.created_at, d.updated_at,
                       p.name as project_name, substr(d.content_markdown, 1, 150) as preview
                FROM documents d
                LEFT JOIN projects p ON d.project_id = p.id
                WHERE 1=1
            """
            params: list[Any] = []
            if project_id:
                query += " AND d.project_id = ?"
                params.append(project_id)
            query += " ORDER BY d.updated_at DESC, d.id DESC;"
            cursor = await conn.execute(query, tuple(params))
            return [dict(r) for r in await cursor.fetchall()]

    async def get_document(self, doc_id: int) -> dict[str, Any] | None:
        async with self.connection() as conn:
            cursor = await conn.execute(
                """
                SELECT d.*, p.name as project_name
                FROM documents d
                LEFT JOIN projects p ON d.project_id = p.id
                WHERE d.id = ?;
                """,
                (doc_id,),
            )
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def create_document(
        self,
        title: str,
        content_markdown: str,
        project_id: int | None = None,
        category: str = "general",
    ) -> int:
        now_iso = datetime.now(timezone.utc).isoformat()
        async with self.connection() as conn:
            cursor = await conn.execute(
                """
                INSERT INTO documents (project_id, title, category, content_markdown, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?);
                """,
                (project_id, title, category, content_markdown, now_iso, now_iso),
            )
            await conn.commit()
            return cursor.lastrowid

    async def update_document(self, doc_id: int, **kwargs: Any) -> bool:
        if not kwargs:
            return False
        kwargs["updated_at"] = datetime.now(timezone.utc).isoformat()
        set_clauses = [f"{k} = ?" for k in kwargs.keys()]
        values = list(kwargs.values()) + [doc_id]
        async with self.connection() as conn:
            cursor = await conn.execute(
                f"UPDATE documents SET {', '.join(set_clauses)} WHERE id = ?;",
                tuple(values),
            )
            await conn.commit()
            return cursor.rowcount > 0

    async def delete_document(self, doc_id: int) -> bool:
        async with self.connection() as conn:
            cursor = await conn.execute("DELETE FROM documents WHERE id = ?;", (doc_id,))
            await conn.commit()
            return cursor.rowcount > 0

    # --- Dashboard Summary ---
    async def get_dashboard_summary(self) -> dict[str, Any]:
        async with self.connection() as conn:
            # P1 Focus tasks
            cursor = await conn.execute(
                """
                SELECT t.*, p.name as project_name
                FROM tasks t
                LEFT JOIN projects p ON t.project_id = p.id
                WHERE t.status != 'done' AND t.priority = 'P1'
                ORDER BY t.due_date ASC LIMIT 5;
                """
            )
            focus_tasks = [dict(r) for r in await cursor.fetchall()]

            # Task counts by status
            cursor = await conn.execute(
                "SELECT status, COUNT(*) as cnt FROM tasks GROUP BY status;"
            )
            task_status_counts = {row["status"]: row["cnt"] for row in await cursor.fetchall()}

            # Task counts by area
            cursor = await conn.execute(
                "SELECT area, COUNT(*) as cnt FROM tasks WHERE status != 'done' GROUP BY area;"
            )
            task_area_counts = {row["area"]: row["cnt"] for row in await cursor.fetchall()}

            # Active reminders
            cursor = await conn.execute(
                "SELECT * FROM reminders WHERE status = 'active' ORDER BY check_date ASC LIMIT 10;"
            )
            active_reminders = [dict(r) for r in await cursor.fetchall()]

            # Active projects count
            cursor = await conn.execute(
                "SELECT COUNT(*) FROM projects WHERE status = 'active';"
            )
            active_projects_count = (await cursor.fetchone())[0]

            # Total documents count
            cursor = await conn.execute("SELECT COUNT(*) FROM documents;")
            total_documents_count = (await cursor.fetchone())[0]

            return {
                "focus_tasks": focus_tasks,
                "task_status_counts": task_status_counts,
                "task_area_counts": task_area_counts,
                "active_reminders": active_reminders,
                "active_projects_count": active_projects_count,
                "total_documents_count": total_documents_count,
            }

    async def save_timesheet_records_batch(self, records: list[dict[str, Any]]) -> int:
        """Batch insert timesheet records, avoiding duplicates by source and external_record_id."""
        if not records:
            return 0
        inserted = 0
        async with aiosqlite.connect(self.db_path) as conn:
            for r in records:
                ext_id = str(r.get("external_record_id") or "")
                if ext_id:
                    cursor = await conn.execute(
                        "SELECT id FROM timesheet_records WHERE source = ? AND external_record_id = ? LIMIT 1;",
                        (r.get("source", "aadhk"), ext_id),
                    )
                    if await cursor.fetchone():
                        continue

                await conn.execute(
                    """
                    INSERT INTO timesheet_records (
                        source, external_record_id, project_name, task_name,
                        start_time, end_time, duration_minutes, hourly_rate,
                        amount, note, has_guap_conflict, conflict_details
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                    """,
                    (
                        r.get("source", "aadhk"),
                        ext_id or None,
                        r.get("project_name", "Тидекс"),
                        r.get("task_name", "Разработка и исследования"),
                        r.get("start_time"),
                        r.get("end_time"),
                        r.get("duration_minutes", 0),
                        r.get("hourly_rate", 0.0),
                        r.get("amount", 0.0),
                        r.get("note", ""),
                        1 if r.get("has_guap_conflict") else 0,
                        r.get("conflict_details", ""),
                    ),
                )
                inserted += 1
            await conn.commit()
        return inserted

    async def list_timesheet_records(
        self,
        start_date: str | None = None,
        end_date: str | None = None,
        project_name: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """List timesheet records with optional date range and project filter."""
        query = "SELECT * FROM timesheet_records WHERE 1=1"
        params: list[Any] = []
        if start_date:
            query += " AND start_time >= ?"
            params.append(start_date)
        if end_date:
            query += " AND start_time <= ?"
            params.append(end_date)
        if project_name:
            query += " AND project_name LIKE ?"
            params.append(f"%{project_name}%")
        query += " ORDER BY start_time DESC LIMIT ?;"
        params.append(limit)

        async with aiosqlite.connect(self.db_path) as conn:
            conn.row_factory = aiosqlite.Row
            cursor = await conn.execute(query, tuple(params))
            return [dict(r) for r in await cursor.fetchall()]

    async def get_timesheet_summary(
        self,
        start_date: str | None = None,
        end_date: str | None = None,
        project_name: str | None = None,
    ) -> dict[str, Any]:
        """Aggregate total hours, shifts count, breakdown by task, and conflicts."""
        query = "SELECT * FROM timesheet_records WHERE 1=1"
        params: list[Any] = []
        if start_date:
            query += " AND start_time >= ?"
            params.append(start_date)
        if end_date:
            query += " AND start_time <= ?"
            params.append(end_date)
        if project_name:
            query += " AND project_name LIKE ?"
            params.append(f"%{project_name}%")

        async with aiosqlite.connect(self.db_path) as conn:
            conn.row_factory = aiosqlite.Row
            cursor = await conn.execute(query, tuple(params))
            rows = [dict(r) for r in await cursor.fetchall()]

        total_minutes = sum(r.get("duration_minutes") or 0 for r in rows)
        total_hours = round(total_minutes / 60.0, 2)
        conflicts = [r for r in rows if r.get("has_guap_conflict")]

        by_task: dict[str, float] = {}
        for r in rows:
            t = r.get("task_name") or "Основная работа"
            dur = (r.get("duration_minutes") or 0) / 60.0
            by_task[t] = round(by_task.get(t, 0.0) + dur, 2)

        return {
            "total_shifts": len(rows),
            "total_hours": total_hours,
            "total_minutes": total_minutes,
            "conflicts_count": len(conflicts),
            "by_task": by_task,
        }

    async def get_timesheet_conflicts(self, limit: int = 50) -> list[dict[str, Any]]:
        """Retrieve timesheet records flagged with SUAI schedule conflicts."""
        async with aiosqlite.connect(self.db_path) as conn:
            conn.row_factory = aiosqlite.Row
            cursor = await conn.execute(
                "SELECT * FROM timesheet_records WHERE has_guap_conflict = 1 ORDER BY start_time DESC LIMIT ?;",
                (limit,),
            )
            return [dict(r) for r in await cursor.fetchall()]




