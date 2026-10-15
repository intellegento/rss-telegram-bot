import feedparser
from typing import List, Dict
from datetime import datetime, timezone
import aiohttp
from bs4 import BeautifulSoup

from config import HTTP_TIMEOUT


def parse_feed(content: str) -> List[Dict]:
    """Парсит содержимое RSS-канала в записи (guid, title, url, summary, published_at)."""
    feed = feedparser.parse(content)
    news_items = []

    for entry in feed.entries:
        title = entry.get('title', '')
        link = entry.get('link', '')

        # Очищаем описание от HTML-тегов
        soup = BeautifulSoup(entry.get('description', ''), 'html.parser')
        clean_description = soup.get_text()

        # Получаем дату публикации
        published = entry.get('published_parsed', None)

        news_items.append({
            'guid': entry.get('id') or link or title,
            'title': title,
            'url': link,
            'summary': clean_description[:200] + '...' if len(clean_description) > 200 else clean_description,
            'published_at': datetime(*published[:6], tzinfo=timezone.utc) if published else None,
        })

    return news_items


async def fetch(url: str) -> List[Dict]:
    """Получает и парсит RSS-канал. Ошибки сети и HTTP пробрасываются."""
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=HTTP_TIMEOUT)) as session:
        async with session.get(url) as response:
            response.raise_for_status()
            return parse_feed(await response.text())
