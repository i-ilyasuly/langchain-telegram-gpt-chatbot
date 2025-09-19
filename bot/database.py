# database.py

import sqlite3
import os
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

# Render Disk-тегі ортақ директория (егер бар болса) немесе жергілікті директория
DATA_DIR = os.getenv("RENDER_DISK_MOUNT_PATH", ".") # Render Disk болмаса, ағымдағы директорияны қолдану
DB_FILE = os.path.join(DATA_DIR, "bot_users.db")

def init_db():
    """Дерекқорды және 'users' кестесін жасайды (егер олар жоқ болса)."""
    os.makedirs(DATA_DIR, exist_ok=True)
    
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        full_name TEXT,
        username TEXT,
        language_code TEXT,
        is_premium INTEGER DEFAULT 0,
        subscription_end_date TEXT,
        created_at TEXT NOT NULL
    )
    ''')
    
    conn.commit()
    conn.close()

def add_or_update_user(user_id, full_name, username, language_code):
    """Жаңа қолданушыны қосады немесе ескісінің мәліметін жаңартады."""
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        
        cursor.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
        existing_user = cursor.fetchone()
        
        current_time = datetime.now().isoformat()

        if existing_user:
            cursor.execute('''
            UPDATE users 
            SET full_name = ?, username = ?, language_code = ?
            WHERE user_id = ?
            ''', (full_name, username, language_code, user_id))
        else:
            cursor.execute('''
            INSERT INTO users (user_id, full_name, username, language_code, created_at)
            VALUES (?, ?, ?, ?, ?)
            ''', (user_id, full_name, username, language_code, current_time))
            
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Дерекқорда қолданушыны қосу/жаңарту кезінде қате: {e}")


def get_user_count():
    """Дерекқордағы жалпы қолданушылар санын қайтарады."""
    if not os.path.exists(DB_FILE):
        return 0
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM users")
        count = cursor.fetchone()[0]
        conn.close()
        return count
    except Exception as e:
        logger.error(f"Қолданушылар санын алу кезінде қате: {e}")
        return 0

# Ең бірінші рет импортталғанда дерекқорды дайындау
init_db()