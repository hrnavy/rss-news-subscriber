"""新闻抓取服务模块

负责从 RSS 订阅源抓取新闻文章。
"""

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from rss_news.db.connection import get_connection
from rss_news.models.article import Article, ArticleCreate
from rss_news.models.feed import Feed
from rss_news.services.config import FetchConfig
from rss_news.services.rss_parser import ParsedArticle, RSSParser, RSSParseError

logger = logging.getLogger(__name__)


@dataclass
class FetchResult:
    """抓取结果
    
    Attributes:
        feed_id: 订阅源 ID
        success: 是否成功
        new_articles: 新文章数量
        total_articles: 总文章数量
        error_message: 错误信息
    """
    feed_id: int
    success: bool
    new_articles: int = 0
    total_articles: int = 0
    error_message: Optional[str] = None


class FeedFetcher:
    """新闻抓取服务
    
    负责从 RSS 订阅源抓取文章并保存到数据库。
    """
    
    def __init__(self, config: Optional[FetchConfig] = None):
        """初始化抓取服务
        
        Args:
            config: 抓取配置
        """
        self.config = config or FetchConfig()
        self._parser = RSSParser(self.config)
    
    async def close(self) -> None:
        """关闭资源"""
        await self._parser.close()
    
    def _get_feed_by_id(self, feed_id: int) -> Optional[Feed]:
        """根据 ID 获取订阅源
        
        Args:
            feed_id: 订阅源 ID
            
        Returns:
            Feed 对象，不存在则返回 None
        """
        with get_connection() as conn:
            cursor = conn.execute(
                "SELECT id, title, url, description, is_active, last_fetched, created_at "
                "FROM feeds WHERE id = ?",
                (feed_id,)
            )
            row = cursor.fetchone()
            if row:
                return Feed.from_row(row)
        return None
    
    def _get_all_active_feeds(self) -> list[Feed]:
        """获取所有活跃的订阅源
        
        Returns:
            活跃订阅源列表
        """
        with get_connection() as conn:
            cursor = conn.execute(
                "SELECT id, title, url, description, is_active, last_fetched, created_at "
                "FROM feeds WHERE is_active = 1"
            )
            rows = cursor.fetchall()
            return [Feed.from_row(row) for row in rows]
    
    def _update_feed_last_fetched(self, feed_id: int) -> None:
        """更新订阅源的最后抓取时间
        
        Args:
            feed_id: 订阅源 ID
        """
        now = datetime.now().isoformat()
        with get_connection() as conn:
            conn.execute(
                "UPDATE feeds SET last_fetched = ? WHERE id = ?",
                (now, feed_id)
            )
    
    def _article_exists(self, link: str) -> bool:
        """检查文章是否已存在
        
        实现增量抓取的关键方法。
        
        Args:
            link: 文章链接
            
        Returns:
            True 如果文章已存在
        """
        with get_connection() as conn:
            cursor = conn.execute(
                "SELECT 1 FROM articles WHERE link = ? LIMIT 1",
                (link,)
            )
            return cursor.fetchone() is not None
    
    def _save_article(self, feed_id: int, article: ParsedArticle, is_title_only: bool = False) -> bool:
        """保存文章到数据库
        
        Args:
            feed_id: 订阅源 ID
            article: 解析后的文章数据
            is_title_only: 是否为标题源（标题源只保存标题，不保存内容）
            
        Returns:
            True 如果保存成功（新文章），False 如果文章已存在
        """
        # 检查文章是否已存在（增量抓取）
        if self._article_exists(article.link):
            logger.debug(f"文章已存在，跳过: {article.link}")
            return False
        
        try:
            with get_connection() as conn:
                if is_title_only:
                    # 标题源：content 为空，summary 为标题，keywords 为空
                    conn.execute(
                        """INSERT INTO articles 
                           (feed_id, title, link, content, summary, keywords, published_at, created_at)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                        (
                            feed_id,
                            article.title,
                            article.link,
                            "",  # content 为空
                            article.title,  # summary 为标题
                            None,  # keywords 为空
                            article.published_at,
                            datetime.now().isoformat(),
                        )
                    )
                else:
                    # 全文源：正常保存
                    conn.execute(
                        """INSERT INTO articles 
                           (feed_id, title, link, content, published_at, created_at)
                           VALUES (?, ?, ?, ?, ?, ?)""",
                        (
                            feed_id,
                            article.title,
                            article.link,
                            article.content,
                            article.published_at,
                            datetime.now().isoformat(),
                        )
                    )
            logger.debug(f"保存新文章: {article.title}")
            return True
        except Exception as e:
            # 可能存在并发插入导致的唯一约束冲突
            logger.warning(f"保存文章失败: {e}")
            return False
    
    async def fetch_feed(self, feed_id: int) -> FetchResult:
        """抓取单个订阅源
        
        Args:
            feed_id: 订阅源 ID
            
        Returns:
            FetchResult: 抓取结果
        """
        # 获取订阅源信息
        feed = self._get_feed_by_id(feed_id)
        if feed is None:
            return FetchResult(
                feed_id=feed_id,
                success=False,
                error_message=f"订阅源不存在: {feed_id}"
            )
        
        if not feed.is_active_bool:
            return FetchResult(
                feed_id=feed_id,
                success=False,
                error_message=f"订阅源已停用: {feed.title}"
            )
        
        logger.info(f"开始抓取订阅源: {feed.title} ({feed.url})")
        
        # 判断是否为标题源
        is_title_only = feed.is_title_only
        if is_title_only:
            logger.info(f"检测到标题源: {feed.title}")
        
        try:
            # 获取并解析 RSS
            parsed_feed = await self._parser.fetch_and_parse(feed.url)
            
            # 保存文章
            new_count = 0
            for article in parsed_feed.articles:
                if self._save_article(feed_id, article, is_title_only=is_title_only):
                    new_count += 1
            
            # 更新最后抓取时间
            self._update_feed_last_fetched(feed_id)
            
            logger.info(f"抓取完成: {feed.title} - {new_count}/{len(parsed_feed.articles)} 篇新文章")
            
            return FetchResult(
                feed_id=feed_id,
                success=True,
                new_articles=new_count,
                total_articles=len(parsed_feed.articles),
            )
            
        except RSSParseError as e:
            error_msg = f"RSS 解析错误: {e}"
            logger.error(f"抓取失败: {feed.title} - {error_msg}")
            return FetchResult(
                feed_id=feed_id,
                success=False,
                error_message=error_msg,
            )
        except Exception as e:
            error_msg = f"未知错误: {e}"
            logger.error(f"抓取失败: {feed.title} - {error_msg}")
            return FetchResult(
                feed_id=feed_id,
                success=False,
                error_message=error_msg,
            )
    
    async def fetch_all_feeds(self, concurrency: int = 3) -> list[FetchResult]:
        """抓取所有活跃的订阅源
        
        使用并发控制，避免同时请求过多订阅源。
        
        Args:
            concurrency: 并发数量，默认 3
            
        Returns:
            所有订阅源的抓取结果列表
        """
        feeds = self._get_all_active_feeds()
        
        if not feeds:
            logger.info("没有活跃的订阅源")
            return []
        
        logger.info(f"开始抓取 {len(feeds)} 个订阅源，并发数: {concurrency}")
        
        # 使用信号量控制并发
        semaphore = asyncio.Semaphore(concurrency)
        
        async def fetch_with_semaphore(feed: Feed) -> FetchResult:
            async with semaphore:
                return await self.fetch_feed(feed.id)
        
        # 并发抓取所有订阅源
        tasks = [fetch_with_semaphore(feed) for feed in feeds]
        results = await asyncio.gather(*tasks)
        
        # 统计结果
        success_count = sum(1 for r in results if r.success)
        total_new = sum(r.new_articles for r in results)
        
        logger.info(f"全部抓取完成: {success_count}/{len(feeds)} 成功, {total_new} 篇新文章")
        
        return list(results)


# 全局抓取器实例
_fetcher: Optional[FeedFetcher] = None


def get_fetcher(config: Optional[FetchConfig] = None) -> FeedFetcher:
    """获取全局抓取器实例
    
    Args:
        config: 抓取配置，仅首次调用时有效
        
    Returns:
        FeedFetcher 实例
    """
    global _fetcher
    if _fetcher is None:
        _fetcher = FeedFetcher(config)
    return _fetcher


async def close_fetcher() -> None:
    """关闭全局抓取器"""
    global _fetcher
    if _fetcher is not None:
        await _fetcher.close()
        _fetcher = None
