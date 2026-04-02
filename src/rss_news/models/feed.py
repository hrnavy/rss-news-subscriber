"""RSS 订阅源数据模型

定义 RSS 订阅源的数据结构和相关操作。
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class Feed:
    """RSS 订阅源数据模型
    
    Attributes:
        id: 订阅源唯一标识符
        title: 订阅源标题
        url: 订阅源 URL（唯一）
        description: 订阅源描述
        is_active: 是否活跃（1=活跃，0=停用）
        last_fetched: 最后抓取时间
        created_at: 创建时间
    """
    id: Optional[int] = None
    title: str = ""
    url: str = ""
    description: str = ""
    is_active: int = 1
    last_fetched: Optional[str] = None
    created_at: Optional[str] = None
    
    def __post_init__(self) -> None:
        """初始化后处理
        
        如果创建时间未设置，则自动设置为当前时间。
        """
        if self.created_at is None:
            self.created_at = datetime.now().isoformat()
    
    @classmethod
    def from_row(cls, row: tuple) -> "Feed":
        """从数据库行数据创建 Feed 实例
        
        Args:
            row: 数据库查询返回的行数据元组
            
        Returns:
            Feed 实例
        """
        return cls(
            id=row[0],
            title=row[1],
            url=row[2],
            description=row[3],
            is_active=row[4],
            last_fetched=row[5],
            created_at=row[6],
        )
    
    def to_tuple(self) -> tuple:
        """转换为数据库插入/更新用的元组
        
        Returns:
            不包含 id 的属性元组
        """
        return (
            self.title,
            self.url,
            self.description,
            self.is_active,
            self.last_fetched,
            self.created_at,
        )
    
    def update_last_fetched(self) -> None:
        """更新最后抓取时间为当前时间"""
        self.last_fetched = datetime.now().isoformat()
    
    @property
    def is_active_bool(self) -> bool:
        """获取活跃状态的布尔值表示
        
        Returns:
            True 如果活跃，否则 False
        """
        return self.is_active == 1


@dataclass
class FeedCreate:
    """创建 RSS 订阅源的输入模型
    
    用于创建新订阅源时的数据验证。
    """
    title: str
    url: str
    description: str = ""
    is_active: int = 1
    
    def to_feed(self) -> Feed:
        """转换为 Feed 实例
        
        Returns:
            新的 Feed 实例
        """
        return Feed(
            title=self.title,
            url=self.url,
            description=self.description,
            is_active=self.is_active,
        )


@dataclass  
class FeedUpdate:
    """更新 RSS 订阅源的输入模型
    
    用于更新订阅源时的数据验证，所有字段均为可选。
    """
    title: Optional[str] = None
    url: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[int] = None
    
    def has_updates(self) -> bool:
        """检查是否有需要更新的字段
        
        Returns:
            True 如果有字段需要更新
        """
        return any([
            self.title is not None,
            self.url is not None,
            self.description is not None,
            self.is_active is not None,
        ])
