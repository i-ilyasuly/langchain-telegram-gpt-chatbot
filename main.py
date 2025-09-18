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

# --- GOOGLE CREDENTIALS ҮШІН ШЕШІМ ---
gcp_credentials_json_str = os.getenv('GOOGLE_APPLICATION_CREDENTIALS')
if gcp_credentials_json_str:
    try:
        json.loads(gcp_credentials_json_str)
        creds_path = "/tmp/gcp_creds.json"
        with open(creds_path, "w") as f:
            f.write(gcp_credentials_json_str)
        os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = creds_path
        logger.info("Google Cloud үшін уақытша credential файлы сәтті жасалды.")
    except Exception as e:
        logger.error(f"Google credential файлын өңдеу кезінде қате: {e}")

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

# --- Тұрақтылар ---
ADMIN_USER_IDS = [929307596]
USER_IDS_FILE = "user_ids.csv"
BROADCAST_MESSAGE = range(1)
WAITING_MESSAGES = [
    "⏳ Талдап жатырмын...", "🤔 Іздеп жатырмын...", "🔎 Аз қалды...",
    "✍️ Жауапты дайындап жатырмын...", "✨ Міне-міне, дайын болады..."
]

# API клиенттерін инициализациялау
client_openai = AsyncOpenAI(api_key=OPENAI_API_KEY)
client_vision = vision.ImageAnnotatorClient()

# --- БОТ ФУНКЦИЯЛАРЫ ---
def add_user_info(user):
    user_id = user.id
    full_name = user.full_name
    username = user.username or "N/A"
    lang_code = user.language_code or "N/A"
    try:
        user_ids = set()
        file_exists = os.path.exists(USER_IDS_FILE)
        if file_exists and os.path.getsize(USER_IDS_FILE) > 0:
            with open(USER_IDS_FILE, 'r', newline='', encoding='utf-8') as f:
                reader = csv.reader(f)
                try:
                    next(reader, None)
                    user_ids = {int(row[0]) for row in reader if row}
                except (ValueError, IndexError): pass
        if user_id not in user_ids:
            with open(USER_IDS_FILE, 'a', newline='', encoding='utf-8') as f:
                fieldnames = ['user_id', 'full_name', 'username', 'language_code']
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                if not file_exists or os.path.getsize(USER_IDS_FILE) == 0:
                    writer.writeheader()
                writer.writerow({'user_id': user_id, 'full_name': full_name, 'username': username, 'language_code': lang_code})
    except Exception as e:
        logger.error(f"Қолданушы ақпаратын сақтау кезінде қате: {e}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    add_user_info(user)
    context.user_data.pop('thread_id', None)
    keyboard = [[InlineKeyboardButton("📝 Мәтінмен сұрау", callback_data='ask_text')], [InlineKeyboardButton("📸 Суретпен талдау", callback_data='ask_photo')]]
    if user.id in ADMIN_USER_IDS:
        keyboard.append([InlineKeyboardButton("🔐 Админ панелі", callback_data='admin_panel')])
    reply_markup = InlineKeyboardMarkup(keyboard)
    welcome_text = "Assalamualaikum! Төмендегі батырмалар арқылы қажетті әрекетті таңдаңыз немесе сұрағыңызды жаза беріңіз:"
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
    await update.callback_query.message.reply_text("Статистика функциясы әзірленуде.")

async def suspicious_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.message.reply_text("Күдікті тізім функциясы әзірленуде.")

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
    file_exists = os.path.isfile('feedback.csv')
    with open('feedback.csv', 'a', newline='', encoding='utf-8') as csvfile:
        fieldnames = ['timestamp', 'user_id', 'question', 'bot_answer', 'vote']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        if not file_exists: writer.writeheader()
        writer.writerow({'timestamp': timestamp, 'user_id': user_id, 'question': question, 'bot_answer': bot_answer, 'vote': vote})
    logger.info(f"Кері байланыс 'feedback.csv' файлына сақталды: User {user_id} '{vote}' деп басты.")

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    if query.data == 'ask_text':
        await query.message.reply_text("Тексергіңіз келетін өнімнің, мекеменің немесе E-қоспаның атауын жазыңыз.")
    elif query.data == 'ask_photo':
        await query.message.reply_text("Талдау үшін өнімнің немесе оның құрамының суретін жіберіңіз.")
    elif query.data == 'admin_panel':
        if user_id in ADMIN_USER_IDS:
            admin_keyboard = [
                [InlineKeyboardButton("📊 Статистиканы көру", callback_data='feedback_stats')],
                [InlineKeyboardButton("🧐 Күдікті тізім", callback_data='suspicious_list')],
                [InlineKeyboardButton("📬 Хабарлама жіберу", callback_data='broadcast_start')],
                [InlineKeyboardButton("🔄 Базаны жаңарту", callback_data='update_db_placeholder')]
            ]
            reply_markup = InlineKeyboardMarkup(admin_keyboard)
            await query.message.reply_text("🔐 Админ панелі:", reply_markup=reply_markup)
    elif query.data == 'feedback_stats':
        if user_id in ADMIN_USER_IDS:
            await feedback_stats(update, context)
    elif query.data == 'suspicious_list':
        if user_id in ADMIN_USER_IDS:
            await suspicious_list(update, context)
    elif query.data == 'update_db_placeholder':
        if user_id in ADMIN_USER_IDS:
            await query.message.reply_text("ℹ️ Бұл функция әзірге жасалу үстінде.")
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
    keyboard = [[InlineKeyboardButton("👍", callback_data='like'), InlineKeyboardButton("👎", callback_data='dislike')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    user_query = update.message.text.strip()
    
    waiting_message = await update.message.reply_text(random.choice(WAITING_MESSAGES))
    
    try:
        thread_id = context.user_data.get('thread_id')
        response_text, new_thread_id, run = await run_openai_assistant(user_query, thread_id)
        
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
                except Exception:
                    pass
            run = await client_openai.beta.threads.runs.retrieve(thread_id=new_thread_id, run_id=run.id)
        
        if run.status == 'completed':
            messages = await client_openai.beta.threads.messages.list(thread_id=new_thread_id, limit=1)
            final_response = messages.data[0].content[0].text.value
            cleaned_response = re.sub(r'【.*?†source】', '', final_response).strip()
            
            await waiting_message.edit_text(cleaned_response, reply_markup=reply_markup)
            
            context.user_data[f'last_question_{waiting_message.message_id}'] = user_query
            context.user_data[f'last_answer_{waiting_message.message_id}'] = cleaned_response
        else:
            error_message = run.last_error.message if run.last_error else 'Белгісіз қате'
            await waiting_message.edit_text(f"Ассистент жұмысында қате: {error_message}")
            
    except Exception as e:
        logger.error(f"Хабарламаны өңдеу қатесі: {e}")
        await waiting_message.edit_text("Жауап алу кезінде қате шықты.")

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
        
        await waiting_message.edit_text("✅ Сурет талданды! Енді OpenAI арқылы ақпарат іздеп жатырмын...")
        
        final_query_to_openai = (
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
                except Exception:
                    pass
            run = await client_openai.beta.threads.runs.retrieve(thread_id=new_thread_id, run_id=run.id)
        
        if run.status == 'completed':
            messages = await client_openai.beta.threads.messages.list(thread_id=new_thread_id, limit=1)
            final_response = messages.data[0].content[0].text.value
            cleaned_response = re.sub(r'【.*?†source】', '', final_response).strip()
            
            await waiting_message.edit_text(cleaned_response, reply_markup=reply_markup)

            context.user_data[f'last_question_{waiting_message.message_id}'] = f"Image Query: {image_description}"
            context.user_data[f'last_answer_{waiting_message.message_id}'] = cleaned_response
        else:
            error_message = run.last_error.message if run.last_error else 'Белгісіз қате'
            await waiting_message.edit_text(f"Ассистент жұмысында қате: {error_message}")
        
    except Exception as e:
        logger.error(f"Суретті өңдеу қатесі: {e}")
        await waiting_message.edit_text("Суретті өңдеу кезінде қате шықты. Қайталап көріңіз.")

# --- Веб-серверді баптау ---
application = Application.builder().token(TELEGRAM_TOKEN).build()
app_fastapi = FastAPI()

@app_fastapi.on_event("startup")
async def startup_event():
    conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(broadcast_start_handler, pattern='^broadcast_start$')],
        states={BROADCAST_MESSAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, broadcast_message_handler)]},
        fallbacks=[CommandHandler('cancel', cancel_broadcast)],
        per_user=True,
    )
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(conv_handler)
    
    await application.initialize()

    if WEBHOOK_URL and WEBHOOK_URL.startswith("https://"):
        try:
            await application.bot.set_webhook(
                url=f"{WEBHOOK_URL}/telegram",
                allowed_updates=Update.ALL_TYPES
            )
            logger.info(f"🚀 Бот Webhook режимінде іске қосылды: {WEBHOOK_URL}")
        except RetryAfter as e:
            logger.warning(f"Webhook орнату кезінде Flood control қатесі: {e}. Басқа жұмысшы орнатқан болуы мүмкін. Жұмысты жалғастырудамыз.")
        except Exception as e:
            logger.error(f"Webhook орнату кезінде белгісіз қате: {e}")
            
    else:
        logger.warning("ℹ️ WEBHOOK_URL жарамсыз немесе көрсетілмеген. Бот Webhook-сыз іске қосылды.")
        await application.bot.delete_webhook()

@app_fastapi.on_event("shutdown")
async def shutdown_event():
    await application.shutdown()
    logger.info("🔚 Бот тоқтатылды.")

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
    logger.info("uvicorn main:app_fastapi --reload")