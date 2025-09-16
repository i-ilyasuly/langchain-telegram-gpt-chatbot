import os
import time
import base64
import csv
import pandas as pd
import re
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
from anthropic import Anthropic
from openai import OpenAI
from dotenv import load_dotenv

# --- API кілттерді және баптауларды жүктеу ---
load_dotenv()
TELEGRAM_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
CLAUDE_API_KEY = os.getenv('CLAUDE_API_KEY')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
OPENAI_ASSISTANT_ID = os.getenv('OPENAI_ASSISTANT_ID')

# --- Админдердің ID тізімі ---
ADMIN_USER_IDS = [929307596] # Өз ID-ыңызды осында жазыңыз

# API клиенттерін инициализациялау
client_claude = Anthropic(api_key=CLAUDE_API_KEY)
client_openai = OpenAI(api_key=OPENAI_API_KEY)

# --- Telegram Боттың негізгі логикасы ---

# main.py файлындағы start функциясын осылай өзгертіңіз

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/start командасын өңдейді және боттың мүмкіндіктерін таныстырады."""
    context.user_data.pop('thread_id', None)
    user_id = update.effective_user.id
    
    welcome_text = (
        "Assalamualaikum, құрметті бауырым! Мен «Халал Даму» ұйымының ресми деректер қорына негізделген көмекші ботпын.\n\n"
        "**Негізгі мүмкіндіктер:**\n"
        "📝 **Мәтінмен сұрау:** Кез келген өнімнің, мекеменің немесе E-қоспаның атауын жазып, оның халал статусын тексеріңіз.\n"
        "📸 **Суретпен талдау:** Өнімнің немесе оның құрамының суретін жіберіп, халал екендігін сұраңыз.\n\n"
        "Сұрағыңызды жаза беріңіз."
    )
    
    # Егер қолданушы админ болса, оған қосымша командалар туралы ақпарат беру
    if user_id in ADMIN_USER_IDS:
        welcome_text += "\n\n"
        welcome_text += "🔐 **Админ командалары:**\n"
        welcome_text += "`/feedback_stats` - Кері байланыс статистикасын көру."

    await update.message.reply_text(welcome_text, parse_mode='HTML')

async def run_openai_assistant(user_query: str, thread_id: str | None) -> tuple[str, str]:
    if not OPENAI_ASSISTANT_ID: return "Қате: OPENAI_ASSISTANT_ID .env файлында көрсетілмеген.", thread_id
    try:
        if thread_id is None: thread = client_openai.beta.threads.create(); thread_id = thread.id
        client_openai.beta.threads.messages.create(thread_id=thread_id, role="user", content=user_query)
        run = client_openai.beta.threads.runs.create(thread_id=thread_id, assistant_id=OPENAI_ASSISTANT_ID)
        while run.status in ['in_progress', 'queued']:
            time.sleep(1)
            run = client_openai.beta.threads.runs.retrieve(thread_id=thread_id, run_id=run.id)
        if run.status == 'completed':
            messages = client_openai.beta.threads.messages.list(thread_id=thread_id)
            return messages.data[0].content[0].text.value, thread_id
        else:
            error_message = run.last_error.message if run.last_error else 'Белгісіз қате'
            return f"Ассистент жұмысында қате: {error_message}", thread_id
    except Exception as e: return f"OpenAI Assistant-пен байланысу кезінде қате шықты: {e}", thread_id

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
    waiting_message = await update.message.reply_text("⏳ Сурет талданып жатыр...")
    try:
        photo_file = await update.message.photo[-1].get_file()
        photo_bytes = await photo_file.download_as_bytearray()
        image_data = base64.b64encode(photo_bytes).decode('utf-8')
        claude_prompt = "Сенің міндетің - суреттен тек қана 'Халал Даму' дерекқорынан іздеуге болатын нақты ақпаратты анықтау. Жалпы сипаттама қажет емес.\n\nБасты назарды мыналарға аудар:\n1. Өнімнің немесе брендтің атауы.\n2. Мекеменің атауы.\n3. Өнім құрамындағы Е-қоспалардың кодтары.\n\nТек осы табылған нақты атауларды немесе кодтарды тізім ретінде, әрқайсысын жаңа жолдан жазып бер. Егер осындай нақты ақпарат табылмаса, 'Маңызды ақпарат табылмады' деп жауап бер."
        claude_response = client_claude.messages.create(model="claude-3-haiku-20240307", max_tokens=500, messages=[{"role": "user", "content": [{"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": image_data}}, {"type": "text", "text": claude_prompt}]}])
        image_description = claude_response.content[0].text
        final_query_to_openai = f"Пайдаланушы маған өнімнің суретін жіберді. Суреттен келесідей атаулар анықталды: '{image_description}'. Осы атаулардың халал статусын өзіңнің білім қорыңнан (жүктелген файлдардан) тексеріп, пайдаланушыға толық жауап бер."
        await waiting_message.edit_text("⏳ Ақпаратты іздеудемін...")
        thread_id = context.user_data.get('thread_id')
        openai_response, new_thread_id = await run_openai_assistant(final_query_to_openai, thread_id)
        context.user_data['thread_id'] = new_thread_id
        await waiting_message.edit_text(openai_response, reply_markup=reply_markup)
        context.user_data[f'last_question_{waiting_message.message_id}'] = f"Image Query: {image_description}"
        context.user_data[f'last_answer_{waiting_message.message_id}'] = openai_response
    except Exception as e: await waiting_message.edit_text(f"Суретті өңдеу кезінде қате шықты: {e}")

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
    user_id = update.effective_user.id
    if user_id not in ADMIN_USER_IDS:
        await update.message.reply_text("⛔️ Бұл команда тек админдерге арналған.")
        return
    try:
        df = pd.read_csv('feedback.csv')
        total_feedback = len(df)
        likes = (df['vote'] == 'like').sum()
        dislikes = (df['vote'] == 'dislike').sum()
        response_text = (f"📊 **Кері байланыс статистикасы**\n\n"
                         f"🔹 **Барлығы:** {total_feedback} баға\n"
                         f"👍 **Лайк:** {likes}\n"
                         f"👎 **Дизлайк:** {dislikes}")
        await update.message.reply_text(response_text, parse_mode='HTML')
    except FileNotFoundError:
        await update.message.reply_text("Әзірге кері байланыс жоқ.")
    except Exception as e:
        await update.message.reply_text(f"Статистиканы есептеу кезінде қате: {e}")

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("feedback_stats", feedback_stats))
    
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    
    # Геолокацияны өңдейтін handler алып тасталды
    # app.add_handler(MessageHandler(filters.LOCATION, handle_location))
    
    app.add_handler(CallbackQueryHandler(button_callback))
    
    print("🚀 Бот іске қосылды... OpenAI Assistants API негізінде жұмыс істеуде.")
    app.run_polling()

if __name__ == '__main__':
    main()