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



