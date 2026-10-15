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

# Таймаут HTTP-запросов к источникам (в секундах)
HTTP_TIMEOUT = 15

# Лимиты бесплатной версии; для премиума ограничений нет
FREE_KEYWORDS_LIMIT = 5
FREE_SOURCES_LIMIT = 2

# Сколько новостей отправлять пользователю за один запуск
MAX_DELIVERIES_PER_RUN = 10

# Посты старше этого срока удаляются вместе с их доставками
POSTS_RETENTION_DAYS = 14

# База данных
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise SystemExit("Ошибка: переменная окружения DATABASE_URL не задана. Укажите её в .env (см. .env.example).")
# Neon в Vercel отдаёт postgresql:// или postgres://, SQLAlchemy нужен драйвер psycopg 3
for _scheme in ("postgresql://", "postgres://"):
    if DATABASE_URL.startswith(_scheme):
        DATABASE_URL = "postgresql+psycopg://" + DATABASE_URL[len(_scheme):]
