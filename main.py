import os
import time
import base64
import csv
import pandas as pd
import re
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    Application, CommandHandler, MessageHandler, filters, ContextTypes, 
    CallbackQueryHandler, ConversationHandler
)
from openai import OpenAI
from dotenv import load_dotenv
from google.cloud import vision

# --- API кілттерді және баптауларды жүктеу ---
load_dotenv()
TELEGRAM_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
OPENAI_ASSISTANT_ID = os.getenv('OPENAI_ASSISTANT_ID')
# GOOGLE_APPLICATION_CREDENTIALS .env файлында болуы керек

# --- Админдердің ID тізімі ---
ADMIN_USER_IDS = [699335248] 
USER_IDS_FILE = "user_ids.csv"
SUSPICIOUS_LOG_FILE = "suspicious_products.csv"
IMAGES_DIR = "suspicious_images"
BROADCAST_MESSAGE = range(1)

# API клиенттерін инициализациялау
client_openai = OpenAI(api_key=OPENAI_API_KEY)
client_vision = vision.ImageAnnotatorClient()

# --- Қолданушы ақпаратын сақтау ---
def add_user_info(user):
    user_id = user.id
    full_name = user.full_name
    username = user.username or "N/A"
    lang_code = user.language_code or "N/A"
    try:
        user_ids = set()
        file_exists = os.path.exists(USER_IDS_FILE)
        if file_exists:
            with open(USER_IDS_FILE, 'r', newline='', encoding='utf-8') as f:
                reader = csv.reader(f)
                next(reader, None)
                user_ids = {int(row[0]) for row in reader if row}
        if user_id not in user_ids:
            with open(USER_IDS_FILE, 'a', newline='', encoding='utf-8') as f:
                fieldnames = ['user_id', 'full_name', 'username', 'language_code']
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                if not file_exists:
                    writer.writeheader()
                writer.writerow({'user_id': user_id, 'full_name': full_name, 'username': username, 'language_code': lang_code})
    except Exception as e:
        print(f"Қолданушы ақпаратын сақтау кезінде қате: {e}")

# --- Күдікті жағдайларды файлға сақтау ---
async def log_suspicious_case(context: ContextTypes.DEFAULT_TYPE, user_id: int, image_description: str, photo_bytes: bytearray):
    if not os.path.exists(IMAGES_DIR):
        os.makedirs(IMAGES_DIR)
    now = datetime.now()
    timestamp = now.strftime("%Y-%m-%d %H:%M:%S")
    image_filename = f"{now.strftime('%Y%m%d_%H%M%S')}_{user_id}.jpg"
    image_path = os.path.join(IMAGES_DIR, image_filename)
    with open(image_path, "wb") as f:
        f.write(photo_bytes)
    file_exists = os.path.isfile(SUSPICIOUS_LOG_FILE)
    with open(SUSPICIOUS_LOG_FILE, 'a', newline='', encoding='utf-8') as csvfile:
        fieldnames = ['timestamp', 'user_id', 'google_vision_text', 'image_path']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()
        writer.writerow({
            'timestamp': timestamp,
            'user_id': user_id,
            'google_vision_text': image_description,
            'image_path': image_path
        })
    print(f"Күдікті жағдай '{SUSPICIOUS_LOG_FILE}' файлына сақталды.")

# --- Telegram Боттың негізгі логикасы ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    add_user_info(user)
    context.user_data.pop('thread_id', None)
    
    keyboard = [
        [InlineKeyboardButton("📝 Мәтінмен сұрау", callback_data='ask_text')],
        [InlineKeyboardButton("📸 Суретпен талдау", callback_data='ask_photo')],
    ]
    if user.id in ADMIN_USER_IDS:
        keyboard.append([InlineKeyboardButton("🔐 Админ панелі", callback_data='admin_panel')])
    reply_markup = InlineKeyboardMarkup(keyboard)
    welcome_text = "Assalamualaikum! Төмендегі батырмалар арқылы қажетті әрекетті таңдаңыз немесе сұрағыңызды жаза беріңіз:"
    await update.message.reply_text(welcome_text, reply_markup=reply_markup)

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
    elif query.data == 'broadcast_start':
        if user_id in ADMIN_USER_IDS:
            await query.message.reply_text("Барлық қолданушыларға жіберілетін хабарламаның мәтінін енгізіңіз:")
            return BROADCAST_MESSAGE
    elif query.data in ['like', 'dislike']:
        await feedback_button_callback(update, context)

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
            time.sleep(0.1)
        except Exception as e:
            failed_count += 1
            print(f"ID {user_id} қолданушысына хабарлама жіберу сәтсіз аяқталды: {e}")
    await update.message.reply_text(f"📬 Хабарлама тарату аяқталды!\n\n✅ Жеткізілді: {sent_count}\n❌ Жеткізілмеді: {failed_count}")
    return ConversationHandler.END

async def cancel_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Хабарлама жіберу тоқтатылды.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

async def run_openai_assistant(user_query: str, thread_id: str | None) -> tuple[str, str]:
    if not OPENAI_ASSISTANT_ID: return "Қате: OPENAI_ASSISTANT_ID .env файлында көрсетілмеген.", thread_id
    try:
        if thread_id is None:
            run = client_openai.beta.threads.create_and_run(
                assistant_id=OPENAI_ASSISTANT_ID,
                thread={"messages": [{"role": "user", "content": user_query}]}
            )
            thread_id = run.thread_id
        else:
            client_openai.beta.threads.messages.create(thread_id=thread_id, role="user", content=user_query)
            run = client_openai.beta.threads.runs.create(thread_id=thread_id, assistant_id=OPENAI_ASSISTANT_ID)
        while run.status in ['in_progress', 'queued']:
            time.sleep(1)
            run = client_openai.beta.threads.runs.retrieve(thread_id=thread_id, run_id=run.id)
        if run.status == 'completed':
            messages = client_openai.beta.threads.messages.list(thread_id=thread_id, limit=1)
            return messages.data[0].content[0].text.value, thread_id
        else:
            error_message = run.last_error.message if run.last_error else 'Белгісіз қате'
            return f"Ассистент жұмысында қате: {error_message}", thread_id
    except Exception as e:
        print(f"OpenAI Assistant қатесі: {e}")
        return f"OpenAI Assistant-пен байланысу кезінде қате шықты: {e}", thread_id

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton("👍", callback_data='like'), InlineKeyboardButton("👎", callback_data='dislike')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    user_query = update.message.text.strip()
    waiting_message = await update.message.reply_text("⏳ Жауап дайындалуда...")
    thread_id = context.user_data.get('thread_id')
    response_text, new_thread_id = await run_openai_assistant(user_query, thread_id)
    context.user_data['thread_id'] = new_thread_id
    await waiting_message.edit_text(response_text, reply_markup=reply_markup)
    context.user_data[f'last_question_{waiting_message.message_id}'] = user_query
    context.user_data[f'last_answer_{waiting_message.message_id}'] = response_text

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton("👍", callback_data='like'), InlineKeyboardButton("👎", callback_data='dislike')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    waiting_message = await update.message.reply_text("⏳ Сурет Google Vision арқылы талданып жатыр...")
    try:
        photo_file = await update.message.photo[-1].get_file()
        photo_bytes = await photo_file.download_as_bytearray()
        
        # --- ҚАТЕ ТҮЗЕТІЛДІ: bytearray -> bytes ---
        image = vision.Image(content=bytes(photo_bytes))
        # ---------------------------------------------
        
        response = client_vision.text_detection(image=image)
        texts = response.text_annotations
        
        if response.error.message:
            raise Exception(f"Google Vision API қатесі: {response.error.message}")

        image_description = texts[0].description.replace('\n', ' ') if texts else "Суреттен мәтін табылмады."
        
        final_query_to_openai = (
            f"Пайдаланушы маған сурет жіберді. Google Vision суреттен мынадай мәтінді оқыды: '{image_description}'.\n\n"
            f"Осы мәтіндегі негізгі атауларды (өнім, бренд, мекеме) анықтап, "
            f"сол бойынша өзіңнің білім қорыңнан (файлдардан) ақпаратты ізде. Табылған ақпарат негізінде, "
            f"суреттегі өнімнің халал статусы туралы толық жауап бер."
        )
        
        await waiting_message.edit_text("⏳ OpenAI ақпаратты іздеуде...")
        thread_id = context.user_data.get('thread_id')
        openai_response, new_thread_id = await run_openai_assistant(final_query_to_openai, thread_id)
        context.user_data['thread_id'] = new_thread_id

        await waiting_message.edit_text(openai_response, reply_markup=reply_markup)
        context.user_data[f'last_question_{waiting_message.message_id}'] = f"Image Query: {image_description}"
        context.user_data[f'last_answer_{waiting_message.message_id}'] = openai_response
        
    except Exception as e:
        print(f"Суретті өңдеу қатесі: {e}")
        await waiting_message.edit_text(f"Суретті өңдеу кезінде қате шықты. Қайталап көріңіз.")

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
    print(f"Кері байланыс 'feedback.csv' файлына сақталды: User {user_id} '{vote}' деп басты.")

async def feedback_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message: user_id = update.effective_user.id
    elif update.callback_query: user_id = update.callback_query.from_user.id
    else: return
    if user_id not in ADMIN_USER_IDS:
        if update.message: await update.message.reply_text("⛔️ Бұл функция тек админдерге арналған.")
        return
    try:
        df = pd.read_csv('feedback.csv')
        total_feedback = len(df); likes = (df['vote'] == 'like').sum(); dislikes = (df['vote'] == 'dislike').sum()
        response_text = (f"📊 **Кері байланыс статистикасы**\n\n🔹 **Барлығы:** {total_feedback} баға\n👍 **Лайк:** {likes}\n👎 **Дизлайк:** {dislikes}")
        if update.message: await update.message.reply_text(response_text, parse_mode='HTML')
        elif update.callback_query: await update.callback_query.message.edit_text(response_text, parse_mode='HTML')
    except FileNotFoundError:
        if update.message: await update.message.reply_text("Әзірге кері байланыс жоқ.")
        elif update.callback_query: await update.callback_query.message.edit_text("Әзірге кері байланыс жоқ.")
    except Exception as e: await update.message.reply_text(f"Статистиканы есептеу кезінде қате: {e}")

async def suspicious_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message: user_id = update.effective_user.id
    elif update.callback_query: user_id = update.callback_query.from_user.id
    else: return
    if user_id not in ADMIN_USER_IDS:
        if update.message: await update.message.reply_text("⛔️ Бұл функция тек админдерге арналған.")
        return
    try:
        df = pd.read_csv(SUSPICIOUS_LOG_FILE)
        if df.empty:
            response_text = "✅ Күдікті өнімдер тізімі бос."
        else:
            response_text = "🧐 **Күдікті өнімдер тізімі (соңғы 5):**\n\n"
            for index, row in df.tail(5).iterrows():
                response_text += (
                    f"🗓️ **Уақыты:** {row['timestamp']}\n"
                    f"👤 **Қолданушы ID:** `{row['user_id']}`\n"
                    f"📝 **Google Vision мәтіні:** {row.get('google_vision_text', row.get('claude_description', 'N/A'))}\n"
                    f"🖼️ **Сурет:** `{row['image_path']}`\n"
                    f"--------------------\n"
                )
        if update.message: await update.message.reply_text(response_text, parse_mode='HTML')
        elif update.callback_query: await context.bot.send_message(chat_id=user_id, text=response_text, parse_mode='HTML')
    except FileNotFoundError:
        response_text = "✅ Күдікті өнімдер тізімі бос."
        if update.message: await update.message.reply_text(response_text)
        elif update.callback_query: await context.bot.send_message(chat_id=user_id, text=response_text)
    except Exception as e:
        print(f"Күдікті тізімді көрсету кезінде қате: {e}")
        if update.message: await update.message.reply_text(f"Тізімді көрсету кезінде қате: {e}")
        elif update.callback_query: await context.bot.send_message(chat_id=user_id, text=f"Тізімді көрсету кезінде қате: {e}")

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(button_handler, pattern='^broadcast_start$')],
        states={
            BROADCAST_MESSAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, broadcast_message_handler)],
        },
        fallbacks=[CommandHandler('cancel', cancel_broadcast)],
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("feedback_stats", feedback_stats))
    app.add_handler(CommandHandler("suspicious_list", suspicious_list))
    
    app.add_handler(conv_handler)
    
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(CallbackQueryHandler(button_handler))
    
    print("🚀 Бот іске қосылды... (Vision: Google, Logic: OpenAI)")
    app.run_polling()

if __name__ == '__main__':
    main()