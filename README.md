# OpenAI Telegram Bot

OpenAI Assistant API қуатымен жұмыс жасайтын Telegram боты.

## Мүмкіндіктер
- 📝 Сұрақтарға жауап беру
- 📷 Суретті талдау (Google Vision OCR арқылы)
- 🗂️ Файл жүктеу арқылы білім қорын жаңарту (админдер үшін)
- 📊 Бот статистикасын көру (админдер үшін)

## Орнату
1. Репозиторийді көшіріп алыңыз.
2. `.env.example` файлының атауын `.env` деп өзгертіп, ішіне API кілттеріңізді енгізіңіз.
3. `pip install -r requirements.txt` командасымен қажетті кітапханаларды орнатыңыз.
4. `main.py` файлын іске қосыңыз немесе веб-серверге деплой жасаңыз.

## API кілттер
- **Telegram Bot Token**: @BotFather ботынан алыңыз.
- **OpenAI API Key & Assistant ID**: platform.openai.com сайтынан алыңыз.
- **Vector Store ID**: OpenAI платформасында Assistant үшін Vector Store жасап, соның ID-ын алыңыз.