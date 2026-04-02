"""RSS 订阅源验证模块

提供 RSS 源 URL 的可访问性和格式验证功能。
"""

from dataclasses import dataclass
from typing import Optional

import feedparser
import httpx


@dataclass
class ValidationResult:
    """验证结果数据模型
    
    Attributes:
        is_valid: 是否验证通过
        url_accessible: URL 是否可访问
        feed_valid: RSS 格式是否正确
        title: RSS 源标题（解析成功时）
        description: RSS 源描述（解析成功时）
        error_message: 错误信息（验证失败时）
    """
    is_valid: bool
    url_accessible: bool = False
    feed_valid: bool = False
    title: Optional[str] = None
    description: Optional[str] = None
    error_message: Optional[str] = None


class FeedValidator:
    """RSS 订阅源验证器
    
    负责验证 RSS 源的 URL 可访问性和 RSS 格式正确性。
    """
    
    def __init__(self, timeout: int = 30):
        """初始化验证器
        
        Args:
            timeout: HTTP 请求超时时间（秒）
        """
        self.timeout = timeout
    
    async def validate_url(self, url: str) -> tuple[bool, Optional[str]]:
        """验证 URL 可访问性
        
        使用 HEAD 请求检查 URL 是否可以访问。
        如果 HEAD 请求失败（如 405），返回 True 让后续内容验证来处理。
        
        Args:
            url: 要验证的 URL
            
        Returns:
            元组 (是否可访问, 错误信息)
        """
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.head(url, follow_redirects=True)
                
                if response.status_code >= 400:
                    return True, None
                
                return True, None
                
        except httpx.TimeoutException:
            return False, "请求超时"
        except httpx.ConnectError:
            return False, "无法连接到服务器"
        except httpx.InvalidURL:
            return False, "URL 格式无效"
        except Exception:
            return True, None
    
    async def validate_feed_content(self, url: str) -> tuple[bool, Optional[str], Optional[str], Optional[str]]:
        """验证 RSS 内容格式
        
        获取并解析 RSS 内容，验证格式是否正确。
        
        Args:
            url: RSS 源 URL
            
        Returns:
            元组 (是否有效, 错误信息, 标题, 描述)
        """
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(url, follow_redirects=True)
                
                if response.status_code >= 400:
                    return False, f"HTTP 错误: {response.status_code}", None, None
                
                content = response.text
                
                feed = feedparser.parse(content)
                
                if feed.bozo:
                    bozo_error = getattr(feed, 'bozo_exception', None)
                    error_msg = f"RSS 格式错误: {str(bozo_error)}" if bozo_error else "RSS 格式错误"
                    return False, error_msg, None, None
                
                if not feed.entries:
                    return False, "RSS 源中没有文章条目", None, None
                
                title = feed.feed.get('title', '')
                description = feed.feed.get('description', '')
                
                return True, None, title, description
                
        except httpx.TimeoutException:
            return False, "请求超时", None, None
        except httpx.ConnectError:
            return False, "无法连接到服务器", None, None
        except Exception as e:
            return False, f"解析错误: {str(e)}", None, None
    
    async def validate(self, url: str) -> ValidationResult:
        """完整验证 RSS 源
        
        先验证 URL 可访问性，再验证 RSS 内容格式。
        
        Args:
            url: RSS 源 URL
            
        Returns:
            ValidationResult: 验证结果对象
        """
        url_accessible, url_error = await self.validate_url(url)
        
        if not url_accessible:
            return ValidationResult(
                is_valid=False,
                url_accessible=False,
                feed_valid=False,
                error_message=url_error,
            )
        
        feed_valid, feed_error, title, description = await self.validate_feed_content(url)
        
        if not feed_valid:
            return ValidationResult(
                is_valid=False,
                url_accessible=True,
                feed_valid=False,
                error_message=feed_error,
            )
        
        return ValidationResult(
            is_valid=True,
            url_accessible=True,
            feed_valid=True,
            title=title,
            description=description,
        )


_validator_instance: Optional[FeedValidator] = None


def get_validator(timeout: int = 30) -> FeedValidator:
    """获取验证器单例
    
    Args:
        timeout: HTTP 请求超时时间（秒）
        
    Returns:
        FeedValidator 实例
    """
    global _validator_instance
    
    if _validator_instance is None:
        _validator_instance = FeedValidator(timeout=timeout)
    
    return _validator_instance
