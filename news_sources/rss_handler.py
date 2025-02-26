import feedparser
import hashlib
from typing import List, Dict, Optional
from datetime import datetime
import aiohttp
import asyncio
from bs4 import BeautifulSoup

class RSSHandler:
    def __init__(self):
        self.session = None

    async def init_session(self):
        if not self.session:
            self.session = aiohttp.ClientSession()

    async def close_session(self):
        if self.session:
            await self.session.close()
            self.session = None

    def generate_news_hash(self, title: str, link: str) -> str:
        """Генерирует уникальный хеш для новости."""
        return hashlib.md5(f"{title}{link}".encode()).hexdigest()

    async def fetch_rss(self, url: str) -> Optional[str]:
        """Асинхронно получает содержимое RSS-канала."""
        try:
            await self.init_session()
            async with self.session.get(url) as response:
                if response.status == 200:
                    return await response.text()
                return None
        except Exception as e:
            print(f"Ошибка при получении RSS с {url}: {e}")
            return None

    async def parse_feed(self, content: str) -> List[Dict]:
        """Парсит содержимое RSS-канала."""
        feed = feedparser.parse(content)
        news_items = []

        for entry in feed.entries:
            try:
                title = entry.get('title', '')
                link = entry.get('link', '')
                description = entry.get('description', '')
                
                # Очищаем описание от HTML-тегов
                soup = BeautifulSoup(description, 'html.parser')
                clean_description = soup.get_text()

                # Получаем дату публикации
                published = entry.get('published_parsed', None)
                if published:
                    published_date = datetime(*published[:6])
                else:
                    published_date = datetime.now()

                news_hash = self.generate_news_hash(title, link)
                
                news_items.append({
                    'title': title,
                    'link': link,
                    'description': clean_description[:200] + '...' if len(clean_description) > 200 else clean_description,
                    'published': published_date,
                    'hash': news_hash
                })
            except Exception as e:
                print(f"Ошибка при обработке новости: {e}")
                continue

        return news_items

    async def get_news(self, urls: List[str]) -> List[Dict]:
        """Получает новости из списка RSS-каналов."""
        all_news = []
        
        for url in urls:
            content = await self.fetch_rss(url)
            if content:
                news_items = await self.parse_feed(content)
                all_news.extend(news_items)

        # Сортируем по дате публикации
        all_news.sort(key=lambda x: x['published'], reverse=True)
        return all_news

    def filter_news_by_keywords(self, news_items: List[Dict], keywords: List[str]) -> List[Dict]:
        """Фильтрует новости по ключевым словам."""
        if not keywords:
            return news_items

        filtered_news = []
        for news in news_items:
            text = f"{news['title']} {news['description']}".lower()
            if any(keyword.lower() in text for keyword in keywords):
                filtered_news.append(news)

        return filtered_news 