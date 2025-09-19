# bot/utils.py
import json
import logging
import openai
from openai import AsyncOpenAI
from bot.config import OPENAI_API_KEY, OPENAI_ASSISTANT_ID

logger = logging.getLogger(__name__)
client_openai = AsyncOpenAI(api_key=OPENAI_API_KEY)

# --- Көптілділікті басқару ---
translations = {}
def load_translations():
    global translations
    try:
        with open('locales.json', 'r', encoding='utf-8') as f:
            translations = json.load(f)
        logger.info("Аудармалар сәтті жүктелді.")
    except Exception as e:
        logger.error(f"Аударма файлын оқу кезінде қате: {e}")
        translations = {}

load_translations()

def get_text(key, lang_code='kk'):
    lang = 'ru' if lang_code == 'ru' else 'kk'
    return translations.get(lang, {}).get(key, translations.get('kk', {}).get(key, f"<{key}>"))

def get_language_instruction(lang_code='kk'):
    if lang_code == 'ru':
        return "Маңызды ереже: жауабыңды орыс тілінде қайтар. "
    return "Маңызды ереже: жауабыңды қазақ тілінде қайтар. "

# --- OpenAI Assistant-пен жұмыс ---
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
        return "Кешіріңіз, OpenAI сервисінде уақытша ақау пайда болды.", thread_id, None
    except openai.RateLimitError as e:
        logger.error(f"OpenAI Rate Limit қатесі: {e}")
        return "Сұраныстар лимитінен асып кетті. Біраз уақыттан кейін қайталаңыз.", thread_id, None
    except Exception as e:
        logger.error(f"OpenAI Assistant-ты іске қосу кезінде белгісіз қате: {e}")
        return "Белгісіз қате пайда болды. Администраторға хабарласыңыз.", thread_id, None