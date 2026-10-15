from sqlalchemy import create_engine, Column, Integer, BigInteger, String, Boolean, ForeignKey, Table, DateTime, UniqueConstraint
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import relationship, sessionmaker
from sqlalchemy.pool import NullPool
from sqlalchemy.sql import func
from typing import List, Optional, Dict
from datetime import datetime, timezone
from config import DATABASE_URL, FREE_KEYWORDS_LIMIT, FREE_SOURCES_LIMIT

Base = declarative_base()

# Связующая таблица для отношения многие-ко-многим между пользователями и источниками новостей
user_sources = Table(
    'user_sources',
    Base.metadata,
    Column('user_id', Integer, ForeignKey('users.id', ondelete='CASCADE'), primary_key=True),
    Column('source_id', Integer, ForeignKey('news_sources.id', ondelete='CASCADE'), primary_key=True),
    # Пользователю приходят только посты, опубликованные после подписки (без даты — полученные после неё)
    Column('created_at', DateTime(timezone=True), server_default=func.now(), nullable=False)
)

class User(Base):
    __tablename__ = 'users'
    
    id = Column(Integer, primary_key=True)
    telegram_id = Column(BigInteger, unique=True, nullable=False)
    is_active = Column(Boolean, default=True)
    update_interval = Column(Integer, default=300)
    last_update = Column(DateTime(timezone=True))
    premium_until = Column(DateTime(timezone=True))
    
    keywords = relationship("Keyword", back_populates="user")
    sources = relationship("NewsSource", secondary=user_sources)

class Keyword(Base):
    __tablename__ = 'keywords'
    __table_args__ = (UniqueConstraint('user_id', 'word'),)
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    word = Column(String, nullable=False)
    
    user = relationship("User", back_populates="keywords")

class NewsSource(Base):
    __tablename__ = 'news_sources'
    
    id = Column(Integer, primary_key=True)
    url = Column(String, unique=True, nullable=False)
    name = Column(String)  # Добавляем имя источника
    type = Column(String)  # 'rss' или 'binance'
    is_active = Column(Boolean, default=True)
    added_at = Column(DateTime(timezone=True), server_default=func.now())
    last_fetch = Column(DateTime(timezone=True))

class Post(Base):
    __tablename__ = 'posts'
    # Дубли записей из источника отсекает UNIQUE(source_id, guid_hash)
    __table_args__ = (UniqueConstraint('source_id', 'guid_hash'),)

    id = Column(Integer, primary_key=True)
    source_id = Column(Integer, ForeignKey('news_sources.id', ondelete='CASCADE'), nullable=False)
    guid_hash = Column(String, nullable=False)
    title = Column(String)
    url = Column(String)
    summary = Column(String)
    published_at = Column(DateTime(timezone=True))
    fetched_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)

class Delivery(Base):
    __tablename__ = 'deliveries'

    user_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), primary_key=True)
    post_id = Column(Integer, ForeignKey('posts.id', ondelete='CASCADE'), primary_key=True)
    sent_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

def is_premium(user: User) -> bool:
    return user.premium_until is not None and user.premium_until > datetime.now(timezone.utc)

# Результаты add_keyword и add_source
ADDED, DUPLICATE, LIMIT, NO_USER = 'added', 'duplicate', 'limit', 'no_user'

# Создаем движок базы данных. Схема создаётся только миграциями Alembic.
# NullPool: на serverless соединение не переживает вызов функции.
# prepare_threshold=None: Neon pooler (PgBouncer, transaction mode) не гарантирует,
# что следующий запрос попадёт в то же серверное соединение, где был подготовлен statement.
engine = create_engine(
    DATABASE_URL,
    poolclass=NullPool,
    connect_args={"sslmode": "require", "prepare_threshold": None},
)

# Создаем сессию
Session = sessionmaker(bind=engine)

class DatabaseManager:
    def __init__(self):
        self.Session = Session

    def get_user(self, telegram_id: int) -> Optional[User]:
        with self.Session() as session:
            return session.query(User).filter_by(telegram_id=telegram_id).first()

    def add_user(self, telegram_id: int) -> User:
        with self.Session() as session:
            user = User(telegram_id=telegram_id)
            session.add(user)
            session.commit()
            return user

    def add_keyword(self, user_id: int, keyword: str) -> str:
        """Возвращает ADDED, DUPLICATE, LIMIT или NO_USER."""
        word = keyword.lower()
        with self.Session() as session:
            user = session.query(User).filter_by(telegram_id=user_id).first()
            if not user:
                return NO_USER
            if session.query(Keyword).filter_by(user_id=user.id, word=word).first():
                return DUPLICATE
            if not is_premium(user) and session.query(Keyword).filter_by(user_id=user.id).count() >= FREE_KEYWORDS_LIMIT:
                return LIMIT
            # Одновременное добавление того же слова отсекает UNIQUE(user_id, word)
            result = session.execute(
                insert(Keyword)
                .values(user_id=user.id, word=word)
                .on_conflict_do_nothing(index_elements=['user_id', 'word'])
                .returning(Keyword.id)
            )
            inserted = result.scalar() is not None
            session.commit()
            return ADDED if inserted else DUPLICATE

    def remove_keyword(self, user_id: int, keyword: str) -> bool:
        with self.Session() as session:
            user = session.query(User).filter_by(telegram_id=user_id).first()
            if user:
                keyword_obj = session.query(Keyword).filter_by(
                    user_id=user.id,
                    word=keyword.lower()
                ).first()
                if keyword_obj:
                    session.delete(keyword_obj)
                    session.commit()
                    return True
            return False

    def get_keywords(self, user_id: int) -> List[str]:
        with self.Session() as session:
            user = session.query(User).filter_by(telegram_id=user_id).first()
            if user:
                return [keyword.word for keyword in user.keywords]
            return []

    def get_sources(self, user_id: int) -> List[Dict]:
        """Получает список источников, на которые подписан пользователь."""
        with self.Session() as session:
            sources = (
                session.query(NewsSource)
                .join(user_sources, user_sources.c.source_id == NewsSource.id)
                .join(User, User.id == user_sources.c.user_id)
                .filter(User.telegram_id == user_id)
                .order_by(user_sources.c.created_at)
                .all()
            )
            return [
                {
                    'id': src.id,
                    'name': src.name,
                    'url': src.url,
                    'type': src.type,
                    'last_fetch': src.last_fetch
                }
                for src in sources
            ]

    def add_source(self, user_id: int, url: str, name: str, source_type: str) -> str:
        """Подписывает пользователя на источник, создавая источник при необходимости.

        Возвращает ADDED, DUPLICATE, LIMIT или NO_USER.
        """
        with self.Session() as session:
            user = session.query(User).filter_by(telegram_id=user_id).first()
            if not user:
                return NO_USER
            # Запись источника общая для всех и уникальна по url
            session.execute(
                insert(NewsSource)
                .values(url=url, name=name, type=source_type)
                .on_conflict_do_nothing(index_elements=['url'])
            )
            source_id = session.query(NewsSource.id).filter_by(url=url).scalar()
            subscribed = session.query(user_sources).filter_by(user_id=user.id, source_id=source_id).first()
            if subscribed:
                return DUPLICATE
            if not is_premium(user) and session.query(user_sources).filter_by(user_id=user.id).count() >= FREE_SOURCES_LIMIT:
                return LIMIT
            result = session.execute(
                insert(user_sources)
                .values(user_id=user.id, source_id=source_id)
                .on_conflict_do_nothing()
                .returning(user_sources.c.source_id)
            )
            inserted = result.scalar() is not None
            session.commit()
            return ADDED if inserted else DUPLICATE

    def remove_source(self, user_id: int, source_id: int) -> bool:
        """Удаляет подписку пользователя на источник. Сам источник остаётся."""
        with self.Session() as session:
            user = session.query(User).filter_by(telegram_id=user_id).first()
            if not user:
                return False
            result = session.execute(
                user_sources.delete().where(
                    user_sources.c.user_id == user.id,
                    user_sources.c.source_id == source_id,
                )
            )
            session.commit()
            return result.rowcount > 0
