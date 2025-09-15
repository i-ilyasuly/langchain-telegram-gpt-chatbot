import os
import time
import base64
import csv
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

# API клиенттерін инициализациялау
client_claude = Anthropic(api_key=CLAUDE_API_KEY)
client_openai = OpenAI(api_key=OPENAI_API_KEY)

# --- Telegram Боттың негізгі логикасы ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop('thread_id', None)
    await update.message.reply_text("Сәлем! Диалог басталды. Халал мекеме/қоспа туралы сұраңыз немесе өнімнің суретін жіберіңіз.")

async def run_openai_assistant(user_query: str, thread_id: str | None) -> tuple[str, str]:
    """OpenAI Assistant-ты іске қосып, жауапты және thread_id-ны қайтаратын функция"""
    if not OPENAI_ASSISTANT_ID:
        return "Қате: OPENAI_ASSISTANT_ID .env файлында көрсетілмеген.", thread_id
        
    try:
        if thread_id is None:
            thread = client_openai.beta.threads.create()
            thread_id = thread.id
        
        client_openai.beta.threads.messages.create(
            thread_id=thread_id,
            role="user",
            content=user_query
        )

        run = client_openai.beta.threads.runs.create(
            thread_id=thread_id,
            assistant_id=OPENAI_ASSISTANT_ID
        )

        while run.status in ['in_progress', 'queued']:
            time.sleep(1)
            run = client_openai.beta.threads.runs.retrieve(thread_id=thread_id, run_id=run.id)

        if run.status == 'completed':
            messages = client_openai.beta.threads.messages.list(thread_id=thread_id)
            assistant_response = messages.data[0].content[0].text.value
            return assistant_response, thread_id
        else:
            error_message = run.last_error.message if run.last_error else 'Белгісіз қате'
            return f"Ассистент жұмысында қате: {error_message}", thread_id

    except Exception as e:
        print(f"OpenAI Assistant қатесі: {e}")
        return f"OpenAI Assistant-пен байланысу кезінде қате шықты: {e}", thread_id

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Мәтіндік сұраныстарды өңдеу"""
    keyboard = [[InlineKeyboardButton("👍", callback_data='like'), InlineKeyboardButton("👎", callback_data='dislike')]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    user_query = update.message.text.strip()
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    
    thread_id = context.user_data.get('thread_id')
    response_text, new_thread_id = await run_openai_assistant(user_query, thread_id)
    context.user_data['thread_id'] = new_thread_id
    
    sent_message = await update.message.reply_text(response_text, reply_markup=reply_markup)
    # Пайдаланушының сұрағын және боттың жауабын кейін feedback үшін сақтап қою
    context.user_data[f'last_question_{sent_message.message_id}'] = user_query
    context.user_data[f'last_answer_{sent_message.message_id}'] = response_text


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Суретті сұраныстарды өңдеу (Гибридті модель)"""
    keyboard = [[InlineKeyboardButton("👍", callback_data='like'), InlineKeyboardButton("👎", callback_data='dislike')]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    
    try:
        # 1-кезең: Суретті Claude-қа жіберіп, сипаттамасын алу
        photo_file = await update.message.photo[-1].get_file()
        photo_bytes = await photo_file.download_as_bytearray()
        image_data = base64.b64encode(photo_bytes).decode('utf-8')
        
        claude_prompt = "Бұл суретті мұқият талдап, ішіндегі барлық объектілерді, брендтерді, өнім атауларын және кез келген мәтінді сипаттап бер. Сипаттаманы өте нақты және толық жаз."
        
        claude_response = client_claude.messages.create(
            model="claude-3-haiku-20240307",
            max_tokens=500,
            messages=[{"role": "user", "content": [
                {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": image_data}},
                {"type": "text", "text": claude_prompt}
            ]}]
        )
        image_description = claude_response.content[0].text
        
        # 2-кезең: Claude-тың сипаттамасын OpenAI-ға жіберу
        final_query_to_openai = (
            f"Пайдаланушы маған сурет жіберді. Мен ол суретті талдап, мынадай сипаттама алдым: "
            f"'{image_description}'. Осы сипаттамаға сүйеніп, өзіңнің білім қорыңнан (жүктелген файлдардан) "
            f"суреттегі өнімнің немесе мекеменің халал статусы туралы ақпаратты тауып, пайдаланушыға жауап бер."
        )
        
        thread_id = context.user_data.get('thread_id')
        openai_response, new_thread_id = await run_openai_assistant(final_query_to_openai, thread_id)
        context.user_data['thread_id'] = new_thread_id

        sent_message = await update.message.reply_text(openai_response, reply_markup=reply_markup)
        # Пайдаланушының сұрағын (сурет сипаттамасы) және боттың жауабын сақтау
        context.user_data[f'last_question_{sent_message.message_id}'] = f"Image Query: {image_description}"
        context.user_data[f'last_answer_{sent_message.message_id}'] = openai_response


    except Exception as e:
        print(f"Суретті өңдеу қатесі: {e}")
        await update.message.reply_text(f"Суретті өңдеу кезінде қате шықты: {e}")

# --- ЖАҢАРТЫЛҒАН: Батырмаларды басқанда іске қосылатын функция ---
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """👍/👎 батырмаларына жауап береді және нәтижені CSV файлына сақтайды"""
    query = update.callback_query
    await query.answer("Кері байланыс үшін рахмет!")
    
    # Кері байланыс берілгеннен кейін батырмаларды өшіру
    await query.edit_message_reply_markup(reply_markup=None)
    
    # Файлға жазылатын деректерді жинау
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    user_id = query.from_user.id
    vote = query.data # "like" немесе "dislike"
    
    # Батырма басылған хабарламаға сәйкес сұрақ пен жауапты алу
    message_id = query.message.message_id
    question = context.user_data.get(f'last_question_{message_id}', 'Сұрақ табылмады')
    bot_answer = context.user_data.get(f'last_answer_{message_id}', 'Жауап табылмады')

    # CSV файлына жазу
    file_exists = os.path.isfile('feedback.csv')
    with open('feedback.csv', 'a', newline='', encoding='utf-8') as csvfile:
        fieldnames = ['timestamp', 'user_id', 'question', 'bot_answer', 'vote']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

        if not file_exists:
            writer.writeheader()  # Егер файл жаңа болса, тақырыптарды жазу
        
        writer.writerow({
            'timestamp': timestamp,
            'user_id': user_id,
            'question': question,
            'bot_answer': bot_answer,
            'vote': vote
        })
    
    print(f"Кері байланыс 'feedback.csv' файлына сақталды: User {user_id} '{vote}' деп басты.")
# ----------------------------------------------------------------------

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(CallbackQueryHandler(button_callback))
    
    print("🚀 Бот іске қосылды... OpenAI Assistants API негізінде жұмыс істеуде (диалогты есте сақтаумен).")
    app.run_polling()

if __name__ == '__main__':
    main()