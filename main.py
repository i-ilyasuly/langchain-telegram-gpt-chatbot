import os
import base64
import requests
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
CLAUDE_API_KEY = os.getenv('CLAUDE_API_KEY')

claude = Anthropic(api_key=CLAUDE_API_KEY)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Сәлем! Мен Claude AI арқылы жұмыс жасайтын ботпын.\n"
        "📝 Сұрақ қойыңыз - жауап берейін!\n"
        "📷 Сурет жіберіңіз - анализ жасаймын!\n"
        "🔍 Суреттегі мәтінді танып оқи аламын! 🤖\n"
        "⚡ Енді стриминг арқылы жауап берейін!"
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_message = update.message.text
    
    try:
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
        
        # Бос хабар жіберіп, кейін өзгертеміз
        sent_message = await update.message.reply_text("💭...")
        
        full_response = ""
        
        with claude.messages.stream(
            model="claude-sonnet-4-20250514",
            max_tokens=1000,
            messages=[{"role": "user", "content": user_message}]
        ) as stream:
            for text in stream.text_stream:
                full_response += text
                # Әр 50 символдан кейін немесе сөйлем аяқталғанда жаңарту
                if len(full_response) % 50 == 0 or text.endswith('.') or text.endswith('!') or text.endswith('?'):
                    try:
                        await sent_message.edit_text(full_response)
                    except:
                        pass  # Rate limit-тен сақтану
        
        # Соңғы нәтижені жаңарту
        await sent_message.edit_text(full_response)
        
    except Exception as e:
        await update.message.reply_text(f"Қате: {str(e)}")

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
        
        photo = update.message.photo[-1]
        file = await context.bot.get_file(photo.file_id)
        
        response = requests.get(file.file_path)
        image_data = base64.b64encode(response.content).decode('utf-8')
        
        caption = update.message.caption or "Суретті анализ жасап, не көрсетілгенін айтыңыз. Мәтін бар болса оқып беріңіз."
        
        sent_message = await update.message.reply_text("🔍 Сурет анализ жасап жатырмын...", parse_mode='HTML')
        
        full_response = ""
        update_count = 0
        
        with claude.messages.stream(
            model="claude-sonnet-4-20250514",
            max_tokens=1500,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": image_data}},
                    {"type": "text", "text": caption}
                ]
            }]
        ) as stream:
            for text in stream.text_stream:
                full_response += text
                update_count += 1
                if update_count % 5 == 0 or text.endswith('.') or text.endswith('!') or text.endswith('?'):
                    try:
                        await sent_message.edit_text(full_response, parse_mode='HTML')
                    except:
                        continue
        
    except Exception as e:
        await update.message.reply_text(f"Сурет анализ қатесі: {str(e)}")

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    
    print("Бот іске қосылды...")
    print("📝 Мәтін | 📷 Сурет | 🔍 OCR | ⚡ Стриминг")
    app.run_polling()

if __name__ == '__main__':
    main()