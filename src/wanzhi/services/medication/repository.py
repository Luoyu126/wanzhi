from __future__ import annotations

import sqlite3
from datetime import date, datetime
from pathlib import Path
from typing import Any


class MedicationRepository:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def add_medication(self, name: str, dosage: str, time_of_day: str) -> int:
        with self._connect() as conn:
            cursor = conn.execute(
                "INSERT INTO medications (name, dosage) VALUES (?, ?)",
                (name, dosage),
            )
            medication_id = int(cursor.lastrowid)
            conn.execute(
                "INSERT INTO schedules (medication_id, time_of_day) VALUES (?, ?)",
                (medication_id, time_of_day),
            )
            return medication_id

    def list_due_on(self, target_date: date) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT m.id, m.name, m.dosage, s.time_of_day
                FROM medications m
                JOIN schedules s ON s.medication_id = m.id
                WHERE m.active = 1 AND s.active = 1
                ORDER BY s.time_of_day, m.name
                """
            ).fetchall()
        return [
            {
                "id": row["id"],
                "name": row["name"],
                "dosage": row["dosage"],
                "time_of_day": row["time_of_day"],
                "date": target_date.isoformat(),
            }
            for row in rows
        ]

    def mark_taken(self, medication_id: int, scheduled_for: str) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO intake_logs
                    (medication_id, scheduled_for, taken_at, status)
                VALUES (?, ?, ?, 'taken')
                """,
                (medication_id, scheduled_for, datetime.now().isoformat(timespec="seconds")),
            )

    def _init_schema(self) -> None:
        schema_path = Path(__file__).with_name("schema.sql")
        with self._connect() as conn:
            conn.executescript(schema_path.read_text(encoding="utf-8"))

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn
