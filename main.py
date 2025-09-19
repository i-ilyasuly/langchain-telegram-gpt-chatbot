# main.py
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackQueryHandler
from telegram.error import RetryAfter

from bot.config import TELEGRAM_TOKEN, WEBHOOK_URL
from bot.handlers.common import start, handle_message, handle_photo
from bot.handlers.admin import button_handler
from bot.handlers.conversations import broadcast_conv_handler, update_db_conv_handler

# Негізгі баптаулар
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

application = Application.builder().token(TELEGRAM_TOKEN).build()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Хэндлерлерді тіркеу
    application.add_handler(broadcast_conv_handler)
    application.add_handler(update_db_conv_handler)
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    application.add_handler(CallbackQueryHandler(button_handler))
    
    await application.initialize()
    if WEBHOOK_URL and WEBHOOK_URL.startswith("https://"):
        await application.bot.set_webhook(url=f"{WEBHOOK_URL}/telegram", allowed_updates=Update.ALL_TYPES)
        logger.info(f"🚀 Бот Webhook режимінде іске қосылды: {WEBHOOK_URL}")
    else:
        logger.warning("ℹ️ WEBHOOK_URL жарамсыз, бот Webhook-сыз іске қосылды.")
        await application.bot.delete_webhook()
    
    yield
    
    await application.shutdown()
    logger.info("🔚 Бот тоқтатылды.")

app_fastapi = FastAPI(lifespan=lifespan)

@app_fastapi.post("/telegram")
async def telegram_webhook(request: Request):
    update = Update.de_json(await request.json(), application.bot)
    await application.process_update(update)
    return {"status": "ok"}

@app_fastapi.get("/")
def index():
    return {"message": "Telegram Bot webhook режимінде жұмыс істеп тұр."}