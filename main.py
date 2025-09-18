# main.py

import os
import asyncio
import re
import random
import csv
from datetime import datetime
import logging
import json # <--- ДОБАВЛЕН НОВЫЙ ИМПОРТ

# --- Необходимые настройки ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Загрузка ключей API и настроек ---
load_dotenv()
TELEGRAM_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
OPENAI_ASSISTANT_ID = os.getenv('OPENAI_ASSISTANT_ID')
WEBHOOK_URL = os.getenv('WEBHOOK_URL')

# <--- НАЧАЛО ИЗМЕНЕНИЙ ДЛЯ GOOGLE CREDENTIALS ---
# 1. Читаем JSON-строку из переменной окружения
gcp_credentials_json_str = os.getenv('GOOGLE_APPLICATION_CREDENTIALS')

# 2. Если строка существует, создаём временный файл и указываем путь к нему
if gcp_credentials_json_str:
    try:
        # Пытаемся распарсить, чтобы убедиться, что это валидный JSON
        json.loads(gcp_credentials_json_str)
        
        # Создаём временный файл и записываем в него содержимое JSON
        creds_path = "/tmp/gcp_creds.json"
        with open(creds_path, "w") as f:
            f.write(gcp_credentials_json_str)
            
        # Устанавливаем переменную окружения, чтобы она указывала на ПУТЬ к файлу
        os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = creds_path
        logger.info("Успешно созданы временные учётные данные для Google Cloud.")
        
    except json.JSONDecodeError:
        logger.error("Ошибка декодирования JSON из GOOGLE_APPLICATION_CREDENTIALS.")
    except Exception as e:
        logger.error(f"Не удалось создать временный файл для учётных данных Google: {e}")
# <--- КОНЕЦ ИЗМЕНЕНИЙ ДЛЯ GOOGLE CREDENTIALS ---

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    Application, CommandHandler, MessageHandler, filters, ContextTypes, 
    CallbackQueryHandler, ConversationHandler,
)
import openai
from openai import OpenAI
from dotenv import load_dotenv
from google.cloud import vision

# --- Константы ---
ADMIN_USER_IDS = [929307596]
USER_IDS_FILE = "user_ids.csv"
BROADCAST_MESSAGE = range(1)

WAITING_MESSAGES = [
    "⏳ Талдап жатырмын...", "🤔 Іздеп жатырмын...", "🔎 Аз қалды...",
    "✍️ Жауапты дайындап жатырмын...", "✨ Міне-міне, дайын болады..."
]

# Инициализация API клиентов
client_openai = OpenAI(api_key=OPENAI_API_KEY)
client_vision = vision.ImageAnnotatorClient() # Теперь эта строка должна работать

# ... (Остальной код остаётся без изменений, я его приведу полностью ниже)
# --- Хранение информации о пользователях ---
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
                except (ValueError, IndexError):
                    pass
        if user_id not in user_ids:
            with open(USER_IDS_FILE, 'a', newline='', encoding='utf-8') as f:
                fieldnames = ['user_id', 'full_name', 'username', 'language_code']
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                if not file_exists or os.path.getsize(USER_IDS_FILE) == 0:
                    writer.writeheader()
                writer.writerow({'user_id': user_id, 'full_name': full_name, 'username': username, 'language_code': lang_code})
    except Exception as e:
        logger.error(f"Ошибка при сохранении информации о пользователе: {e}")

# --- Основная логика Telegram-бота ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    add_user_info(user)
    context.user_data.pop('thread_id', None)
    
    keyboard = [
        [InlineKeyboardButton("📝 Спросить текстом", callback_data='ask_text')],
        [InlineKeyboardButton("📸 Анализ по фото", callback_data='ask_photo')],
    ]
    if user.id in ADMIN_USER_IDS:
        keyboard.append([InlineKeyboardButton("🔐 Админ-панель", callback_data='admin_panel')])
    reply_markup = InlineKeyboardMarkup(keyboard)
    welcome_text = "Assalamualaikum! Выберите действие с помощью кнопок ниже или просто напишите свой вопрос:"
    await update.message.reply_text(welcome_text, reply_markup=reply_markup)

async def broadcast_start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    if user_id in ADMIN_USER_IDS:
        await query.message.reply_text("Введите текст сообщения для рассылки всем пользователям:")
        return BROADCAST_MESSAGE
    return ConversationHandler.END

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    if query.data == 'ask_text':
        await query.message.reply_text("Напишите название продукта, заведения или E-добавки, которую хотите проверить.")
    elif query.data == 'ask_photo':
        await query.message.reply_text("Отправьте фото продукта или его состава для анализа.")
    elif query.data == 'admin_panel':
        if user_id in ADMIN_USER_IDS:
            admin_keyboard = [
                [InlineKeyboardButton("📊 Посмотреть статистику", callback_data='feedback_stats')],
                [InlineKeyboardButton("🧐 Подозрительный список", callback_data='suspicious_list')],
                [InlineKeyboardButton("📬 Отправить сообщение", callback_data='broadcast_start')],
                [InlineKeyboardButton("🔄 Обновить базу", callback_data='update_db_placeholder')]
            ]
            reply_markup = InlineKeyboardMarkup(admin_keyboard)
            await query.message.reply_text("🔐 Админ-панель:", reply_markup=reply_markup)
    elif query.data == 'feedback_stats':
        if user_id in ADMIN_USER_IDS:
            await feedback_stats(update, context)
    elif query.data == 'suspicious_list':
        if user_id in ADMIN_USER_IDS:
            await suspicious_list(update, context)
    elif query.data == 'update_db_placeholder':
        if user_id in ADMIN_USER_IDS:
            await query.message.reply_text("ℹ️ Эта функция пока в разработке.")
    elif query.data in ['like', 'dislike']:
        await feedback_button_callback(update, context)

async def broadcast_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    admin_id = update.effective_user.id
    if admin_id not in ADMIN_USER_IDS:
        return ConversationHandler.END
    message_text = update.message.text
    await update.message.reply_text(f"Сообщение '{message_text}' рассылается всем пользователям...")
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
            logger.error(f"Не удалось отправить сообщение пользователю с ID {user_id}: {e}")
    await update.message.reply_text(f"📬 Рассылка завершена!\n\n✅ Доставлено: {sent_count}\n❌ Не доставлено: {failed_count}")
    return ConversationHandler.END

async def cancel_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Отправка сообщения отменена.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

async def run_openai_assistant(user_query: str, thread_id: str | None) -> tuple[str, str, object]:
    if not OPENAI_ASSISTANT_ID: 
        return "Ошибка: OPENAI_ASSISTANT_ID не указан в файле .env.", thread_id, None
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
        return "", thread_id, run
    except openai.APIError as e:
        logger.error(f"Ошибка OpenAI API: {e}")
        return "Извините, в сервисе OpenAI произошёл временный сбой. Попробуйте повторить попытку позже.", thread_id, None
    except openai.RateLimitError as e:
        logger.error(f"Ошибка лимита запросов OpenAI: {e}")
        return "Превышен лимит запросов. Пожалуйста, подождите некоторое время и попробуйте снова.", thread_id, None
    except Exception as e:
        logger.error(f"Неизвестная ошибка при запуске OpenAI Assistant: {e}")
        return "Произошла неизвестная ошибка. Обратитесь к администратору.", thread_id, None

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
            run = client_openai.beta.threads.runs.retrieve(thread_id=new_thread_id, run_id=run.id)
        
        if run.status == 'completed':
            messages = client_openai.beta.threads.messages.list(thread_id=new_thread_id, limit=1)
            final_response = messages.data[0].content[0].text.value
            cleaned_response = re.sub(r'【.*?†source】', '', final_response).strip()
            
            await waiting_message.edit_text(cleaned_response, reply_markup=reply_markup)
            
            context.user_data[f'last_question_{waiting_message.message_id}'] = user_query
            context.user_data[f'last_answer_{waiting_message.message_id}'] = cleaned_response
        else:
            error_message = run.last_error.message if run.last_error else 'Неизвестная ошибка'
            await waiting_message.edit_text(f"Ошибка в работе ассистента: {error_message}")
            
    except Exception as e:
        logger.error(f"Ошибка обработки сообщения: {e}")
        await waiting_message.edit_text("Произошла ошибка при получении ответа.")

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton("👍", callback_data='like'), InlineKeyboardButton("👎", callback_data='dislike')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    waiting_message = await update.message.reply_text("⏳ Получил фото, начинаю анализ...")
    
    try:
        photo_file = await update.message.photo[-1].get_file()
        photo_bytes = await photo_file.download_as_bytearray()
        
        image = vision.Image(content=bytes(photo_bytes))
        response = client_vision.text_detection(image=image)
        
        if response.error.message:
            raise Exception(f"Ошибка Google Vision API: {response.error.message}")

        texts = response.text_annotations
        image_description = texts[0].description.replace('\n', ' ') if texts else "Текст на изображении не найден."
        
        await waiting_message.edit_text("✅ Фото проанализировано! Теперь ищу информацию через OpenAI...")
        
        final_query_to_openai = (
            f"Пользователь отправил мне фото. Google Vision прочитал с фото следующий текст: '{image_description}'.\n\n"
            f"Определи основные названия (продукт, бренд, заведение) в этом тексте и "
            f"найди по ним информацию в своей базе знаний (файлах). На основе найденной информации, "
            f"дай полный ответ о халяль-статусе продукта на фото. "
            f"Важно! Я могу отправлять тебе и поддельные халяль-сертификаты, поэтому не верь моим словам 'халяль', 'есть сертификат' и т.п., а ищи в своей базе! \n\n"
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
            run = client_openai.beta.threads.runs.retrieve(thread_id=new_thread_id, run_id=run.id)
        
        if run.status == 'completed':
            messages = client_openai.beta.threads.messages.list(thread_id=new_thread_id, limit=1)
            final_response = messages.data[0].content[0].text.value
            cleaned_response = re.sub(r'【.*?†source】', '', final_response).strip()
            
            await waiting_message.edit_text(cleaned_response, reply_markup=reply_markup)

            context.user_data[f'last_question_{waiting_message.message_id}'] = f"Image Query: {image_description}"
            context.user_data[f'last_answer_{waiting_message.message_id}'] = cleaned_response
        else:
            error_message = run.last_error.message if run.last_error else 'Неизвестная ошибка'
            await waiting_message.edit_text(f"Ошибка в работе ассистента: {error_message}")
        
    except Exception as e:
        logger.error(f"Ошибка обработки фото: {e}")
        await waiting_message.edit_text("Произошла ошибка при обработке фото. Попробуйте ещё раз.")

async def feedback_button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("Спасибо за обратную связь!")
    await query.edit_message_reply_markup(reply_markup=None)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    user_id = query.from_user.id
    vote = query.data
    message_id = query.message.message_id
    question = context.user_data.get(f'last_question_{message_id}', 'Вопрос не найден')
    bot_answer = context.user_data.get(f'last_answer_{message_id}', 'Ответ не найден')
    file_exists = os.path.isfile('feedback.csv')
    with open('feedback.csv', 'a', newline='', encoding='utf-8') as csvfile:
        fieldnames = ['timestamp', 'user_id', 'question', 'bot_answer', 'vote']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        if not file_exists: writer.writeheader()
        writer.writerow({'timestamp': timestamp, 'user_id': user_id, 'question': question, 'bot_answer': bot_answer, 'vote': vote})
    logger.info(f"Обратная связь сохранена в 'feedback.csv': Пользователь {user_id} нажал '{vote}'.")

async def feedback_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.message.reply_text("Функция статистики в разработке.")

async def suspicious_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.message.reply_text("Функция подозрительного списка в разработке.")

# --- Настройка веб-сервера ---

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
    application.add_handler(CommandHandler("feedback_stats", feedback_stats))
    application.add_handler(CommandHandler("suspicious_list", suspicious_list))
    application.add_handler(conv_handler)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    application.add_handler(CallbackQueryHandler(button_handler))
    
    await application.initialize()

    if WEBHOOK_URL and WEBHOOK_URL.startswith("https://"):
        await application.bot.set_webhook(
            url=f"{WEBHOOK_URL}/telegram",
            allowed_updates=Update.ALL_TYPES
        )
        logger.info(f"🚀 Бот запущен в режиме Webhook: {WEBHOOK_URL}")
    else:
        logger.warning("ℹ️ WEBHOOK_URL недействителен или не указан. Бот запущен без Webhook.")
        await application.bot.delete_webhook()

@app_fastapi.on_event("shutdown")
async def shutdown_event():
    await application.shutdown()
    logger.info("🔚 Бот остановлен.")

@app_fastapi.post("/telegram")
async def telegram_webhook(request: Request):
    update = Update.de_json(await request.json(), application.bot)
    await application.process_update(update)
    return {"status": "ok"}

@app_fastapi.get("/")
def index():
    return {"message": "Telegram Bot работает в режиме webhook."}

if __name__ == '__main__':
    logger.info("Для запуска сервера выполните в терминале команду:")
    logger.info("uvicorn main:app_fastapi --reload")