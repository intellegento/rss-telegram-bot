from datetime import datetime
from typing import List, Dict

import aiohttp
from bs4 import BeautifulSoup

from config import HTTP_TIMEOUT


def _text(element) -> str:
    """Текст поста без HTML: переносы строк становятся пробелами, лишние пробелы убираются."""
    if element is None:
        return ''
    for br in element.find_all('br'):
        br.replace_with('\n')
    return ' '.join(element.get_text().split())


def parse_channel_page(content: str) -> List[Dict]:
    """Разбирает публичную страницу канала t.me/s/<имя> в записи (guid, title, url, summary, published_at).

    Если постов нет (канал закрытый, не существует или без веб-превью), бросает ValueError.
    """
    soup = BeautifulSoup(content, 'html.parser')
    items = []
    for message in soup.select('.tgme_widget_message[data-post]'):
        # data-post = "<имя>/<id поста>"
        post = message['data-post']
        text = _text(message.select_one('.tgme_widget_message_text'))
        date = message.select_one('.tgme_widget_message_date time[datetime]')
        items.append({
            'guid': post.rsplit('/', 1)[-1],
            # У постов канала нет заголовка: берём начало текста
            'title': text[:100],
            'url': f"https://t.me/{post}",
            'summary': text[:200] + '...' if len(text) > 200 else text,
            'published_at': datetime.fromisoformat(date['datetime']) if date else None,
        })
    if not items:
        raise ValueError("на странице канала нет постов: канал закрытый, не существует или без веб-превью")
    return items


async def fetch(url: str) -> List[Dict]:
    """Читает канал https://t.me/<имя> с его публичной страницы https://t.me/s/<имя>."""
    name = url.rsplit('/', 1)[-1]
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=HTTP_TIMEOUT)) as session:
        async with session.get(f"https://t.me/s/{name}") as response:
            response.raise_for_status()
            return parse_channel_page(await response.text())
