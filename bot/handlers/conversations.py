# bot/handlers/conversations.py
import logging
import asyncio
import os
import csv
from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler, CallbackQueryHandler, MessageHandler, filters, CommandHandler
from telegram.error import Forbidden

from bot.config import ADMIN_USER_IDS, VECTOR_STORE_ID, BROADCAST_MESSAGE, WAITING_FOR_UPDATE_FILE
from bot.utils import client_openai
from bot.database import get_all_user_ids

logger = logging.getLogger(__name__)

# --- Broadcast Conversation ---
async def broadcast_start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    if query.from_user.id in ADMIN_USER_IDS:
        await query.message.reply_text("Жіберілетін хабарламаның мәтінін енгізіңіз. Бас тарту үшін /cancel деп жазыңыз.")
        return BROADCAST_MESSAGE
    return ConversationHandler.END

async def broadcast_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    message_text = update.message.text
    user_ids = get_all_user_ids()
    sent_count = 0
    failed_count = 0

    if not user_ids:
        await update.message.reply_text("Хабарлама жіберетін қолданушылар табылмады.")
        return ConversationHandler.END

    await update.message.reply_text(f"Хабарламаны {len(user_ids)} қолданушыға жіберу басталды...")

    for user_id in user_ids:
        try:
            await context.bot.send_message(chat_id=user_id, text=message_text, parse_mode='HTML')
            sent_count += 1
            await asyncio.sleep(0.1)  # Telegram лимиттеріне түспес үшін кідіріс
        except Forbidden:
            logger.warning(f"Қолданушы {user_id} ботты блоктаған, хабарлама жіберілмеді.")
            failed_count += 1
        except Exception as e:
            logger.error(f"Қолданушы {user_id} үшін хабарлама жіберуде қате: {e}")
            failed_count += 1

    await update.message.reply_text(
        f"✅ Хабарлама тарату аяқталды.\n"
        f"👍 Сәтті жіберілді: {sent_count}\n"
        f"👎 Қатемен аяқталды (немесе ботты блоктаған): {failed_count}"
    )
    return ConversationHandler.END

async def cancel_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Хабарлама жіберу тоқтатылды.")
    return ConversationHandler.END

# --- Update DB Conversation ---
async def update_db_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    if query.from_user.id in ADMIN_USER_IDS:
        await query.message.reply_text("Білім қорын жаңарту үшін файлды жіберіңіз.\nТоқтату үшін: /cancel")
        return WAITING_FOR_UPDATE_FILE
    return ConversationHandler.END

async def update_db_receive_file(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    message = update.message
    if not VECTOR_STORE_ID:
        await message.reply_text("Қате: .env файлында VECTOR_STORE_ID орнатылмаған!")
        return ConversationHandler.END

    waiting_message = await message.reply_text("Файлды өңдеуде...")
    try:
        doc = message.document
        if not doc:
            await waiting_message.edit_text("Файлды документ ретінде жіберіңіз.")
            return ConversationHandler.END

        doc_file = await doc.get_file()
        file_content = await doc_file.download_as_bytearray()

        await waiting_message.edit_text("Файл жүктелді. OpenAI-ға жіберілуде...")
        
        openai_file = await client_openai.files.create(file=(doc.file_name, file_content), purpose="assistants")
        
        await waiting_message.edit_text(f"Файл OpenAI-ға жүктелді (ID: {openai_file.id}). Білім қорына қосылуда...")

        await client_openai.beta.vector_stores.files.create(vector_store_id=VECTOR_STORE_ID, file_id=openai_file.id)
        
        await waiting_message.edit_text(f"🎉 '{doc.file_name}' файлы білім қорына сәтті қосылды.")
    except Exception as e:
        logger.error(f"Базаны жаңарту қатесі: {e}")
        await waiting_message.edit_text(f"❌ Файлды өңдеу кезінде қате пайда болды: {e}")
    return ConversationHandler.END

async def update_db_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Базаны жаңарту тоқтатылды.")
    return ConversationHandler.END

# --- ConversationHandlers ---
broadcast_conv_handler = ConversationHandler(
    entry_points=[CallbackQueryHandler(broadcast_start_handler, pattern='^broadcast_start$')],
    states={
        BROADCAST_MESSAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, broadcast_message_handler)]
    },
    fallbacks=[CommandHandler('cancel', cancel_broadcast)],
    per_user=True,
    conversation_timeout=20  # 20 секундтан кейін автоматты түрде тоқтайды
)

update_db_conv_handler = ConversationHandler(
    entry_points=[CallbackQueryHandler(update_db_start, pattern='^update_db_placeholder$')],
    states={
        WAITING_FOR_UPDATE_FILE: [MessageHandler(filters.Document.ALL, update_db_receive_file)]
    },
    fallbacks=[CommandHandler('cancel', update_db_cancel)],
    per_user=True
)