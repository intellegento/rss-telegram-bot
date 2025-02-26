from sqlalchemy import create_engine, Column, Integer, String, Boolean, ForeignKey, Table, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, sessionmaker
from sqlalchemy.sql import func
from typing import List, Optional, Dict
from config import DATABASE_URL

Base = declarative_base()

# Связующая таблица для отношения многие-ко-многим между пользователями и источниками новостей
user_sources = Table(
    'user_sources',
    Base.metadata,
    Column('user_id', Integer, ForeignKey('users.id')),
    Column('source_id', Integer, ForeignKey('news_sources.id'))
)

class User(Base):
    __tablename__ = 'users'
    
    id = Column(Integer, primary_key=True)
    telegram_id = Column(Integer, unique=True)
    is_active = Column(Boolean, default=True)
    update_interval = Column(Integer, default=300)
    last_update = Column(DateTime(timezone=True))
    
    keywords = relationship("Keyword", back_populates="user")
    sources = relationship("NewsSource", secondary=user_sources)

class Keyword(Base):
    __tablename__ = 'keywords'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'))
    word = Column(String)
    
    user = relationship("User", back_populates="keywords")

class NewsSource(Base):
    __tablename__ = 'news_sources'
    
    id = Column(Integer, primary_key=True)
    url = Column(String, unique=True)
    name = Column(String)  # Добавляем имя источника
    type = Column(String)  # 'rss' или 'binance'
    is_active = Column(Boolean, default=True)
    added_at = Column(DateTime(timezone=True), server_default=func.now())
    last_fetch = Column(DateTime(timezone=True))

class SeenNews(Base):
    __tablename__ = 'seen_news'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'))
    news_hash = Column(String)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())

# Создаем движок базы данных
engine = create_engine(DATABASE_URL)

# Создаем все таблицы
Base.metadata.create_all(engine)

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

    def add_keyword(self, user_id: int, keyword: str) -> bool:
        with self.Session() as session:
            user = session.query(User).filter_by(telegram_id=user_id).first()
            if user and len(user.keywords) < 10:
                keyword_obj = Keyword(user_id=user.id, word=keyword.lower())
                session.add(keyword_obj)
                session.commit()
                return True
            return False

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

    def add_seen_news(self, user_id: int, news_hash: str):
        with self.Session() as session:
            user = session.query(User).filter_by(telegram_id=user_id).first()
            if user:
                seen = SeenNews(user_id=user.id, news_hash=news_hash)
                session.add(seen)
                session.commit()

    def is_news_seen(self, user_id: int, news_hash: str) -> bool:
        with self.Session() as session:
            user = session.query(User).filter_by(telegram_id=user_id).first()
            if user:
                return session.query(SeenNews).filter_by(
                    user_id=user.id,
                    news_hash=news_hash
                ).first() is not None
            return False

    def get_sources(self, source_type: Optional[str] = None) -> List[Dict]:
        """Получает список источников новостей."""
        with self.Session() as session:
            query = session.query(NewsSource)
            if source_type:
                query = query.filter_by(type=source_type)
            sources = query.filter_by(is_active=True).all()
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

    def add_source(self, url: str, name: str, source_type: str) -> bool:
        """Добавляет новый источник новостей."""
        with self.Session() as session:
            try:
                source = NewsSource(url=url, name=name, type=source_type)
                session.add(source)
                session.commit()
                return True
            except Exception as e:
                logger.error(f"Ошибка при добавлении источника: {e}")
                session.rollback()
                return False

    def remove_source(self, source_id: int) -> bool:
        """Удаляет источник новостей."""
        with self.Session() as session:
            try:
                source = session.query(NewsSource).filter_by(id=source_id).first()
                if source:
                    source.is_active = False
                    session.commit()
                    return True
                return False
            except Exception as e:
                logger.error(f"Ошибка при удалении источника: {e}")
                session.rollback()
                return False

    def update_source_last_fetch(self, source_id: int):
        """Обновляет время последней проверки источника."""
        with self.Session() as session:
            try:
                source = session.query(NewsSource).filter_by(id=source_id).first()
                if source:
                    source.last_fetch = func.now()
                    session.commit()
            except Exception as e:
                logger.error(f"Ошибка при обновлении времени проверки источника: {e}")
                session.rollback() 