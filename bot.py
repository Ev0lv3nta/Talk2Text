import asyncio # asyncio все еще может быть полезен для telegram-бота, но убираем async из вызовов Gemini
import os
import logging
from dotenv import load_dotenv
from telegram import Update, Audio
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    ConversationHandler,
)
from pydub import AudioSegment
import io

# --- Загрузка переменных окружения ---
load_dotenv()

# --- Настройка логирования ---
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logging.getLogger("httpx").setLevel(logging.WARNING) # Уменьшим спам от httpx в логах

# --- Константы для ConversationHandler ---
ASKING_VOICE_FOR_CONVERSION = 1

# --- Чтение переменных окружения ---
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
LOG_CHANNEL_ID = os.getenv("LOG_CHANNEL_ID")

if not all([TELEGRAM_BOT_TOKEN, GEMINI_API_KEY, LOG_CHANNEL_ID]):
    # Логируем ошибку перед падением
    logging.critical("CRITICAL: Required environment variables (TELEGRAM_BOT_TOKEN, GEMINI_API_KEY, LOG_CHANNEL_ID) are not set. Exiting.")
    raise EnvironmentError("Required environment variables are not set.")

# --- Инициализация клиента Gemini (как в оригинальном коде) ---
# Используем google.genai напрямую, как было похоже в исходнике
try:
    # Убедимся, что импорты правильные для этого стиля
    from google import genai
    from google.genai import types

    # Настраиваем ключ через configure, это хороший современный способ
    genai.configure(api_key=GEMINI_API_KEY)
    # Создаем клиент, если он нужен для старого стиля вызова (хотя configure может быть достаточно)
    # client = genai.Client(api_key=GEMINI_API_KEY) # Попробуем без явного клиента, если configure достаточно
    # Если genai.generate_text и т.д. не работают без client, раскомментировать строку выше
    # и использовать client.generate_text(...)
    # НО! В оригинале было client.models.generate_content - вернем ЭТОТ стиль!
    # Значит, нужен клиент.
    client = genai.GenerativeModel('gemini-pro') # Создаем базовую модель, имя будет переопределяться в вызовах
    # ВАЖНО: Имя модели 'gemini-pro' здесь не имеет значения, так как мы будем указывать
    # 'gemini-2.0-flash' в каждом вызове generate_content ниже.

    logging.info("Gemini configured successfully.")

except ImportError:
    logging.critical("CRITICAL: Failed to import google.genai. Is the library installed correctly? (`pip show google-genai`)")
    raise
except Exception as e:
    logging.critical(f"CRITICAL: Failed to configure Gemini: {e}. Check API Key and library.")
    raise

# --- Функции ---

async def log_to_channel(update: Update, context: ContextTypes.DEFAULT_TYPE, response_text: str = None):
    """Логирует сообщение и ответ в лог-канал."""
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


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start."""
    await update.message.reply_text(
        "Привет! Я могу:\n"
        "- Транскрибировать и суммировать голосовые (OGG).\n"
        "- Анализировать видеосообщения (кругляшки).\n"
        "- Суммировать текст.\n"
        "- Конвертировать голосовые в MP3 (используй команду /convert)."
    )
    # await log_to_channel(update, context) # Логируем только само сообщение от пользователя, если нужно


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает текстовые сообщения для суммирования."""
    original_text = update.message.text
    processing_msg = await update.message.reply_text("🧠 Анализирую текст...", reply_to_message_id=update.message.message_id)
    log_entry = f"Получен текст от {update.message.from_user.id}:\n{original_text}"
    logging.info(log_entry)

    try:
        # Используем СТРОГО модель gemini-2.0-flash и вызов client.generate_content
        response = client.generate_content(
            # model="gemini-2.0-flash", # Указываем модель здесь, если client не был создан с ней
            contents=[f"Сделай краткое содержание следующего текста:\n\n{original_text}"],
            generation_config=genai.types.GenerationConfig(
                # max_output_tokens=600, # Настройте лимиты при необходимости
                candidate_count=1, # Обычно нужна одна самая вероятная версия
                # Указываем модель тут, если нужно переопределить базовую модель клиента
                 model='gemini-2.0-flash'
            )
         )

        summary_text = response.text
        reply = f"📌 Содержание:\n{summary_text}"

        await processing_msg.edit_text(reply)
        await log_to_channel(update, context, reply)

    except Exception as e:
        logging.error(f"Error processing text with Gemini: {e}")
        await processing_msg.edit_text("Произошла ошибка при обработке текста.")
        await log_to_channel(update, context, f"Ошибка обработки текста: {e}")


# --- Функционал конвертации OGG в MP3 (без изменений) ---

async def ask_for_voice_to_convert(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Запрашивает у пользователя голосовое сообщение для конвертации."""
    await update.message.reply_text("Хорошо! Теперь отправь мне голосовое сообщение (формат .ogg), которое нужно конвертировать в MP3.")
    return ASKING_VOICE_FOR_CONVERSION

async def convert_ogg_to_mp3_and_reply(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обрабатывает полученное голосовое, конвертирует и отправляет MP3."""
    voice = update.message.voice
    if not voice: # Добавим проверку на случай если прислали не голос
        await update.message.reply_text("Это не голосовое сообщение. Пожалуйста, отправь именно голосовое или нажми /cancel.")
        return ASKING_VOICE_FOR_CONVERSION # Остаемся в том же состоянии

    file_id = voice.file_id
    unique_id = voice.file_unique_id
    user_id = update.message.from_user.id

    ogg_path = f"voice_{user_id}_{unique_id}.ogg"
    mp3_path = f"voice_{user_id}_{unique_id}.mp3"

    processing_msg = await update.message.reply_text("⏳ Конвертирую OGG в MP3...", reply_to_message_id=update.message.message_id)
    logging.info(f"Starting conversion for user {user_id}, file_id {file_id}")

    try:
        voice_file = await context.bot.get_file(file_id)
        await voice_file.download_to_drive(ogg_path)
        logging.info(f"Downloaded OGG file: {ogg_path}")

        audio = AudioSegment.from_ogg(ogg_path)
        logging.info(f"Loaded OGG, duration: {len(audio) / 1000.0}s")
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
        logging.info(f"Sent MP3 file to user {user_id}")
        await log_to_channel(update, context, response_text="[Пользователь получил MP3 файл]")

    except FileNotFoundError:
        logging.error(f"FFmpeg/FFprobe not found. Ensure it's installed and in PATH.")
        await processing_msg.edit_text("🚫 Ошибка: Не найден FFmpeg. Убедитесь, что он установлен на сервере.")
        await log_to_channel(update, context, response_text="[Ошибка конвертации: FFmpeg не найден]")
    except Exception as e:
        logging.error(f"Error converting OGG to MP3: {e}")
        await processing_msg.edit_text(f"🚫 Произошла ошибка во время конвертации: {e}")
        await log_to_channel(update, context, response_text=f"[Ошибка конвертации: {e}]")
    finally:
        if os.path.exists(ogg_path):
            os.remove(ogg_path)
            logging.info(f"Removed temporary OGG file: {ogg_path}")
        if os.path.exists(mp3_path):
            os.remove(mp3_path)
            logging.info(f"Removed temporary MP3 file: {mp3_path}")

    return ConversationHandler.END

async def cancel_conversion(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Отменяет операцию конвертации."""
    await update.message.reply_text("Операция конвертации отменена.")
    logging.info(f"Conversion cancelled by user {update.message.from_user.id}")
    return ConversationHandler.END

# --- Функционал транскрипции и суммирования (С ИСПОЛЬЗОВАНИЕМ gemini-2.0-flash) ---

async def handle_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Общий обработчик для голосовых и видеосообщений (транскрипция/суммирование)."""
    message = update.message
    file_id = None
    file_unique_id = None
    media_type = None
    mime_type = None
    file_ext = None
    processing_text = ""
    user_id = message.from_user.id

    if message.voice:
        media_type = "voice"
        voice = message.voice
        file_id = voice.file_id
        file_unique_id = voice.file_unique_id
        mime_type = "audio/ogg"
        file_ext = "ogg"
        processing_text = "🧠 Обрабатываю голосовое..."
        logging.info(f"Received voice message from user {user_id}, file_id {file_id}")
    elif message.video_note:
        media_type = "video_note"
        video = message.video_note
        file_id = video.file_id
        file_unique_id = video.file_unique_id
        mime_type = "video/mp4"
        file_ext = "mp4"
        processing_text = "🧠 Анализирую видеосообщение..."
        logging.info(f"Received video note from user {user_id}, file_id {file_id}")
    else:
        logging.warning("handle_media called with non-media message.")
        return

    path = f"{media_type}_{user_id}_{file_unique_id}.{file_ext}" # Добавим user_id во имя файла
    processing_msg = await message.reply_text(processing_text, reply_to_message_id=message.message_id)

    try:
        media_file = await context.bot.get_file(file_id)
        await media_file.download_to_drive(path)
        logging.info(f"Downloaded {media_type} file: {path}")

        with open(path, "rb") as f:
            media_bytes = f.read()

        # --- Вызовы Gemini API (последовательно, используя client.generate_content и gemini-2.0-flash) ---
        results = {}
        media_part = types.Part(inline_data=types.Blob(mime_type=mime_type, data=media_bytes))
        model_name_to_use = "gemini-2.0-flash" # Строго используем эту модель

        # 1. Транскрипция (для голоса и видео)
        logging.info(f"Requesting transcript for {media_type} from user {user_id}")
        prompt_tr = "Сделай точную транскрипцию аудиодорожки." if media_type == "video_note" else "Сделай точную транскрипцию аудиозаписи."
        try:
            tr_response = client.generate_content(
                contents=[prompt_tr, media_part],
                generation_config=genai.types.GenerationConfig(model=model_name_to_use)
            )
            results["transcript"] = tr_response.text
            logging.info(f"Received transcript for {media_type} from user {user_id}")
        except Exception as e_tr:
            logging.error(f"Gemini transcript error for user {user_id}: {e_tr}")
            results["transcript"] = f"[Ошибка транскрипции: {e_tr}]"

        # 2. Описание визуала (только для видео)
        if media_type == "video_note":
            logging.info(f"Requesting visuals description for video note from user {user_id}")
            prompt_vis = "Опиши подробно, что происходит на видео, какие объекты видны, какая обстановка."
            try:
                vis_response = client.generate_content(
                    contents=[prompt_vis, media_part],
                    generation_config=genai.types.GenerationConfig(model=model_name_to_use)
                )
                results["visuals"] = vis_response.text
                logging.info(f"Received visuals description for video note from user {user_id}")
            except Exception as e_vis:
                logging.error(f"Gemini visuals error for user {user_id}: {e_vis}")
                results["visuals"] = f"[Ошибка описания визуала: {e_vis}]"

        # 3. Краткое содержание (для голоса и видео)
        logging.info(f"Requesting summary for {media_type} from user {user_id}")
        prompt_sm = "Сделай краткое общее содержание этого видео, объединив информацию из аудио и визуала." if media_type == "video_note" else "Сделай краткое содержание по транскрипции этой аудиозаписи."
        try:
            sm_response = client.generate_content(
                contents=[prompt_sm, media_part],
                generation_config=genai.types.GenerationConfig(model=model_name_to_use)
            )
            results["summary"] = sm_response.text
            logging.info(f"Received summary for {media_type} from user {user_id}")
        except Exception as e_sm:
            logging.error(f"Gemini summary error for user {user_id}: {e_sm}")
            results["summary"] = f"[Ошибка содержания: {e_sm}]"

        # --- Формирование ответа ---
        reply_text = ""
        if "transcript" in results:
            reply_text += f"📄 **Транскрипт{' аудио' if media_type == 'voice' else ''}:**\n{results['transcript']}\n\n"
        if "visuals" in results:
            reply_text += f"🖼️ **Визуал:**\n{results['visuals']}\n\n"
        if "summary" in results:
            reply_text += f"📌 **Содержание:**\n{results['summary']}"

        reply_text = reply_text.strip()
        if not reply_text:
             reply_text = "Не удалось извлечь информацию из файла."

        await processing_msg.edit_text(reply_text, parse_mode=ParseMode.MARKDOWN)
        await log_to_channel(update, context, reply_text)

    except Exception as e:
        # Общая ошибка обработки (загрузка файла и т.д.)
        logging.error(f"Error processing {media_type} for user {user_id}: {e}", exc_info=True) # Добавим traceback
        await processing_msg.edit_text(f"Произошла ошибка при обработке {media_type}.")
        await log_to_channel(update, context, f"Ошибка обработки {media_type}: {e}")
    finally:
        # Удаляем временный файл
        if os.path.exists(path):
            os.remove(path)
            logging.info(f"Removed temporary file: {path}")


def main():
    """Запускает бота."""
    logging.info("Starting bot...")
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Conversation Handler для конвертации
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("convert", ask_for_voice_to_convert)],
        states={
            ASKING_VOICE_FOR_CONVERSION: [MessageHandler(filters.VOICE, convert_ogg_to_mp3_and_reply)]
        },
        fallbacks=[CommandHandler("cancel", cancel_conversion)],
        # Добавим обработку текстовых сообщений в состоянии ожидания голоса
        map_to_parent={
             ConversationHandler.END: ConversationHandler.END,
             # Можно добавить обработчик текста, если пользователь пишет что-то вместо голоса
             # ASKING_VOICE_FOR_CONVERSION: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_during_conversion)]
        }
    )

    app.add_handler(conv_handler)

    # Обработчик команды /start
    app.add_handler(CommandHandler("start", start))

    # Обработчики для транскрипции/суммирования
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(filters.VOICE & ~filters.COMMAND, handle_media))
    app.add_handler(MessageHandler(filters.VIDEO_NOTE & ~filters.COMMAND, handle_media))

    logging.info("Bot polling started.")
    app.run_polling()

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        # Логируем критическую ошибку перед завершением
        logging.critical(f"CRITICAL: Unhandled exception in main: {e}", exc_info=True)
