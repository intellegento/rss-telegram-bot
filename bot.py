from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackContext
import feedparser
import re
import os
from dotenv import load_dotenv

# Загружаем переменные окружения из .env файла
load_dotenv()

# Получаем API-ключ
TELEGRAM_API_KEY = os.getenv("TELEGRAM_API_KEY")

# Храним ключевые слова, просмотренные заголовки и интервалы
user_keywords = {}
seen_titles = {}
update_intervals = {}

# Функция для парсинга RSS
def parse_rss(url):
    feed = feedparser.parse(url)
    if feed.bozo:
        print(f"Ошибка при чтении RSS-ленты: {url}")
        return None
    return feed.entries[:10]

# Команда для отображения стартового меню
async def start(update: Update, context: CallbackContext) -> None:
    keyboard = [
        ["Установить ключевые слова", "Посмотреть ключевые слова"],
        ["Сбросить ключевые слова", "Установить интервал обновлений"],
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text(
        "Привет! Выберите действие:",
        reply_markup=reply_markup,
    )

# Обработчик текстовых сообщений
async def handle_message(update: Update, context: CallbackContext) -> None:
    text = update.message.text
    user_id = update.effective_user.id

    if context.user_data.get("awaiting_keywords"):
        # Обрабатываем установку ключевых слов
        user_keywords[user_id] = text.split()
        seen_titles[user_id] = set()
        context.user_data["awaiting_keywords"] = False
        await update.message.reply_text(f"Ключевые слова установлены: {', '.join(user_keywords[user_id])}")
    
    elif context.user_data.get("awaiting_interval"):
        # Обрабатываем установку интервала
        if text.isdigit():
            update_intervals[user_id] = int(text)
            context.user_data["awaiting_interval"] = False
            await update.message.reply_text(f"Интервал обновлений установлен: {update_intervals[user_id]} секунд.")
        else:
            await update.message.reply_text("Пожалуйста, введите числовое значение.")

    elif text == "Установить ключевые слова":
        # Начинаем процесс установки ключевых слов
        await update.message.reply_text("Введите ключевые слова через пробел:")
        context.user_data["awaiting_keywords"] = True

    elif text == "Посмотреть ключевые слова":
        # Показываем текущие ключевые слова
        if user_id in user_keywords and user_keywords[user_id]:
            keywords = ', '.join(user_keywords[user_id])
            await update.message.reply_text(f"Ваши ключевые слова: {keywords}")
        else:
            await update.message.reply_text("Ключевые слова не установлены.")
    
    elif text == "Сбросить ключевые слова":
        # Сбрасываем ключевые слова
        user_keywords.pop(user_id, None)
        seen_titles.pop(user_id, None)
        await update.message.reply_text("Ключевые слова сброшены.")
    
    elif text == "Установить интервал обновлений":
        # Начинаем процесс установки интервала
        await update.message.reply_text("Введите интервал в секундах:")
        context.user_data["awaiting_interval"] = True

# Автообновления
async def auto_update(context: CallbackContext) -> None:
    url = "https://cointelegraph.com/rss"
    entries = parse_rss(url)
    if not entries:
        print("Ошибка: RSS-лента не содержит записей или не загружена.")
        return

    for user_id, keywords in user_keywords.items():
        if user_id not in seen_titles:
            seen_titles[user_id] = set()

        for entry in entries:
            if entry.title not in seen_titles[user_id]:
                for keyword in keywords:
                    if keyword.lower() in entry.title.lower():
                        seen_titles[user_id].add(entry.title)
                        highlighted_title = re.sub(
                            f"({re.escape(keyword)})",
                            r"<b>\1</b>",
                            entry.title,
                            flags=re.IGNORECASE
                        )
                        message = f"📰 {highlighted_title}\n\n{entry.link}"
                        try:
                            await context.bot.send_message(chat_id=user_id, text=message, parse_mode="HTML")
                        except Exception as e:
                            print(f"Ошибка при отправке сообщения пользователю {user_id}: {e}")

# Основная функция
def main():
    application = Application.builder().token(TELEGRAM_API_KEY).build()

    # Команды
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Автообновления
    application.job_queue.run_repeating(auto_update, interval=10, first=10)

    print("Бот готов к использованию...")
    application.run_polling()

if __name__ == "__main__":
    main()
