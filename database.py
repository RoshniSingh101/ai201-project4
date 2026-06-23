import sqlite3
import json
import datetime
from pathlib import Path

DEFAULT_DB_PATH = "provenance_guard.db"

def resolve_db_path(db_path):
    return db_path if db_path is not None else DEFAULT_DB_PATH

def get_db_connection(db_path=None):
    path = resolve_db_path(db_path)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn

def init_db(db_path=None):
    path = resolve_db_path(db_path)
    conn = get_db_connection(path)
    cursor = conn.cursor()
    
    # Submissions Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS submissions (
            content_id TEXT PRIMARY KEY,
            creator_id TEXT NOT NULL,
            text TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            llm_score REAL,
            stylometric_score REAL,
            combined_score REAL,
            attribution TEXT NOT NULL,
            confidence REAL NOT NULL,
            label TEXT NOT NULL,
            status TEXT NOT NULL,
            appeal_reasoning TEXT
        )
    """)
    
    # Audit Log Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS audit_log (
            log_id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            content_id TEXT NOT NULL,
            event_type TEXT NOT NULL,
            creator_id TEXT,
            attribution TEXT,
            confidence REAL,
            llm_score REAL,
            stylometric_score REAL,
            combined_score REAL,
            status TEXT,
            appeal_reasoning TEXT,
            details TEXT
        )
    """)
    
    conn.commit()
    conn.close()

def save_submission(content_id, creator_id, text, llm_score, stylometric_score, 
                    combined_score, attribution, confidence, label, db_path=None):
    path = resolve_db_path(db_path)
    timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")
    status = "classified"
    
    conn = get_db_connection(path)
    cursor = conn.cursor()
    
    # Insert submission
    cursor.execute("""
        INSERT INTO submissions (
            content_id, creator_id, text, timestamp, llm_score, 
            stylometric_score, combined_score, attribution, confidence, label, status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (content_id, creator_id, text, timestamp, llm_score, 
          stylometric_score, combined_score, attribution, confidence, label, status))
    
    # Insert initial log entry
    cursor.execute("""
        INSERT INTO audit_log (
            timestamp, content_id, event_type, creator_id, attribution, 
            confidence, llm_score, stylometric_score, combined_score, status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (timestamp, content_id, "submission", creator_id, attribution, 
          confidence, llm_score, stylometric_score, combined_score, status))
    
    conn.commit()
    conn.close()
    return timestamp

def get_submission(content_id, db_path=None):
    path = resolve_db_path(db_path)
    conn = get_db_connection(path)
    cursor = conn.cursor()
    row = cursor.execute("SELECT * FROM submissions WHERE content_id = ?", (content_id,)).fetchone()
    conn.close()
    if row:
        return dict(row)
    return None

def submit_appeal(content_id, creator_reasoning, db_path=None):
    path = resolve_db_path(db_path)
    conn = get_db_connection(path)
    cursor = conn.cursor()
    
    # Fetch existing submission to log it in audit log
    row = cursor.execute("SELECT * FROM submissions WHERE content_id = ?", (content_id,)).fetchone()
    if not row:
        conn.close()
        return False
    
    sub = dict(row)
    timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")
    new_status = "under_review"
    
    # Update submission
    cursor.execute("""
        UPDATE submissions 
        SET status = ?, appeal_reasoning = ? 
        WHERE content_id = ?
    """, (new_status, creator_reasoning, content_id))
    
    # Log appeal entry
    cursor.execute("""
        INSERT INTO audit_log (
            timestamp, content_id, event_type, creator_id, attribution, 
            confidence, llm_score, stylometric_score, combined_score, status, appeal_reasoning
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (timestamp, content_id, "appeal", sub["creator_id"], sub["attribution"], 
          sub["confidence"], sub["llm_score"], sub["stylometric_score"], 
          sub["combined_score"], new_status, creator_reasoning))
    
    conn.commit()
    conn.close()
    return True

def get_audit_logs(limit=50, db_path=None):
    path = resolve_db_path(db_path)
    conn = get_db_connection(path)
    cursor = conn.cursor()
    rows = cursor.execute("""
        SELECT * FROM audit_log 
        ORDER BY log_id DESC 
        LIMIT ?
    """, (limit,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]
