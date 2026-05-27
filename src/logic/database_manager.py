"""SQLite persistence for test data and user authentication metadata."""

from __future__ import annotations

import hashlib
import secrets
import sqlite3
from datetime import datetime
from pathlib import Path

from logic.models import TestRunRecord
from paths import user_data_path


class DatabaseManager:
    """Create/open DB, ensure schema, save runs with parameterized queries."""

    _PBKDF2_ITERATIONS = 200_000
    _ROLE_VALUES = ("Operator", "Technician", "Admin")

    def __init__(self, db_path: Path | None = None) -> None:
        self._db_path = db_path or user_data_path("database.db")
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
                role TEXT NOT NULL CHECK(role IN ('Operator','Technician','Admin')),
                employee_id TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );"""
            )
            conn.execute(
                """CREATE TABLE IF NOT EXISTS test_versions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                test_name TEXT NOT NULL,
                uut_type TEXT NOT NULL,
                version_name TEXT NOT NULL,
                test_content TEXT NOT NULL,
                connection_params TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                created_by TEXT NOT NULL,
                UNIQUE(test_name, version_name)
            );"""
            )
            existing_cols = {
                row["name"]
                for row in conn.execute("PRAGMA table_info(test_versions);").fetchall()
            }
            if "connection_params" not in existing_cols:
                conn.execute(
                    "ALTER TABLE test_versions "
                    "ADD COLUMN connection_params TEXT NOT NULL DEFAULT '';"
                )
            conn.execute(
                """CREATE TABLE IF NOT EXISTS audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                username TEXT NOT NULL DEFAULT '',
                employee_id TEXT NOT NULL DEFAULT '',
                action TEXT NOT NULL,
                details TEXT NOT NULL DEFAULT ''
            );"""
            )
            self._ensure_initial_admin(conn)
            conn.commit()

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
            (username, password_hash, salt, role, employee_id, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?);
            """,
            ("lior", password_hash, salt, "Admin", "0000", now, now),
        )

    def _validate_role(self, role: str) -> str:
        normalized = role.strip().title()
        if normalized not in self._ROLE_VALUES:
            raise ValueError(
                f"Invalid role {role!r}. Expected one of: {', '.join(self._ROLE_VALUES)}"
            )
        return normalized

    def verify_login(self, username: str, password: str) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT username, password_hash, salt, role, employee_id
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
                "employee_id": str(row["employee_id"] or ""),
            }

    def create_user(
        self,
        username: str,
        password: str,
        role: str,
        employee_id: str,
    ) -> None:
        clean_username = username.strip()
        if not clean_username:
            raise ValueError("Username is required.")
        role_value = self._validate_role(role)
        eid = employee_id.strip()
        now = datetime.now().isoformat()
        salt = secrets.token_bytes(16)
        password_hash = self._hash_password(password, salt)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO users
                (username, password_hash, salt, role, employee_id, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    clean_username,
                    password_hash,
                    salt,
                    role_value,
                    eid,
                    now,
                    now,
                ),
            )
            conn.commit()

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
                SET password_hash = ?, salt = ?, updated_at = ?
                WHERE username = ?;
                """,
                (password_hash, salt, datetime.now().isoformat(), clean_username),
            )
            if cur.rowcount == 0:
                raise ValueError("User does not exist.")
            conn.commit()

    def update_user(
        self,
        username: str,
        *,
        role: str | None = None,
        employee_id: str | None = None,
        password: str | None = None,
    ) -> None:
        clean_username = username.strip()
        with self._connect() as conn:
            exists = conn.execute(
                "SELECT role FROM users WHERE username = ?;",
                (clean_username,),
            ).fetchone()
            if exists is None:
                raise ValueError("User does not exist.")

            if role is not None:
                role_value = self._validate_role(role)
                current_role = exists["role"]
                if current_role == "Admin" and role_value != "Admin" and self._admin_count(conn) <= 1:
                    raise ValueError("Cannot demote the last admin user.")
                conn.execute(
                    "UPDATE users SET role = ?, updated_at = ? WHERE username = ?;",
                    (role_value, datetime.now().isoformat(), clean_username),
                )

            if employee_id is not None:
                conn.execute(
                    "UPDATE users SET employee_id = ?, updated_at = ? WHERE username = ?;",
                    (employee_id.strip(), datetime.now().isoformat(), clean_username),
                )

            if password is not None:
                salt = secrets.token_bytes(16)
                password_hash = self._hash_password(password, salt)
                conn.execute(
                    """
                    UPDATE users
                    SET password_hash = ?, salt = ?, updated_at = ?
                    WHERE username = ?;
                    """,
                    (password_hash, salt, datetime.now().isoformat(), clean_username),
                )

            conn.commit()

    def list_users(self) -> list[dict[str, str]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT username, role, employee_id
                FROM users
                ORDER BY role DESC, username COLLATE NOCASE ASC;
                """
            ).fetchall()
            return [
                {
                    "username": row["username"],
                    "role": row["role"],
                    "employee_id": str(row["employee_id"] or ""),
                }
                for row in rows
            ]

    # --- Test versions ------------------------------------------------------------

    def add_test_version(
        self,
        test_name: str,
        uut_type: str,
        version_name: str,
        content: str,
        created_by: str,
        connection_params: str = "",
    ) -> int:
        name = test_name.strip()
        ver = version_name.strip()
        if not name or not ver:
            raise ValueError("test_name and version_name are required.")
        now = datetime.now().isoformat()
        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO test_versions
                    (test_name, uut_type, version_name, test_content,
                     connection_params, created_at, created_by)
                VALUES (?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    name,
                    uut_type.strip(),
                    ver,
                    content,
                    connection_params.strip(),
                    now,
                    created_by.strip(),
                ),
            )
            conn.commit()
            return int(cur.lastrowid)

    def list_test_versions(self) -> list[dict[str, str | int]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, test_name, uut_type, version_name,
                       connection_params, created_at, created_by
                FROM test_versions
                ORDER BY created_at DESC, test_name COLLATE NOCASE ASC, version_name COLLATE NOCASE DESC;
                """
            ).fetchall()
            return [
                {
                    "id": int(row["id"]),
                    "test_name": row["test_name"],
                    "uut_type": row["uut_type"],
                    "version_name": row["version_name"],
                    "connection_params": str(row["connection_params"] or ""),
                    "created_at": row["created_at"],
                    "created_by": row["created_by"],
                }
                for row in rows
            ]

    def get_test_version(self, version_id: int) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT id, test_name, uut_type, version_name, test_content,
                       connection_params, created_at, created_by
                FROM test_versions WHERE id = ?;
                """,
                (version_id,),
            ).fetchone()
            if row is None:
                return None
            return {
                "id": int(row["id"]),
                "test_name": row["test_name"],
                "uut_type": row["uut_type"],
                "version_name": row["version_name"],
                "test_content": row["test_content"],
                "connection_params": str(row["connection_params"] or ""),
                "created_at": row["created_at"],
                "created_by": row["created_by"],
            }

    def delete_test_version(self, version_id: int) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM test_versions WHERE id = ?;", (version_id,))
            conn.commit()

    def version_exists(self, test_name: str, version_name: str) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT 1 FROM test_versions
                WHERE test_name = ? AND version_name = ?;
                """,
                (test_name.strip(), version_name.strip()),
            ).fetchone()
            return row is not None

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

    # --- Audit trail ---------------------------------------------------------------

    def log_audit_action(
        self,
        action: str,
        *,
        username: str = "",
        employee_id: str = "",
        details: str = "",
    ) -> None:
        """Append one row to ``audit_logs`` (UI and security events)."""
        text = action.strip()
        if not text:
            raise ValueError("Audit action is required.")
        ts = datetime.now().isoformat()
        clean_username = username.strip()
        clean_employee_id = employee_id.strip()
        clean_details = details.strip()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO audit_logs (timestamp, username, employee_id, action, details)
                VALUES (?, ?, ?, ?, ?);
                """,
                (
                    ts,
                    clean_username,
                    clean_employee_id,
                    text,
                    clean_details,
                ),
            )
            conn.commit()
        try:
            from logic.secure_logger import get_secure_logger

            get_secure_logger().log_system_event(
                username=clean_username,
                action=text,
                details=clean_details,
            )
        except Exception:
            pass

    def get_audit_logs(self, *, limit: int = 1000) -> list[dict[str, str]]:
        """Newest-first audit rows for admin review."""
        cap = max(1, min(int(limit), 50_000))
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, timestamp, username, employee_id, action, details
                FROM audit_logs
                ORDER BY timestamp DESC
                LIMIT ?;
                """,
                (cap,),
            ).fetchall()
        return [
            {
                "id": str(row["id"]),
                "timestamp": str(row["timestamp"]),
                "username": str(row["username"] or ""),
                "employee_id": str(row["employee_id"] or ""),
                "action": str(row["action"] or ""),
                "details": str(row["details"] or ""),
            }
            for row in rows
        ]
