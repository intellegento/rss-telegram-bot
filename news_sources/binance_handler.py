import aiohttp
import hashlib
from typing import List, Dict, Optional
from datetime import datetime
import json

class BinanceHandler:
    def __init__(self, api_key: Optional[str] = None, api_secret: Optional[str] = None):
        self.api_key = api_key
        self.api_secret = api_secret
        self.session = None
        self.base_url = "https://www.binance.com/bapi/composite/v1/public/cms"

    async def init_session(self):
        if not self.session:
            self.session = aiohttp.ClientSession()

    async def close_session(self):
        if self.session:
            await self.session.close()
            self.session = None

    def generate_news_hash(self, title: str, code: str) -> str:
        """Генерирует уникальный хеш для новости."""
        return hashlib.md5(f"{title}{code}".encode()).hexdigest()

    async def get_announcements(self, limit: int = 50) -> List[Dict]:
        """Получает последние объявления с Binance."""
        try:
            await self.init_session()
            
            params = {
                "type": "1",
                "pageSize": str(limit),
                "pageNo": "1"
            }
            
            async with self.session.post(
                f"{self.base_url}/announcement/query",
                json=params
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    if data.get("code") == "000000":
                        announcements = []
                        for item in data.get("data", {}).get("catalogs", []):
                            try:
                                title = item.get("title", "")
                                code = item.get("code", "")
                                description = item.get("description", "")
                                published = datetime.fromtimestamp(item.get("releaseDate", 0) / 1000)
                                
                                news_hash = self.generate_news_hash(title, code)
                                
                                announcements.append({
                                    "title": title,
                                    "link": f"https://www.binance.com/en/support/announcement/{code}",
                                    "description": description[:200] + "..." if len(description) > 200 else description,
                                    "published": published,
                                    "hash": news_hash,
                                    "source": "binance"
                                })
                            except Exception as e:
                                print(f"Ошибка при обработке объявления Binance: {e}")
                                continue
                        
                        return announcements
                return []
        except Exception as e:
            print(f"Ошибка при получении объявлений Binance: {e}")
            return []

    def filter_announcements_by_keywords(self, announcements: List[Dict], keywords: List[str]) -> List[Dict]:
        """Фильтрует объявления по ключевым словам."""
        if not keywords:
            return announcements

        filtered_announcements = []
        for announcement in announcements:
            text = f"{announcement['title']} {announcement['description']}".lower()
            if any(keyword.lower() in text for keyword in keywords):
                filtered_announcements.append(announcement)

        return filtered_announcements 