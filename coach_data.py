"""Persistent, privacy-conscious storage for the RASHED AI Telegram coach."""
from __future__ import annotations

import json
import os
import sqlite3
import threading
from datetime import datetime, timezone
from typing import Any

DB_PATH = os.getenv("COACH_DB_PATH", "rashd_coach.db")
_LOCK = threading.RLock()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db() -> None:
    with _LOCK, connect() as db:
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                telegram_id INTEGER PRIMARY KEY,
                first_name TEXT NOT NULL DEFAULT '',
                username TEXT NOT NULL DEFAULT '',
                preferred_name TEXT NOT NULL DEFAULT '',
                state TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS profiles (
                telegram_id INTEGER PRIMARY KEY REFERENCES users(telegram_id) ON DELETE CASCADE,
                preferred_name TEXT NOT NULL DEFAULT '',
                goal TEXT NOT NULL DEFAULT '',
                experience TEXT NOT NULL DEFAULT '',
                age INTEGER,
                height_cm REAL,
                weight_kg REAL,
                days_per_week INTEGER,
                session_minutes INTEGER,
                training_place TEXT NOT NULL DEFAULT '',
                equipment TEXT NOT NULL DEFAULT '',
                injury_note TEXT NOT NULL DEFAULT '',
                diet_preferences TEXT NOT NULL DEFAULT '',
                privacy_consent_at TEXT,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS plans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER NOT NULL REFERENCES users(telegram_id) ON DELETE CASCADE,
                version INTEGER NOT NULL DEFAULT 1,
                plan_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS workouts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER NOT NULL REFERENCES users(telegram_id) ON DELETE CASCADE,
                workout_date TEXT NOT NULL,
                completed INTEGER NOT NULL DEFAULT 0,
                effort INTEGER,
                pain_flag INTEGER NOT NULL DEFAULT 0,
                notes TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_workouts_user_date ON workouts(telegram_id, workout_date DESC);
            """
        )
        # Safe migration for databases created by the first MVP release.
        columns = {row[1] for row in db.execute("PRAGMA table_info(profiles)").fetchall()}
        for name, definition in (("age", "INTEGER"), ("height_cm", "REAL"), ("weight_kg", "REAL")):
            if name not in columns:
                db.execute(f"ALTER TABLE profiles ADD COLUMN {name} {definition}")


def register_user(user: Any) -> None:
    now = _now()
    with _LOCK, connect() as db:
        db.execute(
            """INSERT INTO users(telegram_id, first_name, username, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(telegram_id) DO UPDATE SET first_name=excluded.first_name,
               username=excluded.username, updated_at=excluded.updated_at""",
            (user.id, user.first_name or "", user.username or "", now, now),
        )


def set_state(telegram_id: int, state: str) -> None:
    with _LOCK, connect() as db:
        db.execute("UPDATE users SET state=?, updated_at=? WHERE telegram_id=?", (state, _now(), telegram_id))


def get_state(telegram_id: int) -> str:
    with _LOCK, connect() as db:
        row = db.execute("SELECT state FROM users WHERE telegram_id=?", (telegram_id,)).fetchone()
        return str(row["state"] or "") if row else ""


def save_profile(telegram_id: int, data: dict[str, Any]) -> None:
    with _LOCK, connect() as db:
        db.execute(
            """INSERT INTO profiles(telegram_id, preferred_name, goal, experience, age, height_cm, weight_kg, days_per_week, session_minutes,
               training_place, equipment, injury_note, diet_preferences, privacy_consent_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(telegram_id) DO UPDATE SET preferred_name=excluded.preferred_name, goal=excluded.goal, experience=excluded.experience,
               age=excluded.age, height_cm=excluded.height_cm, weight_kg=excluded.weight_kg,
               days_per_week=excluded.days_per_week, session_minutes=excluded.session_minutes,
               training_place=excluded.training_place, equipment=excluded.equipment,
               injury_note=excluded.injury_note, diet_preferences=excluded.diet_preferences,
               privacy_consent_at=excluded.privacy_consent_at, updated_at=excluded.updated_at""",
            (
                telegram_id, data.get("preferred_name", ""), data.get("goal", ""), data.get("experience", ""),
                data.get("age"), data.get("height_cm"), data.get("weight_kg"), data.get("days_per_week"),
                data.get("session_minutes"), data.get("training_place", ""), data.get("equipment", ""),
                data.get("injury_note", ""), data.get("diet_preferences", ""), _now(), _now(),
            ),
        )


def get_profile(telegram_id: int) -> dict[str, Any] | None:
    with _LOCK, connect() as db:
        row = db.execute("SELECT * FROM profiles WHERE telegram_id=?", (telegram_id,)).fetchone()
        return dict(row) if row else None


def save_plan(telegram_id: int, plan: dict[str, Any]) -> None:
    with _LOCK, connect() as db:
        previous = db.execute("SELECT COALESCE(MAX(version), 0) FROM plans WHERE telegram_id=?", (telegram_id,)).fetchone()[0]
        db.execute("INSERT INTO plans(telegram_id, version, plan_json, created_at) VALUES (?, ?, ?, ?)", (telegram_id, int(previous) + 1, json.dumps(plan, ensure_ascii=False), _now()))


def get_plan(telegram_id: int) -> dict[str, Any] | None:
    with _LOCK, connect() as db:
        row = db.execute("SELECT plan_json, version, created_at FROM plans WHERE telegram_id=? ORDER BY id DESC LIMIT 1", (telegram_id,)).fetchone()
        if not row:
            return None
        try:
            plan = json.loads(row["plan_json"])
        except (TypeError, json.JSONDecodeError):
            return None
        plan["version"] = row["version"]
        plan["created_at"] = row["created_at"]
        return plan


def save_workout(telegram_id: int, completed: bool, effort: int | None = None, pain_flag: bool = False, notes: str = "") -> None:
    with _LOCK, connect() as db:
        db.execute("INSERT INTO workouts(telegram_id, workout_date, completed, effort, pain_flag, notes, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)", (telegram_id, _now(), int(completed), effort, int(pain_flag), notes[:1200], _now()))


def recent_workouts(telegram_id: int, limit: int = 8) -> list[dict[str, Any]]:
    with _LOCK, connect() as db:
        rows = db.execute("SELECT * FROM workouts WHERE telegram_id=? ORDER BY workout_date DESC LIMIT ?", (telegram_id, limit)).fetchall()
        return [dict(row) for row in rows]


def delete_user_data(telegram_id: int) -> None:
    with _LOCK, connect() as db:
        db.execute("DELETE FROM users WHERE telegram_id=?", (telegram_id,))


def user_count() -> int:
    with _LOCK, connect() as db:
        return int(db.execute("SELECT COUNT(*) FROM users").fetchone()[0])
