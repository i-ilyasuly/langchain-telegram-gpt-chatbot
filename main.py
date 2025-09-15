import os
import time
import base64
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
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
    await update.message.reply_text("Сәлем! Халал мекеме/қоспа туралы сұраңыз немесе өнімнің суретін жіберіңіз.")

async def run_openai_assistant(user_query: str) -> str:
    """OpenAI Assistant-ты іске қосып, жауапты алатын функция (ЕҢ ЖАҢА СИНТАКСИС)"""
    if not OPENAI_ASSISTANT_ID:
        return "Қате: OPENAI_ASSISTANT_ID .env файлында көрсетілмеген."
        
    try:
        # 1. Жаңа "Thread" (диалог желісі) құрып, оған бірден сұрақты қосып, іске қосу
        run = client_openai.beta.threads.create_and_run(
            assistant_id=OPENAI_ASSISTANT_ID,
            thread={
                "messages": [
                    {"role": "user", "content": user_query}
                ]
            }
        )

        # 2. Ассистенттің жауабын күту
        while run.status != "completed":
            time.sleep(0.5)
            run = client_openai.beta.threads.runs.retrieve(thread_id=run.thread_id, run_id=run.id)
            if run.status in ["failed", "cancelled", "expired"]:
                error_message = run.last_error.message if run.last_error else 'Белгісіз қате'
                print(f"Run сәтсіз аяқталды: {error_message}")
                return f"Ассистент жұмысында қате: {error_message}"

        # 3. Жауапты алу
        messages = client_openai.beta.threads.messages.list(thread_id=run.thread_id)
        assistant_response = messages.data[0].content[0].text.value
        return assistant_response

    except Exception as e:
        print(f"OpenAI Assistant қатесі: {e}")
        return f"OpenAI Assistant-пен байланысу кезінде қате шықты: {e}"


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Мәтіндік сұраныстарды өңдеу"""
    user_query = update.message.text.strip()
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    
    response_text = await run_openai_assistant(user_query)
    await update.message.reply_text(response_text)

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Суретті сұраныстарды өңдеу (Гибридті модель)"""
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
        
        openai_response = await run_openai_assistant(final_query_to_openai)
        await update.message.reply_text(openai_response)

    except Exception as e:
        print(f"Суретті өңдеу қатесі: {e}")
        await update.message.reply_text(f"Суретті өңдеу кезінде қате шықты: {e}")

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    
    print("🚀 Бот іске қосылды... OpenAI Assistants API негізінде жұмыс істеуде.")
    app.run_polling()

if __name__ == '__main__':
    main()