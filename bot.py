import asyncio
import os
import logging
from dotenv import load_dotenv
from google import genai
from google.genai import types
from telegram import Update, Audio # Добавлен импорт Audio
from telegram.constants import ParseMode # Добавлен импорт ParseMode для возможного форматирования
from telegram.ext import filters
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, ConversationHandler # Добавлен ConversationHandler
from pydub import AudioSegment # Добавлен импорт pydub
import io # Добавлен импорт io

load_dotenv()

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

# --- Константы для ConversationHandler ---
ASKING_VOICE_FOR_CONVERSION = 1

# --- Переменные окружения ---
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
LOG_CHANNEL_ID = os.getenv("LOG_CHANNEL_ID")

if not all([TELEGRAM_BOT_TOKEN, GEMINI_API_KEY, LOG_CHANNEL_ID]):
    raise EnvironmentError("Required environment variables are not set.")

# --- Инициализация Gemini ---
# Убедитесь, что genai правильно импортирован и настроен
try:
    genai.configure(api_key=GEMINI_API_KEY)
    # Используем модель, которая подходит для ваших задач
    # 'gemini-pro' или 'gemini-1.5-flash' если нужна последняя версия
    # 'gemini-1.0-pro' может быть более стабильной опцией для генерации текста
    gemini_model_text = "gemini-1.0-pro" # Модель для текста
    gemini_model_multimodal = "gemini-1.5-flash" # Модель для аудио/видео

    # Создаем экземпляры моделей (опционально, можно вызывать generate_content напрямую)
    text_model = genai.GenerativeModel(gemini_model_text)
    multimodal_model = genai.GenerativeModel(gemini_model_multimodal)

except AttributeError:
    logging.error("Could not configure genai. Check google-genai library version and API key.")
    # В старых версиях могло быть client = genai.Client(api_key=...)
    # Но сейчас рекомендуется genai.configure() и genai.GenerativeModel()
    # Если используете старую версию google-generativeai, код ниже может потребовать адаптации
    multimodal_model = None # или fallback
    text_model = None

async def log_to_channel(update: Update, context: ContextTypes.DEFAULT_TYPE, response_text: str = None):
    # Проверяем, есть ли вообще сообщение для пересылки (например, для /start)
    if not update.message:
        logging.warning("log_to_channel called without update.message")
        return
    try:
        # Пересылаем исходное сообщение пользователя
        await context.bot.forward_message(
            chat_id=LOG_CHANNEL_ID,
            from_chat_id=update.message.chat_id,
            message_id=update.message.message_id
        )
        # Если был сгенерирован ответ бота, отправляем его
        if response_text:
            user_info = update.message.from_user
            log_prefix = f"Ответ бота для {user_info.full_name} (ID: {user_info.id})"
            # Убедимся, что текст не слишком длинный для одного сообщения
            max_len = 4096
            if len(response_text) > max_len:
                 # Простая обрезка, можно разбить на части если нужно
                response_text = response_text[:max_len-len("... (обрезано)")] + "... (обрезано)"

            await context.bot.send_message(
                chat_id=LOG_CHANNEL_ID,
                text=f"{log_prefix}:\n\n{response_text}"
            )
    except Exception as e:
        logging.error(f"Log channel error: {e}. Update: {update.to_dict()}")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет! Я могу:\n"
        "- Транскрибировать и суммировать голосовые (OGG).\n"
        "- Анализировать видеосообщения (кругляшки).\n"
        "- Суммировать текст.\n"
        "- Конвертировать голосовые в MP3 (используй команду /convert)."
        )
    # Логируем только команду /start, без ответа бота в данном случае
    # await log_to_channel(update, context)

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not text_model:
        await update.message.reply_text("Ошибка: Модель Gemini для текста не инициализирована.")
        return

    original_text = update.message.text
    processing_msg = await update.message.reply_text("🧠 Анализирую текст...", reply_to_message_id=update.message.message_id)

    try:
        prompt = f"Сделай краткое содержание следующего текста:\n\n{original_text}"
        response = await text_model.generate_content_async(prompt) # Используем async

        summary_text = response.text
        reply = f"📌 Содержание:\n{summary_text}"

        await processing_msg.edit_text(reply) # Редактируем сообщение "Анализирую..."
        await log_to_channel(update, context, reply)

    except Exception as e:
        logging.error(f"Error processing text with Gemini: {e}")
        await processing_msg.edit_text("Произошла ошибка при обработке текста.")
        await log_to_channel(update, context, f"Ошибка обработки текста: {e}")

# --- Функционал конвертации OGG в MP3 ---

async def ask_for_voice_to_convert(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Запрашивает у пользователя голосовое сообщение для конвертации."""
    await update.message.reply_text("Хорошо! Теперь отправь мне голосовое сообщение (формат .ogg), которое нужно конвертировать в MP3.")
    return ASKING_VOICE_FOR_CONVERSION # Переходим в состояние ожидания голосового

async def convert_ogg_to_mp3_and_reply(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обрабатывает полученное голосовое, конвертирует и отправляет MP3."""
    voice = update.message.voice
    file_id = voice.file_id
    unique_id = voice.file_unique_id
    user_id = update.message.from_user.id

    ogg_path = f"voice_{user_id}_{unique_id}.ogg"
    mp3_path = f"voice_{user_id}_{unique_id}.mp3"

    processing_msg = await update.message.reply_text("⏳ Конвертирую OGG в MP3...", reply_to_message_id=update.message.message_id)

    try:
        voice_file = await context.bot.get_file(file_id)
        await voice_file.download_to_drive(ogg_path)
        logging.info(f"Downloaded OGG file: {ogg_path}")

        # Конвертация с помощью pydub
        audio = AudioSegment.from_ogg(ogg_path)
        logging.info(f"Loaded OGG, duration: {len(audio) / 1000.0}s")
        audio.export(mp3_path, format="mp3")
        logging.info(f"Exported MP3 file: {mp3_path}")

        # Отправка MP3 файла как аудио
        with open(mp3_path, "rb") as mp3_file:
            await context.bot.send_audio(
                chat_id=update.message.chat_id,
                audio=mp3_file,
                title=f"Converted_{unique_id}.mp3", # Имя файла при отправке
                caption="✅ Готово! Вот ваш MP3 файл.",
                reply_to_message_id=update.message.message_id
            )
        await processing_msg.delete() # Удаляем сообщение "Конвертирую..."
        logging.info(f"Sent MP3 file to user {user_id}")
        await log_to_channel(update, context, response_text="[Пользователь получил MP3 файл]") # Логируем действие

    except FileNotFoundError:
        logging.error(f"FFmpeg/FFprobe not found. Ensure it's installed and in PATH.")
        await processing_msg.edit_text("🚫 Ошибка: Не найден FFmpeg. Убедитесь, что он установлен на сервере.")
        await log_to_channel(update, context, response_text="[Ошибка конвертации: FFmpeg не найден]")
    except Exception as e:
        logging.error(f"Error converting OGG to MP3: {e}")
        await processing_msg.edit_text(f"🚫 Произошла ошибка во время конвертации: {e}")
        await log_to_channel(update, context, response_text=f"[Ошибка конвертации: {e}]")
    finally:
        # Удаляем временные файлы
        if os.path.exists(ogg_path):
            os.remove(ogg_path)
            logging.info(f"Removed temporary OGG file: {ogg_path}")
        if os.path.exists(mp3_path):
            os.remove(mp3_path)
            logging.info(f"Removed temporary MP3 file: {mp3_path}")

    return ConversationHandler.END # Завершаем диалог конвертации

async def cancel_conversion(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Отменяет операцию конвертации."""
    await update.message.reply_text("Операция конвертации отменена.")
    return ConversationHandler.END

# --- Функционал транскрипции и суммирования (существующий) ---

async def handle_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Общий обработчик для голосовых и видеосообщений (транскрипция/суммирование)."""
    if not multimodal_model:
        await update.message.reply_text("Ошибка: Модель Gemini для аудио/видео не инициализирована.")
        return

    message = update.message
    file_id = None
    file_unique_id = None
    media_type = None
    mime_type = None
    file_ext = None
    processing_text = ""

    if message.voice:
        media_type = "voice"
        voice = message.voice
        file_id = voice.file_id
        file_unique_id = voice.file_unique_id
        mime_type = "audio/ogg"
        file_ext = "ogg"
        processing_text = "🧠 Обрабатываю голосовое..."
    elif message.video_note:
        media_type = "video_note"
        video = message.video_note
        file_id = video.file_id
        file_unique_id = video.file_unique_id
        mime_type = "video/mp4" # Telegram video notes are mp4
        file_ext = "mp4"
        processing_text = "🧠 Анализирую видеосообщение..."
    else:
        logging.warning("handle_media called with non-media message.")
        return # Не должно вызываться для других типов, но на всякий случай

    path = f"{media_type}_{file_unique_id}.{file_ext}"
    processing_msg = await message.reply_text(processing_text, reply_to_message_id=message.message_id)

    try:
        media_file = await context.bot.get_file(file_id)
        await media_file.download_to_drive(path)
        logging.info(f"Downloaded {media_type} file: {path}")

        with open(path, "rb") as f:
            media_bytes = f.read()

        # Используем новую асинхронную версию API, если возможно
        tasks = []
        prompts = {}

        if media_type == "voice":
            prompts["transcript"] = "Сделай точную транскрипцию аудиозаписи."
            prompts["summary"] = "Сделай краткое содержание по транскрипции этой аудиозаписи."
        elif media_type == "video_note":
            prompts["transcript"] = "Сделай точную транскрипцию аудиодорожки из этого видео."
            prompts["visuals"] = "Опиши подробно, что происходит на видео, какие объекты видны, какая обстановка."
            prompts["summary"] = "Сделай краткое общее содержание этого видео, объединив информацию из аудио и визуала."

        # Собираем задачи для асинхронного выполнения
        for key, prompt_text in prompts.items():
            # Создаем контент: текстовый промпт + байты медиа
            content = [prompt_text, types.Part(inline_data=types.Blob(mime_type=mime_type, data=media_bytes))]
            # Добавляем задачу генерации
            tasks.append(
                 multimodal_model.generate_content_async(
                    content,
                    # generation_config=genai.types.GenerationConfig(max_output_tokens=800) # Настройте лимиты по необходимости
                 )
            )

        # Ожидаем выполнения всех задач
        results = await asyncio.gather(*tasks)

        # Собираем результаты
        response_parts = {}
        idx = 0
        for key in prompts.keys():
            try:
                response_parts[key] = results[idx].text
            except Exception as e:
                logging.error(f"Error getting part '{key}' from Gemini response: {e} | Response: {results[idx]}")
                response_parts[key] = f"[Ошибка обработки части '{key}']"
            idx += 1

        # Формируем финальный текст ответа
        reply_text = ""
        if "transcript" in response_parts:
            reply_text += f"📄 **Транскрипт{' аудио' if media_type == 'voice' else ''}:**\n{response_parts['transcript']}\n\n"
        if "visuals" in response_parts:
            reply_text += f"🖼️ **Визуал:**\n{response_parts['visuals']}\n\n"
        if "summary" in response_parts:
            reply_text += f"📌 **Содержание:**\n{response_parts['summary']}"

        # Убираем лишние пробелы и переносы строк
        reply_text = reply_text.strip()
        if not reply_text:
             reply_text = "Не удалось извлечь информацию из файла."

        await processing_msg.edit_text(reply_text, parse_mode=ParseMode.MARKDOWN)
        await log_to_channel(update, context, reply_text)

    except Exception as e:
        logging.error(f"Error processing {media_type} with Gemini: {e}")
        await processing_msg.edit_text(f"Произошла ошибка при обработке {media_type}.")
        await log_to_channel(update, context, f"Ошибка обработки {media_type}: {e}")
    finally:
        # Удаляем временный файл
        if os.path.exists(path):
            os.remove(path)
            logging.info(f"Removed temporary file: {path}")


def main():
    """Запускает бота."""
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Conversation Handler для конвертации
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("convert", ask_for_voice_to_convert)],
        states={
            ASKING_VOICE_FOR_CONVERSION: [MessageHandler(filters.VOICE, convert_ogg_to_mp3_and_reply)]
        },
        fallbacks=[CommandHandler("cancel", cancel_conversion)],
    )

    app.add_handler(conv_handler)

    # Обработчик команды /start
    app.add_handler(CommandHandler("start", start))

    # Обработчики для транскрипции/суммирования (текст, голос, видео)
    # Важно: Эти обработчики не должны пересекаться с ConversationHandler
    # Поэтому используем ~filters.UpdateType.EDITED стандартные фильтры,
    # они не будут срабатывать внутри диалога конвертации.
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(filters.VOICE & ~filters.COMMAND, handle_media)) # Используем общий handle_media
    app.add_handler(MessageHandler(filters.VIDEO_NOTE & ~filters.COMMAND, handle_media)) # Используем общий handle_media

    logging.info("Starting bot polling...")
    app.run_polling()

if __name__ == "__main__":
    main()
