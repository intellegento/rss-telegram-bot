import re
from typing import List, Dict
from datetime import datetime
import pytz

def format_message(news_item: Dict) -> str:
    """Форматирует новость для отправки в Telegram."""
    title = news_item['title']
    link = news_item['link']
    description = news_item['description']
    source = news_item.get('source', 'rss')
    
    # Форматируем дату в московское время
    moscow_tz = pytz.timezone('Europe/Moscow')
    if isinstance(news_item['published'], datetime):
        published = news_item['published'].astimezone(moscow_tz)
        date_str = published.strftime('%d.%m.%Y %H:%M')
    else:
        date_str = "Дата не указана"

    source_emoji = "📰" if source == "rss" else "💰"
    
    message = (
        f"{source_emoji} <b>{title}</b>\n\n"
        f"{description}\n\n"
        f"🕒 {date_str}\n"
        f"🔗 <a href='{link}'>Подробнее</a>"
    )
    
    return message

def highlight_keywords(text: str, keywords: List[str]) -> str:
    """Выделяет ключевые слова в тексте жирным шрифтом."""
    if not keywords:
        return text
        
    pattern = '|'.join(map(re.escape, keywords))
    return re.sub(
        f'({pattern})',
        r'<b>\1</b>',
        text,
        flags=re.IGNORECASE
    )

def validate_keyword(keyword: str) -> bool:
    """Проверяет валидность ключевого слова."""
    # Минимальная длина - 2 символа
    if len(keyword) < 2:
        return False
        
    # Максимальная длина - 50 символов
    if len(keyword) > 50:
        return False
        
    # Разрешаем буквы, цифры и некоторые специальные символы
    if not re.match(r'^[\w\s\-\.\,]+$', keyword):
        return False
        
    return True

def clean_username(username: str) -> str:
    """Очищает имя пользователя от специальных символов."""
    return re.sub(r'[^\w\s\-]', '', username) 