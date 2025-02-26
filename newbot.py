from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import cv2
import logging

def decode_barcode(image_path):
    try:
        image = cv2.imread(image_path)
        detector = cv2.barcode_BarcodeDetector()
        retval, decoded_info, decoded_type, points = detector.detectAndDecode(image)
        if retval:
            return decoded_info[0]
        return None
    except Exception as e:
        logger.error(f"Ошибка при обработке изображения: {e}")
        return None


# Настройка логирования для вывода информации в консоль
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Функция для обработки изображения и распознавания штрихкода

# Обработчик команды /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_message = (
        "Привет! Я бот для распознавания штрихкодов. 📸\n"
        "Просто отправь мне фотографию штрихкода, и я расшифрую его для тебя.\n"
        "Попробуй отправить фото сейчас!"
    )
    await update.message.reply_text(welcome_message)

# Обработчик для загруженных фотографий
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        # Скачиваем фото
        file = await update.message.photo[-1].get_file()
        await file.download_to_drive('barcode.jpg')
        logger.info("Фотография успешно загружена.")

        # Распознаем штрихкод
        barcode_data = decode_barcode('barcode.jpg')
        if barcode_data:
            await update.message.reply_text(f"✅ Штрихкод успешно распознан: {barcode_data}")
            logger.info(f"Распознанный штрихкод: {barcode_data}")
        else:
            await update.message.reply_text("❌ Не удалось распознать штрихкод. Попробуйте снова.")
            logger.warning("Штрихкод не распознан.")
    except Exception as e:
        await update.message.reply_text("❌ Произошла ошибка при обработке фотографии. Попробуйте снова.")
        logger.error(f"Ошибка: {e}")

# Основная функция для запуска бота
async def main():
    token = "8081704880:AAE4uCB8kqBj9SCdQuYl8bsFlSWefUz36aU"  # Замените на ваш токен
    application = Application.builder().token(token).build()

    # Добавляем обработчики команд и сообщений
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))

    # Уведомление в консоль о запуске бота
    logger.info("Бот запущен и готов к работе!")

    # Запуск бота
    await application.run_polling()

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())