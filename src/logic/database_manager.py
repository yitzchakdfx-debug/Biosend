"""SQLite persistence for test data and user authentication metadata."""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path
import hashlib
import secrets

from logic.models import TestRunRecord


class DatabaseManager:
    """Create/open DB, ensure schema, save runs with parameterized queries."""
    _PBKDF2_ITERATIONS = 200_000
    _ROLE_VALUES = ("Operator", "Engineer", "Admin")

    def __init__(self, db_path: Path | None = None) -> None:
        self._db_path = db_path or (
            Path(__file__).resolve().parent.parent / "data" / "database.db"
        )
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._create_tables()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        return conn

    def _create_tables(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """CREATE TABLE IF NOT EXISTS test_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                operator TEXT,
                part_number TEXT,
                serial_number TEXT,
                overall_passed INTEGER,
                start_time TEXT,
                end_time TEXT
            );"""
            )
            conn.execute(
                """CREATE TABLE IF NOT EXISTS test_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id INTEGER NOT NULL,
                test_name TEXT,
                value REAL,
                min_val REAL,
                max_val REAL,
                unit TEXT,
                passed INTEGER,
                FOREIGN KEY(run_id) REFERENCES test_runs(id)
            );"""
            )
            conn.execute(
                """CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL COLLATE NOCASE,
                password_hash BLOB NOT NULL,
                salt BLOB NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('Operator','Engineer','Admin')),
                must_change_pwd INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );"""
            )
            self._ensure_initial_admin(conn)

    def _hash_password(self, password: str, salt: bytes) -> bytes:
        return hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt,
            self._PBKDF2_ITERATIONS,
        )

    def _ensure_initial_admin(self, conn: sqlite3.Connection) -> None:
        now = datetime.now().isoformat()
        salt = secrets.token_bytes(16)
        password_hash = self._hash_password("Aa123456", salt)
        conn.execute(
            """
            INSERT OR IGNORE INTO users
            (username, password_hash, salt, role, must_change_pwd, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?);
            """,
            ("lior", password_hash, salt, "Admin", 0, now, now),
        )

    def _validate_role(self, role: str) -> str:
        normalized = role.strip().title()
        if normalized not in self._ROLE_VALUES:
            raise ValueError(
                f"Invalid role {role!r}. Expected one of: {', '.join(self._ROLE_VALUES)}"
            )
        return normalized

    def _generate_temp_password(self) -> str:
        alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789"
        return "".join(secrets.choice(alphabet) for _ in range(8))

    def verify_login(self, username: str, password: str) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT username, password_hash, salt, role, must_change_pwd
                FROM users
                WHERE username = ?;
                """,
                (username.strip(),),
            ).fetchone()
            if row is None:
                return None
            computed = self._hash_password(password, row["salt"])
            if not secrets.compare_digest(computed, row["password_hash"]):
                return None
            return {
                "name": row["username"],
                "username": row["username"],
                "role": row["role"],
                "must_change_pwd": bool(row["must_change_pwd"]),
            }

    def create_user(
        self,
        username: str,
        password: str,
        role: str,
        must_change_pwd: bool = False,
    ) -> None:
        clean_username = username.strip()
        if not clean_username:
            raise ValueError("Username is required.")
        role_value = self._validate_role(role)
        now = datetime.now().isoformat()
        salt = secrets.token_bytes(16)
        password_hash = self._hash_password(password, salt)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO users
                (username, password_hash, salt, role, must_change_pwd, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    clean_username,
                    password_hash,
                    salt,
                    role_value,
                    int(must_change_pwd),
                    now,
                    now,
                ),
            )
            conn.commit()

    def reset_password_for_new_user(self, username: str, role: str) -> str:
        temp_password = self._generate_temp_password()
        self.create_user(username, temp_password, role, must_change_pwd=True)
        return temp_password

    def _admin_count(self, conn: sqlite3.Connection) -> int:
        row = conn.execute(
            "SELECT COUNT(*) AS c FROM users WHERE role = 'Admin';"
        ).fetchone()
        return int(row["c"]) if row is not None else 0

    def delete_user(self, username: str) -> None:
        clean_username = username.strip()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT role FROM users WHERE username = ?;",
                (clean_username,),
            ).fetchone()
            if row is None:
                raise ValueError("User does not exist.")
            if row["role"] == "Admin" and self._admin_count(conn) <= 1:
                raise ValueError("Cannot delete the last admin user.")
            conn.execute("DELETE FROM users WHERE username = ?;", (clean_username,))
            conn.commit()

    def update_role(self, username: str, role: str) -> None:
        clean_username = username.strip()
        role_value = self._validate_role(role)
        with self._connect() as conn:
            current = conn.execute(
                "SELECT role FROM users WHERE username = ?;",
                (clean_username,),
            ).fetchone()
            if current is None:
                raise ValueError("User does not exist.")
            if current["role"] == "Admin" and role_value != "Admin" and self._admin_count(conn) <= 1:
                raise ValueError("Cannot demote the last admin user.")
            conn.execute(
                "UPDATE users SET role = ?, updated_at = ? WHERE username = ?;",
                (role_value, datetime.now().isoformat(), clean_username),
            )
            conn.commit()

    def change_password(self, username: str, new_password: str) -> None:
        clean_username = username.strip()
        salt = secrets.token_bytes(16)
        password_hash = self._hash_password(new_password, salt)
        with self._connect() as conn:
            cur = conn.execute(
                """
                UPDATE users
                SET password_hash = ?, salt = ?, must_change_pwd = 0, updated_at = ?
                WHERE username = ?;
                """,
                (password_hash, salt, datetime.now().isoformat(), clean_username),
            )
            if cur.rowcount == 0:
                raise ValueError("User does not exist.")
            conn.commit()

    def reset_password(self, username: str) -> str:
        temp_password = self._generate_temp_password()
        clean_username = username.strip()
        salt = secrets.token_bytes(16)
        password_hash = self._hash_password(temp_password, salt)
        with self._connect() as conn:
            cur = conn.execute(
                """
                UPDATE users
                SET password_hash = ?, salt = ?, must_change_pwd = 1, updated_at = ?
                WHERE username = ?;
                """,
                (password_hash, salt, datetime.now().isoformat(), clean_username),
            )
            if cur.rowcount == 0:
                raise ValueError("User does not exist.")
            conn.commit()
        return temp_password

    def list_users(self) -> list[dict[str, str | bool]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT username, role, must_change_pwd
                FROM users
                ORDER BY role DESC, username COLLATE NOCASE ASC;
                """
            ).fetchall()
            return [
                {
                    "username": row["username"],
                    "role": row["role"],
                    "must_change_pwd": bool(row["must_change_pwd"]),
                }
                for row in rows
            ]

    def save_run(self, record: TestRunRecord) -> int:
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO test_runs (operator, part_number, serial_number, "
                "overall_passed, start_time, end_time) VALUES (?, ?, ?, ?, ?, ?);",
                (
                    record.operator,
                    record.part_number,
                    record.serial_number,
                    int(record.overall_passed),
                    record.start_time.isoformat(),
                    record.end_time.isoformat() if record.end_time else None,
                ),
            )
            run_id = int(cur.lastrowid)
            cur.executemany(
                "INSERT INTO test_results (run_id, test_name, value, min_val, "
                "max_val, unit, passed) VALUES (?, ?, ?, ?, ?, ?, ?);",
                [
                    (
                        run_id,
                        r["test_name"],
                        r["value"],
                        r["min"],
                        r["max"],
                        r["unit"],
                        int(r["passed"]),
                    )
                    for r in record.results
                ],
            )
            conn.commit()
            return run_id
