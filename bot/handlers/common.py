# bot/handlers/common.py

import logging
import re
import random
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from google.cloud import vision

from bot.database import add_or_update_user
from bot.utils import get_text, get_language_instruction, run_openai_assistant, client_openai
from bot.config import ADMIN_USER_IDS, WAITING_MESSAGES

logger = logging.getLogger(__name__)
client_vision = vision.ImageAnnotatorClient()

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

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    lang_code = user.language_code
    user_query_original = update.message.text.strip()
    logger.info(f"User {user.id} ({user.full_name}) sent text: '{user_query_original}'")

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
        
        while run.status in ['in_progress', 'queued']:
            await asyncio.sleep(2)
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
    waiting_message = await update.message.reply_text(get_text('ask_photo_prompt', lang_code))
    
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
        final_query_to_openai = (f"{language_instruction} "
                                 f"Пайдаланушы маған сурет жіберді. Google Vision суреттен мынадай мәтінді оқыды: '{image_description}'.\n\n"
                                 "Осы мәтіндегі негізгі атауларды анықтап, сол бойынша өзіңнің білім қорыңнан ақпаратты ізде. "
                                 "Табылған ақпарат негізінде, суреттегі өнімнің халал статусы туралы толық жауап бер.")
        
        thread_id = context.user_data.get('thread_id')
        response_text, new_thread_id, run = await run_openai_assistant(final_query_to_openai, thread_id)
        if run is None:
            await waiting_message.edit_text(response_text)
            return
        context.user_data['thread_id'] = new_thread_id
        
        while run.status in ['in_progress', 'queued']:
            await asyncio.sleep(2)
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
        logger.error(f"Суретті өңдеу қатесі (User ID: {user.id}): {e}")
        await waiting_message.edit_text("Суретті өңдеу кезінде қате шықты.")