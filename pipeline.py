import asyncio
import hashlib
import logging
from collections import defaultdict
from datetime import timedelta

from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.sql import func
from telegram.error import Forbidden

from config import MAX_DELIVERIES_PER_RUN, POSTS_RETENTION_DAYS
from database import Delivery, Keyword, NewsSource, Post, Session, User, engine, user_sources
from news_sources import binance_handler, rss_handler
from utils import format_message, matches_keywords

logger = logging.getLogger(__name__)

# Тип источника -> async-функция(url), возвращающая записи (guid, title, url, summary, published_at)
FETCHERS = {
    'rss': rss_handler.fetch,
    'binance': binance_handler.fetch,
}


def guid_hash(guid: str) -> str:
    return hashlib.sha256(guid.encode()).hexdigest()


async def collect() -> int:
    """Опрашивает активные источники с подписчиками и сохраняет новые посты.

    Удаляет посты старше POSTS_RETENTION_DAYS вместе с доставками.
    Возвращает число новых постов.
    """
    # С NullPool каждое соединение — новый TLS-хендшейк к Neon, поэтому весь запуск идёт через одно.
    # Сессия, привязанная к соединению, сохраняет его между commit().
    with engine.connect() as connection, Session(bind=connection) as session:
        session.execute(delete(Post).where(Post.fetched_at < func.now() - timedelta(days=POSTS_RETENTION_DAYS)))
        sources = session.execute(
            select(NewsSource.id, NewsSource.url, NewsSource.type)
            .where(NewsSource.is_active, NewsSource.id.in_(select(user_sources.c.source_id)))
        ).all()
        session.commit()

        new_posts = 0
        for source in sources:
            fetch = FETCHERS.get(source.type)
            if fetch is None:
                logger.warning(f"Нет обработчика для источника {source.id} типа {source.type}")
                continue
            try:
                items = await fetch(source.url)
            except Exception as e:
                logger.error(f"Ошибка при получении новостей из {source.url}: {e}")
                continue

            if items:
                # Дубли отсекает UNIQUE(source_id, guid_hash)
                result = session.execute(
                    insert(Post)
                    .values([
                        {
                            'source_id': source.id,
                            'guid_hash': guid_hash(item['guid']),
                            'title': item['title'],
                            'url': item['url'],
                            'summary': item['summary'],
                            'published_at': item['published_at'],
                        }
                        for item in items
                    ])
                    .on_conflict_do_nothing(index_elements=['source_id', 'guid_hash'])
                    .returning(Post.id)
                )
                new_posts += len(result.all())
            session.execute(update(NewsSource).where(NewsSource.id == source.id).values(last_fetch=func.now()))
            session.commit()
        return new_posts


async def deliver(bot) -> int:
    """Отправляет пользователям недоставленные посты по их ключевым словам.

    Берутся только посты, опубликованные (без даты — полученные) после подписки, не больше MAX_DELIVERIES_PER_RUN на пользователя.
    Возвращает число отправленных сообщений.
    """
    with engine.connect() as connection, Session(bind=connection) as session:
        keywords = defaultdict(list)
        for user_id, word in session.execute(
            select(Keyword.user_id, Keyword.word).join(User, User.id == Keyword.user_id).where(User.is_active)
        ):
            keywords[user_id].append(word)

        rows = session.execute(
            select(
                User.id.label('user_id'),
                User.telegram_id,
                Post.id.label('post_id'),
                Post.title,
                Post.url,
                Post.summary,
                Post.published_at,
                NewsSource.type.label('source'),
            )
            .join(user_sources, user_sources.c.user_id == User.id)
            .join(Post, Post.source_id == user_sources.c.source_id)
            .join(NewsSource, NewsSource.id == Post.source_id)
            .outerjoin(Delivery, (Delivery.user_id == User.id) & (Delivery.post_id == Post.id))
            .where(
                User.is_active,
                User.id.in_(list(keywords)),
                Delivery.post_id.is_(None),
                # Старые посты ленты подписчику не приходят; без даты публикации сравнивается время получения
                func.coalesce(Post.published_at, Post.fetched_at) >= user_sources.c.created_at,
            )
            .order_by(Post.published_at.desc().nulls_last(), Post.id.desc())
        ).all()
        session.commit()

        queue = defaultdict(list)
        for row in rows:
            if len(queue[row.user_id]) < MAX_DELIVERIES_PER_RUN and matches_keywords(row.title, row.summary, keywords[row.user_id]):
                queue[row.user_id].append(row)

        sent = 0
        for user_id, posts in queue.items():
            for post in posts:
                try:
                    await bot.send_message(
                        chat_id=post.telegram_id,
                        text=format_message(post._mapping),
                        parse_mode='HTML',
                        disable_web_page_preview=True
                    )
                except Forbidden:
                    # Пользователь заблокировал бота: больше ему не отправляем
                    session.execute(update(User).where(User.id == user_id).values(is_active=False))
                    session.commit()
                    break
                except Exception as e:
                    logger.error(f"Ошибка при отправке новости пользователю {post.telegram_id}: {e}")
                    continue
                # Доставка записывается только после успешной отправки
                session.execute(
                    insert(Delivery).values(user_id=user_id, post_id=post.post_id).on_conflict_do_nothing()
                )
                session.commit()
                sent += 1
                await asyncio.sleep(0.5)  # Небольшая задержка между сообщениями
        return sent
