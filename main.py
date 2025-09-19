# main.py

import os
import asyncio
import re
import random
import csv
from datetime import datetime
import logging
import json 
from dotenv import load_dotenv
import pandas as pd
from contextlib import asynccontextmanager

# --- Жаңа дерекқор функцияларын импорттау ---
from database import add_or_update_user, get_user_count

# --- Негізгі баптаулар ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- API кілттерді және баптауларды жүктеу ---
load_dotenv()
TELEGRAM_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
OPENAI_ASSISTANT_ID = os.getenv('OPENAI_ASSISTANT_ID')
WEBHOOK_URL = os.getenv('WEBHOOK_URL')
VECTOR_STORE_ID = os.getenv('VECTOR_STORE_ID')

import uvicorn
from fastapi import FastAPI, Request
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardRemove
from telegram.error import RetryAfter
from telegram.ext import (
    Application, CommandHandler, MessageHandler, filters, ContextTypes, 
    CallbackQueryHandler, ConversationHandler,
)
import openai
from openai import AsyncOpenAI
from google.cloud import vision

# --- Көптілділікті басқару ---
translations = {}
def load_translations():
    global translations
    try:
        with open('locales.json', 'r', encoding='utf-8') as f:
            translations = json.load(f)
        logger.info("Аудармалар сәтті жүктелді.")
    except FileNotFoundError:
        logger.error("Аударма файлы (locales.json) табылмады.")
        translations = {}
    except json.JSONDecodeError:
        logger.error("locales.json файлының форматы дұрыс емес.")
        translations = {}
load_translations()

def get_text(key, lang_code='kk'):
    lang = 'ru' if lang_code == 'ru' else 'kk'
    return translations.get(lang, {}).get(key, translations.get('kk', {}).get(key, f"<{key}>"))

def get_language_instruction(lang_code='kk'):
    if lang_code == 'ru':
        return "Маңызды ереже: жауабыңды орыс тілінде қайтар. "
    return "Маңызды ереже: жауабыңды қазақ тілінде қайтар. "

# --- Тұрақтылар ---
DATA_DIR = os.getenv("RENDER_DISK_MOUNT_PATH", ".")
ADMIN_USER_IDS = [929307596]
SUSPICIOUS_LOG_FILE = os.path.join(DATA_DIR, "suspicious_products.csv")
FEEDBACK_FILE = os.path.join(DATA_DIR, "feedback.csv")
BROADCAST_MESSAGE = range(1)
WAITING_FOR_UPDATE_FILE = range(2)
WAITING_MESSAGES = [
    "⏳ Талдап жатырмын...", "🤔 Іздеп жатырмын...", "🔎 Аз қалды...",
    "✍️ Жауапты дайындап жатырмын...", "✨ Міне-міне, дайын болады..."
]

# --- API клиенттері ---
client_openai = AsyncOpenAI(api_key=OPENAI_API_KEY)
client_vision = vision.ImageAnnotatorClient()

# --- БОТ ФУНКЦИЯЛАРЫ ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    add_or_update_user(user.id, user.full_name, user.username, user.language_code)
    context.user_data.pop('thread_id', None)
    lang_code = user.language_code
    keyboard = [
        [InlineKeyboardButton(get_text('ask_text_button', lang_code), callback_data='ask_text')],
        [InlineKeyboardButton(get_text('ask_photo_button', lang_code), callback_data='ask_photo')],
    ]
    if user.id in ADMIN_USER_IDS:
        keyboard.append([InlineKeyboardButton(get_text('admin_panel_button', lang_code), callback_data='admin_panel')])
    reply_markup = InlineKeyboardMarkup(keyboard)
    welcome_text = get_text('welcome_message', lang_code)
    await update.message.reply_text(welcome_text, reply_markup=reply_markup)

async def broadcast_start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    if user_id in ADMIN_USER_IDS:
        await query.message.reply_text("Барлық қолданушыларға жіберілетін хабарламаның мәтінін енгізіңіз:")
        return BROADCAST_MESSAGE
    return ConversationHandler.END

async def broadcast_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    admin_id = update.effective_user.id
    if admin_id not in ADMIN_USER_IDS:
        return ConversationHandler.END
    message_text = update.message.text
    await update.message.reply_text(f"'{message_text}' хабарламасы барлық қолданушыларға жіберілуде...")
    user_ids = set()
    if os.path.exists(USER_IDS_FILE):
        with open(USER_IDS_FILE, 'r', newline='', encoding='utf-8') as f:
            reader = csv.reader(f)
            next(reader, None)
            user_ids = {int(row[0]) for row in reader if row}
    sent_count = 0
    failed_count = 0
    for user_id in user_ids:
        try:
            await context.bot.send_message(chat_id=user_id, text=message_text)
            sent_count += 1
            await asyncio.sleep(0.1)
        except Exception as e:
            failed_count += 1
            logger.error(f"ID {user_id} қолданушысына хабарлама жіберу сәтсіз аяқталды: {e}")
    await update.message.reply_text(f"📬 Хабарлама тарату аяқталды!\n\n✅ Жеткізілді: {sent_count}\n❌ Жеткізілмеді: {failed_count}")
    return ConversationHandler.END

async def cancel_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Хабарлама жіберу тоқтатылды.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

async def feedback_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    try:
        user_count = get_user_count()
        feedback_count = 0
        likes = 0
        dislikes = 0
        if os.path.exists(FEEDBACK_FILE):
            df = pd.read_csv(FEEDBACK_FILE)
            feedback_count = len(df)
            if 'vote' in df.columns:
                likes = df['vote'].value_counts().get('like', 0)
                dislikes = df['vote'].value_counts().get('dislike', 0)
        stats_text = (
            f"📊 **Бот Статистикасы**\n\n"
            f"👥 **Жалпы қолданушылар:** {user_count}\n"
            f"📝 **Барлық пікірлер:** {feedback_count}\n"
            f"👍 **Лайктар:** {likes}\n"
            f"👎 **Дизлайктар:** {dislikes}"
        )
        await query.message.reply_text(stats_text, parse_mode='Markdown')
    except Exception as e:
        await query.message.reply_text(f"❌ Статистиканы алу кезінде қате пайда болды: {e}")

async def suspicious_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    try:
        if not os.path.exists(SUSPICIOUS_LOG_FILE) or os.path.getsize(SUSPICIOUS_LOG_FILE) == 0:
            await query.message.reply_text("ℹ️ Күдікті өнімдер тізімі бос.")
            return
        df = pd.read_csv(SUSPICIOUS_LOG_FILE)
        if df.empty:
            await query.message.reply_text("ℹ️ Күдікті өнімдер тізімі бос.")
            return
        last_5_suspicious = df.tail(5)
        await query.message.reply_text(f"🧐 **Соңғы {len(last_5_suspicious)} күдікті өнім:**")
        for index, row in last_5_suspicious.iterrows():
            timestamp = row.get('timestamp', 'Белгісіз')
            user_id = row.get('user_id', 'Белгісіз')
            description = row.get('claude_description', 'Сипаттама жоқ')
            caption = (
                f"🗓 **Уақыты:** `{timestamp}`\n"
                f"👤 **Қолданушы ID:** `{user_id}`\n"
                f"📝 **Сипаттама:**\n{description}"
            )
            await query.message.reply_text(caption, parse_mode='Markdown')
            await asyncio.sleep(0.5)
    except FileNotFoundError:
        await query.message.reply_text(f"⚠️ `{SUSPICIOUS_LOG_FILE}` файлы табылмады.")
    except Exception as e:
        await query.message.reply_text(f"❌ Күдікті тізімді алу кезінде қате пайда болды: {e}")

async def feedback_button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("Кері байланыс үшін рахмет!")
    await query.edit_message_reply_markup(reply_markup=None)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    user_id = query.from_user.id
    vote = query.data
    message_id = query.message.message_id
    question = context.user_data.get(f'last_question_{message_id}', 'Сұрақ табылмады')
    bot_answer = context.user_data.get(f'last_answer_{message_id}', 'Жауап табылмады')
    file_exists = os.path.isfile(FEEDBACK_FILE)
    with open(FEEDBACK_FILE, 'a', newline='', encoding='utf-8') as csvfile:
        fieldnames = ['timestamp', 'user_id', 'question', 'bot_answer', 'vote']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        if not file_exists: writer.writeheader()
        writer.writerow({'timestamp': timestamp, 'user_id': user_id, 'question': question, 'bot_answer': bot_answer, 'vote': vote})
    logger.info(f"Кері байланыс '{FEEDBACK_FILE}' файлына сақталды: User {user_id} '{vote}' деп басты.")

async def update_db_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    if user_id in ADMIN_USER_IDS:
        await query.message.reply_text(
            "Білім қорын жаңарту үшін .txt, .csv, .md немесе .pdf файлын жіберіңіз.\n"
            "Тоқтату үшін /cancel командасын басыңыз."
        )
        return WAITING_FOR_UPDATE_FILE
    else:
        await query.message.reply_text("Бұл мүмкіндік тек админдерге арналған.")
        return ConversationHandler.END

async def update_db_receive_file(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    message = update.message
    document = message.document
    user_id = message.from_user.id
    if user_id not in ADMIN_USER_IDS:
        return ConversationHandler.END
    if not VECTOR_STORE_ID:
        await message.reply_text("❌ Қате: VECTOR_STORE_ID .env файлында көрсетілмеген!")
        return ConversationHandler.END
    waiting_message = await message.reply_text("⏳ Файлды қабылдадым, OpenAI-ға жүктеп жатырмын...")
    try:
        file = await document.get_file()
        file_content = await file.download_as_bytearray()
        openai_file = await client_openai.files.create(
            file=(document.file_name, file_content),
            purpose="assistants"
        )
        await waiting_message.edit_text(f"✅ Файл OpenAI-ға сәтті жүктелді (ID: {openai_file.id}).\n"
                                      f"Енді білім қорына (Vector Store) қосып жатырмын...")
        vector_store_file = await client_openai.beta.vector_stores.files.create(
            vector_store_id=VECTOR_STORE_ID,
            file_id=openai_file.id
        )
        await waiting_message.edit_text(f"🎉 Тамаша! '{document.file_name}' файлы білім қорына сәтті қосылды.")
    except Exception as e:
        logger.error(f"Базаны жаңарту кезінде қате: {e}")
        await waiting_message.edit_text(f"❌ Қате пайда болды: {e}")
    return ConversationHandler.END

async def update_db_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Базаны жаңарту тоқтатылды.")
    return ConversationHandler.END

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    user_id = user.id
    lang_code = user.language_code
    if query.data in ['ask_text', 'ask_photo', 'admin_panel']:
        await query.answer()
    if query.data == 'ask_text':
        await query.message.reply_text(get_text('ask_text_prompt', lang_code))
    elif query.data == 'ask_photo':
        await query.message.reply_text(get_text('ask_photo_prompt', lang_code))
    elif query.data == 'admin_panel':
        if user_id in ADMIN_USER_IDS:
            admin_keyboard = [
                [InlineKeyboardButton(get_text('stats_button', lang_code), callback_data='feedback_stats')],
                [InlineKeyboardButton(get_text('suspicious_list_button', lang_code), callback_data='suspicious_list')],
                [InlineKeyboardButton(get_text('broadcast_button', lang_code), callback_data='broadcast_start')],
                [InlineKeyboardButton(get_text('update_db_button', lang_code), callback_data='update_db_placeholder')]
            ]
            reply_markup = InlineKeyboardMarkup(admin_keyboard)
            await query.message.reply_text(get_text('admin_panel_title', lang_code), reply_markup=reply_markup)
    elif query.data == 'feedback_stats':
        if user_id in ADMIN_USER_IDS:
            await feedback_stats(update, context)
    elif query.data == 'suspicious_list':
        if user_id in ADMIN_USER_IDS:
            await suspicious_list(update, context)
    elif query.data in ['like', 'dislike']:
        await feedback_button_callback(update, context)

async def run_openai_assistant(user_query: str, thread_id: str | None) -> tuple[str, str, object]:
    if not OPENAI_ASSISTANT_ID: 
        return "Қате: OPENAI_ASSISTANT_ID .env файлында көрсетілмеген.", thread_id, None
    try:
        if thread_id is None:
            run = await client_openai.beta.threads.create_and_run(
                assistant_id=OPENAI_ASSISTANT_ID,
                thread={"messages": [{"role": "user", "content": user_query}]}
            )
            thread_id = run.thread_id
        else:
            await client_openai.beta.threads.messages.create(thread_id=thread_id, role="user", content=user_query)
            run = await client_openai.beta.threads.runs.create(thread_id=thread_id, assistant_id=OPENAI_ASSISTANT_ID)
        return "", thread_id, run
    except openai.APIError as e:
        logger.error(f"OpenAI API қатесі: {e}")
        return "Кешіріңіз, OpenAI сервисінде уақытша ақау пайда болды. Сәлден соң қайталап көріңіз.", thread_id, None
    except openai.RateLimitError as e:
        logger.error(f"OpenAI Rate Limit қатесі: {e}")
        return "Сұраныстар лимитінен асып кетті. Біраз уақыттан кейін қайталаңыз.", thread_id, None
    except Exception as e:
        logger.error(f"OpenAI Assistant-ты іске қосу кезінде белгісіз қате: {e}")
        return "Белгісіз қате пайда болды. Администраторға хабарласыңыз.", thread_id, None

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    lang_code = user.language_code
    user_query_original = update.message.text.strip()
    logger.info(f"User {user.id} ({user.full_name}) sent a text message: '{user_query_original}'")
    keyboard = [[InlineKeyboardButton("👍", callback_data='like'), InlineKeyboardButton("👎", callback_data='dislike')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    language_instruction = get_language_instruction(lang_code)
    user_query_for_ai = language_instruction + user_query_original
    waiting_message = await update.message.reply_text(random.choice(WAITING_MESSAGES))
    try:
        thread_id = context.user_data.get('thread_id')
        response_text, new_thread_id, run = await run_openai_assistant(user_query_for_ai, thread_id)
        if run is None:
             await waiting_message.edit_text(response_text)
             return
        context.user_data['thread_id'] = new_thread_id
        last_message_text = ""
        while run.status in ['in_progress', 'queued']:
            await asyncio.sleep(2)
            current_message_text = random.choice(WAITING_MESSAGES)
            if current_message_text != last_message_text:
                try:
                    await waiting_message.edit_text(current_message_text)
                    last_message_text = current_message_text
                except Exception: pass
            run = await client_openai.beta.threads.runs.retrieve(thread_id=new_thread_id, run_id=run.id)
        if run.status == 'completed':
            messages = await client_openai.beta.threads.messages.list(thread_id=new_thread_id, limit=1)
            final_response = messages.data[0].content[0].text.value
            cleaned_response = re.sub(r'【.*?†source】', '', final_response).strip()
            logger.info(f"Bot response for user {user.id}: '{cleaned_response[:100]}...'")
            await waiting_message.edit_text(cleaned_response, reply_markup=reply_markup)
            context.user_data[f'last_question_{waiting_message.message_id}'] = user_query_original
            context.user_data[f'last_answer_{waiting_message.message_id}'] = cleaned_response
        else:
            error_message = run.last_error.message if run.last_error else 'Белгісіз қате'
            logger.error(f"OpenAI run failed for user {user.id}. Status: {run.status}, Error: {error_message}")
            await waiting_message.edit_text(f"Ассистент жұмысында қате: {error_message}")
    except Exception as e:
        logger.error(f"Хабарламаны өңдеу қатесі (User ID: {user.id}): {e}")
        await waiting_message.edit_text("Жауап алу кезінде қате шықты.")

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    lang_code = user.language_code
    logger.info(f"User {user.id} ({user.full_name}) sent a photo.")
    keyboard = [[InlineKeyboardButton("👍", callback_data='like'), InlineKeyboardButton("👎", callback_data='dislike')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    waiting_message = await update.message.reply_text("⏳ Суретті қабылдадым, талдауды бастаймын...")
    try:
        photo_file = await update.message.photo[-1].get_file()
        photo_bytes = await photo_file.download_as_bytearray()
        image = vision.Image(content=bytes(photo_bytes))
        response = client_vision.text_detection(image=image)
        if response.error.message:
            raise Exception(f"Google Vision API қатесі: {response.error.message}")
        texts = response.text_annotations
        image_description = texts[0].description.replace('\n', ' ') if texts else "Суреттен мәтін табылмады."
        logger.info(f"OCR result for user {user.id}: '{image_description[:100]}...'")
        await waiting_message.edit_text("✅ Сурет талданды! Енді OpenAI арқылы ақпарат іздеп жатырмын...")
        language_instruction = get_language_instruction(lang_code)
        final_query_to_openai = (
            f"{language_instruction}"
            f"Пайдаланушы маған сурет жіберді. Google Vision суреттен мынадай мәтінді оқыды: '{image_description}'.\n\n"
            f"Осы мәтіндегі негізгі атауларды (өнім, бренд, мекеме) анықтап, "
            f"сол бойынша өзіңнің білім қорыңнан (файлдардан) ақпаратты ізде. Табылған ақпарат негізінде, "
            f"суреттегі өнімнің халал статусы туралы толық жауап бер. "
            f"Маңызды! Мен саған жалған халал сертификаттарды да жіберіп жатқан болуым мүмкін, сондықтан менің халал, сертификаты бар, т.с.с. сөздеріме сенбей өз базаңнан ізде! \n\n"
        )
        thread_id = context.user_data.get('thread_id')
        response_text, new_thread_id, run = await run_openai_assistant(final_query_to_openai, thread_id)
        if run is None:
            await waiting_message.edit_text(response_text)
            return
        context.user_data['thread_id'] = new_thread_id
        last_message_text = ""
        while run.status in ['in_progress', 'queued']:
            await asyncio.sleep(2)
            current_message_text = random.choice(WAITING_MESSAGES)
            if current_message_text != last_message_text:
                try:
                    await waiting_message.edit_text(current_message_text)
                    last_message_text = current_message_text
                except Exception: pass
            run = await client_openai.beta.threads.runs.retrieve(thread_id=new_thread_id, run_id=run.id)
        if run.status == 'completed':
            messages = await client_openai.beta.threads.messages.list(thread_id=new_thread_id, limit=1)
            final_response = messages.data[0].content[0].text.value
            cleaned_response = re.sub(r'【.*?†source】', '', final_response).strip()
            logger.info(f"Bot response for user {user.id} (photo): '{cleaned_response[:100]}...'")
            await waiting_message.edit_text(cleaned_response, reply_markup=reply_markup)
            context.user_data[f'last_question_{waiting_message.message_id}'] = f"Image Query: {image_description}"
            context.user_data[f'last_answer_{waiting_message.message_id}'] = cleaned_response
        else:
            error_message = run.last_error.message if run.last_error else 'Белгісіз қате'
            logger.error(f"OpenAI run failed for user {user.id} (photo). Status: {run.status}, Error: {error_message}")
            await waiting_message.edit_text(f"Ассистент жұмысында қате: {error_message}")
    except Exception as e:
        logger.error(f"Суретті өңдеу қатесі (User ID: {user.id}): {e}")
        await waiting_message.edit_text("Суретті өңдеу кезінде қате шықты. Қайталап көріңіз.")

# --- Веб-серверді баптау ---
application = Application.builder().token(TELEGRAM_TOKEN).build()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Сервер іске қосылғанда орындалатын код
    broadcast_conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(broadcast_start_handler, pattern='^broadcast_start$')],
        states={BROADCAST_MESSAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, broadcast_message_handler)]},
        fallbacks=[CommandHandler('cancel', cancel_broadcast)], per_user=True,
    )
    update_db_conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(update_db_start, pattern='^update_db_placeholder$')],
        states={WAITING_FOR_UPDATE_FILE: [MessageHandler(filters.Document.ALL, update_db_receive_file)]},
        fallbacks=[CommandHandler('cancel', update_db_cancel)], per_user=True,
    )
    application.add_handler(broadcast_conv_handler)
    application.add_handler(update_db_conv_handler)
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    application.add_handler(CallbackQueryHandler(button_handler))
    
    await application.initialize()
    if WEBHOOK_URL and WEBHOOK_URL.startswith("https://"):
        try:
            await application.bot.set_webhook(url=f"{WEBHOOK_URL}/telegram", allowed_updates=Update.ALL_TYPES)
            logger.info(f"🚀 Бот Webhook режимінде іске қосылды: {WEBHOOK_URL}")
        except RetryAfter as e:
            logger.warning(f"Webhook орнату кезінде Flood control қатесі: {e}.")
        except Exception as e:
            logger.error(f"Webhook орнату кезінде белгісіз қате: {e}")
    else:
        logger.warning("ℹ️ WEBHOOK_URL жарамсыз, бот Webhook-сыз іске қосылды.")
        await application.bot.delete_webhook()
    
    yield
    
    # Сервер тоқтағанда орындалатын код
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

if __name__ == '__main__':
    logger.info("Серверді іске қосу үшін терминалда келесі команданы орындаңыз:")
    logger.info("python3 -m uvicorn main:app_fastapi --reload")