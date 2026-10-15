import re
from typing import List, Dict, Optional

import config
from news_sources import rss_handler

PUBLIC_RSSHUB_URL = "https://rsshub.app"

# @channel, channel, t.me/channel, t.me/s/channel и ссылка на пост t.me/channel/123
_CHANNEL_RE = re.compile(
    r"^(?:@|(?:https?://)?(?:www\.)?(?:t|telegram)\.me/(?:s/)?)?"
    r"([a-z][a-z0-9_]{4,31})"
    r"(?:/\d+)?/?(?:\?\S*)?$",
    re.IGNORECASE,
)


def channel_name(text: str) -> Optional[str]:
    """Возвращает имя публичного канала из того, что прислал пользователь, или None."""
    match = _CHANNEL_RE.match(text.strip())
    # Имена в Telegram не зависят от регистра
    return match.group(1).lower() if match else None


# Маршрут RSSHub /telegram/channel/<имя>[/routeParams][?query]
_ROUTE_CHANNEL_RE = re.compile(r"^/telegram/channel/([a-z][a-z0-9_]{4,31})(?:/[^?]*)?(?:\?.*)?$", re.IGNORECASE)


def route_channel_name(path: str) -> Optional[str]:
    """Имя канала, если путь маршрута RSSHub — Telegram-канал, иначе None."""
    match = _ROUTE_CHANNEL_RE.match(path)
    return match.group(1).lower() if match else None


def channel_url(name: str) -> str:
    """Канонический адрес канала, который хранится в news_sources.url."""
    return f"https://t.me/{name}"


def route_path(url: str) -> Optional[str]:
    """Путь маршрута, если url ведёт на RSSHub (свой экземпляр или публичный), иначе None."""
    for base in (config.RSSHUB_BASE_URL, PUBLIC_RSSHUB_URL):
        if base and url.startswith(base + "/"):
            return url[len(base):]
    return None


async def fetch_route(path: str) -> List[Dict]:
    """Опрашивает маршрут RSSHub по пути, сохранённому в news_sources.url."""
    if not config.RSSHUB_BASE_URL:
        raise RuntimeError("маршруты RSSHub отключены: не задан RSSHUB_BASE_URL")
    return await rss_handler.fetch(config.RSSHUB_BASE_URL + path)
