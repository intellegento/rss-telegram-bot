import os
from dotenv import load_dotenv

# Загружаем переменные окружения из файла .env
load_dotenv()

# Telegram Bot Token (получите у @BotFather)
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")

# Настройки RSS-каналов
DEFAULT_RSS_SOURCES = [
    {
        "name": "CoinTelegraph",
        "url": "https://cointelegraph.com/rss"
    }
]

# Настройки Binance
BINANCE_API_KEY = os.getenv("BINANCE_API_KEY")
BINANCE_API_SECRET = os.getenv("BINANCE_API_SECRET")

# Интервалы обновлений (в секундах)
DEFAULT_UPDATE_INTERVAL = 300  # 5 минут
MIN_UPDATE_INTERVAL = 60  # Минимальный интервал
MAX_UPDATE_INTERVAL = 3600  # Максимальный интервал

# Максимальное количество ключевых слов на пользователя
MAX_KEYWORDS_PER_USER = 10

# База данных
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///bot_data.db") 