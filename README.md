# Talk2Text

Telegram-бот, который обрабатывает голосовые, видео и текстовые сообщения, создавая краткое содержание с помощью Gemini AI.

## 📦 Возможности

-   Транскрипт и саммари голосовых сообщений (OGG)
-   Анализ видео (включая описание визуала и транскрипт аудиодорожки)
-   Сводка текста
-   Пересылка обработанных сообщений и ответов бота в лог-канал

## 🚀 Установка

1.  **Клонируйте репозиторий:**
    ```bash
    git clone [https://github.com/Ev0lv3nta/Talk2Text.git](https://github.com/Ev0lv3nta/Talk2Text.git)
    cd Talk2Text
    ```
2.  **Создайте и активируйте виртуальное окружение:**
    ```bash
    python3 -m venv venv
    source venv/bin/activate 
    # Для Windows: venv\Scripts\activate
    ```
3.  **Установите зависимости:**
    * *Убедитесь, что в файле `requirements.txt` указана корректная библиотека `google-genai`.*
    ```bash
    pip install -r requirements.txt
    ```
4.  **Создайте файл конфигурации:**
    ```bash
    cp .env.example .env
    ```
5.  **Настройте переменные окружения:** Откройте файл `.env` в текстовом редакторе (например, `nano .env` или `notepad .env`) и укажите ваши значения.

## ⚙️ Переменные окружения

Создайте файл `.env` на основе `.env.example` и заполните его:

```env
# Токен вашего Telegram-бота (получить у @BotFather в Telegram)
TELEGRAM_BOT_TOKEN=your_telegram_token_here

# Ваш API-ключ для Gemini AI (получить в Google AI Studio или Google Cloud Console)
GEMINI_API_KEY=your_gemini_api_key_here

# Числовой ID вашего Telegram-канала или чата для логирования 
# (бот должен быть добавлен в этот чат/канал с правами администратора)
LOG_CHANNEL_ID=your_log_channel_id_here 
▶️ Запуск
Убедитесь, что ваше виртуальное окружение активировано (source venv/bin/activate).

Bash

python bot.py
Бот начнет работу и будет работать, пока вы не остановите процесс (Ctrl+C).

🛠 Автозапуск через systemd (для Linux, опционально)
Это позволит боту работать в фоновом режиме и автоматически перезапускаться.

Создайте файл сервиса:

Bash

sudo nano /etc/systemd/system/talk2text_bot.service # Вы можете выбрать другое имя для .service файла
Вставьте и адаптируйте конфигурацию:

Ini, TOML

[Unit]Description=Talk2Text Telegram BotAfter=network.target[Service]# --- ВАЖНО: Укажите правильные значения ниже! ---User=your_user          # Пользователь, от имени которого запускать бота (например, root или www-data)Group=your_group        # Группа пользователя (например, root или www-data)WorkingDirectory=/full/path/to/Talk2Text  # Замените на ПОЛНЫЙ путь к папке проектаEnvironmentFile=/full/path/to/Talk2Text/.env # Замените на ПОЛНЫЙ путь к .env файлуExecStart=/full/path/to/Talk2Text/venv/bin/python3 bot.py # Замените на ПОЛНЫЙ путь к python в venv# --- Конец важных настроек ---Restart=always # Автоматический перезапуск при сбоеRestartSec=5   # Пауза перед перезапуском[Install]WantedBy=multi-user.target
Обязательно замените /full/path/to/Talk2Text на актуальный полный путь к директории вашего проекта.
Укажите правильного пользователя (User=) и группу (Group=), от имени которых будет работать бот (если не root, убедитесь, что у этого пользователя есть права на чтение/запись в WorkingDirectory).
Активируйте сервис:

Bash

# Перезагрузить конфигурацию systemd
sudo systemctl daemon-reload # Включить автозапуск сервиса при старте системы
sudo systemctl enable talk2text_bot.service # Запустить сервис немедленно
sudo systemctl start talk2text_bot.service # Проверить статус сервиса
sudo systemctl status talk2text_bot.service 
⚠️ Возможные проблемы
Ошибка telegram.error.Conflict: ... make sure that only one bot instance is running:Причина: Вы пытаетесь запустить бота, когда другой экземпляр этого же бота (с тем же TELEGRAM_BOT_TOKEN) уже запущен и получает обновления. Telegram разрешает только один активный "слушатель" на токен.
Решение:Убедитесь, что вы не запустили python bot.py в нескольких терминалах.
Если вы настроили systemd, проверьте его статус (sudo systemctl status talk2text_bot.service) и остановите его (sudo systemctl stop talk2text_bot.service), если хотите запустить бота вручную для отладки.
Проверьте, нет ли "зависших" процессов бота: ps aux | grep bot.py или pgrep -f bot.py. Остановите найденные процессы командой kill <PID>.
Убедитесь, что ваш TELEGRAM_BOT_TOKEN не используется одновременно в другом проекте или на другом сервере.
