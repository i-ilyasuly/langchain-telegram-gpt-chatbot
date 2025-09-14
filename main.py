import os
import base64
import requests
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from anthropic import Anthropic
from dotenv import load_dotenv

# .env файлын жүктеу
load_dotenv()

# API кілттер
TELEGRAM_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
CLAUDE_API_KEY = os.getenv('CLAUDE_API_KEY')

# Claude клиентін жасау
claude = Anthropic(api_key=CLAUDE_API_KEY)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Бастау командасы"""
    await update.message.reply_text(
        "Сәлем! Мен Claude AI арқылы жұмыс жасайтын ботпын.\n"
        "📝 Сұрақ қойыңыз - жауап берейін!\n"
        "📷 Сурет жіберіңіз - анализ жасаймын!\n"
        "🔍 Суреттегі мәтінді танып оқи аламын! 🤖"
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Хабарларды өңдеу"""
    user_message = update.message.text
    
    try:
        await context.bot.send_chat_action(
            chat_id=update.effective_chat.id, 
            action="typing"
        )
        
        response = claude.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1000,
            messages=[{
                "role": "user",
                "content": user_message
            }]
        )
        
        claude_response = response.content[0].text
        await update.message.reply_text(claude_response)
        
    except Exception as e:
        await update.message.reply_text(f"Қате: {str(e)}")

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Суреттерді өңдеу"""
    try:
        await context.bot.send_chat_action(
            chat_id=update.effective_chat.id, 
            action="typing"
        )
        
        photo = update.message.photo[-1]
        file = await context.bot.get_file(photo.file_id)
        
        response = requests.get(file.file_path)
        image_data = base64.b64encode(response.content).decode('utf-8')
        
        caption = update.message.caption or "Суретті анализ жасап, не көрсетілгенін айтыңыз. Мәтін бар болса оқып беріңіз."
        
        response = claude.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1500,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/jpeg",
                            "data": image_data
                        }
                    },
                    {
                        "type": "text",
                        "text": caption
                    }
                ]
            }]
        )
        
        claude_response = response.content[0].text
        await update.message.reply_text(claude_response)
        
    except Exception as e:
        await update.message.reply_text(f"Сурет анализ қатесі: {str(e)}")

def main():
    """Негізгі функция"""
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    
    print("Бот іске қосылды...")
    print("📝 Мәтін | 📷 Сурет | 🔍 OCR | ⚡ Стриминг")
    app.run_polling()

if __name__ == '__main__':
    main()