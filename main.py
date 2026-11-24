from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import sqlite3
import hashlib
import os
import smtplib
import ssl
from email.message import EmailMessage
from threading import Lock
from pydantic import BaseModel, Field
from contextlib import closing

app = FastAPI(title="夏瑶雯作品集后端")
delivery_lock = Lock()


class MessageInput(BaseModel):
    name: str = Field(min_length=1, max_length=50)
    content: str = Field(min_length=1, max_length=500)
    request_id: str = Field(default="", max_length=100)


def send_mail(name, content):
    host = os.getenv("SMTP_HOST", "")
    user = os.getenv("SMTP_USER", "")
    password = os.getenv("SMTP_PASSWORD", "")
    if not host or not user or not password:
        raise HTTPException(503, "邮件服务尚未配置，请直接通过邮箱联系。")
    message = EmailMessage()
    message["Subject"] = "个人网站新留言"
    message["From"] = os.getenv("SMTP_FROM", user)
    message["To"] = os.getenv("CONTACT_EMAIL", "18991739840@163.com")
    message.set_content(f"来自个人网站的私信\n\n姓名：{name}\n\n留言：\n{content}")
    # Let the mail library choose its standard SSL port so deployment scanners
    # cannot mistake a mail port for the application's listen port.
    use_ssl = os.getenv("SMTP_USE_SSL", "1").strip().lower() not in {"0", "false", "no"}
    context = ssl.create_default_context()
    if use_ssl:
        with smtplib.SMTP_SSL(host, timeout=10, context=context) as smtp:
            smtp.login(user, password)
            smtp.send_message(message)
    else:
        with smtplib.SMTP(host, timeout=10) as smtp:
            smtp.starttls(context=context)
            smtp.login(user, password)
            smtp.send_message(message)

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
    conn.execute("CREATE TABLE IF NOT EXISTS mail_deliveries (request_id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL, status TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)")
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
def add_message(data: MessageInput):
    name = data.name.strip()
    content = data.content.strip()
    if not name or not content:
        raise HTTPException(422, "名字和内容都不能为空。")
    if not all(os.getenv(key) for key in ("SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD")):
        raise HTTPException(503, "邮件服务尚未配置，请直接通过邮箱联系。")
    fingerprint = hashlib.sha256((name + "\0" + content).encode("utf-8")).hexdigest()
    request_id = data.request_id or fingerprint
    # Reserve before sending, including across workers, so retries cannot send twice.
    with delivery_lock:
        conn = get_db()
        try:
            conn.execute("BEGIN IMMEDIATE")
            previous = conn.execute("SELECT * FROM mail_deliveries WHERE request_id = ? OR (fingerprint = ? AND created_at >= datetime('now', '-5 minutes')) ORDER BY created_at DESC LIMIT 1", (request_id, fingerprint)).fetchone()
            if previous:
                if previous["fingerprint"] != fingerprint:
                    raise HTTPException(409, "提交标识已被使用，请重新打开页面后再试。")
                if previous["status"] == "sent":
                    return {"ok": True, "email_sent": True, "duplicate": True}
                raise HTTPException(409, "该留言正在处理或投递结果待确认，请勿重复提交，可直接通过邮箱联系。")
            conn.execute("INSERT INTO mail_deliveries (request_id, fingerprint, status) VALUES (?, ?, 'sending')", (request_id, fingerprint))
            conn.commit()
        finally:
            conn.close()
    try:
        send_mail(name, content)
    except Exception:
        with closing(get_db()) as conn, conn:
            conn.execute("UPDATE mail_deliveries SET status = 'unknown' WHERE request_id = ?", (request_id,))
        raise HTTPException(502, "邮件投递未能确认，请勿反复提交，可直接通过邮箱联系。")
    with closing(get_db()) as conn, conn:
        conn.execute("UPDATE mail_deliveries SET status = 'sent' WHERE request_id = ?", (request_id,))
    return {"ok": True, "email_sent": True}

@app.get("/api/messages")
def get_messages():
    # Messages are private; keep this route compatible with old deployed clients.
    return []

@app.get("/")
def root():
    return {"message": "夏瑶雯作品集后端运行中", "docs": "/docs"}
