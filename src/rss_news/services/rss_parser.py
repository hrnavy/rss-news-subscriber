"""RSS 解析模块

负责获取和解析 RSS/Atom feed 内容。
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Optional
from urllib.parse import urlparse

import feedparser
import httpx

from rss_news.services.config import FetchConfig

logger = logging.getLogger(__name__)


@dataclass
class ParsedArticle:
    """解析后的文章数据
    
    Attributes:
        title: 文章标题
        link: 文章链接
        content: 文章内容
        published_at: 发布时间
        author: 作者
    """
    title: str
    link: str
    content: str = ""
    published_at: Optional[str] = None
    author: Optional[str] = None


@dataclass
class ParsedFeed:
    """解析后的订阅源数据
    
    Attributes:
        title: 订阅源标题
        description: 订阅源描述
        link: 订阅源网站链接
        articles: 文章列表
    """
    title: str
    description: str = ""
    link: str = ""
    articles: list[ParsedArticle] = None
    
    def __post_init__(self):
        if self.articles is None:
            self.articles = []


class RSSParseError(Exception):
    """RSS 解析错误"""
    pass


class RSSParser:
    """RSS/Atom 解析器
    
    负责异步获取 RSS 内容并解析为结构化数据。
    """
    
    def __init__(self, config: Optional[FetchConfig] = None):
        """初始化解析器
        
        Args:
            config: 抓取配置，如果未提供则使用默认配置
        """
        self.config = config or FetchConfig()
        self._client: Optional[httpx.AsyncClient] = None
    
    async def _get_client(self) -> httpx.AsyncClient:
        """获取或创建 HTTP 客户端
        
        使用懒加载模式，首次调用时创建客户端。
        
        Returns:
            httpx.AsyncClient 实例
        """
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=self.config.timeout,
                follow_redirects=True,
                headers={
                    "User-Agent": "RSS-News-Reader/1.0",
                    "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, */*",
                }
            )
        return self._client
    
    async def close(self) -> None:
        """关闭 HTTP 客户端
        
        释放资源，应在不再使用解析器时调用。
        """
        if self._client is not None:
            await self._client.aclose()
            self._client = None
    
    async def fetch_content(self, url: str) -> str:
        """异步获取 RSS 内容
        
        Args:
            url: RSS 订阅源 URL
            
        Returns:
            RSS 内容字符串
            
        Raises:
            RSSParseError: 获取失败时抛出
        """
        client = await self._get_client()
        
        for attempt in range(self.config.max_retries):
            try:
                response = await client.get(url)
                response.raise_for_status()
                return response.text
            except httpx.TimeoutException:
                logger.warning(f"获取 RSS 超时 (尝试 {attempt + 1}/{self.config.max_retries}): {url}")
                if attempt == self.config.max_retries - 1:
                    raise RSSParseError(f"获取 RSS 超时: {url}")
            except httpx.HTTPStatusError as e:
                logger.error(f"HTTP 错误: {e.response.status_code} - {url}")
                raise RSSParseError(f"HTTP 错误 {e.response.status_code}: {url}")
            except httpx.RequestError as e:
                logger.warning(f"网络错误 (尝试 {attempt + 1}/{self.config.max_retries}): {e}")
                if attempt == self.config.max_retries - 1:
                    raise RSSParseError(f"网络错误: {e}")
        
        raise RSSParseError(f"获取 RSS 失败: {url}")
    
    def _parse_datetime(self, dt_struct) -> Optional[str]:
        """解析时间结构为 ISO 格式字符串
        
        feedparser 返回的时间结构可能是 time.struct_time 或字符串。
        
        Args:
            dt_struct: feedparser 返回的时间结构
            
        Returns:
            ISO 格式的时间字符串，解析失败返回 None
        """
        if dt_struct is None:
            return None
        
        try:
            if hasattr(dt_struct, 'tm_year'):
                dt = datetime(
                    year=dt_struct.tm_year,
                    month=dt_struct.tm_mon,
                    day=dt_struct.tm_mday,
                    hour=dt_struct.tm_hour,
                    minute=dt_struct.tm_min,
                    second=dt_struct.tm_sec,
                )
                return dt.isoformat()
        except (ValueError, AttributeError) as e:
            logger.debug(f"解析时间失败: {e}")
        
        return None
    
    def _extract_content(self, entry) -> str:
        """从 entry 中提取文章内容
        
        RSS 和 Atom 格式存储内容的位置不同，需要尝试多个字段。
        
        Args:
            entry: feedparser 解析的 entry 对象
            
        Returns:
            文章内容字符串
        """
        # 优先级：content > content:encoded > summary > description
        if hasattr(entry, 'content') and entry.content:
            # content 可能是列表，取第一个
            content = entry.content[0] if isinstance(entry.content, list) else entry.content
            if hasattr(content, 'value'):
                return content.value
            return str(content)
        
        # 尝试 content:encoded (常见于 WordPress RSS)
        if hasattr(entry, 'content_encoded'):
            return entry.content_encoded
        
        # 使用 summary 作为后备
        if hasattr(entry, 'summary'):
            return entry.summary
        
        # 最后尝试 description
        if hasattr(entry, 'description'):
            return entry.description
        
        return ""
    
    def _extract_link(self, entry) -> str:
        """从 entry 中提取文章链接
        
        不同 feed 格式链接字段可能不同。
        
        Args:
            entry: feedparser 解析的 entry 对象
            
        Returns:
            文章链接字符串
        """
        # 优先使用 link
        if hasattr(entry, 'link') and entry.link:
            return entry.link
        
        # 尝试 links 列表中的 alternate 链接
        if hasattr(entry, 'links'):
            for link in entry.links:
                if link.get('rel') == 'alternate':
                    return link.get('href', '')
        
        # 尝试 href
        if hasattr(entry, 'href'):
            return entry.href
        
        return ""
    
    def _extract_title(self, entry) -> str:
        """从 entry 中提取文章标题
        
        Args:
            entry: feedparser 解析的 entry 对象
            
        Returns:
            文章标题字符串
        """
        if hasattr(entry, 'title') and entry.title:
            return entry.title
        if hasattr(entry, 'title_detail') and hasattr(entry.title_detail, 'value'):
            return entry.title_detail.value
        return "无标题"
    
    def parse_feed(self, content: str, feed_url: str = "") -> ParsedFeed:
        """解析 RSS 内容
        
        Args:
            content: RSS 内容字符串
            feed_url: 订阅源 URL（用于错误提示）
            
        Returns:
            解析后的 ParsedFeed 对象
            
        Raises:
            RSSParseError: 解析失败时抛出
        """
        try:
            feed = feedparser.parse(content)
        except Exception as e:
            logger.error(f"RSS 解析异常: {e}")
            raise RSSParseError(f"RSS 解析异常: {e}")
        
        # 检查解析结果
        if feed.bozo:
            # bozo 表示解析遇到问题，但可能仍有数据
            logger.warning(f"RSS 解析警告 ({feed_url}): {feed.bozo_exception}")
            
            # 如果没有任何条目，则认为是严重错误
            if not feed.entries:
                raise RSSParseError(f"无效的 RSS 格式: {feed_url}")
        
        # 提取 feed 信息
        feed_info = feed.feed if hasattr(feed, 'feed') else {}
        title = getattr(feed_info, 'title', '') or urlparse(feed_url).netloc or "未知订阅源"
        description = getattr(feed_info, 'description', '') or getattr(feed_info, 'subtitle', '') or ""
        link = getattr(feed_info, 'link', '') or ""
        
        # 解析文章列表
        articles = []
        for entry in feed.entries:
            article = ParsedArticle(
                title=self._extract_title(entry),
                link=self._extract_link(entry),
                content=self._extract_content(entry),
                published_at=self._parse_datetime(
                    getattr(entry, 'published_parsed', None) or 
                    getattr(entry, 'updated_parsed', None)
                ),
                author=getattr(entry, 'author', None),
            )
            
            # 只保留有效链接的文章
            if article.link:
                articles.append(article)
        
        logger.info(f"解析完成: {title} - {len(articles)} 篇文章")
        
        return ParsedFeed(
            title=title,
            description=description,
            link=link,
            articles=articles,
        )
    
    async def fetch_and_parse(self, url: str) -> ParsedFeed:
        """获取并解析 RSS 订阅源
        
        这是主要入口方法，组合了获取和解析两个步骤。
        
        Args:
            url: RSS 订阅源 URL
            
        Returns:
            解析后的 ParsedFeed 对象
            
        Raises:
            RSSParseError: 获取或解析失败时抛出
        """
        logger.info(f"开始获取 RSS: {url}")
        content = await self.fetch_content(url)
        return self.parse_feed(content, url)


# 全局解析器实例
_parser: Optional[RSSParser] = None


def get_parser(config: Optional[FetchConfig] = None) -> RSSParser:
    """获取全局解析器实例
    
    使用单例模式，避免重复创建 HTTP 客户端。
    
    Args:
        config: 抓取配置，仅首次调用时有效
        
    Returns:
        RSSParser 实例
    """
    global _parser
    if _parser is None:
        _parser = RSSParser(config)
    return _parser


async def close_parser() -> None:
    """关闭全局解析器"""
    global _parser
    if _parser is not None:
        await _parser.close()
        _parser = None
