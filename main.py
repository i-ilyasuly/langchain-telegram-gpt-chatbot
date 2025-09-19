# main.py
import logging
import httpx
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from telegram import Update, Bot
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackQueryHandler
from telegram.error import RetryAfter

from bot.config import TELEGRAM_TOKEN, WEBHOOK_URL
from bot.handlers.common import start, handle_message, handle_photo
from bot.handlers.admin import button_handler
from bot.handlers.conversations import broadcast_conv_handler, update_db_conv_handler

# Негізгі баптаулар
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Application-ды глобалды түрде құру, бірақ инициализацияны кейінге қалдыру
application = Application.builder().token(TELEGRAM_TOKEN).build()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Webhook-ты тек бір рет орнату
    # Бұл код gunicorn-ның негізгі процесінде ғана орындалуы керек, бірақ оны анықтау қиын.
    # Сондықтан, webhook-ты бөлек скриптпен орнатуға немесе осында қалдырып,
    # gunicorn жұмысшыларының санын 1-ге дейін азайтуға болады.
    # Ең дұрысы - webhook-ты бөлек орнатып алу.
    # Бірақ қазіргі жағдайды түзету үшін webhook-ты орнату кезінде қателерді ұстап аламыз.

    # Хэндлерлерді тіркеу
    application.add_handler(broadcast_conv_handler)
    application.add_handler(update_db_conv_handler)
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    application.add_handler(CallbackQueryHandler(button_handler))
    
    await application.initialize()
    if WEBHOOK_URL:
        try:
            # Webhook-ты орнату үшін Bot-ты бөлек инициализациялау
            bot = Bot(token=TELEGRAM_TOKEN)
            webhook_url_with_path = f"{WEBHOOK_URL}/telegram"
            
            # Ағымдағы webhook ақпаратын алу
            current_webhook_info = await bot.get_webhook_info()

            # Егер webhook URL басқа болса ғана жаңарту
            if current_webhook_info.url != webhook_url_with_path:
                await bot.set_webhook(url=webhook_url_with_path, allowed_updates=Update.ALL_TYPES)
                logger.info(f"🚀 Webhook сәтті орнатылды: {webhook_url_with_path}")
            else:
                logger.info(f"ℹ️ Webhook қазірдің өзінде дұрыс орнатылған: {webhook_url_with_path}")

        except RetryAfter as e:
            logger.warning(f"Webhook орнату кезінде Flood control қатесі: {e}. Бұл gunicorn-ның бірнеше жұмысшысымен қалыпты жағдай.")
        except Exception as e:
            logger.error(f"Webhook орнату кезінде белгісіз қате: {e}")
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