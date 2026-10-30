import sqlite3
import threading
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id          TEXT PRIMARY KEY,
    created_at  TEXT NOT NULL,
    ip_hash     TEXT NOT NULL,
    user_agent  TEXT,
    ref         TEXT
);

CREATE TABLE IF NOT EXISTS messages (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id         TEXT NOT NULL REFERENCES sessions(id),
    role               TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content            TEXT NOT NULL,
    created_at         TEXT NOT NULL,
    model              TEXT,
    prompt_tokens      INTEGER,
    completion_tokens  INTEGER,
    cached_tokens      INTEGER,
    latency_ms         INTEGER,
    finish_reason      TEXT,
    error              TEXT
);

CREATE INDEX IF NOT EXISTS idx_sessions_ip_hash ON sessions(ip_hash);
CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id, id);
CREATE INDEX IF NOT EXISTS idx_messages_created ON messages(role, created_at);
"""


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _since(hours: int) -> str:
    return (datetime.now(UTC) - timedelta(hours=hours)).isoformat(timespec="seconds")


class Store:
    """Oturumlar ve mesajlar için ince bir SQLite katmanı.

    Uygulama tek worker çalıştığı için tek bağlantı + kilit yeterli. Sorgular
    milisaniye mertebesinde olduğundan event loop'u bloklaması sorun değil.
    """

    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        with self._lock:
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA foreign_keys=ON")
            self._conn.executescript(SCHEMA)

    def close(self) -> None:
        self._conn.close()

    def ping(self) -> None:
        with self._lock:
            self._conn.execute("SELECT 1")

    def session_exists(self, session_id: str) -> bool:
        with self._lock:
            row = self._conn.execute("SELECT 1 FROM sessions WHERE id = ?", (session_id,)).fetchone()
        return row is not None

    def create_session(self, ip_hash: str, user_agent: str | None, ref: str | None) -> str:
        session_id = uuid.uuid4().hex
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT INTO sessions (id, created_at, ip_hash, user_agent, ref) VALUES (?, ?, ?, ?, ?)",
                (session_id, _now(), ip_hash, user_agent, ref),
            )
        return session_id

    def add_message(self, session_id: str, role: str, content: str, **meta) -> None:
        columns = ["session_id", "role", "content", "created_at", *meta.keys()]
        values = [session_id, role, content, _now(), *meta.values()]
        placeholders = ", ".join("?" * len(columns))
        with self._lock, self._conn:
            self._conn.execute(
                f"INSERT INTO messages ({', '.join(columns)}) VALUES ({placeholders})", values
            )

    def history(self, session_id: str, limit: int) -> list[dict[str, str]]:
        """Son en fazla `limit` mesaj, eskiden yeniye.

        Hatalı (fallback) cevaplar ve onları tetikleyen kullanıcı mesajı modele
        geri gönderilmez; böylece roller user/assistant sırasıyla değişmeye devam eder.
        """
        with self._lock:
            rows = self._conn.execute(
                "SELECT role, content, error FROM messages WHERE session_id = ? ORDER BY id DESC LIMIT ?",
                (session_id, limit * 2),
            ).fetchall()
        out: list[dict[str, str]] = []
        for r in reversed(rows):
            if r["error"] is not None:
                if out and out[-1]["role"] == "user":
                    out.pop()
                continue
            out.append({"role": r["role"], "content": r["content"]})
        out = out[-limit:]
        while out and out[0]["role"] != "user":
            out.pop(0)
        return out

    def count_user_messages_in_session(self, session_id: str) -> int:
        with self._lock:
            return self._conn.execute(
                "SELECT COUNT(*) FROM messages WHERE session_id = ? AND role = 'user'", (session_id,)
            ).fetchone()[0]

    def count_user_messages_by_ip(self, ip_hash: str, hours: int = 24) -> int:
        with self._lock:
            return self._conn.execute(
                """
                SELECT COUNT(*) FROM messages m JOIN sessions s ON s.id = m.session_id
                WHERE m.role = 'user' AND s.ip_hash = ? AND m.created_at >= ?
                """,
                (ip_hash, _since(hours)),
            ).fetchone()[0]

    def count_user_messages_total(self, hours: int = 24) -> int:
        with self._lock:
            return self._conn.execute(
                "SELECT COUNT(*) FROM messages WHERE role = 'user' AND created_at >= ?",
                (_since(hours),),
            ).fetchone()[0]
