import sqlite3
import os
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

DATA_DIR = os.getenv("RENDER_DISK_MOUNT_PATH", ".")
DB_FILE = os.path.join(DATA_DIR, "bot_users.db")

def _run_migrations(conn):
    """Дерекқор кестесіне жетіспейтін бағандарды қосады."""
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(users)")
    columns = [info[1] for info in cursor.fetchall()]

    new_columns = {
        "text_requests_count": "INTEGER DEFAULT 0",
        "photo_requests_count": "INTEGER DEFAULT 0",
        "last_request_date": "TEXT",
        "openai_thread_id": "TEXT",
        "last_question": "TEXT",
        "last_answer": "TEXT"
    }

    for col_name, col_type in new_columns.items():
        if col_name not in columns:
            cursor.execute(f"ALTER TABLE users ADD COLUMN {col_name} {col_type}")
            logger.info(f"`{col_name}` бағаны қосылды.")
    conn.commit()

def init_db():
    """Дерекқорды және 'users' кестесін жасайды."""
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
    _run_migrations(conn)
    conn.close()

def add_or_update_user(user_id, full_name, username, language_code):
    """Жаңа қолданушыны қосады немесе ескісінің мәліметін жаңартады."""
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
        if cursor.fetchone():
            cursor.execute("UPDATE users SET full_name = ?, username = ? WHERE user_id = ?", (full_name, username, user_id))
        else:
            cursor.execute(
                "INSERT INTO users (user_id, full_name, username, language_code, created_at) VALUES (?, ?, ?, ?, ?)",
                (user_id, full_name, username, language_code, datetime.now().isoformat())
            )
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Қолданушыны қосу/жаңарту кезінде қате: {e}")

def get_user_language(user_id: int) -> str:
    """Қолданушының сақталған тіл кодын қайтарады."""
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT language_code FROM users WHERE user_id = ?", (user_id,))
        result = cursor.fetchone()
        conn.close()
        return result[0] if result and result[0] else 'kk'
    except Exception:
        return 'kk'
        
def check_and_increment_usage(user_id: int, request_type: str, limit: int) -> bool:
    """Лимитті тексереді және жетпесе, санауышты арттырады. Лимиттен асса, False қайтарады."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    try:
        today_str = datetime.now().strftime("%Y-%m-%d")
        cursor.execute("SELECT text_requests_count, photo_requests_count, last_request_date FROM users WHERE user_id = ?", (user_id,))
        usage = cursor.fetchone()

        text_count, photo_count, last_date = usage if usage else (0, 0, None)

        if last_date != today_str:
            cursor.execute("UPDATE users SET text_requests_count = 0, photo_requests_count = 0, last_request_date = ? WHERE user_id = ?", (today_str, user_id))
            text_count, photo_count = 0, 0

        can_proceed = False
        field_to_update = None
        if request_type == 'text' and text_count < limit:
            can_proceed = True
            field_to_update = "text_requests_count"
        elif request_type == 'photo' and photo_count < limit:
            can_proceed = True
            field_to_update = "photo_requests_count"

        if can_proceed:
            cursor.execute(f"UPDATE users SET {field_to_update} = {field_to_update} + 1 WHERE user_id = ?", (user_id,))
        
        conn.commit()
        return can_proceed
    except Exception as e:
        logger.error(f"Лимитті тексеру/арттыру кезінде қате: {e}")
        return False
    finally:
        conn.close()

def set_last_q_and_a(user_id: int, question: str, answer: str):
    """Қолданушының соңғы сұрағы мен жауабын дерекқорға сақтайды."""
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET last_question = ?, last_answer = ? WHERE user_id = ?", (question, answer, user_id))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Соңғы сұрақ-жауапты сақтауда қате: {e}")

def get_last_q_and_a(user_id: int) -> tuple[str, str]:
    """Қолданушының соңғы сұрағы мен жауабын дерекқордан алады."""
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT last_question, last_answer FROM users WHERE user_id = ?", (user_id,))
        result = cursor.fetchone()
        conn.close()
        return result if result else ("Сұрақ табылмады", "Жауап табылмады")
    except Exception as e:
        logger.error(f"Соңғы сұрақ-жауапты алуда қате: {e}")
        return ("Сұрақ табылмады", "Жауап табылмады")


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
            
        end_date = datetime.fromisoformat(end_date_str)
        if end_date > datetime.now():
            return True
            
    except Exception as e:
        logger.error(f"Премиум статусын тексеру кезінде қате (user_id: {user_id}): {e}")
    return False

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

# Ең бірінші рет импортталғанда дерекқорды дайындау
init_db()