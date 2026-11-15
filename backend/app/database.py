"""Persistencia en SQLite (biblioteca estándar, sin ORM).

Cada operación abre su propia conexión: es sencillo y seguro entre hilos
(el procesamiento corre en segundo plano mientras el frontend consulta el estado).
"""
from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY,
    original_name TEXT NOT NULL,
    stored_name TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    page_count INTEGER NOT NULL,
    status TEXT NOT NULL,
    extraction_method TEXT,
    stages TEXT NOT NULL,
    message TEXT,
    extracted_text TEXT,
    text_override TEXT,
    blocks_json TEXT,
    project_id TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL,
    document_name TEXT NOT NULL,
    title TEXT NOT NULL,
    resource_type TEXT NOT NULL,
    map_json TEXT NOT NULL,
    original_map_json TEXT NOT NULL,
    edited INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""

DOCUMENT_FIELDS = {
    "status", "extraction_method", "stages", "message", "extracted_text",
    "text_override", "project_id", "page_count", "blocks_json",
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


class Database:
    def __init__(self, path: Path):
        self.path = Path(path)

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path, timeout=30)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def init(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as c:
            c.executescript(SCHEMA)
            # Migración para bases creadas antes de existir el módulo de cuestionarios
            columns = {row["name"] for row in c.execute("PRAGMA table_info(documents)")}
            if "blocks_json" not in columns:
                c.execute("ALTER TABLE documents ADD COLUMN blocks_json TEXT")

    # ------------------------------------------------------------------ documentos
    def insert_document(self, *, doc_id: str, original_name: str, stored_name: str,
                        size_bytes: int, page_count: int, stages: dict[str, str]) -> None:
        with self._conn() as c:
            c.execute(
                "INSERT INTO documents (id, original_name, stored_name, size_bytes, page_count,"
                " status, stages, created_at) VALUES (?,?,?,?,?,?,?,?)",
                (doc_id, original_name, stored_name, size_bytes, page_count, "uploaded",
                 json.dumps(stages), now_iso()),
            )

    def get_document(self, doc_id: str) -> dict[str, Any] | None:
        with self._conn() as c:
            row = c.execute("SELECT * FROM documents WHERE id = ?", (doc_id,)).fetchone()
        return dict(row) if row else None

    def update_document(self, doc_id: str, **fields: Any) -> None:
        unknown = set(fields) - DOCUMENT_FIELDS
        if unknown:
            raise ValueError(f"Campos no permitidos: {unknown}")
        if "stages" in fields and not isinstance(fields["stages"], str):
            fields["stages"] = json.dumps(fields["stages"])
        if not fields:
            return
        cols = ", ".join(f"{k} = ?" for k in fields)
        with self._conn() as c:
            c.execute(f"UPDATE documents SET {cols} WHERE id = ?", (*fields.values(), doc_id))

    def delete_document(self, doc_id: str) -> None:
        with self._conn() as c:
            c.execute("DELETE FROM documents WHERE id = ?", (doc_id,))

    # ------------------------------------------------------------------ proyectos
    def insert_project(self, *, project_id: str, document_id: str, document_name: str,
                       title: str, map_json: str, resource_type: str = "mapa_conceptual") -> None:
        ts = now_iso()
        with self._conn() as c:
            c.execute(
                "INSERT INTO projects (id, document_id, document_name, title, resource_type,"
                " map_json, original_map_json, edited, created_at, updated_at)"
                " VALUES (?,?,?,?,?,?,?,0,?,?)",
                (project_id, document_id, document_name, title, resource_type,
                 map_json, map_json, ts, ts),
            )

    def list_projects(self) -> list[dict[str, Any]]:
        with self._conn() as c:
            rows = c.execute("SELECT * FROM projects ORDER BY created_at DESC, id").fetchall()
        return [dict(r) for r in rows]

    def get_project(self, project_id: str) -> dict[str, Any] | None:
        with self._conn() as c:
            row = c.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
        return dict(row) if row else None

    def save_project_map(self, project_id: str, *, title: str, map_json: str, edited: bool) -> None:
        with self._conn() as c:
            c.execute(
                "UPDATE projects SET title = ?, map_json = ?, edited = ?, updated_at = ? WHERE id = ?",
                (title, map_json, int(edited), now_iso(), project_id),
            )

    def delete_project(self, project_id: str) -> dict[str, Any] | None:
        """Elimina el proyecto y devuelve su fila (para borrar también el PDF asociado)."""
        project = self.get_project(project_id)
        if project:
            with self._conn() as c:
                c.execute("DELETE FROM projects WHERE id = ?", (project_id,))
        return project
