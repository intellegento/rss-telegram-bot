# RSS Telegram Bot

Бот для отслеживания новостей из различных источников (RSS, Binance, Telegram) по ключевым словам.

## Установка

1. Клонируйте репозиторий:
```bash
git clone https://github.com/your-username/rss-telegram-bot.git
cd rss-telegram-bot
```

2. Создайте виртуальное окружение и активируйте его (проверено на Python 3.12 и 3.13):
```bash
python3.12 -m venv .venv
source .venv/bin/activate  # для Linux/Mac
# или
.venv\Scripts\activate  # для Windows
```

3. Установите зависимости:
```bash
pip install -r requirements.txt
```

4. Создайте файл `.env` из шаблона и заполните значения:
```bash
cp .env.example .env
```

| Переменная | Назначение |
|---|---|
| `TELEGRAM_TOKEN` | токен бота от [@BotFather](https://t.me/BotFather), обязательно |
| `DATABASE_URL` | PostgreSQL (Neon) в формате SQLAlchemy для psycopg 3: `postgresql+psycopg://user:password@host/dbname?sslmode=require`. Обязательно: без неё бот завершается с ошибкой. Подходит и pooled-адрес Neon (`...-pooler...`) |
| `BINANCE_API_KEY` | ключ Binance (сейчас не используется, можно оставить пустым) |
| `BINANCE_API_SECRET` | секрет Binance (сейчас не используется, можно оставить пустым) |
| `TEST_DATABASE_URL` | отдельная БД для тестов, в том же формате. Тесты её очищают, поэтому это не должна быть рабочая БД |

`config.py` только читает эти переменные из окружения и `.env`, секретов в нём нет.

## Миграции

Схема БД создаётся только миграциями Alembic. Перед первым запуском и после обновления кода:

```bash
alembic upgrade head
```

Новая миграция после изменения моделей в `database.py`:

```bash
alembic revision --autogenerate -m "описание изменения"
```

Проверьте сгенерированный файл в `alembic/versions/` и примените его через `alembic upgrade head`. Откат последней миграции: `alembic downgrade -1`.

## Запуск

```bash
python main.py
```

Бот работает в режиме polling.

## Тесты

```bash
pip install -r requirements-dev.txt
pytest
```

Тесты не обращаются к Telegram и внешним источникам: всё подменено моками. Тесты с БД используют `TEST_DATABASE_URL`: перед прогоном применяют миграции, после каждого теста очищают таблицы. Если `TEST_DATABASE_URL` не задан или совпадает с `DATABASE_URL`, эти тесты пропускаются.

## Функциональность

- Отслеживание новостей из RSS-каналов
- Интеграция с Binance Announcements
- Мониторинг сообщений в Telegram группах
- Фильтрация новостей по ключевым словам
- Автоматическое добавление групп как источников новостей
- Управление источниками и ключевыми словами через удобное меню

## Команды

- `/start` - Запустить бота
- `/help` - Показать справку
- `/keywords` - Показать ваши ключевые слова
- `/add` - Добавить ключевое слово
- `/remove` - Удалить ключевое слово
- `/sources` - Показать список источников
- `/add_source` - Добавить источник
- `/remove_source` - Удалить источник

## Безопасность

Секреты хранятся только в `.env`, который не включается в репозиторий. Шаблон со списком переменных — `.env.example`.