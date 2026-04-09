"""新闻读取服务

从数据库读取新闻内容。
"""

from dataclasses import dataclass
from typing import Optional

from rss_news.db.connection import get_connection


@dataclass
class ArticleInfo:
    """新闻信息"""
    id: int
    title: str
    content: str
    source: str = ""
    published_at: str = ""
    link: str = ""
    summary: str = ""


class ArticleReader:
    """新闻读取器
    
    从 SQLite 数据库读取新闻内容。
    """
    
    def get_article(self, article_id: int) -> Optional[ArticleInfo]:
        """获取新闻详情
        
        Args:
            article_id: 新闻 ID
            
        Returns:
            新闻信息，不存在返回 None
        """
        with get_connection() as conn:
            cursor = conn.execute(
                """SELECT a.id, a.title, a.content, a.published_at, a.link, a.summary,
                          f.title as source_name
                   FROM articles a
                   LEFT JOIN feeds f ON a.feed_id = f.id
                   WHERE a.id = ?""",
                (article_id,)
            )
            row = cursor.fetchone()
            
            if not row:
                return None
            
            return ArticleInfo(
                id=row[0],
                title=row[1],
                content=row[2] or "",
                published_at=row[3] or "",
                link=row[4] or "",
                summary=row[5] or "",
                source=row[6] or "",
            )
    
    def get_articles_by_ids(self, article_ids: list[int]) -> list[ArticleInfo]:
        """批量获取新闻
        
        Args:
            article_ids: 新闻 ID 列表
            
        Returns:
            新闻列表
        """
        if not article_ids:
            return []
        
        with get_connection() as conn:
            placeholders = ",".join("?" * len(article_ids))
            cursor = conn.execute(
                f"""SELECT a.id, a.title, a.content, a.published_at, a.link, a.summary,
                           f.title as source_name
                    FROM articles a
                    LEFT JOIN feeds f ON a.feed_id = f.id
                    WHERE a.id IN ({placeholders})""",
                article_ids
            )
            
            articles = []
            for row in cursor.fetchall():
                articles.append(ArticleInfo(
                    id=row[0],
                    title=row[1],
                    content=row[2] or "",
                    published_at=row[3] or "",
                    link=row[4] or "",
                    summary=row[5] or "",
                    source=row[6] or "",
                ))
            
            return articles
