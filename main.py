from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import sqlite3
from datetime import datetime

app = FastAPI(title="夏瑶雯作品集后端")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

def get_db():
    conn = sqlite3.connect("portfolio.db")
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    conn.execute("CREATE TABLE IF NOT EXISTS visitor_count (id INTEGER PRIMARY KEY, count INTEGER DEFAULT 0)")
    row = conn.execute("SELECT count FROM visitor_count LIMIT 1").fetchone()
    if not row:
        conn.execute("INSERT INTO visitor_count (count) VALUES (0)")
    conn.execute("CREATE TABLE IF NOT EXISTS messages (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, content TEXT NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP)")
    conn.commit()
    conn.close()

init_db()

@app.get("/api/stats")
def get_stats():
    conn = get_db()
    row = conn.execute("SELECT count FROM visitor_count LIMIT 1").fetchone()
    current_count = row["count"] if row else 0
    conn.execute("UPDATE visitor_count SET count = count + 1")
    conn.commit()
    conn.close()
    return {"visitors": current_count + 1}

@app.post("/api/message")
def add_message(data: dict):
    name = data.get("name", "").strip()
    content = data.get("content", "").strip()
    if not name or not content:
        return {"error": "名字和内容都不能为空"}
    if len(name) > 50 or len(content) > 500:
        return {"error": "名字不超过50字，内容不超过500字"}
    conn = get_db()
    conn.execute("INSERT INTO messages (name, content, created_at) VALUES (?, ?, ?)", (name, content, datetime.now().isoformat()))
    conn.commit()
    conn.close()
    return {"ok": True}

@app.get("/api/messages")
def get_messages():
    conn = get_db()
    rows = conn.execute("SELECT id, name, content, created_at FROM messages ORDER BY id DESC LIMIT 10").fetchall()
    conn.close()
    return [dict(row) for row in rows]

@app.get("/")
def root():
    return {"message": "夏瑶雯作品集后端运行中", "docs": "/docs"}