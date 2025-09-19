# bot/handlers/conversations.py
import logging
import asyncio
import os
from telegram import Update, ReplyKeyboardRemove
from telegram.ext import ContextTypes, ConversationHandler

from bot.config import ADMIN_USER_IDS, VECTOR_STORE_ID, BROADCAST_MESSAGE, WAITING_FOR_UPDATE_FILE
from bot.utils import client_openai
from bot.database import get_user_count # get_all_user_ids керек болады

logger = logging.getLogger(__name__)

# --- Broadcast Conversation ---
async def broadcast_start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.from_user.id in ADMIN_USER_IDS:
        await query.message.reply_text("Жіберілетін хабарламаның мәтінін енгізіңіз:")
        return BROADCAST_MESSAGE
    return ConversationHandler.END

async def broadcast_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Бұл функцияны database.py-дан барлық user_id алу үшін өзгерту керек
    await update.message.reply_text("Бұл функция дерекқорға бейімделуі керек.")
    return ConversationHandler.END

async def cancel_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Хабарлама жіберу тоқтатылды.")
    return ConversationHandler.END

# --- Update DB Conversation ---
async def update_db_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.from_user.id in ADMIN_USER_IDS:
        await query.message.reply_text("Білім қорын жаңарту үшін файлды жіберіңіз.\nТоқтату: /cancel")
        return WAITING_FOR_UPDATE_FILE
    return ConversationHandler.END

async def update_db_receive_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not VECTOR_STORE_ID:
        await message.reply_text("Қате: VECTOR_STORE_ID орнатылмаған!")
        return ConversationHandler.END
    
    waiting_message = await message.reply_text("Файлды өңдеуде...")
    try:
        doc_file = await message.document.get_file()
        file_content = await doc_file.download_as_bytearray()
        
        openai_file = await client_openai.files.create(file=(message.document.file_name, file_content), purpose="assistants")
        await waiting_message.edit_text(f"Файл OpenAI-ға жүктелді (ID: {openai_file.id}). Білім қорына қосылуда...")
        
        await client_openai.beta.vector_stores.files.create(vector_store_id=VECTOR_STORE_ID, file_id=openai_file.id)
        await waiting_message.edit_text(f"🎉 '{message.document.file_name}' файлы білім қорына сәтті қосылды.")
    except Exception as e:
        logger.error(f"Базаны жаңарту қатесі: {e}")
        await waiting_message.edit_text(f"❌ Қате: {e}")
    return ConversationHandler.END

async def update_db_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Базаны жаңарту тоқтатылды.")
    return ConversationHandler.END

# --- ConversationHandlers ---
broadcast_conv_handler = ConversationHandler(
    entry_points=[CallbackQueryHandler(broadcast_start_handler, pattern='^broadcast_start$')],
    states={BROADCAST_MESSAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, broadcast_message_handler)]},
    fallbacks=[CommandHandler('cancel', cancel_broadcast)], per_user=True
)

update_db_conv_handler = ConversationHandler(
    entry_points=[CallbackQueryHandler(update_db_start, pattern='^update_db_placeholder$')],
    states={WAITING_FOR_UPDATE_FILE: [MessageHandler(filters.Document.ALL, update_db_receive_file)]},
    fallbacks=[CommandHandler('cancel', update_db_cancel)], per_user=True
)