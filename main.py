import os
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
        "Сәлем! Мен Claude AI арқылы жұмыс жасайтын ботпын. "
        "Сұрақ қойыңыз - жауап берейін! 🤖"
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Хабарларды өңдеу"""
    user_message = update.message.text
    
    try:
        # "Жазып жатыр..." көрсету
        await context.bot.send_chat_action(
            chat_id=update.effective_chat.id, 
            action="typing"
        )
        
        # Claude API-ға сұрау
        response = claude.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1000,
            messages=[{
                "role": "user",
                "content": user_message
            }]
        )
        
        # Жауапты жіберу
        claude_response = response.content[0].text
        await update.message.reply_text(claude_response)
        
    except Exception as e:
        await update.message.reply_text(
            f"Кешіріңіз, қате шықты: {str(e)}"
        )

def main():
    """Негізгі функция"""
    # Bot жасау
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    # Хандлерлерді қосу
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # Ботты іске қосу
    print("Бот іске қосылды...")
    app.run_polling()

if __name__ == '__main__':
    main()