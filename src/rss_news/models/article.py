"""新闻文章数据模型

定义新闻文章的数据结构和相关操作。
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class Article:
    """新闻文章数据模型
    
    Attributes:
        id: 文章唯一标识符
        feed_id: 关联的订阅源 ID
        title: 文章标题
        link: 文章链接（唯一）
        content: 文章内容
        summary: LLM 生成的摘要
        category: LLM 分类的类别
        keywords: LLM 提取的关键词
        published_at: 文章发布时间
        created_at: 记录创建时间
    """
    id: Optional[int] = None
    feed_id: int = 0
    title: str = ""
    link: str = ""
    content: str = ""
    summary: Optional[str] = None
    category: Optional[str] = None
    keywords: Optional[str] = None
    published_at: Optional[str] = None
    created_at: Optional[str] = None
    
    def __post_init__(self) -> None:
        """初始化后处理
        
        如果创建时间未设置，则自动设置为当前时间。
        """
        if self.created_at is None:
            self.created_at = datetime.now().isoformat()
    
    @classmethod
    def from_row(cls, row: tuple) -> "Article":
        """从数据库行数据创建 Article 实例
        
        Args:
            row: 数据库查询返回的行数据元组
            
        Returns:
            Article 实例
        """
        return cls(
            id=row[0],
            feed_id=row[1],
            title=row[2],
            link=row[3],
            content=row[4],
            summary=row[5],
            category=row[6],
            keywords=row[7],
            published_at=row[8],
            created_at=row[9],
        )
    
    def to_tuple(self) -> tuple:
        """转换为数据库插入/更新用的元组
        
        Returns:
            不包含 id 的属性元组
        """
        return (
            self.feed_id,
            self.title,
            self.link,
            self.content,
            self.summary,
            self.category,
            self.keywords,
            self.published_at,
            self.created_at,
        )
    
    def has_llm_analysis(self) -> bool:
        """检查是否已完成 LLM 分析
        
        Returns:
            True 如果已有摘要或分类信息
        """
        return self.summary is not None or self.category is not None


@dataclass
class ArticleCreate:
    """创建新闻文章的输入模型
    
    用于创建新文章时的数据验证。
    """
    feed_id: int
    title: str
    link: str
    content: str = ""
    published_at: Optional[str] = None
    
    def to_article(self) -> Article:
        """转换为 Article 实例
        
        Returns:
            新的 Article 实例
        """
        return Article(
            feed_id=self.feed_id,
            title=self.title,
            link=self.link,
            content=self.content,
            published_at=self.published_at,
        )


@dataclass
class ArticleLLMUpdate:
    """LLM 分析结果更新模型
    
    用于更新文章的 LLM 分析结果。
    """
    summary: Optional[str] = None
    category: Optional[str] = None
    keywords: Optional[str] = None
    
    def has_updates(self) -> bool:
        """检查是否有需要更新的字段
        
        Returns:
            True 如果有字段需要更新
        """
        return any([
            self.summary is not None,
            self.category is not None,
            self.keywords is not None,
        ])
    
    def to_tuple_for_update(self) -> tuple:
        """转换为更新用的元组
        
        Returns:
            用于 SQL UPDATE 语句的元组（不含 id）
        """
        return (
            self.summary,
            self.category,
            self.keywords,
        )
