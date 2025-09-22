import logging
from warnings import filterwarnings

from dotenv import load_dotenv
from telegram.warnings import PTBUserWarning

# Конфигурацияны импорттау
from bot import config 

# Хэндлерлерді импорттау
# admin.py-дан ТЕК қажетті функцияларды импорттаймыз
from bot.handlers.admin import button_handler, grant_premium, revoke_premium
from bot.handlers.common import error_handle, help_handle, start_handle
from bot.handlers.conversations import (
    conv_handler,
    image_handler,
    reset_handle,
    voice_handler,
    broadcast_message_handler,
    get_message_for_broadcast,
    cancel_broadcast,
    WAITING_FOR_UPDATE_FILE,
    BROADCAST_MESSAGE
)
# Сіз қосқан жаңа location_handler
from bot.handlers.location_handler import location_handler
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    filters,
)

filterwarnings(
    action="ignore", message=r".*CallbackQueryHandler", category=PTBUserWarning
)

load_dotenv()
# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)


def main():
    """Start the bot."""
    # Create the Application and pass it your bot's token.
    application = Application.builder().token(config.TELEGRAM_TOKEN).build()

    # --- ХЭНДЛЕРЛЕРДІ ТІРКЕУ ---

    # 1. Жалпы командалар (/start, /help, /reset)
    application.add_handler(CommandHandler("start", start_handle))
    application.add_handler(CommandHandler("help", help_handle))
    application.add_handler(CommandHandler("reset", reset_handle))

    # 2. Админ командалары (/grant_premium, /revoke_premium)
    application.add_handler(CommandHandler("grant_premium", grant_premium))
    application.add_handler(CommandHandler("revoke_premium", revoke_premium))
    
    # 3. ЛОКАЦИЯ бойынша іздеу хэндлері (сіздің негізгі функцияңыз)
    application.add_handler(MessageHandler(filters.LOCATION, location_handler))

    # 4. Түймелерді өңдейтін хэндлер (админ панелі, тіл ауыстыру, т.б.)
    # Бұл сіздің админ панеліңіздің жұмысы үшін КЕРЕК
    application.add_handler(CallbackQueryHandler(button_handler))

    # 5. Хабарлама тарату (broadcast) диалогы
    broadcast_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(get_message_for_broadcast, pattern='^broadcast_start$')],
        states={
            BROADCAST_MESSAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, broadcast_message_handler)],
        },
        fallbacks=[CallbackQueryHandler(cancel_broadcast, pattern='^broadcast_stop$')],
    )
    application.add_handler(broadcast_handler)

    # 6. Негізгі диалогтар (сурет, дауыс, мәтін)
    application.add_handler(conv_handler)
    application.add_handler(MessageHandler(filters.VOICE, voice_handler))

    # 7. Қателерді журналға жазу (ең соңында тұрғаны дұрыс)
    application.add_error_handler(error_handle)

    # Ботты іске қосу
    application.run_polling()


if __name__ == "__main__":
    main()