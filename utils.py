import html
import re
from typing import List, Dict, Optional
from urllib.parse import urlparse
from datetime import datetime
import pytz

def format_message(news_item: Dict) -> str:
    """Форматирует новость для отправки в Telegram."""
    title = html.escape(news_item['title'] or '')
    url = news_item['url'] or ''
    description = html.escape(news_item['summary'] or '')
    source = news_item.get('source', 'rss')
    
    # Форматируем дату в московское время
    moscow_tz = pytz.timezone('Europe/Moscow')
    if isinstance(news_item['published_at'], datetime):
        published = news_item['published_at'].astimezone(moscow_tz)
        date_str = published.strftime('%d.%m.%Y %H:%M')
    else:
        date_str = "Дата не указана"

    source_emoji = "📰" if source == "rss" else "💰"
    
    message = (
        f"{source_emoji} <b>{title}</b>\n\n"
        f"{description}\n\n"
        f"🕒 {date_str}"
    )
    # В href попадают только http(s)-ссылки, экранированные вместе с кавычками
    if urlparse(url).scheme.lower() in ('http', 'https'):
        message += f"\n🔗 <a href='{html.escape(url, quote=True)}'>Подробнее</a>"
    
    return message

def matches_keywords(title: Optional[str], summary: Optional[str], keywords: List[str]) -> bool:
    """Проверяет, есть ли в заголовке или описании хотя бы одно ключевое слово (без учёта регистра)."""
    text = f"{title or ''} {summary or ''}".lower()
    return any(keyword.lower() in text for keyword in keywords)

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