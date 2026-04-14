from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class TaskRepository:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._init_db()

    @contextmanager
    def connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _column_names(self, conn: sqlite3.Connection, table_name: str) -> set[str]:
        rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
        return {row[1] for row in rows}

    def _ensure_column(self, conn: sqlite3.Connection, table_name: str, name: str, ddl: str) -> None:
        if name not in self._column_names(conn, table_name):
            conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {name} {ddl}")

    def _init_db(self) -> None:
        with self.connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS tasks (
                    task_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    progress INTEGER NOT NULL,
                    message TEXT NOT NULL,
                    upload_dir TEXT NOT NULL,
                    excel_path TEXT NOT NULL,
                    output_path TEXT,
                    error_message TEXT,
                    total_docs INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    mappings_json TEXT,
                    preview_rows_json TEXT
                )
                """
            )
            self._ensure_column(conn, "tasks", "mappings_json", "TEXT")
            self._ensure_column(conn, "tasks", "preview_rows_json", "TEXT")

            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS uploads (
                    upload_id TEXT PRIMARY KEY,
                    upload_dir TEXT NOT NULL,
                    excel_path TEXT NOT NULL,
                    headers_json TEXT NOT NULL,
                    mappings_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )

            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS task_documents (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    owner_id TEXT,
                    owner_type TEXT,
                    filename TEXT NOT NULL,
                    path TEXT NOT NULL
                )
                """
            )
            self._ensure_column(conn, "task_documents", "owner_id", "TEXT")
            self._ensure_column(conn, "task_documents", "owner_type", "TEXT")

            task_document_columns = self._column_names(conn, "task_documents")
            if "task_id" in task_document_columns:
                conn.execute(
                    """
                    UPDATE task_documents
                    SET owner_id = COALESCE(owner_id, task_id),
                        owner_type = COALESCE(owner_type, 'task')
                    WHERE owner_id IS NULL OR owner_type IS NULL
                    """
                )

    def create_upload(
        self,
        upload_id: str,
        upload_dir: str,
        excel_path: str,
        headers: list[str],
        mappings: list[dict[str, Any]],
        documents: list[dict[str, str]],
    ) -> None:
        now = utcnow_iso()
        with self.connection() as conn:
            conn.execute(
                """
                INSERT INTO uploads (upload_id, upload_dir, excel_path, headers_json, mappings_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    upload_id,
                    upload_dir,
                    excel_path,
                    json.dumps(headers, ensure_ascii=False),
                    json.dumps(mappings, ensure_ascii=False),
                    now,
                ),
            )
            conn.executemany(
                """
                INSERT INTO task_documents (owner_id, owner_type, filename, path)
                VALUES (?, 'upload', ?, ?)
                """,
                [(upload_id, doc["filename"], doc["path"]) for doc in documents],
            )

    def get_upload(self, upload_id: str) -> sqlite3.Row | None:
        with self.connection() as conn:
            return conn.execute("SELECT * FROM uploads WHERE upload_id = ?", (upload_id,)).fetchone()

    def list_upload_documents(self, upload_id: str) -> list[sqlite3.Row]:
        with self.connection() as conn:
            return conn.execute(
                "SELECT filename, path FROM task_documents WHERE owner_id = ? AND owner_type = 'upload' ORDER BY id",
                (upload_id,),
            ).fetchall()

    def create_task(
        self,
        task_id: str,
        upload_id: str,
        mappings: list[dict[str, Any]],
    ) -> None:
        upload = self.get_upload(upload_id)
        if upload is None:
            raise ValueError("Upload session not found.")
        documents = self.list_upload_documents(upload_id)
        now = utcnow_iso()
        with self.connection() as conn:
            conn.execute(
                """
                INSERT INTO tasks (
                    task_id, status, progress, message, upload_dir, excel_path,
                    output_path, error_message, total_docs, created_at, updated_at,
                    mappings_json, preview_rows_json
                )
                VALUES (?, 'pending', 0, 'Task created', ?, ?, NULL, NULL, ?, ?, ?, ?, '[]')
                """,
                (
                    task_id,
                    upload["upload_dir"],
                    upload["excel_path"],
                    len(documents),
                    now,
                    now,
                    json.dumps(mappings, ensure_ascii=False),
                ),
            )
            conn.executemany(
                """
                INSERT INTO task_documents (owner_id, owner_type, filename, path)
                VALUES (?, 'task', ?, ?)
                """,
                [(task_id, row["filename"], row["path"]) for row in documents],
            )

    def list_documents(self, task_id: str) -> list[sqlite3.Row]:
        with self.connection() as conn:
            return conn.execute(
                "SELECT filename, path FROM task_documents WHERE owner_id = ? AND owner_type = 'task' ORDER BY id",
                (task_id,),
            ).fetchall()

    def get_task(self, task_id: str) -> sqlite3.Row | None:
        with self.connection() as conn:
            return conn.execute("SELECT * FROM tasks WHERE task_id = ?", (task_id,)).fetchone()

    def get_pending_task(self) -> sqlite3.Row | None:
        with self.connection() as conn:
            return conn.execute(
                "SELECT * FROM tasks WHERE status = 'pending' ORDER BY created_at ASC LIMIT 1"
            ).fetchone()

    def update_task(self, task_id: str, **fields: Any) -> None:
        if not fields:
            return
        if "preview_rows" in fields:
            fields["preview_rows_json"] = json.dumps(fields.pop("preview_rows"), ensure_ascii=False)
        if "mappings" in fields:
            fields["mappings_json"] = json.dumps(fields.pop("mappings"), ensure_ascii=False)
        fields["updated_at"] = utcnow_iso()
        assignments = ", ".join(f"{key} = ?" for key in fields)
        values = list(fields.values()) + [task_id]
        with self.connection() as conn:
            conn.execute(f"UPDATE tasks SET {assignments} WHERE task_id = ?", values)
