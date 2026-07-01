
import sqlite3
import os

# Data directory for persistence (especially for Railway Volumes)
DATA_DIR = os.getenv("DATA_DIR", "data")
DB_PATH = os.path.join(DATA_DIR, "bot_database.db")

def init_db():
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR)
        
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Table for worker accounts
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS worker_accounts (
        phone_number TEXT PRIMARY KEY,
        session_name TEXT NOT NULL,
        status TEXT DEFAULT 'active'
    )
    """)
    
    conn.commit()
    conn.close()

def add_worker(phone_number, session_name):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO worker_accounts (phone_number, session_name) VALUES (?, ?)", (phone_number, session_name))
    conn.commit()
    conn.close()

def get_all_workers():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT phone_number, session_name FROM worker_accounts")
    workers = cursor.fetchall()
    conn.close()
    return workers

def remove_worker(phone_number):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM worker_accounts WHERE phone_number = ?", (phone_number,))
    conn.commit()
    conn.close()

if __name__ == "__main__":
    init_db()
