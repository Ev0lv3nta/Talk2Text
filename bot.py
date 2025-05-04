import asyncio # Оставляем, т.к. python-telegram-bot его использует
import os
import logging
from dotenv import load_dotenv
# --- Добавленные импорты ---
from pydub import AudioSegment
import io
from telegram import Update, Audio # Добавлен Audio
from telegram.constants import ParseMode # Может понадобиться для форматирования
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    ConversationHandler, # Добавлен ConversationHandler
)
# --- Оригинальные импорты Gemini ---
from google import genai
from google.genai import types

# --- Загрузка переменных окружения ---
load_dotenv()

# --- Настройка логирования ---
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logging.getLogger("httpx").setLevel(logging.WARNING) # Уменьшим спам

# --- Константы для ConversationHandler (новое) ---
ASKING_VOICE_FOR_CONVERSION = 1

# --- Чтение переменных окружения ---
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
LOG_CHANNEL_ID = os.getenv("LOG_CHANNEL_ID")

if not all([TELEGRAM_BOT_TOKEN, GEMINI_API_KEY, LOG_CHANNEL_ID]):
    logging.critical("CRITICAL: Required environment variables are not set.")
    raise EnvironmentError("Required environment variables are not set.")

# --- Инициализация клиента Gemini (КАК В САМОМ ПЕРВОМ КОДЕ) ---
try:
    client = genai.Client(api_key=GEMINI_API_KEY)
    if client is None:
         raise ValueError("Gemini client initialization returned None.")
    logging.info("Gemini client initialized successfully using genai.Client().")
except Exception as e:
    logging.critical(f"CRITICAL: Failed to initialize Gemini client: {e}")
    raise

# --- Функции ---

# --- Функция log_to_channel (ИЗ ОРИГИНАЛЬНОГО КОДА) ---
async def log_to_channel(update: Update, context: ContextTypes.DEFAULT_TYPE, response_text: str = None):
    # (Код этой функции взят из твоего второго сообщения, он чуть полнее чем в первом)
    if not update.message:
        logging.warning("log_to_channel called without update.message")
        return
    try:
        await context.bot.forward_message(
            chat_id=LOG_CHANNEL_ID,
            from_chat_id=update.message.chat_id,
            message_id=update.message.message_id
        )
        if response_text:
            user_info = update.message.from_user
            log_prefix = f"Ответ бота для {user_info.full_name} (ID: {user_info.id})"
            max_len = 4096
            if len(response_text) > max_len:
                response_text = response_text[:max_len-len("... (обрезано)")] + "... (обрезано)"
            await context.bot.send_message(
                chat_id=LOG_CHANNEL_ID,
                text=f"{log_prefix}:\n\n{response_text}"
            )
    except Exception as e:
        logging.error(f"Log channel error: {e}. Update: {update.to_dict()}")

# --- Функция start (ИЗ ОРИГИНАЛЬНОГО КОДА, чуть дополнено описание) ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет! Я могу:\n"
        "- Транскрибировать и суммировать голосовые (OGG).\n"
        "- Анализировать видеосообщения (кругляшки).\n"
        "- Суммировать текст.\n"
        "- Конвертировать голосовые в MP3 (используй команду /convert)." # Добавлено описание новой команды
        )
    # await log_to_channel(update, context) # Логируем если нужно

# --- Функция handle_voice (ИЗ ОРИГИНАЛЬНОГО КОДА, БЕЗ ИЗМЕНЕНИЙ ЛОГИКИ) ---
async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    voice = update.message.voice
    user_id = update.message.from_user.id
    processing_msg = await update.message.reply_text("🧠 Обрабатываю голосовое...", reply_to_message_id=update.message.message_id)
    path = f"voice_{user_id}_{voice.file_unique_id}.ogg" # Добавим user_id
    logging.info(f"Handling voice from user {user_id}")
    try:
        file = await context.bot.get_file(voice.file_id)
        await file.download_to_drive(path)
        with open(path, "rb") as f:
            audio = f.read()

        # Используем вызовы как в оригинале
        tr = client.models.generate_content(
            model="gemini-2.0-flash", # Твоя модель
            contents=["Сделай транскрипт аудио", types.Part.from_bytes(data=audio, mime_type="audio/ogg")],
            # config=types.GenerateContentConfig(max_output_tokens=800) # Если нужен конфиг
        )
        sm = client.models.generate_content(
            model="gemini-2.0-flash", # Твоя модель
            contents=["Сделай краткое содержание аудио", types.Part.from_bytes(data=audio, mime_type="audio/ogg")],
            # config=types.GenerateContentConfig(max_output_tokens=600) # Если нужен конфиг
        )
        text = f"📄 Транскрипт:\n{tr.text}\n\n📌 Содержание:\n{sm.text}"
        await processing_msg.edit_text(text) # Редактируем сообщение
        await log_to_channel(update, context, text)
    except Exception as e:
        logging.error(f"Error in handle_voice for user {user_id}: {e}", exc_info=True)
        await processing_msg.edit_text(f"Произошла ошибка при обработке голосового: {e}")
        await log_to_channel(update, context, f"Ошибка handle_voice: {e}")
    finally:
        if os.path.exists(path):
            os.remove(path)

# --- Функция handle_video_note (ИЗ ОРИГИНАЛЬНОГО КОДА, БЕЗ ИЗМЕНЕНИЙ ЛОГИКИ) ---
async def handle_video_note(update: Update, context: ContextTypes.DEFAULT_TYPE):
    video = update.message.video_note
    user_id = update.message.from_user.id
    processing_msg = await update.message.reply_text("🧠 Анализирую видеосообщение...", reply_to_message_id=update.message.message_id)
    path = f"video_{user_id}_{video.file_unique_id}.mp4" # Добавим user_id
    logging.info(f"Handling video_note from user {user_id}")
    try:
        file = await context.bot.get_file(video.file_id)
        await file.download_to_drive(path)
        with open(path, "rb") as f:
            video_bytes = f.read()

        # Используем вызовы как в оригинале
        tr = client.models.generate_content(
            model="gemini-2.0-flash", # Твоя модель
            contents=["Сделай транскрипт аудио дорожки", types.Part.from_bytes(data=video_bytes, mime_type="video/mp4")],
            # config=types.GenerateContentConfig(max_output_tokens=800)
        )
        visual = client.models.generate_content(
            model="gemini-2.0-flash", # Твоя модель
            contents=["Опиши визуальные детали", types.Part.from_bytes(data=video_bytes, mime_type="video/mp4")],
            # config=types.GenerateContentConfig(max_output_tokens=800)
        )
        sm = client.models.generate_content(
            model="gemini-2.0-flash", # Твоя модель
            contents=["Сделай общее содержание", types.Part.from_bytes(data=video_bytes, mime_type="video/mp4")],
            # config=types.GenerateContentConfig(max_output_tokens=800)
        )
        text = f"📄 Аудио:\n{tr.text}\n\n🖼️ Визуал:\n{visual.text}\n\n📌 Содержание:\n{sm.text}"
        await processing_msg.edit_text(text) # Редактируем сообщение
        await log_to_channel(update, context, text)
    except Exception as e:
        logging.error(f"Error in handle_video_note for user {user_id}: {e}", exc_info=True)
        await processing_msg.edit_text(f"Произошла ошибка при обработке видео: {e}")
        await log_to_channel(update, context, f"Ошибка handle_video_note: {e}")
    finally:
        if os.path.exists(path):
            os.remove(path)

# --- Функция handle_text (ИЗ ОРИГИНАЛЬНОГО КОДА, БЕЗ ИЗМЕНЕНИЙ ЛОГИКИ) ---
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user_id = update.message.from_user.id
    processing_msg = await update.message.reply_text("🧠 Анализирую текст...", reply_to_message_id=update.message.message_id)
    logging.info(f"Handling text from user {user_id}")
    try:
        # Используем вызовы как в оригинале
        sm = client.models.generate_content(
            model="gemini-2.0-flash", # Твоя модель
            contents=["Сделай краткое содержание текста", text],
            # config=types.GenerateContentConfig(max_output_tokens=600)
        )
        reply = f"📌 Содержание:\n{sm.text}"
        await processing_msg.edit_text(reply) # Редактируем сообщение
        await log_to_channel(update, context, reply)
    except Exception as e:
        logging.error(f"Error in handle_text for user {user_id}: {e}", exc_info=True)
        await processing_msg.edit_text(f"Произошла ошибка при обработке текста: {e}")
        await log_to_channel(update, context, f"Ошибка handle_text: {e}")

# --- НОВЫЕ Функции для конвертации OGG в MP3 ---

async def ask_for_voice_to_convert(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Запрашивает у пользователя голосовое сообщение для конвертации."""
    await update.message.reply_text("Хорошо! Теперь отправь мне голосовое сообщение (формат .ogg), которое нужно конвертировать в MP3.")
    return ASKING_VOICE_FOR_CONVERSION

async def convert_ogg_to_mp3_and_reply(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обрабатывает полученное голосовое, конвертирует и отправляет MP3."""
    # (Код этой функции берем из предыдущих рабочих версий)
    voice = update.message.voice
    if not voice:
        await update.message.reply_text("Это не голосовое сообщение. Пожалуйста, отправь именно голосовое или нажми /cancel.")
        return ASKING_VOICE_FOR_CONVERSION

    file_id = voice.file_id
    unique_id = voice.file_unique_id
    user_id = update.message.from_user.id

    ogg_path = f"voice_conv_{user_id}_{unique_id}.ogg" # Немного изменим имя файла
    mp3_path = f"voice_conv_{user_id}_{unique_id}.mp3"

    processing_msg = await update.message.reply_text("⏳ Конвертирую OGG в MP3...", reply_to_message_id=update.message.message_id)
    logging.info(f"Starting conversion for user {user_id}, file_id {file_id}")

    try:
        voice_file = await context.bot.get_file(file_id)
        await voice_file.download_to_drive(ogg_path)
        logging.info(f"Downloaded OGG file for conversion: {ogg_path}")

        audio = AudioSegment.from_ogg(ogg_path)
        logging.info(f"Loaded OGG for conversion, duration: {len(audio) / 1000.0}s")
        audio.export(mp3_path, format="mp3")
        logging.info(f"Exported MP3 file: {mp3_path}")

        with open(mp3_path, "rb") as mp3_file:
            await context.bot.send_audio(
                chat_id=update.message.chat_id,
                audio=mp3_file,
                title=f"Converted_{unique_id}.mp3",
                caption="✅ Готово! Вот ваш MP3 файл.",
                reply_to_message_id=update.message.message_id
            )
        await processing_msg.delete()
        logging.info(f"Sent converted MP3 file to user {user_id}")
        await log_to_channel(update, context, response_text="[Пользователь получил MP3 файл после конвертации]")

    except FileNotFoundError:
        logging.error(f"FFmpeg/FFprobe not found during conversion for user {user_id}.")
        await processing_msg.edit_text("🚫 Ошибка: Не найден FFmpeg. Убедитесь, что он установлен на сервере.")
        await log_to_channel(update, context, response_text="[Ошибка конвертации: FFmpeg не найден]")
    except Exception as e:
        logging.error(f"Error converting OGG to MP3 for user {user_id}: {e}", exc_info=True)
        await processing_msg.edit_text(f"🚫 Произошла ошибка во время конвертации: {e}")
        await log_to_channel(update, context, response_text=f"[Ошибка конвертации: {e}]")
    finally:
        if os.path.exists(ogg_path):
            os.remove(ogg_path)
            logging.info(f"Removed temporary conversion OGG file: {ogg_path}")
        if os.path.exists(mp3_path):
            os.remove(mp3_path)
            logging.info(f"Removed temporary conversion MP3 file: {mp3_path}")

    return ConversationHandler.END

async def cancel_conversion(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Отменяет операцию конвертации."""
    await update.message.reply_text("Операция конвертации отменена.")
    logging.info(f"Conversion cancelled by user {update.message.from_user.id}")
    return ConversationHandler.END

# --- Функция main (ДОБАВЛЕН ConversationHandler) ---
def main():
    """Запускает бота."""
    logging.info("Starting bot application...")
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # --- НОВЫЙ Conversation Handler для /convert ---
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("convert", ask_for_voice_to_convert)],
        states={
            ASKING_VOICE_FOR_CONVERSION: [MessageHandler(filters.VOICE, convert_ogg_to_mp3_and_reply)]
        },
        fallbacks=[CommandHandler("cancel", cancel_conversion)],
    )
    # Добавляем обработчик диалога ПЕРЕД основными обработчиками медиа
    app.add_handler(conv_handler)

    # --- ОРИГИНАЛЬНЫЕ обработчики ---
    app.add_handler(CommandHandler("start", start))
    # Важно: Эти обработчики не должны ловить голосовые, пока активен диалог конвертации
    # ConversationHandler имеет более высокий приоритет, так что это должно работать.
    # Если возникнут проблемы, можно будет добавить проверку состояния в handle_voice.
    app.add_handler(MessageHandler(filters.VOICE & ~filters.COMMAND, handle_voice))
    app.add_handler(MessageHandler(filters.VIDEO_NOTE & ~filters.COMMAND, handle_video_note))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    logging.info("Bot polling started.")
    app.run_polling()

# --- Запуск main ---
if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logging.critical(f"CRITICAL: Unhandled exception in __main__: {e}", exc_info=True)
