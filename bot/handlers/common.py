# bot/handlers/common.py

import logging
import re
import random
import asyncio
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from google.cloud import vision

# --- Жобаның ішкі импорттары ---
from bot.config import ADMIN_USER_IDS, FREE_TEXT_LIMIT, FREE_PHOTO_LIMIT
from bot.utils import get_text, get_language_instruction, run_openai_assistant
from bot.database import (
    add_or_update_user, is_user_premium, get_user_language,
    set_thread_id, get_thread_id, set_last_q_and_a,
    check_and_increment_usage
)
from openai import AsyncOpenAI
from bot.config import OPENAI_API_KEY
client_openai = AsyncOpenAI(api_key=OPENAI_API_KEY)


# --- Негізгі баптаулар ---
logger = logging.getLogger(__name__)
client_vision = vision.ImageAnnotatorClient()


# --- Хэндлер функциялары ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/start командасын өңдейді, алдымен тілді таңдауды сұрайды."""
    user = update.effective_user
    add_or_update_user(user.id, user.full_name, user.username, user.language_code)
    set_thread_id(user.id, None)  # Сұхбатты дерекқорда тазалаймыз
    
    keyboard = [
        [InlineKeyboardButton("🇰🇿 Қазақша", callback_data='set_lang_kk_start')],
        [InlineKeyboardButton("🇷🇺 Русский", callback_data='set_lang_ru_start')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Тілді таңдаңыз / Выберите язык:", reply_markup=reply_markup)


async def premium_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/premium командасын өңдейді, жазылым туралы ақпарат береді."""
    user = update.effective_user
    lang_code = get_user_language(user.id)
    premium_text = get_text('premium_info_text', lang_code)
    await update.message.reply_text(premium_text, parse_mode='Markdown')


async def check_user_limits(user: dict, request_type: str, lang_code: str) -> str | None:
    """Қолданушының лимиттерін тексереді және қажет болса жаңартады."""
    if is_user_premium(user.id) or user.id in ADMIN_USER_IDS:
        return None

    # ТҮЗЕТІЛДІ: Лимиттерді тексеретін және санайтын сенімдірек логика
    limit = FREE_TEXT_LIMIT if request_type == 'text' else FREE_PHOTO_LIMIT
    can_proceed = check_and_increment_usage(user.id, request_type, limit)

    if not can_proceed:
        key = 'limit_reached_text' if request_type == 'text' else 'limit_reached_photo'
        limit_message = get_text(key, lang_code).format(limit=limit)
        return limit_message + "\n" + get_text('limit_reset_info', lang_code)
    
    return None


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Кіріс мәтіндік хабарламаларды өңдейді."""
    user = update.effective_user
    lang_code = get_user_language(user.id)

    limit_error = await check_user_limits(user, 'text', lang_code)
    if limit_error:
        await update.message.reply_text(limit_error)
        return
    
    user_query_original = update.message.text.strip()
    logger.info(f"User {user.id} ({user.full_name}) sent text: '{user_query_original}'")

    keyboard = [[InlineKeyboardButton("👍", callback_data='like'), InlineKeyboardButton("👎", callback_data='dislike')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    language_instruction = get_language_instruction(lang_code)
    user_query_for_ai = language_instruction + user_query_original
    
    try:
        waiting_message = await update.message.reply_text(random.choice(get_text('waiting_messages', lang_code)))
        
        # ТҮЗЕТІЛДІ: thread_id дерекқордан алынады
        thread_id = get_thread_id(user.id)
        response_text, new_thread_id, run = await run_openai_assistant(user_query_for_ai, thread_id)
        
        if run is None:
             await waiting_message.edit_text(response_text)
             return
        
        # ТҮЗЕТІЛДІ: жаңа thread_id дерекқорға сақталады
        set_thread_id(user.id, new_thread_id)
        
        while run.status in ['in_progress', 'queued']:
            await asyncio.sleep(2)
            run = await client_openai.beta.threads.runs.retrieve(thread_id=new_thread_id, run_id=run.id)
        
        if run.status == 'completed':
            messages = await client_openai.beta.threads.messages.list(thread_id=new_thread_id, limit=1)
            final_response = messages.data[0].content[0].text.value
            cleaned_response = re.sub(r'【.*?†source】', '', final_response).strip()
            await waiting_message.edit_text(cleaned_response, reply_markup=reply_markup, parse_mode='Markdown')
            
            # ТҮЗЕТІЛДІ: Кері байланыс үшін дерекқорды қолдану
            set_last_q_and_a(user.id, user_query_original, cleaned_response)
        else:
            error_message = run.last_error.message if run.last_error else 'Белгісіз қате'
            logger.error(f"OpenAI Assistant run аяқталмады, статусы: {run.status}, қате: {error_message}")
            await waiting_message.edit_text(f"Ассистент жұмысында қате: {run.status}")

    except Exception as e:
        logger.error(f"Хабарламаны өңдеу кезінде күтпеген қате (User ID: {user.id}): {e}", exc_info=True)
        await update.message.reply_text("Кешіріңіз, күтпеген техникалық ақау пайда болды. Администраторға хабарласыңыз.")


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Кіріс суреттерді өңдейді."""
    user = update.effective_user
    lang_code = get_user_language(user.id)

    limit_error = await check_user_limits(user, 'photo', lang_code)
    if limit_error:
        await update.message.reply_text(limit_error)
        return

    logger.info(f"User {user.id} ({user.full_name}) sent a photo.")
    keyboard = [[InlineKeyboardButton("👍", callback_data='like'), InlineKeyboardButton("👎", callback_data='dislike')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    try:
        waiting_message = await update.message.reply_text(random.choice(get_text('waiting_messages', lang_code)))
        
        photo_file = await update.message.photo[-1].get_file()
        photo_bytes = await photo_file.download_as_bytearray()
        image = vision.Image(content=bytes(photo_bytes))
        response = client_vision.text_detection(image=image)
        texts = response.text_annotations
        
        if response.error.message and not texts:
            raise Exception(f"Google Vision API қатесі: {response.error.message}")
            
        image_description = texts[0].description.replace('\n', ' ') if texts else "Суреттен мәтін табылмады."
        
        await waiting_message.edit_text(get_text('photo_analyzed_prompt', lang_code))
        
        language_instruction = get_language_instruction(lang_code)
        final_query_to_openai = (
            f"{language_instruction} "
            f"Пайдаланушы маған сурет жіберді. Google Vision суреттен мынадай мәтінді оқыды: '{image_description}'.\n\n"
            "Осы мәтінге сүйеніп, өнімнің халал статусы туралы толық жауап бер."
        )
        
        # ТҮЗЕТІЛДІ: thread_id дерекқордан алынады
        thread_id = get_thread_id(user.id)
        response_text, new_thread_id, run = await run_openai_assistant(final_query_to_openai, thread_id)
        
        if run is None:
            await waiting_message.edit_text(response_text)
            return
            
        # ТҮЗЕТІЛДІ: жаңа thread_id дерекқорға сақталады
        set_thread_id(user.id, new_thread_id)
        
        while run.status in ['in_progress', 'queued']:
            await asyncio.sleep(2)
            run = await client_openai.beta.threads.runs.retrieve(thread_id=new_thread_id, run_id=run.id)
            
        if run.status == 'completed':
            messages = await client_openai.beta.threads.messages.list(thread_id=new_thread_id, limit=1)
            final_response = messages.data[0].content[0].text.value
            cleaned_response = re.sub(r'【.*?†source】', '', final_response).strip()
            await waiting_message.edit_text(cleaned_response, reply_markup=reply_markup, parse_mode='Markdown')
            
            # ТҮЗЕТІЛДІ: Кері байланыс үшін дерекқорды қолдану
            set_last_q_and_a(user.id, f"Image Query: {image_description[:100]}...", cleaned_response)
        else:
            error_message = run.last_error.message if run.last_error else 'Белгісіз қате'
            await waiting_message.edit_text(f"Ассистент жұмысында қате: {run.status}")
            
    except Exception as e:
        logger.error(f"Суретті өңдеу қатесі (User ID: {user.id}): {e}", exc_info=True)
        await update.message.reply_text("Кешіріңіз, суретті өңдеу кезінде күтпеген техникалық ақау пайда болды.")


async def language_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/language командасын өңдейді, тіл таңдау батырмаларын жібереді."""
    user = update.effective_user
    lang_code = get_user_language(user.id)
    keyboard = [
        [InlineKeyboardButton("🇰🇿 Қазақша", callback_data='set_lang_kk')],
        [InlineKeyboardButton("🇷🇺 Русский", callback_data='set_lang_ru')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(get_text('change_language_button', lang_code), reply_markup=reply_markup)