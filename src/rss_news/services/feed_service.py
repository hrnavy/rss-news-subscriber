"""RSS 订阅源管理服务

提供订阅源的增删改查和状态管理功能。
"""

from datetime import datetime
from typing import List, Optional

from rss_news.db.connection import get_connection
from rss_news.models.feed import Feed, FeedCreate, FeedUpdate
from rss_news.services.feed_validator import FeedValidator, ValidationResult


class FeedServiceError(Exception):
    """订阅源服务错误基类"""
    pass


class FeedNotFoundError(FeedServiceError):
    """订阅源不存在错误"""
    pass


class FeedAlreadyExistsError(FeedServiceError):
    """订阅源已存在错误"""
    pass


class FeedValidationError(FeedServiceError):
    """订阅源验证错误"""
    pass


class FeedService:
    """RSS 订阅源管理服务
    
    提供订阅源的完整生命周期管理，包括验证、添加、更新、删除和查询。
    """
    
    def __init__(self, validator: Optional[FeedValidator] = None):
        """初始化订阅源服务
        
        Args:
            validator: RSS 源验证器实例，如果为 None 则创建默认实例
        """
        self.validator = validator or FeedValidator()
    
    async def add_feed(
        self,
        url: str,
        title: Optional[str] = None,
        description: Optional[str] = None,
        skip_validation: bool = False,
    ) -> Feed:
        """添加新的订阅源
        
        验证 URL 可访问性和 RSS 格式，然后添加到数据库。
        
        Args:
            url: RSS 源 URL
            title: 订阅源标题（可选，默认使用 RSS 源标题）
            description: 订阅源描述（可选，默认使用 RSS 源描述）
            skip_validation: 是否跳过验证（默认 False）
            
        Returns:
            Feed: 新创建的订阅源对象
            
        Raises:
            FeedAlreadyExistsError: 订阅源 URL 已存在
            FeedValidationError: RSS 源验证失败
        """
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM feeds WHERE url = ?", (url,))
            if cursor.fetchone():
                raise FeedAlreadyExistsError(f"订阅源已存在: {url}")
        
        if not skip_validation:
            validation_result = await self.validator.validate(url)
            
            if not validation_result.is_valid:
                raise FeedValidationError(
                    f"RSS 源验证失败: {validation_result.error_message}"
                )
            
            if title is None:
                title = validation_result.title or "未知标题"
            if description is None:
                description = validation_result.description or ""
        else:
            if title is None:
                title = "未知标题"
            if description is None:
                description = ""
        
        feed_create = FeedCreate(
            title=title,
            url=url,
            description=description,
            is_active=1,
        )
        
        feed = feed_create.to_feed()
        
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO feeds (title, url, description, is_active, last_fetched, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                feed.to_tuple(),
            )
            feed.id = cursor.lastrowid
        
        return feed
    
    def remove_feed(self, feed_id: int) -> None:
        """删除订阅源
        
        删除指定的订阅源及其关联的所有文章（CASCADE）。
        
        Args:
            feed_id: 订阅源 ID
            
        Raises:
            FeedNotFoundError: 订阅源不存在
        """
        with get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("SELECT id FROM feeds WHERE id = ?", (feed_id,))
            if not cursor.fetchone():
                raise FeedNotFoundError(f"订阅源不存在: ID={feed_id}")
            
            cursor.execute("DELETE FROM feeds WHERE id = ?", (feed_id,))
    
    def update_feed(self, feed_id: int, **kwargs) -> Feed:
        """更新订阅源信息
        
        支持更新 title、url、description、is_active 字段。
        
        Args:
            feed_id: 订阅源 ID
            **kwargs: 要更新的字段和值
            
        Returns:
            Feed: 更新后的订阅源对象
            
        Raises:
            FeedNotFoundError: 订阅源不存在
            FeedAlreadyExistsError: 新 URL 已被其他订阅源使用
        """
        allowed_fields = {'title', 'url', 'description', 'is_active'}
        update_fields = {k: v for k, v in kwargs.items() if k in allowed_fields}
        
        if not update_fields:
            raise ValueError("没有提供有效的更新字段")
        
        with get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute(
                "SELECT id, title, url, description, is_active, last_fetched, created_at FROM feeds WHERE id = ?",
                (feed_id,),
            )
            row = cursor.fetchone()
            if not row:
                raise FeedNotFoundError(f"订阅源不存在: ID={feed_id}")
            
            if 'url' in update_fields:
                cursor.execute(
                    "SELECT id FROM feeds WHERE url = ? AND id != ?",
                    (update_fields['url'], feed_id),
                )
                if cursor.fetchone():
                    raise FeedAlreadyExistsError(f"URL 已被其他订阅源使用: {update_fields['url']}")
            
            set_clause = ", ".join(f"{field} = ?" for field in update_fields.keys())
            values = list(update_fields.values()) + [feed_id]
            
            cursor.execute(
                f"UPDATE feeds SET {set_clause} WHERE id = ?",
                values,
            )
            
            cursor.execute(
                "SELECT id, title, url, description, is_active, last_fetched, created_at FROM feeds WHERE id = ?",
                (feed_id,),
            )
            updated_row = cursor.fetchone()
            
            return Feed.from_row(updated_row)
    
    def get_feed(self, feed_id: int) -> Feed:
        """获取单个订阅源
        
        Args:
            feed_id: 订阅源 ID
            
        Returns:
            Feed: 订阅源对象
            
        Raises:
            FeedNotFoundError: 订阅源不存在
        """
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, title, url, description, is_active, last_fetched, created_at FROM feeds WHERE id = ?",
                (feed_id,),
            )
            row = cursor.fetchone()
            
            if not row:
                raise FeedNotFoundError(f"订阅源不存在: ID={feed_id}")
            
            return Feed.from_row(row)
    
    def list_feeds(self, is_active: Optional[bool] = None) -> List[Feed]:
        """列出订阅源
        
        Args:
            is_active: 过滤活跃状态（None 表示不过滤）
            
        Returns:
            List[Feed]: 订阅源列表
        """
        with get_connection() as conn:
            cursor = conn.cursor()
            
            if is_active is None:
                cursor.execute(
                    "SELECT id, title, url, description, is_active, last_fetched, created_at FROM feeds ORDER BY created_at DESC"
                )
            else:
                active_value = 1 if is_active else 0
                cursor.execute(
                    "SELECT id, title, url, description, is_active, last_fetched, created_at FROM feeds WHERE is_active = ? ORDER BY created_at DESC",
                    (active_value,),
                )
            
            rows = cursor.fetchall()
            
            return [Feed.from_row(row) for row in rows]
    
    def toggle_feed(self, feed_id: int) -> Feed:
        """切换订阅源活跃状态
        
        将活跃状态在 0 和 1 之间切换。
        
        Args:
            feed_id: 订阅源 ID
            
        Returns:
            Feed: 更新后的订阅源对象
            
        Raises:
            FeedNotFoundError: 订阅源不存在
        """
        with get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute(
                "SELECT id, title, url, description, is_active, last_fetched, created_at FROM feeds WHERE id = ?",
                (feed_id,),
            )
            row = cursor.fetchone()
            if not row:
                raise FeedNotFoundError(f"订阅源不存在: ID={feed_id}")
            
            current_status = row[4]
            new_status = 0 if current_status == 1 else 1
            
            cursor.execute(
                "UPDATE feeds SET is_active = ? WHERE id = ?",
                (new_status, feed_id),
            )
            
            cursor.execute(
                "SELECT id, title, url, description, is_active, last_fetched, created_at FROM feeds WHERE id = ?",
                (feed_id,),
            )
            updated_row = cursor.fetchone()
            
            return Feed.from_row(updated_row)
    
    def update_last_fetched(self, feed_id: int) -> None:
        """更新订阅源的最后抓取时间
        
        Args:
            feed_id: 订阅源 ID
            
        Raises:
            FeedNotFoundError: 订阅源不存在
        """
        with get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("SELECT id FROM feeds WHERE id = ?", (feed_id,))
            if not cursor.fetchone():
                raise FeedNotFoundError(f"订阅源不存在: ID={feed_id}")
            
            now = datetime.now().isoformat()
            cursor.execute(
                "UPDATE feeds SET last_fetched = ? WHERE id = ?",
                (now, feed_id),
            )
    
    def get_feed_count(self, is_active: Optional[bool] = None) -> int:
        """获取订阅源数量
        
        Args:
            is_active: 过滤活跃状态（None 表示不过滤）
            
        Returns:
            int: 订阅源数量
        """
        with get_connection() as conn:
            cursor = conn.cursor()
            
            if is_active is None:
                cursor.execute("SELECT COUNT(*) FROM feeds")
            else:
                active_value = 1 if is_active else 0
                cursor.execute("SELECT COUNT(*) FROM feeds WHERE is_active = ?", (active_value,))
            
            return cursor.fetchone()[0]


_service_instance: Optional[FeedService] = None


def get_feed_service(validator: Optional[FeedValidator] = None) -> FeedService:
    """获取订阅源服务单例
    
    Args:
        validator: RSS 源验证器实例
        
    Returns:
        FeedService 实例
    """
    global _service_instance
    
    if _service_instance is None:
        _service_instance = FeedService(validator=validator)
    
    return _service_instance
