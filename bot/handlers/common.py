# bot/handlers/common.py

import logging
import re
import random
import asyncio
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from google.cloud import vision

# --- Жобаның ішкі импорттары (тазартылған нұсқа) ---
from bot.config import ADMIN_USER_IDS, FREE_TEXT_LIMIT, FREE_PHOTO_LIMIT
from bot.utils import get_text, get_language_instruction, run_openai_assistant, client_openai
from bot.database import (
    add_or_update_user,
    is_user_premium,
    get_user_usage,
    reset_user_limits,
    increment_request_count,
    get_user_language,
    set_thread_id,
    get_thread_id
)

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

    text_count, photo_count, last_date = get_user_usage(user.id)
    today_str = datetime.now().strftime("%Y-%m-%d")

    if last_date != today_str:
        reset_user_limits(user.id)
        text_count, photo_count = 0, 0
    
    limit_message = None
    if request_type == 'text':
        if text_count >= FREE_TEXT_LIMIT:
            limit_message = get_text('limit_reached_text', lang_code).format(limit=FREE_TEXT_LIMIT)
    elif request_type == 'photo':
        if photo_count >= FREE_PHOTO_LIMIT:
            limit_message = get_text('limit_reached_photo', lang_code).format(limit=FREE_PHOTO_LIMIT)

    if limit_message:
        return limit_message + "\n" + get_text('limit_reset_info', lang_code)
    
    increment_request_count(user.id, request_type)
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
    waiting_message = await update.message.reply_text(random.choice(get_text('waiting_messages', lang_code)))
    
    try:
        # Дұрыс: thread_id дерекқордан алынады
        thread_id = get_thread_id(user.id)
        response_text, new_thread_id, run = await run_openai_assistant(user_query_for_ai, thread_id)
        
        if run is None:
             await waiting_message.edit_text(response_text)
             return
        
        # Дұрыс: жаңа thread_id дерекқорға сақталады
        set_thread_id(user.id, new_thread_id)
        
        while run.status in ['in_progress', 'queued']:
            await asyncio.sleep(2)
            run = await client_openai.beta.threads.runs.retrieve(thread_id=new_thread_id, run_id=run.id)
        
        if run.status == 'completed':
            messages = await client_openai.beta.threads.messages.list(thread_id=new_thread_id, limit=1)
            final_response = messages.data[0].content[0].text.value
            cleaned_response = re.sub(r'【.*?†source】', '', final_response).strip()
            logger.info(f"Bot response for user {user.id}: '{cleaned_response[:100]}...'")
            await waiting_message.edit_text(cleaned_response, reply_markup=reply_markup, parse_mode='Markdown')
            context.user_data[f'last_question_{waiting_message.message_id}'] = user_query_original
            context.user_data[f'last_answer_{waiting_message.message_id}'] = cleaned_response
        else:
            error_message = "Белгісіз қате"
            if run.last_error:
                error_message = run.last_error.message
            logger.error(f"OpenAI Assistant жұмысы аяқталмады, статусы: {run.status}, қате: {error_message}")
            user_friendly_error = (
                "Кешіріңіз, жауапты өңдеу кезінде қате пайда болды.\n\n"
                f"Техникалық ақпарат: `{run.status}`"
            )
            await waiting_message.edit_text(user_friendly_error, parse_mode='Markdown')

    except Exception as e:
        logger.error(f"Хабарламаны өңдеу кезінде күтпеген қате (User ID: {user.id}): {e}", exc_info=True)
        await waiting_message.edit_text(
            "Кешіріңіз, күтпеген техникалық ақау пайда болды. "
            "Администраторға хабарласыңыз."
        )


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
    waiting_message = await update.message.reply_text(random.choice(get_text('waiting_messages', lang_code)))
    
    try:
        photo_file = await update.message.photo[-1].get_file()
        photo_bytes = await photo_file.download_as_bytearray()
        image = vision.Image(content=bytes(photo_bytes))
        response = client_vision.text_detection(image=image)
        if response.error.message:
            raise Exception(f"Google Vision API қатесі: {response.error.message}")
        texts = response.text_annotations
        image_description = texts[0].description.replace('\n', ' ') if texts else "Суреттен мәтін табылмады."
        
        await waiting_message.edit_text(get_text('photo_analyzed_prompt', lang_code))
        
        language_instruction = get_language_instruction(lang_code)
        final_query_to_openai = (
            f"{language_instruction} "
            f"Пайдаланушы маған сурет жіберді. Google Vision суреттен мынадай мәтінді оқыды: '{image_description}'.\n\n"
            "Осы мәтіндегі негізгі атауларды анықтап, сол бойынша өзіңнің білім қорыңнан ақпаратты ізде. "
            "Табылған ақпарат негізінде, суреттегі өнімнің халал статусы туралы толық жауап бер. "
            "Маңызды ереже: Ешқашан сілтемелерді ойдан құрастырма және bit.ly сияқты сервистермен қысқартпа. Тек білім қорында бар нақты, толық сілтемені ғана бер."
        )
        
        # Дұрыс: thread_id дерекқордан алынады
        thread_id = get_thread_id(user.id)
        response_text, new_thread_id, run = await run_openai_assistant(final_query_to_openai, thread_id)
        
        if run is None:
            await waiting_message.edit_text(response_text)
            return
            
        # Дұрыс: жаңа thread_id дерекқорға сақталады
        set_thread_id(user.id, new_thread_id)
        
        while run.status in ['in_progress', 'queued']:
            await asyncio.sleep(2)
            run = await client_openai.beta.threads.runs.retrieve(thread_id=new_thread_id, run_id=run.id)
            
        if run.status == 'completed':
            messages = await client_openai.beta.threads.messages.list(thread_id=new_thread_id, limit=1)
            final_response = messages.data[0].content[0].text.value
            cleaned_response = re.sub(r'【.*?†source】', '', final_response).strip()
            await waiting_message.edit_text(cleaned_response, reply_markup=reply_markup, parse_mode='Markdown')
            context.user_data[f'last_question_{waiting_message.message_id}'] = f"Image Query: {image_description}"
            context.user_data[f'last_answer_{waiting_message.message_id}'] = cleaned_response
        else:
            error_message = run.last_error.message if run.last_error else 'Белгісіз қате'
            await waiting_message.edit_text(f"Ассистент жұмысында қате: {error_message}")
            
    except Exception as e:
        logger.error(f"Суретті өңдеу қатесі (User ID: {user.id}): {e}")
        await waiting_message.edit_text("Суретті өңдеу кезінде қате шықты.")


async def language_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/language командасын өңдейді, тіл таңдау батырмаларын жібереді."""
    keyboard = [
        [InlineKeyboardButton("🇰🇿 Қазақша", callback_data='set_lang_kk')],
        [InlineKeyboardButton("🇷🇺 Русский", callback_data='set_lang_ru')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Тілді таңдаңыз / Выберите язык:", reply_markup=reply_markup)