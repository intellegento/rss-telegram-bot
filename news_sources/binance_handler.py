import aiohttp
from typing import List, Dict
from datetime import datetime, timezone

from config import HTTP_TIMEOUT

ANNOUNCEMENTS_URL = "https://www.binance.com/bapi/composite/v1/public/cms/announcement/query"


async def fetch(url: str, limit: int = 50) -> List[Dict]:
    """Получает последние объявления с Binance в записи (guid, title, url, summary, published_at).

    url источника не используется: у Binance один публичный эндпоинт.
    """
    params = {
        "type": "1",
        "pageSize": str(limit),
        "pageNo": "1"
    }
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=HTTP_TIMEOUT)) as session:
        async with session.post(ANNOUNCEMENTS_URL, json=params) as response:
            response.raise_for_status()
            data = await response.json()

    if data.get("code") != "000000":
        raise ValueError(f"Binance вернул код {data.get('code')}")

    announcements = []
    for item in data.get("data", {}).get("catalogs", []):
        code = item.get("code", "")
        description = item.get("description", "")
        release_date = item.get("releaseDate")
        announcements.append({
            "guid": code,
            "title": item.get("title", ""),
            "url": f"https://www.binance.com/en/support/announcement/{code}",
            "summary": description[:200] + "..." if len(description) > 200 else description,
            "published_at": datetime.fromtimestamp(release_date / 1000, tz=timezone.utc) if release_date else None,
        })
    return announcements
