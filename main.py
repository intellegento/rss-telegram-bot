import html
import logging
from typing import Dict

from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    ConversationHandler,
)

from config import (
    TELEGRAM_TOKEN,
    DEFAULT_RSS_SOURCES,
    DEFAULT_UPDATE_INTERVAL,
    FREE_KEYWORDS_LIMIT,
    FREE_SOURCES_LIMIT,
)
from database import DatabaseManager, ADDED, DUPLICATE, LIMIT, NO_USER
from pipeline import collect, deliver
from utils import validate_keyword, clean_username

# Состояния для ConversationHandler
CHOOSING_ACTION, ADDING_KEYWORD, REMOVING_KEYWORD, ADDING_SOURCE, REMOVING_SOURCE = range(5)

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

def main_keyboard() -> ReplyKeyboardMarkup:
    """Главная клавиатура бота."""
    keyboard = [
        ["📝 Добавить ключевое слово", "🗑 Удалить ключевое слово"],
        ["📋 Мои ключевые слова", "📰 Список источников"],
        ["📝 Добавить источник", "🗑 Удалить источник"],
        ["ℹ️ Помощь"]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def limit_message(what: str, used: int, limit: int) -> str:
    """Сообщение о достигнутом лимите бесплатной версии."""
    return (
        f"❌ Достигнут лимит бесплатной версии: {what} — использовано {used} из {limit}.\n"
        "Премиум снимает ограничение."
    )

NO_USER_MESSAGE = "❌ Сначала отправьте /start."

class NewsBot:
    def __init__(self):
        self.db = DatabaseManager()
        self.user_states: Dict[int, str] = {}

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Обработчик команды /start."""
        user = update.effective_user
        chat_id = update.effective_chat.id
        
        # Очищаем имя пользователя от специальных символов
        clean_name = clean_username(user.first_name)
        
        # Добавляем пользователя в базу данных, если его там нет
        if not self.db.get_user(chat_id):
            self.db.add_user(chat_id)

        reply_markup = main_keyboard()

        await update.message.reply_text(
            f"Привет, {clean_name}! 👋\n\n"
            "Я буду отправлять тебе новости по твоим ключевым словам.\n"
            "Используй кнопки ниже для управления настройками:",
            reply_markup=reply_markup
        )
        return CHOOSING_ACTION

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Показывает справку по использованию бота."""
        help_text = (
            "🤖 <b>Как использовать бота:</b>\n\n"
            "1️⃣ Добавьте источники новостей через меню или команду /add_source\n"
            "2️⃣ Добавьте ключевые слова для отслеживания новостей\n"
            "3️⃣ Бот будет автоматически отправлять новости, содержащие ваши ключевые слова\n"
            "4️⃣ Вы можете изменить ключевые слова и источники в любой момент\n\n"
            "<b>Доступные команды:</b>\n"
            "/start - Перезапустить бота\n"
            "/help - Показать эту справку\n"
            "/keywords - Показать ваши ключевые слова\n"
            "/add - Добавить ключевое слово\n"
            "/remove - Удалить ключевое слово\n"
            "/sources - Показать список источников\n"
            "/add_source - Добавить источник\n"
            "/remove_source - Удалить источник\n\n"
            "<b>Управление через кнопки:</b>\n"
            "• Используйте кнопки меню для быстрого доступа к функциям\n"
            "• Кнопка 'Список источников' покажет текущие источники новостей\n"
            "• Кнопки 'Добавить/Удалить источник' для управления источниками\n"
        )
        await update.message.reply_text(help_text, parse_mode='HTML')

    async def add_keyword_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Начинает процесс добавления ключевого слова."""
        await update.message.reply_text(
            "Введите ключевые слова для отслеживания через запятую:\n"
            "(минимум 2 символа для каждого слова, только буквы, цифры и знаки - . )\n\n"
            "Например: bitcoin, eth, binance"
        )
        return ADDING_KEYWORD

    async def process_new_keyword(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Обрабатывает новые ключевые слова."""
        text = update.message.text.strip()
        user_id = update.effective_user.id
        
        # Разбиваем текст на отдельные ключевые слова
        keywords = [kw.strip() for kw in text.split(',') if kw.strip()]
        
        if not keywords:
            await update.message.reply_text(
                "❌ Пожалуйста, введите хотя бы одно ключевое слово."
            )
            return ADDING_KEYWORD

        added_keywords = []
        skipped_keywords = []
        invalid_keywords = []
        over_limit_keywords = []

        for keyword in keywords:
            if not validate_keyword(keyword):
                invalid_keywords.append(keyword)
                continue

            result = self.db.add_keyword(user_id, keyword)
            if result == NO_USER:
                await update.message.reply_text(NO_USER_MESSAGE)
                return CHOOSING_ACTION
            if result == ADDED:
                added_keywords.append(keyword)
            elif result == DUPLICATE:
                skipped_keywords.append(keyword)
            elif result == LIMIT:
                over_limit_keywords.append(keyword)

        # Формируем ответное сообщение
        response_parts = []
        if added_keywords:
            response_parts.append(f"✅ Добавлены ключевые слова: {', '.join(added_keywords)}")
        if skipped_keywords:
            response_parts.append(f"ℹ️ Уже существуют: {', '.join(skipped_keywords)}")
        if invalid_keywords:
            response_parts.append(f"❌ Недопустимые слова: {', '.join(invalid_keywords)}")
        if over_limit_keywords:
            response_parts.append(f"Не добавлены: {', '.join(over_limit_keywords)}")
            response_parts.append(limit_message(
                "ключевые слова", len(self.db.get_keywords(user_id)), FREE_KEYWORDS_LIMIT
            ))

        await update.message.reply_text("\n".join(response_parts) or "❌ Не удалось добавить ключевые слова.")
        return CHOOSING_ACTION

    async def remove_keyword_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Начинает процесс удаления ключевого слова."""
        user_id = update.effective_user.id
        keywords = self.db.get_keywords(user_id)

        if not keywords:
            await update.message.reply_text("У вас нет добавленных ключевых слов.")
            return CHOOSING_ACTION

        keyboard = [[word] for word in keywords]
        keyboard.append(["Отмена"])
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

        await update.message.reply_text(
            "Выберите ключевое слово для удаления:",
            reply_markup=reply_markup
        )
        return REMOVING_KEYWORD

    async def process_remove_keyword(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Обрабатывает удаление ключевого слова."""
        keyword = update.message.text.strip()
        user_id = update.effective_user.id

        if keyword == "Отмена":
            reply_markup = main_keyboard()
            await update.message.reply_text("Операция отменена.", reply_markup=reply_markup)
            return CHOOSING_ACTION

        if self.db.remove_keyword(user_id, keyword):
            reply_markup = main_keyboard()
            await update.message.reply_text(
                f"✅ Ключевое слово '{keyword}' удалено.",
                reply_markup=reply_markup
            )
        else:
            await update.message.reply_text("❌ Не удалось удалить ключевое слово.")

        return CHOOSING_ACTION

    async def show_keywords(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Показывает список ключевых слов пользователя."""
        user_id = update.effective_user.id
        keywords = self.db.get_keywords(user_id)

        if keywords:
            text = "📋 Ваши ключевые слова:\n\n" + "\n".join(f"• {word}" for word in keywords)
        else:
            text = "У вас нет добавленных ключевых слов."

        await update.message.reply_text(text)

    async def sources_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Показывает список источников пользователя."""
        sources = self.db.get_sources(update.effective_user.id)
        rss_sources = [src for src in sources if src['type'] == 'rss']
        binance_sources = [src for src in sources if src['type'] == 'binance']

        message = "📋 <b>Ваши источники новостей:</b>\n\n"
        if not sources:
            message += "У вас пока нет источников.\n"
        
        if rss_sources:
            message += "📰 <b>RSS-каналы:</b>\n"
            for src in rss_sources:
                last_fetch = src['last_fetch'].strftime('%d.%m.%Y %H:%M') if src['last_fetch'] else 'Никогда'
                message += f"• {html.escape(src['name'] or '')} (ID: {src['id']})\n  └ {html.escape(src['url'])}\n  └ Последняя проверка: {last_fetch}\n\n"
        
        if binance_sources:
            message += "\n💰 <b>Binance:</b>\n"
            for src in binance_sources:
                last_fetch = src['last_fetch'].strftime('%d.%m.%Y %H:%M') if src['last_fetch'] else 'Никогда'
                message += f"• {html.escape(src['name'] or '')} (ID: {src['id']})\n  └ Последняя проверка: {last_fetch}\n\n"

        message += "\nДля управления источниками используйте команды:\n"
        message += "/add_source - Добавить источник\n"
        message += "/remove_source - Удалить источник"

        await update.message.reply_text(message, parse_mode='HTML')

    async def add_source_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Начинает процесс добавления источника."""
        keyboard = [
            ["RSS-канал", "Binance"],
            ["Отмена"]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        await update.message.reply_text(
            "Выберите тип источника:\n\n"
            "Публичный Telegram-канал добавляется как RSS-лента RSSHub",
            reply_markup=reply_markup
        )
        return ADDING_SOURCE

    async def reply_add_source_result(self, update: Update, result: str, added_text: str) -> None:
        """Отвечает пользователю по результату add_source."""
        if result == ADDED:
            await update.message.reply_text(added_text, reply_markup=main_keyboard())
        elif result == DUPLICATE:
            await update.message.reply_text(
                "ℹ️ Этот источник уже есть в вашем списке.\n"
                "Попробуйте другой источник или нажмите 'Отмена'"
            )
        elif result == LIMIT:
            used = len(self.db.get_sources(update.effective_user.id))
            await update.message.reply_text(
                limit_message("источники", used, FREE_SOURCES_LIMIT),
                reply_markup=main_keyboard()
            )
        else:
            await update.message.reply_text(NO_USER_MESSAGE)

    async def process_add_source(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Обрабатывает добавление источника."""
        text = update.message.text
        user_id = update.effective_user.id

        # Обработка кнопки отмены
        if text == "Отмена":
            reply_markup = main_keyboard()
            await update.message.reply_text(
                "Операция отменена.",
                reply_markup=reply_markup
            )
            return CHOOSING_ACTION

        # Выбор типа источника
        if text in ["RSS-канал", "Binance"]:
            if text == "RSS-канал":
                context.user_data['source_type'] = 'rss'
                await update.message.reply_text(
                    "Введите название и URL RSS-канала в формате:\n"
                    "название | url\n\n"
                    "Например:\n"
                    "CoinTelegraph | https://cointelegraph.com/rss\n\n"
                    "Для отмены нажмите кнопку 'Отмена'"
                )
                return ADDING_SOURCE
            else:  # Binance
                try:
                    result = self.db.add_source(
                        user_id,
                        url="https://www.binance.com/bapi/composite/v1/public/cms/article/catalog/list",
                        name="Binance News",
                        source_type="binance"
                    )
                    await self.reply_add_source_result(update, result, "✅ Источник Binance успешно добавлен!")
                except Exception as e:
                    await update.message.reply_text(
                        f"❌ Ошибка при добавлении Binance: {str(e)}"
                    )
                return CHOOSING_ACTION

        # Обработка добавления RSS-канала
        if 'source_type' in context.user_data and context.user_data['source_type'] == 'rss':
            try:
                if '|' not in text:
                    await update.message.reply_text(
                        "❌ Неверный формат. Используйте формат:\n"
                        "название | url\n\n"
                        "Для отмены нажмите кнопку 'Отмена'"
                    )
                    return ADDING_SOURCE

                name, url = map(str.strip, text.split('|'))
                if not name or not url:
                    await update.message.reply_text(
                        "❌ Название и URL не могут быть пустыми.\n"
                        "Для отмены нажмите кнопку 'Отмена'"
                    )
                    return ADDING_SOURCE

                result = self.db.add_source(user_id, url=url, name=name, source_type='rss')
                await self.reply_add_source_result(update, result, f"✅ RSS-канал '{name}' успешно добавлен!")
                if result == DUPLICATE:
                    return ADDING_SOURCE
                context.user_data.pop('source_type', None)
                return CHOOSING_ACTION
            except Exception as e:
                await update.message.reply_text(
                    f"❌ Ошибка при добавлении RSS-канала: {str(e)}\n"
                    "Попробуйте снова или нажмите 'Отмена'"
                )
                return ADDING_SOURCE

        return ADDING_SOURCE

    async def remove_source_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Начинает процесс удаления источника."""
        sources = self.db.get_sources(update.effective_user.id)
        
        if not sources:
            reply_markup = main_keyboard()
            await update.message.reply_text(
                "Нет доступных источников для удаления.",
                reply_markup=reply_markup
            )
            return CHOOSING_ACTION

        keyboard = [[f"{src['name']} (ID: {src['id']})"] for src in sources]
        keyboard.append(["Отмена"])
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

        await update.message.reply_text(
            "Выберите источник для удаления:",
            reply_markup=reply_markup
        )
        return REMOVING_SOURCE

    async def process_remove_source(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Обрабатывает удаление источника."""
        text = update.message.text

        if text == "Отмена":
            reply_markup = main_keyboard()
            await update.message.reply_text("Операция отменена.", reply_markup=reply_markup)
            return CHOOSING_ACTION

        try:
            source_id = int(text.split('ID: ')[1].rstrip(')'))
            if self.db.remove_source(update.effective_user.id, source_id):
                reply_markup = main_keyboard()
                await update.message.reply_text(
                    "✅ Источник успешно удален.",
                    reply_markup=reply_markup
                )
            else:
                await update.message.reply_text("❌ Не удалось удалить источник.")
        except (ValueError, IndexError):
            await update.message.reply_text("❌ Неверный формат ID источника.")

        return CHOOSING_ACTION

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Обрабатывает текстовые сообщения."""
        text = update.message.text

        if text == "📝 Добавить ключевое слово":
            return await self.add_keyword_command(update, context)
        elif text == "🗑 Удалить ключевое слово":
            return await self.remove_keyword_command(update, context)
        elif text == "📋 Мои ключевые слова":
            await self.show_keywords(update, context)
            return CHOOSING_ACTION
        elif text == "ℹ️ Помощь":
            await self.help_command(update, context)
            return CHOOSING_ACTION
        elif text == "📰 Список источников":
            await self.sources_command(update, context)
            return CHOOSING_ACTION
        elif text == "📝 Добавить источник":
            return await self.add_source_command(update, context)
        elif text == "🗑 Удалить источник":
            return await self.remove_source_command(update, context)

        return CHOOSING_ACTION

    async def check_news(self, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Проверяет новости и отправляет их пользователям."""
        try:
            await collect()
            await deliver(context.bot)
        except Exception as e:
            logger.error(f"Ошибка при проверке новостей: {e}")

def main():
    """Запускает бота."""
    # Инициализируем бота
    bot = NewsBot()
    
    # Создаем приложение
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    
    # Создаем ConversationHandler
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", bot.start)],
        states={
            CHOOSING_ACTION: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, bot.handle_message),
            ],
            ADDING_KEYWORD: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, bot.process_new_keyword),
            ],
            REMOVING_KEYWORD: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, bot.process_remove_keyword),
            ],
            ADDING_SOURCE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, bot.process_add_source),
            ],
            REMOVING_SOURCE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, bot.process_remove_source),
            ],
        },
        fallbacks=[CommandHandler("start", bot.start)],
    )
    
    # Добавляем обработчики
    application.add_handler(conv_handler)
    application.add_handler(CommandHandler("help", bot.help_command))
    application.add_handler(CommandHandler("keywords", bot.show_keywords))
    application.add_handler(CommandHandler("sources", bot.sources_command))
    application.add_handler(CommandHandler("add_source", bot.add_source_command))
    application.add_handler(CommandHandler("remove_source", bot.remove_source_command))
    
    # Добавляем задачу проверки новостей
    application.job_queue.run_repeating(bot.check_news, interval=300, first=10)
    
    # Запускаем бота
    application.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)

if __name__ == "__main__":
    main() 