import sqlite3
import json
import os
from config import Config


def get_db():
    os.makedirs(Config.DATA_DIR, exist_ok=True)
    conn = sqlite3.connect(Config.DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS tasks (
            id TEXT PRIMARY KEY,
            app_id TEXT NOT NULL,
            app_name TEXT,
            status TEXT DEFAULT 'pending',
            progress REAL DEFAULT 0,
            current_stage TEXT,
            analysis_target TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now')),
            error TEXT,
            result_summary TEXT
        );

        CREATE TABLE IF NOT EXISTS reviews (
            id TEXT PRIMARY KEY,
            task_id TEXT NOT NULL,
            review_id TEXT NOT NULL,
            title TEXT,
            content TEXT,
            rating INTEGER,
            author TEXT,
            version TEXT,
            date TEXT,
            app_id TEXT,
            FOREIGN KEY (task_id) REFERENCES tasks(id)
        );

        CREATE TABLE IF NOT EXISTS analysis_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT NOT NULL,
            stage TEXT NOT NULL,
            result_type TEXT NOT NULL,
            result_data TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (task_id) REFERENCES tasks(id)
        );

        CREATE INDEX IF NOT EXISTS idx_reviews_task ON reviews(task_id);
        CREATE INDEX IF NOT EXISTS idx_reviews_app ON reviews(app_id);
        CREATE INDEX IF NOT EXISTS idx_analysis_task ON analysis_results(task_id);
    """)
    conn.commit()
    conn.close()


def save_task(task_id, app_id, app_name, analysis_target=""):
    conn = get_db()
    conn.execute(
        "INSERT OR REPLACE INTO tasks (id, app_id, app_name, status, analysis_target) VALUES (?, ?, ?, 'pending', ?)",
        (task_id, app_id, app_name, analysis_target)
    )
    conn.commit()
    conn.close()


def update_task_status(task_id, status, progress=None, stage=None, error=None, summary=None):
    conn = get_db()
    updates = ["status = ?", "updated_at = datetime('now')"]
    params = [status]
    if progress is not None:
        updates.append("progress = ?")
        params.append(progress)
    if stage:
        updates.append("current_stage = ?")
        params.append(stage)
    if error:
        updates.append("error = ?")
        params.append(error)
    if summary:
        updates.append("result_summary = ?")
        params.append(summary)
    params.append(task_id)
    conn.execute(f"UPDATE tasks SET {', '.join(updates)} WHERE id = ?", params)
    conn.commit()
    conn.close()


def get_task(task_id):
    conn = get_db()
    row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    conn.close()
    if row:
        return dict(row)
    return None


def save_reviews(task_id, reviews):
    conn = get_db()
    for r in reviews:
        conn.execute(
            "INSERT OR REPLACE INTO reviews (id, task_id, review_id, title, content, rating, author, version, date, app_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (r["review_id"], task_id, r["review_id"], r.get("title", ""), r.get("content", ""),
             r.get("rating", 0), r.get("author", ""), r.get("version", ""), r.get("date", ""), r.get("app_id", ""))
        )
    conn.commit()
    conn.close()


def get_reviews(task_id):
    conn = get_db()
    rows = conn.execute("SELECT * FROM reviews WHERE task_id = ?", (task_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def save_analysis_result(task_id, stage, result_type, result_data):
    conn = get_db()
    conn.execute(
        "INSERT INTO analysis_results (task_id, stage, result_type, result_data) VALUES (?, ?, ?, ?)",
        (task_id, stage, result_type, json.dumps(result_data, ensure_ascii=False))
    )
    conn.commit()
    conn.close()


def get_analysis_results(task_id):
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM analysis_results WHERE task_id = ? ORDER BY id", (task_id,)
    ).fetchall()
    conn.close()
    results = []
    for r in rows:
        d = dict(r)
        d["result_data"] = json.loads(d["result_data"])
        results.append(d)
    return results
