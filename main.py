import logging
from warnings import filterwarnings
import asyncio

from dotenv import load_dotenv
from telegram import Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    filters,
    ContextTypes,
)
from telegram.warnings import PTBUserWarning
from fastapi import FastAPI, Request

# Конфигурацияны импорттау
from bot import config

# Хэндлерлерді импорттау
from bot.handlers.admin import button_handler, grant_premium, revoke_premium
from bot.handlers.common import error_handle, premium_info, handle_message, handle_photo, language_command, start
from bot.handlers.conversations import (
    broadcast_conv_handler,
    update_db_conv_handler,
)
from bot.handlers.location_handler import location_handler


# Логгингті баптау
filterwarnings(
    action="ignore", message=r".*CallbackQueryHandler", category=PTBUserWarning
)
load_dotenv()
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# FastAPI экземплярын құру
app_fastapi = FastAPI()

# --- TELEGRAM BOT SETUP ---
application = Application.builder().token(config.TELEGRAM_TOKEN).build()

# 1. Жалпы командалар
application.add_handler(CommandHandler("start", start))
application.add_handler(CommandHandler("premium", premium_info))
application.add_handler(CommandHandler("language", language_command))

# 2. Админ командалары
application.add_handler(CommandHandler("grant_premium", grant_premium))
application.add_handler(CommandHandler("revoke_premium", revoke_premium))

# 3. Түймелерді өңдеу
application.add_handler(CallbackQueryHandler(button_handler))

# 4. Диалогтар (Broadcast, DB Update)
application.add_handler(broadcast_conv_handler)
application.add_handler(update_db_conv_handler)

# 5. Негізгі хэндлерлер (мәтін, фото, локация)
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
application.add_handler(MessageHandler(filters.LOCATION, location_handler))

# 6. Қателерді өңдеу
application.add_error_handler(error_handle)


# --- WEBHOOK SETUP ---
@app_fastapi.on_event("startup")
async def startup():
    """Webhook орнату."""
    await application.bot.set_webhook(url=f"{config.WEBHOOK_URL}/telegram")
    logger.info(f"Webhook {config.WEBHOOK_URL} адресіне орнатылды")


@app_fastapi.post("/telegram")
async def telegram_webhook(request: Request):
    """Telegram-нан келетін жаңартуларды өңдейді."""
    await application.update_queue.put(
        Update.de_json(await request.json(), application.bot)
    )
    return {"ok": True}


@app_fastapi.get("/")
def index():
    return {"message": "Bot is running..."}

# Ботты polling режимінде жергілікті тестілеу үшін
async def main_polling():
    """Ботты polling режимінде іске қосады."""
    logger.info("Polling режимінде іске қосылуда...")
    await application.initialize()
    await application.updater.start_polling()
    await application.start()
    logger.info("Бот polling режимінде жұмыс істеп тұр.")

if __name__ == "__main__":
    # Жергілікті тестілеу үшін осы блокты іске қосыңыз
    # Render сияқты серверге жүктегенде бұл код орындалмайды
    # asyncio.run(main_polling())
    pass