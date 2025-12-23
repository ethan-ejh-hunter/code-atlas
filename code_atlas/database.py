
import sqlite3
import os

DB_PATH = "code_atlas.db"

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as conn:
        # Files table: Index of all files
        conn.execute("""
            CREATE TABLE IF NOT EXISTS files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                path TEXT UNIQUE NOT NULL,
                filename TEXT NOT NULL,
                file_type TEXT,
                encoding TEXT
            )
        """)
        
        # Annotations table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS annotations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_id INTEGER NOT NULL,
                line_number INTEGER,
                content TEXT,
                author TEXT,
                type TEXT, -- 'manual', 'translation', 'tool_output'
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(file_id) REFERENCES files(id)
            )
        """)
        
        # Performance Index
        conn.execute("CREATE INDEX IF NOT EXISTS idx_filename ON files(filename)")
        
        conn.commit()
    print("Database initialized.")

def get_file_id(path):
    with get_db() as conn:
        cur = conn.execute("SELECT id FROM files WHERE path = ?", (path,))
        row = cur.fetchone()
        if row:
            return row['id']
    return None

def add_file(path, filename, file_type=None, encoding=None):
    with get_db() as conn:
        try:
            cur = conn.execute(
                "INSERT INTO files (path, filename, file_type, encoding) VALUES (?, ?, ?, ?)",
                (path, filename, file_type, encoding)
            )
            return cur.lastrowid
        except sqlite3.IntegrityError:
            return get_file_id(path)
