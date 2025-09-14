import os
import base64
import chromadb
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from anthropic import Anthropic
from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer

load_dotenv()
TELEGRAM_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
CLAUDE_API_KEY = os.getenv('CLAUDE_API_KEY')
claude = Anthropic(api_key=CLAUDE_API_KEY)

# Embedding моделін бот іске қосылғанда бір рет жүктеп алу
embedding_model = SentenceTransformer('all-MiniLM-L6-v2')

try:
    client_chroma = chromadb.PersistentClient(path="./db")
    collection = client_chroma.get_collection(name="halal_data")
    print("✅ Векторлық деректер қорына сәтті қосылды.")
    
    # --- ДИАГНОСТИКАЛЫҚ КОД ---
    record_count = collection.count()
    print(f"📊 Векторлық базадағы жазбалар саны: {record_count}")
    if record_count == 0:
        print("❗️❗️❗️ ЕСКЕРТУ: Векторлық база бос. 'python create_vector_db.py' скриптін қайта іске қосыңыз.")
    # ---------------------------

except Exception as e:
    print(f"❌ Векторлық деректер қорын іске қосу кезінде қате: {e}")
    print("❗️ Алдымен 'python create_vector_db.py' скриптін іске қосыңыз.")
    exit()

SYSTEM_PROMPT = """Сен — «Халал Даму» деректер қорының ассистентісің. Саған '# Табылған ұқсас деректер:' бөлімінде векторлық іздеу арқылы табылған ең сәйкес ақпарат беріледі. Сенің міндетің — сол деректерді ғана пайдаланып, сұраққа әдемілеп, түсінікті форматта жауап беру. Егер ештеңе табылмаса, сыпайы түрде 'Кешіріңіз, сұранысыңызға сәйкес нақты ақпарат табылмады' деп жауап бер. Өзіңнен артық ақпарат қоспа."""

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Сәлем! Халал мекеме/қоспа туралы сұраңыз немесе сурет жіберіңіз.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_query = update.message.text.strip()
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

    try:
        # Пайдаланушы сұрауын векторға айналдыру
        query_embedding = embedding_model.encode(user_query).tolist()

        # Векторлық базадан ең ұқсас 5 нәтижені іздеу
        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=5
        )
        
        found_data_text = "\n\n".join(results['documents'][0]) if results['documents'] and results['documents'][0] else "Ештеңе табылмады."

    except Exception as e:
        print(f"Векторлық іздеу қатесі: {e}")
        found_data_text = "Ішкі қате: Деректерді іздеу кезінде мәселе туындады."

    final_prompt = f"# Табылған ұқсас деректер:\n{found_data_text}\n\n# Пайдаланушы сұрағы:\n{user_query}"
    try:
        response = claude.messages.create(
            model="claude-3-haiku-20240307", max_tokens=1500, system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": final_prompt}]
        )
        await update.message.reply_text(response.content[0].text)
    except Exception as e:
        await update.message.reply_text(f"Claude API қатесі: {e}")

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    try:
        photo_file = await update.message.photo[-1].get_file()
        photo_bytes = await photo_file.download_as_bytearray()
        image_data = base64.b64encode(photo_bytes).decode('utf-8')
        caption = update.message.caption or "Бұл суретте не бейнеленген? Мәтін болса, оқып бер."

        response = claude.messages.create(
            model="claude-3-haiku-20240307", max_tokens=1024,
            messages=[{"role": "user", "content": [
                {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": image_data}},
                {"type": "text", "text": caption}
            ]}]
        )
        await update.message.reply_text(response.content[0].text)
    except Exception as e:
        await update.message.reply_text(f"Суретті өңдеу қатесі: {e}")

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    print("🚀 Бот іске қосылды... Векторлық деректер қорымен жұмыс істеуде.")
    app.run_polling()

if __name__ == '__main__':
    main()