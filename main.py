import asyncio
import logging
from typing import Dict, List
from datetime import datetime, timedelta

from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    ConversationHandler,
    ChatMemberHandler,
)

from config import (
    TELEGRAM_TOKEN,
    DEFAULT_RSS_SOURCES,
    DEFAULT_UPDATE_INTERVAL,
    MAX_KEYWORDS_PER_USER
)
from database import DatabaseManager, User
from news_sources.rss_handler import RSSHandler
from news_sources.binance_handler import BinanceHandler
from utils import format_message, validate_keyword, clean_username

# Состояния для ConversationHandler
CHOOSING_ACTION, ADDING_KEYWORD, REMOVING_KEYWORD, ADDING_SOURCE, REMOVING_SOURCE = range(5)

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class NewsBot:
    def __init__(self):
        self.db = DatabaseManager()
        self.rss_handler = RSSHandler()
        self.binance_handler = BinanceHandler()
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

        keyboard = [
            ["📝 Добавить ключевое слово", "🗑 Удалить ключевое слово"],
            ["📋 Мои ключевые слова", "📰 Список источников"],
            ["📝 Добавить источник", "🗑 Удалить источник"],
            ["ℹ️ Помощь"]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

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

        current_keywords = self.db.get_keywords(user_id)
        if len(current_keywords) + len(keywords) > MAX_KEYWORDS_PER_USER:
            await update.message.reply_text(
                f"❌ Превышен лимит ключевых слов ({MAX_KEYWORDS_PER_USER}).\n"
                "Удалите некоторые слова перед добавлением новых."
            )
            return CHOOSING_ACTION

        added_keywords = []
        skipped_keywords = []
        invalid_keywords = []

        for keyword in keywords:
            if not validate_keyword(keyword):
                invalid_keywords.append(keyword)
                continue

            if keyword.lower() in [k.lower() for k in current_keywords]:
                skipped_keywords.append(keyword)
                continue

            if self.db.add_keyword(user_id, keyword):
                added_keywords.append(keyword)

        # Формируем ответное сообщение
        response_parts = []
        if added_keywords:
            response_parts.append(f"✅ Добавлены ключевые слова: {', '.join(added_keywords)}")
        if skipped_keywords:
            response_parts.append(f"ℹ️ Уже существуют: {', '.join(skipped_keywords)}")
        if invalid_keywords:
            response_parts.append(f"❌ Недопустимые слова: {', '.join(invalid_keywords)}")

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
            keyboard = [
                ["📝 Добавить ключевое слово", "🗑 Удалить ключевое слово"],
                ["📋 Мои ключевые слова", "📰 Список источников"],
                ["📝 Добавить источник", "🗑 Удалить источник"],
                ["ℹ️ Помощь"]
            ]
            reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
            await update.message.reply_text("Операция отменена.", reply_markup=reply_markup)
            return CHOOSING_ACTION

        if self.db.remove_keyword(user_id, keyword):
            keyboard = [
                ["📝 Добавить ключевое слово", "🗑 Удалить ключевое слово"],
                ["📋 Мои ключевые слова", "📰 Список источников"],
                ["📝 Добавить источник", "🗑 Удалить источник"],
                ["ℹ️ Помощь"]
            ]
            reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
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
        """Показывает список источников новостей."""
        # Получаем все источники
        rss_sources = self.db.get_sources(source_type='rss')
        binance_sources = self.db.get_sources(source_type='binance')
        telegram_sources = self.db.get_sources(source_type='telegram')

        message = "📋 <b>Список источников новостей:</b>\n\n"
        
        if rss_sources:
            message += "📰 <b>RSS-каналы:</b>\n"
            for src in rss_sources:
                last_fetch = src['last_fetch'].strftime('%d.%m.%Y %H:%M') if src['last_fetch'] else 'Никогда'
                message += f"• {src['name']} (ID: {src['id']})\n  └ {src['url']}\n  └ Последняя проверка: {last_fetch}\n\n"
        
        if binance_sources:
            message += "\n💰 <b>Binance:</b>\n"
            for src in binance_sources:
                last_fetch = src['last_fetch'].strftime('%d.%m.%Y %H:%M') if src['last_fetch'] else 'Никогда'
                message += f"• {src['name']} (ID: {src['id']})\n  └ Последняя проверка: {last_fetch}\n\n"

        if telegram_sources:
            message += "\n💬 <b>Telegram группы:</b>\n"
            for src in telegram_sources:
                last_fetch = src['last_fetch'].strftime('%d.%m.%Y %H:%M') if src['last_fetch'] else 'Никогда'
                message += f"• {src['name']} (ID: {src['id']})\n  └ Последняя проверка: {last_fetch}\n\n"

        message += "\nДля управления источниками используйте команды:\n"
        message += "/add_source - Добавить источник\n"
        message += "/remove_source - Удалить источник"

        await update.message.reply_text(message, parse_mode='HTML')

    async def handle_group_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обрабатывает сообщения в группах."""
        if not update.effective_chat or not update.effective_message:
            return

        chat = update.effective_chat
        message = update.effective_message

        # Проверяем, является ли чат группой или супергруппой
        if chat.type not in ['group', 'supergroup']:
            return

        # Добавляем группу как источник, если её ещё нет
        chat_id = str(chat.id)
        if not any(src['url'] == chat_id for src in self.db.get_sources(source_type='telegram')):
            self.db.add_source(
                url=chat_id,
                name=chat.title or "Telegram группа",
                source_type='telegram'
            )
            await message.reply_text(
                f"✅ Группа '{chat.title}' добавлена как источник новостей!"
            )

        # Обновляем время последней проверки
        sources = self.db.get_sources(source_type='telegram')
        for source in sources:
            if source['url'] == chat_id:
                self.db.update_source_last_fetch(source['id'])
                break

    async def handle_my_chat_member(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обрабатывает изменения статуса бота в чате."""
        if not update.my_chat_member or not update.my_chat_member.chat:
            return

        chat = update.my_chat_member.chat
        new_status = update.my_chat_member.new_chat_member.status
        old_status = update.my_chat_member.old_chat_member.status

        # Если бота добавили в группу
        if (chat.type in ['group', 'supergroup'] and 
            old_status in ['left', 'kicked'] and 
            new_status in ['member', 'administrator']):
            
            chat_id = str(chat.id)
            if not any(src['url'] == chat_id for src in self.db.get_sources(source_type='telegram')):
                self.db.add_source(
                    url=chat_id,
                    name=chat.title or "Telegram группа",
                    source_type='telegram'
                )
                await context.bot.send_message(
                    chat_id=chat.id,
                    text=f"👋 Привет! Я буду отслеживать сообщения в этой группе.\n"
                         f"✅ Группа '{chat.title}' добавлена как источник новостей!"
                )

        # Если бота удалили из группы
        elif (chat.type in ['group', 'supergroup'] and 
              old_status in ['member', 'administrator'] and 
              new_status in ['left', 'kicked']):
            
            sources = self.db.get_sources(source_type='telegram')
            for source in sources:
                if source['url'] == str(chat.id):
                    self.db.remove_source(source['id'])
                    break

    async def add_source_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Начинает процесс добавления источника."""
        keyboard = [
            ["RSS-канал", "Binance"],
            ["Отмена"]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        await update.message.reply_text(
            "Выберите тип источника:\n\n"
            "Примечание: Telegram группы добавляются автоматически при добавлении бота в группу",
            reply_markup=reply_markup
        )
        return ADDING_SOURCE

    async def process_add_source(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Обрабатывает добавление источника."""
        text = update.message.text

        # Обработка кнопки отмены
        if text == "Отмена":
            keyboard = [
                ["📝 Добавить ключевое слово", "🗑 Удалить ключевое слово"],
                ["📋 Мои ключевые слова", "📰 Список источников"],
                ["📝 Добавить источник", "🗑 Удалить источник"],
                ["ℹ️ Помощь"]
            ]
            reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
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
                    if self.db.add_source(
                        url="https://www.binance.com/bapi/composite/v1/public/cms/article/catalog/list",
                        name="Binance News",
                        source_type="binance"
                    ):
                        keyboard = [
                            ["📝 Добавить ключевое слово", "🗑 Удалить ключевое слово"],
                            ["📋 Мои ключевые слова", "📰 Список источников"],
                            ["📝 Добавить источник", "🗑 Удалить источник"],
                            ["ℹ️ Помощь"]
                        ]
                        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
                        await update.message.reply_text(
                            "✅ Источник Binance успешно добавлен!",
                            reply_markup=reply_markup
                        )
                    else:
                        await update.message.reply_text(
                            "❌ Не удалось добавить источник Binance. Возможно, он уже существует."
                        )
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

                if self.db.add_source(url=url, name=name, source_type='rss'):
                    keyboard = [
                        ["📝 Добавить ключевое слово", "🗑 Удалить ключевое слово"],
                        ["📋 Мои ключевые слова", "📰 Список источников"],
                        ["📝 Добавить источник", "🗑 Удалить источник"],
                        ["ℹ️ Помощь"]
                    ]
                    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
                    await update.message.reply_text(
                        f"✅ RSS-канал '{name}' успешно добавлен!",
                        reply_markup=reply_markup
                    )
                    context.user_data.pop('source_type', None)
                    return CHOOSING_ACTION
                else:
                    await update.message.reply_text(
                        "❌ Не удалось добавить RSS-канал. Возможно, он уже существует.\n"
                        "Попробуйте другой источник или нажмите 'Отмена'"
                    )
                    return ADDING_SOURCE
            except Exception as e:
                await update.message.reply_text(
                    f"❌ Ошибка при добавлении RSS-канала: {str(e)}\n"
                    "Попробуйте снова или нажмите 'Отмена'"
                )
                return ADDING_SOURCE

        return ADDING_SOURCE

    async def remove_source_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Начинает процесс удаления источника."""
        sources = self.db.get_sources()
        
        if not sources:
            keyboard = [
                ["📝 Добавить ключевое слово", "🗑 Удалить ключевое слово"],
                ["📋 Мои ключевые слова", "📰 Список источников"],
                ["📝 Добавить источник", "🗑 Удалить источник"],
                ["ℹ️ Помощь"]
            ]
            reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
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
            keyboard = [
                ["📝 Добавить ключевое слово", "🗑 Удалить ключевое слово"],
                ["📋 Мои ключевые слова", "📰 Список источников"],
                ["📝 Добавить источник", "🗑 Удалить источник"],
                ["ℹ️ Помощь"]
            ]
            reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
            await update.message.reply_text("Операция отменена.", reply_markup=reply_markup)
            return CHOOSING_ACTION

        try:
            source_id = int(text.split('ID: ')[1].rstrip(')'))
            if self.db.remove_source(source_id):
                keyboard = [
                    ["📝 Добавить ключевое слово", "🗑 Удалить ключевое слово"],
                    ["📋 Мои ключевые слова", "📰 Список источников"],
                    ["📝 Добавить источник", "🗑 Удалить источник"],
                    ["ℹ️ Помощь"]
                ]
                reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
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
            all_news = []
            
            # Получаем все активные источники
            rss_sources = self.db.get_sources(source_type='rss')
            binance_sources = self.db.get_sources(source_type='binance')
            
            # Получаем новости из RSS-каналов
            for source in rss_sources:
                try:
                    news = await self.rss_handler.get_news([source['url']])
                    all_news.extend(news)
                    self.db.update_source_last_fetch(source['id'])
                except Exception as e:
                    logger.error(f"Ошибка при получении новостей из {source['name']}: {e}")
            
            # Получаем новости из Binance
            if binance_sources:
                try:
                    binance_news = await self.binance_handler.get_announcements()
                    all_news.extend(binance_news)
                    for source in binance_sources:
                        self.db.update_source_last_fetch(source['id'])
                except Exception as e:
                    logger.error(f"Ошибка при получении новостей из Binance: {e}")
            
            # Сортируем по дате публикации
            all_news.sort(key=lambda x: x['published'], reverse=True)
            
            # Получаем всех пользователей из базы данных
            with self.db.Session() as session:
                users = session.query(User).filter_by(is_active=True).all()
                
                for user in users:
                    keywords = self.db.get_keywords(user.telegram_id)
                    if not keywords:
                        continue
                        
                    # Фильтруем новости по ключевым словам
                    filtered_news = []
                    for news in all_news:
                        text = f"{news['title']} {news['description']}".lower()
                        if any(keyword.lower() in text for keyword in keywords):
                            # Проверяем, не отправляли ли мы эту новость ранее
                            if not self.db.is_news_seen(user.telegram_id, news['hash']):
                                filtered_news.append(news)

                    # Отправляем новости пользователю; остальные придут в следующих циклах
                    for news in filtered_news[:10]:  # Ограничиваем количество новостей
                        try:
                            message = format_message(news)
                            await context.bot.send_message(
                                chat_id=user.telegram_id,
                                text=message,
                                parse_mode='HTML',
                                disable_web_page_preview=True
                            )
                            # Помечаем как увиденную только после успешной отправки
                            self.db.add_seen_news(user.telegram_id, news['hash'])
                            await asyncio.sleep(0.5)  # Небольшая задержка между сообщениями
                        except Exception as e:
                            logger.error(f"Ошибка при отправке новости пользователю {user.telegram_id}: {e}")
                            continue
                            
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
    
    # Добавляем обработчик сообщений в группах
    application.add_handler(MessageHandler(
        filters.ChatType.GROUPS & ~filters.COMMAND,
        bot.handle_group_message
    ))
    
    # Добавляем обработчик изменений статуса бота в чате
    application.add_handler(ChatMemberHandler(
        bot.handle_my_chat_member,
        ChatMemberHandler.MY_CHAT_MEMBER
    ))
    
    # Добавляем задачу проверки новостей
    application.job_queue.run_repeating(bot.check_news, interval=300, first=10)
    
    # Запускаем бота
    application.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)

if __name__ == "__main__":
    main() 