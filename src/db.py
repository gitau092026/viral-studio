"""Durable local state (SQLite, stdlib only).

One shared connection guarded by a write lock — correct and more than fast
enough for a single-process, single-user local tool. Tables: jobs, videos
(with the persisted review gate), schedule (also the upload record), analytics.

The DB lives OUTSIDE the OneDrive project dir (see settings.load_config) so it
never syncs to the cloud.
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time

_SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
  id          TEXT PRIMARY KEY,
  kind        TEXT NOT NULL,
  status      TEXT NOT NULL,
  topic       TEXT,
  result_json TEXT,
  error       TEXT,
  started_at  REAL NOT NULL,
  ended_at    REAL
);

CREATE TABLE IF NOT EXISTS videos (
  file        TEXT PRIMARY KEY,
  title       TEXT,
  topic       TEXT,
  duration_s  INTEGER,
  created_at  REAL NOT NULL,
  review_json TEXT,
  approved    INTEGER NOT NULL DEFAULT 0,
  approved_at REAL,
  style       TEXT,
  width       INTEGER,
  height      INTEGER
);

CREATE TABLE IF NOT EXISTS schedule (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  file          TEXT NOT NULL,
  youtube_id    TEXT,
  url           TEXT,
  privacy       TEXT,
  scheduled_for TEXT,
  status        TEXT NOT NULL,
  error         TEXT,
  created_at    REAL NOT NULL,
  updated_at    REAL,
  FOREIGN KEY (file) REFERENCES videos(file)
);
CREATE INDEX IF NOT EXISTS idx_schedule_file ON schedule(file);

CREATE TABLE IF NOT EXISTS analytics (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  youtube_id  TEXT NOT NULL,
  file        TEXT,
  captured_at REAL NOT NULL,
  views       INTEGER,
  likes       INTEGER,
  comments    INTEGER,
  UNIQUE (youtube_id, captured_at)
);
CREATE INDEX IF NOT EXISTS idx_analytics_vid ON analytics(youtube_id);
"""

_CONN: sqlite3.Connection | None = None
_LOCK = threading.Lock()


def init_db(cfg: dict) -> None:
    """Idempotent — safe to call from both app startup and CLI commands."""
    global _CONN
    with _LOCK:
        if _CONN is not None:
            return
        conn = sqlite3.connect(cfg["db_path"], check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.executescript(_SCHEMA)
        _migrate(conn)
        conn.commit()
        _CONN = conn


def _migrate(conn: sqlite3.Connection) -> None:
    """Add columns to pre-existing tables (CREATE TABLE IF NOT EXISTS won't).

    Idempotent: only ALTERs columns that are missing, so existing rows (incl.
    the persisted review gate) are preserved across upgrades.
    """
    have = {r["name"] for r in conn.execute("PRAGMA table_info(videos)")}
    for col, decl in (("style", "TEXT"), ("width", "INTEGER"), ("height", "INTEGER")):
        if col not in have:
            conn.execute(f"ALTER TABLE videos ADD COLUMN {col} {decl}")


def _conn() -> sqlite3.Connection:
    if _CONN is None:
        raise RuntimeError("db.init_db(cfg) was not called")
    return _CONN


def _exec(sql: str, params: tuple = ()) -> None:
    with _LOCK:
        _conn().execute(sql, params)
        _conn().commit()


def _one(sql: str, params: tuple = ()):
    with _LOCK:
        return _conn().execute(sql, params).fetchone()


def _all(sql: str, params: tuple = ()):
    with _LOCK:
        return _conn().execute(sql, params).fetchall()


# ---- jobs -------------------------------------------------------------------
def create_job(jid: str, kind: str, topic: str | None = None) -> None:
    _exec("INSERT OR REPLACE INTO jobs (id,kind,status,topic,started_at) VALUES (?,?,?,?,?)",
          (jid, kind, "running", topic, time.time()))


def update_job(jid: str, status: str, result_json: str | None = None, error: str | None = None) -> None:
    _exec("UPDATE jobs SET status=?, result_json=?, error=?, ended_at=? WHERE id=?",
          (status, result_json, error, time.time(), jid))


def get_job(jid: str) -> dict | None:
    row = _one("SELECT * FROM jobs WHERE id=?", (jid,))
    return dict(row) if row else None


def list_jobs(limit: int = 100) -> list[dict]:
    return [dict(r) for r in _all("SELECT * FROM jobs ORDER BY started_at DESC LIMIT ?", (limit,))]


# ---- videos -----------------------------------------------------------------
def upsert_video(file: str, title: str | None = None, topic: str | None = None,
                 duration_s: int | None = None, created_at: float | None = None,
                 style: str | None = None, width: int | None = None,
                 height: int | None = None) -> None:
    # ON CONFLICT preserves the review columns so a re-render never wipes approval.
    # COALESCE on style/width/height keeps a known look if a later upsert omits it.
    _exec(
        """INSERT INTO videos (file,title,topic,duration_s,created_at,style,width,height)
           VALUES (?,?,?,?,?,?,?,?)
           ON CONFLICT(file) DO UPDATE SET
             title=excluded.title, topic=excluded.topic, duration_s=excluded.duration_s,
             style=COALESCE(excluded.style, videos.style),
             width=COALESCE(excluded.width, videos.width),
             height=COALESCE(excluded.height, videos.height)""",
        (file, title, topic, duration_s, created_at or time.time(), style, width, height),
    )


def get_video(file: str) -> dict | None:
    row = _one("SELECT * FROM videos WHERE file=?", (file,))
    return dict(row) if row else None


def list_videos() -> list[dict]:
    return [dict(r) for r in _all("SELECT * FROM videos ORDER BY created_at DESC")]


def delete_video(file: str) -> None:
    """Remove a draft's rows. Caller deletes the files; caller must also refuse
    deletion of anything already uploaded (schedule row with a youtube_id)."""
    _exec("DELETE FROM schedule WHERE file=?", (file,))
    _exec("DELETE FROM videos WHERE file=?", (file,))


# ---- review gate (persisted, authoritative) ---------------------------------
def set_review(file: str, checks, approved: bool) -> None:
    _exec("INSERT OR IGNORE INTO videos (file, created_at) VALUES (?,?)", (file, time.time()))
    _exec("UPDATE videos SET review_json=?, approved=?, approved_at=? WHERE file=?",
          (json.dumps([bool(c) for c in checks]), 1 if approved else 0,
           time.time() if approved else None, file))


def get_review(file: str) -> dict:
    row = _one("SELECT review_json, approved, approved_at FROM videos WHERE file=?", (file,))
    if not row:
        return {"checks": [], "approved": False, "approved_at": None}
    checks = json.loads(row["review_json"]) if row["review_json"] else []
    return {"checks": checks, "approved": bool(row["approved"]), "approved_at": row["approved_at"]}


# ---- schedule / upload record -----------------------------------------------
def create_or_update_schedule(file: str, scheduled_for: str | None = None, status: str = "draft",
                              youtube_id: str | None = None, privacy: str | None = None,
                              url: str | None = None, error: str | None = None) -> None:
    now = time.time()
    exists = _one("SELECT id FROM schedule WHERE file=?", (file,))
    if exists:
        _exec(
            """UPDATE schedule SET
                 youtube_id=COALESCE(?,youtube_id), url=COALESCE(?,url),
                 privacy=COALESCE(?,privacy), scheduled_for=COALESCE(?,scheduled_for),
                 status=?, error=?, updated_at=? WHERE file=?""",
            (youtube_id, url, privacy, scheduled_for, status, error, now, file),
        )
    else:
        _exec(
            """INSERT INTO schedule
                 (file,youtube_id,url,privacy,scheduled_for,status,error,created_at,updated_at)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (file, youtube_id, url, privacy, scheduled_for, status, error, now, now),
        )


def list_schedule() -> list[dict]:
    rows = _all(
        """SELECT s.*, v.title AS title FROM schedule s
           LEFT JOIN videos v ON v.file=s.file
           ORDER BY COALESCE(s.scheduled_for,'') DESC, s.updated_at DESC"""
    )
    return [dict(r) for r in rows]


def get_schedule_for(file: str) -> dict | None:
    row = _one("SELECT * FROM schedule WHERE file=?", (file,))
    return dict(row) if row else None


def uploaded_video_ids() -> list[tuple[str, str]]:
    """[(youtube_id, file)] for everything we've uploaded — drives analytics refresh."""
    return [(r["youtube_id"], r["file"])
            for r in _all("SELECT youtube_id, file FROM schedule WHERE youtube_id IS NOT NULL")]


# ---- analytics --------------------------------------------------------------
def insert_analytics(youtube_id: str, file: str | None, views: int, likes: int,
                     comments: int, captured_at: float | None = None) -> None:
    _exec(
        """INSERT OR IGNORE INTO analytics (youtube_id,file,captured_at,views,likes,comments)
           VALUES (?,?,?,?,?,?)""",
        (youtube_id, file, captured_at or time.time(), views, likes, comments),
    )


def leaderboard() -> list[dict]:
    """Latest snapshot per video, richest first, with derived views/day."""
    rows = _all(
        """SELECT a.youtube_id, a.file, a.views, a.likes, a.comments, a.captured_at,
                  v.title, v.topic, v.created_at
           FROM analytics a
           JOIN (SELECT youtube_id, MAX(captured_at) mc FROM analytics GROUP BY youtube_id) latest
             ON a.youtube_id=latest.youtube_id AND a.captured_at=latest.mc
           LEFT JOIN videos v ON v.file=a.file
           ORDER BY a.views DESC"""
    )
    out = []
    for r in rows:
        d = dict(r)
        created = d.get("created_at")
        if created and d.get("views"):
            days = max((d["captured_at"] - created) / 86400.0, 0.5)
            d["views_per_day"] = int(d["views"] / days)
        else:
            d["views_per_day"] = None
        out.append(d)
    return out
