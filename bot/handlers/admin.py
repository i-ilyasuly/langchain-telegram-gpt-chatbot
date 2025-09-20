# bot/handlers/admin.py
import os
import logging
import pandas as pd
import asyncio
import csv
from datetime import datetime
from bot.database import get_user_count, grant_premium_access, revoke_premium_access, update_user_language
from bot.database import get_user_language

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from bot.database import get_user_count
from bot.config import ADMIN_USER_IDS, FEEDBACK_FILE, SUSPICIOUS_LOG_FILE
from bot.utils import get_text
from bot.database import get_user_count, grant_premium_access, revoke_premium_access # импорттарды жаңарту

logger = logging.getLogger(__name__)

async def feedback_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    try:
        user_count = get_user_count()
        feedback_count, likes, dislikes = 0, 0, 0
        if os.path.exists(FEEDBACK_FILE):
            df = pd.read_csv(FEEDBACK_FILE)
            feedback_count = len(df)
            if 'vote' in df.columns:
                likes = df['vote'].value_counts().get('like', 0)
                dislikes = df['vote'].value_counts().get('dislike', 0)
        stats_text = (f"📊 **Бот Статистикасы**\n\n"
                      f"👥 **Жалпы қолданушылар:** {user_count}\n"
                      f"📝 **Барлық пікірлер:** {feedback_count}\n"
                      f"👍 **Лайктар:** {likes}\n"
                      f"👎 **Дизлайктар:** {dislikes}")
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
        last_5 = df.tail(5)
        await query.message.reply_text(f"🧐 **Соңғы {len(last_5)} күдікті өнім:**")
        for _, row in last_5.iterrows():
            caption = (f"🗓 **Уақыты:** `{row.get('timestamp', 'N/A')}`\n"
                       f"👤 **Қолданушы ID:** `{row.get('user_id', 'N/A')}`\n"
                       f"📝 **Сипаттама:**\n{row.get('claude_description', 'N/A')}")
            await query.message.reply_text(caption, parse_mode='Markdown')
            await asyncio.sleep(0.5)
    except Exception as e:
        await query.message.reply_text(f"❌ Күдікті тізімді алу кезінде қате: {e}")

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
    
    os.makedirs(os.path.dirname(FEEDBACK_FILE), exist_ok=True)
    file_exists = os.path.isfile(FEEDBACK_FILE)
    with open(FEEDBACK_FILE, 'a', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=['timestamp', 'user_id', 'question', 'bot_answer', 'vote'])
        if not file_exists: writer.writeheader()
        writer.writerow({'timestamp': timestamp, 'user_id': user_id, 'question': question, 'bot_answer': bot_answer, 'vote': vote})
    logger.info(f"Кері байланыс сақталды: User {user_id} '{vote}' деп басты.")

def get_main_menu(lang_code: str, user_id: int) -> InlineKeyboardMarkup:
    """Негізгі мәзірдің пернетақтасын жасайды."""
    keyboard = [
        [InlineKeyboardButton(get_text('features_button', lang_code), callback_data='show_features')],
        [InlineKeyboardButton(get_text('settings_button', lang_code), callback_data='settings')],
    ]
    if user_id in ADMIN_USER_IDS:
        keyboard.append([InlineKeyboardButton(get_text('admin_panel_button', lang_code), callback_data='admin_panel')])
    return InlineKeyboardMarkup(keyboard)

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user = query.from_user
    lang_code = get_user_language(user.id)

    # Негізгі мәзірге оралу
    if query.data == 'back_to_main':
        reply_markup = get_main_menu(lang_code, user.id)
        await query.edit_message_text(get_text('main_menu_title', lang_code), reply_markup=reply_markup)
        return

    # Тілді ауыстыру
    elif query.data.startswith('set_lang_'):
        new_lang_code = query.data.split('_')[-1]
        if new_lang_code == 'start':
            new_lang_code = query.data.split('_')[-2]

        update_user_language(user.id, new_lang_code)
        confirmation_text = get_text(f'language_set_{new_lang_code}', new_lang_code)
        await query.edit_message_text(confirmation_text)

        reply_markup = get_main_menu(new_lang_code, user.id)
        await query.message.reply_text(get_text('main_menu_title', new_lang_code), reply_markup=reply_markup)
        return

    # Баптаулар мәзірі
    elif query.data == 'settings':
        keyboard = [
            [InlineKeyboardButton(get_text('change_language_button', lang_code), callback_data='change_language')],
            [InlineKeyboardButton(get_text('contact_admin_button', lang_code), callback_data='contact_admin')],
            [InlineKeyboardButton(get_text('back_button', lang_code), callback_data='back_to_main')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(get_text('settings_title', lang_code), reply_markup=reply_markup)

    # Тілді өзгерту батырмасы (баптаулар ішінде)
    elif query.data == 'change_language':
        keyboard = [
            [InlineKeyboardButton("🇰🇿 Қазақша", callback_data='set_lang_kk')],
            [InlineKeyboardButton("🇷🇺 Русский", callback_data='set_lang_ru')],
            [InlineKeyboardButton(get_text('back_button', lang_code), callback_data='settings')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(get_text('change_language_button', lang_code), reply_markup=reply_markup)

    # Админмен байланыс
    elif query.data == 'contact_admin':
        await query.edit_message_text(
            get_text('contact_admin_text', lang_code),
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(get_text('back_button', lang_code), callback_data='settings')]])
        )

    # Бот мүмкіндіктері
    elif query.data == 'show_features':
        await query.edit_message_text(
            get_text('bot_features_text', lang_code),
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(get_text('back_button', lang_code), callback_data='back_to_main')]])
        )

    # -- Админ панелінің ескі логикасы --
    elif query.data == 'admin_panel':
        if user.id in ADMIN_USER_IDS:
            admin_keyboard = [
                [InlineKeyboardButton(get_text('stats_button', lang_code), callback_data='feedback_stats')],
                [InlineKeyboardButton(get_text('suspicious_list_button', lang_code), callback_data='suspicious_list')],
                [InlineKeyboardButton(get_text('broadcast_button', lang_code), callback_data='broadcast_start')],
                [InlineKeyboardButton(get_text('update_db_button', lang_code), callback_data='update_db_placeholder')],
                [InlineKeyboardButton(get_text('back_button', lang_code), callback_data='back_to_main')]
            ]
            reply_markup = InlineKeyboardMarkup(admin_keyboard)
            await query.edit_message_text(get_text('admin_panel_title', lang_code), reply_markup=reply_markup)
    
    elif query.data == 'feedback_stats':
        if user.id in ADMIN_USER_IDS: await feedback_stats(update, context)
    
    elif query.data == 'suspicious_list':
        if user.id in ADMIN_USER_IDS: await suspicious_list(update, context)

    # Лайк/Дизлайк
    elif query.data in ['like', 'dislike']:
        await feedback_button_callback(update, context)
    

async def grant_premium(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id not in ADMIN_USER_IDS:
        return

    try:
        # Команда аргументтерін алу: /grant_premium user_id days
        user_id_to_grant = int(context.args[0])
        days = int(context.args[1])
        
        grant_premium_access(user_id_to_grant, days)
        await update.message.reply_text(f"✅ {user_id_to_grant} қолданушысына {days} күнге премиум сәтті берілді.")
    except (IndexError, ValueError):
        await update.message.reply_text("❌ Қате қолданыс. Мысал: /grant_premium 12345678 30")
    except Exception as e:
        await update.message.reply_text(f"❌ Қате: {e}")

async def revoke_premium(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id not in ADMIN_USER_IDS:
        return

    try:
        # Команда аргументін алу: /revoke_premium user_id
        user_id_to_revoke = int(context.args[0])
        
        revoke_premium_access(user_id_to_revoke)
        await update.message.reply_text(f"✅ {user_id_to_revoke} қолданушысының премиум жазылымы тоқтатылды.")
    except (IndexError, ValueError):
        await update.message.reply_text("❌ Қате қолданыс. Мысал: /revoke_premium 12345678")
    except Exception as e:
        await update.message.reply_text(f"❌ Қате: {e}")