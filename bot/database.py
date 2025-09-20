
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
    created_at TEXT NOT NULL,
    text_requests_count INTEGER DEFAULT 0,
    photo_requests_count INTEGER DEFAULT 0,
    last_request_date TEXT,
    openai_thread_id TEXT
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
def update_user_language(user_id: int, lang_code: str):
    """Қолданушының тіл кодын дерекқорда жаңартады."""
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE users SET language_code = ? WHERE user_id = ?",
            (lang_code, user_id)
        )
        conn.commit()
        conn.close()
        logger.info(f"{user_id} қолданушысы тілді '{lang_code}' деп өзгертті.")
    except Exception as e:
        logger.error(f"Тілді жаңарту кезінде қате (user_id: {user_id}): {e}")
       
def get_user_usage(user_id: int):
    """Қолданушының сұраныс санын және соңғы сұраныс күнін қайтарады."""
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT text_requests_count, photo_requests_count, last_request_date FROM users WHERE user_id = ?",
            (user_id,)
        )
        usage = cursor.fetchone()
        conn.close()
        return usage if usage else (0, 0, None)
    except Exception as e:
        logger.error(f"Қолданушының сұраныс санын алуда қате: {e}")
        return (0, 0, None)

def reset_user_limits(user_id: int):
    """Қолданушының лимиттерін жаңартады (күн ауысқанда)."""
    today_str = datetime.now().strftime("%Y-%m-%d")
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE users SET text_requests_count = 0, photo_requests_count = 0, last_request_date = ? WHERE user_id = ?",
            (today_str, user_id)
        )
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Қолданушы лимитін жаңартуда қате: {e}")

def increment_request_count(user_id: int, request_type: str):
    """Сұраныс санауышын біреуге арттырады ('text' немесе 'photo')."""
    field_to_update = "text_requests_count" if request_type == "text" else "photo_requests_count"
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute(
            f"UPDATE users SET {field_to_update} = {field_to_update} + 1 WHERE user_id = ?",
            (user_id,)
        )
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Сұраныс санын арттыруда қате: {e}")
def get_user_language(user_id: int) -> str:
    """Қолданушының сақталған тіл кодын қайтарады."""
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT language_code FROM users WHERE user_id = ?", (user_id,))
        result = cursor.fetchone()
        conn.close()
        # Егер тіл табылса, соны, болмаса әдепкі 'kk' тілін қайтарамыз
        return result[0] if result and result[0] else 'kk'
    except Exception:
        return 'kk'
    
def set_thread_id(user_id: int, thread_id: str | None):
    """Қолданушының OpenAI thread_id-ын сақтайды немесе тазалайды."""
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET openai_thread_id = ? WHERE user_id = ?", (thread_id, user_id))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Thread ID сақтауда қате: {e}")

def get_thread_id(user_id: int) -> str | None:
    """Қолданушының OpenAI thread_id-ын дерекқордан алады."""
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT openai_thread_id FROM users WHERE user_id = ?", (user_id,))
        result = cursor.fetchone()
        conn.close()
        return result[0] if result else None
    except Exception as e:
        logger.error(f"Thread ID алуда қате: {e}")
        return None
def set_thread_id(user_id: int, thread_id: str | None):
    """Қолданушының OpenAI thread_id-ын сақтайды немесе тазалайды."""
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET openai_thread_id = ? WHERE user_id = ?", (thread_id, user_id))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Thread ID сақтауда қате: {e}")

def get_thread_id(user_id: int) -> str | None:
    """Қолданушының OpenAI thread_id-ын дерекқордан алады."""
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT openai_thread_id FROM users WHERE user_id = ?", (user_id,))
        result = cursor.fetchone()
        conn.close()
        return result[0] if result else None
    except Exception as e:
        logger.error(f"Thread ID алуда қате: {e}")
        return None        
def _run_migrations(conn):
    """Дерекқор кестесіне жетіспейтін бағандарды қосады."""
    cursor = conn.cursor()

    # 'users' кестесінің ағымдағы бағандарын тексеру
    cursor.execute("PRAGMA table_info(users)")
    columns = [info[1] for info in cursor.fetchall()]

    # Жетіспейтін бағандарды қосу
    if 'text_requests_count' not in columns:
        cursor.execute("ALTER TABLE users ADD COLUMN text_requests_count INTEGER DEFAULT 0")
        logger.info("`text_requests_count` бағаны қосылды.")

    if 'photo_requests_count' not in columns:
        cursor.execute("ALTER TABLE users ADD COLUMN photo_requests_count INTEGER DEFAULT 0")
        logger.info("`photo_requests_count` бағаны қосылды.")

    if 'last_request_date' not in columns:
        cursor.execute("ALTER TABLE users ADD COLUMN last_request_date TEXT")
        logger.info("`last_request_date` бағаны қосылды.")

    if 'openai_thread_id' not in columns:
        cursor.execute("ALTER TABLE users ADD COLUMN openai_thread_id TEXT")
        logger.info("`openai_thread_id` бағаны қосылды.")

    conn.commit()
def init_db():
    """Дерекқорды және 'users' кестесін жасайды (егер олар жоқ болса)."""
    os.makedirs(DATA_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_FILE)

    _run_migrations(conn) # МИГРАЦИЯНЫ ОСЫ ЖЕРДЕ ІСКЕ ҚОСАМЫЗ

    cursor = conn.cursor()
# Ең бірінші рет импортталғанда дерекқорды дайындау
init_db()