Directory structure:
└── ev0lv3nta-talk2text/
    ├── README.md
    ├── bot.py
    ├── requirements.txt
    └── .env.example


Files Content:

================================================
FILE: README.md
================================================
# Talk2Text

Telegram-бот, который обрабатывает голосовые, видео и текстовые сообщения, создавая краткое содержание с помощью Gemini AI.

## 📦 Возможности

- Транскрипт и саммари голосовых сообщений (OGG)
- Анализ видео (включая описание визуала)
- Сводка текста
- Пересылка в лог-канал

## 🚀 Установка

```bash
git clone https://github.com/Ev0lv3nta/Talk2Text.git
cd Talk2Text
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
nano .env
```

## ⚙️ Переменные окружения

Создай файл `.env` на основе `.env.example` и заполни:

```env
TELEGRAM_BOT_TOKEN=your_telegram_token_here
GEMINI_API_KEY=your_gemini_api_key_here
LOG_CHANNEL_ID=your_log_channel_id_here
```

## ▶️ Запуск

```bash
python bot.py
```

## 🛠 Автозапуск через systemd (опционально)

Создай файл `/etc/systemd/system/telegram_gemini_bot.service`:

```ini
[Unit]
Description=Talk2Text Bot
After=network.target

[Service]
WorkingDirectory=/path/to/Talk2Text
ExecStart=/path/to/Talk2Text/venv/bin/python3 bot.py
Restart=always
EnvironmentFile=/path/to/Talk2Text/.env

[Install]
WantedBy=multi-user.target
```

Активируй:

```bash
sudo systemctl daemon-reload
sudo systemctl enable telegram_gemini_bot
sudo systemctl start telegram_gemini_bot
```

---






================================================
FILE: bot.py
================================================
import asyncio
import os
import logging
from dotenv import load_dotenv
from google import genai
from google.genai import types
from telegram import Update
from telegram.ext import filters
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes

load_dotenv()

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
LOG_CHANNEL_ID = os.getenv("LOG_CHANNEL_ID")

if not all([TELEGRAM_BOT_TOKEN, GEMINI_API_KEY, LOG_CHANNEL_ID]):
    raise EnvironmentError("Required environment variables are not set.")

client = genai.Client(api_key=GEMINI_API_KEY)

async def log_to_channel(update: Update, context: ContextTypes.DEFAULT_TYPE, response_text: str = None):
    try:
        await context.bot.forward_message(
            chat_id=LOG_CHANNEL_ID,
            from_chat_id=update.message.chat_id,
            message_id=update.message.message_id
        )
        if response_text:
            await context.bot.send_message(
                chat_id=LOG_CHANNEL_ID,
                text=f"Ответ бота (ID {update.message.from_user.id}):\n{response_text}"
            )
    except Exception as e:
        logging.error(f"Log channel error: {e}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Привет! Отправь голосовое, видеосообщение или текст.")
    await log_to_channel(update, context)

async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    voice = update.message.voice
    file = await context.bot.get_file(voice.file_id)
    path = f"voice_{voice.file_unique_id}.ogg"
    await file.download_to_drive(path)
    with open(path, "rb") as f:
        audio = f.read()

    tr = client.models.generate_content(
        model="gemini-2.0-flash",
        contents=["Сделай транскрипт аудио", types.Part.from_bytes(data=audio, mime_type="audio/ogg")],
        config=types.GenerateContentConfig(max_output_tokens=800)
    )
    sm = client.models.generate_content(
        model="gemini-2.0-flash",
        contents=["Сделай краткое содержание аудио", types.Part.from_bytes(data=audio, mime_type="audio/ogg")],
        config=types.GenerateContentConfig(max_output_tokens=600)
    )
    text = f"📄 Транскрипт:\n{tr.text}\n\n📌 Содержание:\n{sm.text}"
    await update.message.reply_text(text, reply_to_message_id=update.message.message_id)
    await log_to_channel(update, context, text)
    os.remove(path)

async def handle_video_note(update: Update, context: ContextTypes.DEFAULT_TYPE):
    video = update.message.video_note
    file = await context.bot.get_file(video.file_id)
    path = f"video_{video.file_unique_id}.mp4"
    await file.download_to_drive(path)
    with open(path, "rb") as f:
        video_bytes = f.read()

    tr = client.models.generate_content(
        model="gemini-2.0-flash",
        contents=["Сделай транскрипт аудио дорожки", types.Part.from_bytes(data=video_bytes, mime_type="video/mp4")],
        config=types.GenerateContentConfig(max_output_tokens=800)
    )
    visual = client.models.generate_content(
        model="gemini-2.0-flash",
        contents=["Опиши визуальные детали", types.Part.from_bytes(data=video_bytes, mime_type="video/mp4")],
        config=types.GenerateContentConfig(max_output_tokens=800)
    )
    sm = client.models.generate_content(
        model="gemini-2.0-flash",
        contents=["Сделай общее содержание", types.Part.from_bytes(data=video_bytes, mime_type="video/mp4")],
        config=types.GenerateContentConfig(max_output_tokens=800)
    )
    text = f"📄 Аудио:\n{tr.text}\n\n🖼️ Визуал:\n{visual.text}\n\n📌 Содержание:\n{sm.text}"
    await update.message.reply_text(text, reply_to_message_id=update.message.message_id)
    await log_to_channel(update, context, text)
    os.remove(path)

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    sm = client.models.generate_content(
        model="gemini-2.0-flash",
        contents=["Сделай краткое содержание текста", text],
        config=types.GenerateContentConfig(max_output_tokens=600)
    )
    reply = f"📌 Содержание:\n{sm.text}"
    await update.message.reply_text(reply, reply_to_message_id=update.message.message_id)
    await log_to_channel(update, context, reply)

def main():
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    app.add_handler(MessageHandler(filters.VIDEO_NOTE, handle_video_note))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.run_polling()

if __name__ == "__main__":
    main()



================================================
FILE: requirements.txt
================================================
python-telegram-bot==20.7
google-generativeai==0.5.4
python-dotenv==1.0.1



================================================
FILE: .env.example
================================================
TELEGRAM_BOT_TOKEN=your_telegram_token_here
GEMINI_API_KEY=your_gemini_api_key_here
LOG_CHANNEL_ID=your_log_channel_id_here


