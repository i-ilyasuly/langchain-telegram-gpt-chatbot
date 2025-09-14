# Claude Telegram Bot

Claude AI қуатымен жұмыс жасайтын Telegram боты.

## Мүмкіндіктер

- Claude AI арқылы сұрақтарға жауап беру
- Қазақ және ағылшын тілдерін қолдау
- Жедел жауап беру

## Орнату

### 1. Репозиторийді клондау
```bash
git clone https://github.com/YOUR_USERNAME/YOUR_REPO_NAME.git
cd YOUR_REPO_NAME
```

### 2. Виртуал орта жасау
```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
# немесе
venv\Scripts\activate     # Windows
```

### 3. Тәуелділіктерді орнату
```bash
pip install -r requirements.txt
```

### 4. API кілттерін орнату
```bash
# .env файлын жасау
cp .env.example .env
```

`.env` файлына сіздің API кілттеріңізді қойыңыз:
```
TELEGRAM_BOT_TOKEN=сіздің_телеграм_токеніңіз
CLAUDE_API_KEY=сіздің_claude_кілтіңіз
```

### 5. Ботты іске қосу
```bash
python main.py
```

## API кілттерін алу

### Telegram Bot Token:
1. [@BotFather](https://t.me/botfather) ботына барыңыз
2. `/newbot` командасын жіберіңіз
3. Бот атын беріңіз
4. Токенді сақтаңыз

### Claude API Key:
1. [console.anthropic.com](https://console.anthropic.com) сайтына кіріңіз
2. API Keys бөліміне барыңыз
3. Жаңа кілт жасаңыз

## Пайдалану

1. Telegram-да ботыңызды тауып, `/start` командасын жіберіңіз
2. Кез келген сұрақ қойыңыз
3. Claude AI арқылы жауап алыңыз

## Лицензия

MIT License