# database.py

import sqlite3
import os
from datetime import datetime
import logging
from datetime import datetime, timedelta

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

def get_all_user_ids():
    """Дерекқордағы барлық қолданушылардың ID тізімін қайтарады."""
    if not os.path.exists(DB_FILE):
        return []
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT user_id FROM users")
        user_ids = [row[0] for row in cursor.fetchall()]
        conn.close()
        return user_ids
    except Exception as e:
        logger.error(f"Барлық қолданушы ID-ларын алу кезінде қате: {e}")
        return []
def is_user_premium(user_id: int) -> bool:
    """Қолданушының жарамды премиум жазылымы бар-жоғын тексереді."""
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        
        cursor.execute("SELECT is_premium, subscription_end_date FROM users WHERE user_id = ?", (user_id,))
        user_data = cursor.fetchone()
        conn.close()
        
        if not user_data:
            return False
            
        is_premium, end_date_str = user_data
        
        if not is_premium or not end_date_str:
            return False
            
        # Жазылымның аяқталу күнін бүгінгі күнмен салыстыру
        end_date = datetime.fromisoformat(end_date_str)
        if end_date > datetime.now():
            return True # Жазылым жарамды
            
    except Exception as e:
        logger.error(f"Премиум статусын тексеру кезінде қате (user_id: {user_id}): {e}")
        return False
        
    return False # Жазылым мерзімі өтіп кеткен немесе басқа қате
def grant_premium_access(user_id: int, days: int):
    """Қолданушыға белгілі бір күнге премиум жазылым береді."""
    end_date = datetime.now() + timedelta(days=days)
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE users SET is_premium = 1, subscription_end_date = ? WHERE user_id = ?",
            (end_date.isoformat(), user_id)
        )
        conn.commit()
        conn.close()
        logger.info(f"{user_id} қолданушысына {days} күнге премиум берілді.")
    except Exception as e:
        logger.error(f"Премиум беру кезінде қате (user_id: {user_id}): {e}")

def revoke_premium_access(user_id: int):
    """Қолданушының премиум жазылымын тоқтатады."""
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE users SET is_premium = 0, subscription_end_date = NULL WHERE user_id = ?",
            (user_id,)
        )
        conn.commit()
        conn.close()
        logger.info(f"{user_id} қолданушысының премиум жазылымы тоқтатылды.")
    except Exception as e:
        logger.error(f"Премиумды тоқтату кезінде қате (user_id: {user_id}): {e}")
# Ең бірінші рет импортталғанда дерекқорды дайындау
init_db()