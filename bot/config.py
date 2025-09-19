# bot/config.py
import os
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
OPENAI_ASSISTANT_ID = os.getenv('OPENAI_ASSISTANT_ID')
WEBHOOK_URL = os.getenv('WEBHOOK_URL')
VECTOR_STORE_ID = os.getenv('VECTOR_STORE_ID')

# ADMIN_IDS .env файлынан алынады, егер жоқ болса, стандартты ID қолданылады
ADMIN_IDS_STR = os.getenv('ADMIN_IDS', '929307596')
ADMIN_USER_IDS = [int(admin_id.strip()) for admin_id in ADMIN_IDS_STR.split('929307596') if admin_id.strip()]

# Render Disk
DATA_DIR = os.getenv("RENDER_DISK_MOUNT_PATH", ".")
FEEDBACK_FILE = os.path.join(DATA_DIR, "feedback.csv")
SUSPICIOUS_LOG_FILE = os.path.join(DATA_DIR, "suspicious_products.csv")
USER_IDS_FILE = os.path.join(DATA_DIR, "user_ids.csv") # Бұл енді қолданылмайды, бірақ қауіпсіздік үшін қалдырамыз

# Conversation States
BROADCAST_MESSAGE = 0
WAITING_FOR_UPDATE_FILE = 1

WAITING_MESSAGES = [
    "⏳ Талдап жатырмын...", "🤔 Іздеп жатырмын...", "🔎 Аз қалды...",
    "✍️ Жауапты дайындап жатырмын...", "✨ Міне-міне, дайын болады..."
]