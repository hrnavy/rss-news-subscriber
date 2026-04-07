"""文章服务模块

提供文章的增删改查操作。
"""

import logging
from datetime import datetime, date
from typing import Optional

from rss_news.db.connection import get_connection
from rss_news.models.article import Article, ArticleCreate, ArticleLLMUpdate

logger = logging.getLogger(__name__)


class ArticleService:
    """文章服务
    
    提供文章的数据库操作方法。
    """
    
    def save_article(self, article_data: ArticleCreate) -> Optional[Article]:
        """保存文章到数据库
        
        Args:
            article_data: 文章创建数据
            
        Returns:
            保存后的 Article 对象，如果链接已存在则返回 None
        """
        # 先检查链接是否已存在
        if self._link_exists(article_data.link):
            logger.debug(f"文章链接已存在: {article_data.link}")
            return None
        
        try:
            with get_connection() as conn:
                cursor = conn.execute(
                    """INSERT INTO articles 
                       (feed_id, title, link, content, published_at, created_at)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (
                        article_data.feed_id,
                        article_data.title,
                        article_data.link,
                        article_data.content,
                        article_data.published_at,
                        # created_at 由 Article 模型自动生成
                    )
                )
                article_id = cursor.lastrowid
                
                # 返回完整的 Article 对象
                return Article(
                    id=article_id,
                    feed_id=article_data.feed_id,
                    title=article_data.title,
                    link=article_data.link,
                    content=article_data.content,
                    published_at=article_data.published_at,
                )
        except Exception as e:
            logger.error(f"保存文章失败: {e}")
            return None
    
    def _link_exists(self, link: str) -> bool:
        """检查文章链接是否已存在
        
        Args:
            link: 文章链接
            
        Returns:
            True 如果链接已存在
        """
        with get_connection() as conn:
            cursor = conn.execute(
                "SELECT 1 FROM articles WHERE link = ? LIMIT 1",
                (link,)
            )
            return cursor.fetchone() is not None
    
    def get_article(self, article_id: int) -> Optional[Article]:
        """获取单篇文章
        
        Args:
            article_id: 文章 ID
            
        Returns:
            Article 对象，不存在则返回 None
        """
        with get_connection() as conn:
            cursor = conn.execute(
                """SELECT id, feed_id, title, link, content, summary, category, 
                          keywords, published_at, created_at
                   FROM articles WHERE id = ?""",
                (article_id,)
            )
            row = cursor.fetchone()
            if row:
                return Article.from_row(row)
        return None
    
    def get_article_by_link(self, link: str) -> Optional[Article]:
        """根据链接获取文章
        
        Args:
            link: 文章链接
            
        Returns:
            Article 对象，不存在则返回 None
        """
        with get_connection() as conn:
            cursor = conn.execute(
                """SELECT id, feed_id, title, link, content, summary, category, 
                          keywords, published_at, created_at
                   FROM articles WHERE link = ?""",
                (link,)
            )
            row = cursor.fetchone()
            if row:
                return Article.from_row(row)
        return None
    
    def list_articles(
        self,
        feed_id: Optional[int] = None,
        limit: int = 20,
        offset: int = 0,
        order_by: str = "published_at",
        descending: bool = True,
    ) -> list[Article]:
        """列出文章
        
        支持按订阅源筛选、分页和排序。
        
        Args:
            feed_id: 订阅源 ID，为 None 时不筛选
            limit: 返回数量限制
            offset: 偏移量（用于分页）
            order_by: 排序字段
            descending: 是否降序
            
        Returns:
            文章列表
        """
        # 构建查询
        order_direction = "DESC" if descending else "ASC"
        
        if feed_id is not None:
            sql = f"""
                SELECT id, feed_id, title, link, content, summary, category, 
                       keywords, published_at, created_at
                FROM articles 
                WHERE feed_id = ?
                ORDER BY {order_by} {order_direction}
                LIMIT ? OFFSET ?
            """
            params = (feed_id, limit, offset)
        else:
            sql = f"""
                SELECT id, feed_id, title, link, content, summary, category, 
                       keywords, published_at, created_at
                FROM articles 
                ORDER BY {order_by} {order_direction}
                LIMIT ? OFFSET ?
            """
            params = (limit, offset)
        
        with get_connection() as conn:
            cursor = conn.execute(sql, params)
            rows = cursor.fetchall()
            return [Article.from_row(row) for row in rows]
    
    def count_articles(self, feed_id: Optional[int] = None) -> int:
        """统计文章数量
        
        Args:
            feed_id: 订阅源 ID，为 None 时统计所有文章
            
        Returns:
            文章数量
        """
        with get_connection() as conn:
            if feed_id is not None:
                cursor = conn.execute(
                    "SELECT COUNT(*) FROM articles WHERE feed_id = ?",
                    (feed_id,)
                )
            else:
                cursor = conn.execute("SELECT COUNT(*) FROM articles")
            return cursor.fetchone()[0]
    
    def search_articles(
        self,
        keyword: str,
        limit: int = 20,
        offset: int = 0,
    ) -> list[Article]:
        """搜索文章
        
        在标题和内容中搜索关键词。
        
        Args:
            keyword: 搜索关键词
            limit: 返回数量限制
            offset: 偏移量
            
        Returns:
            匹配的文章列表
        """
        # 使用 LIKE 进行模糊搜索
        search_pattern = f"%{keyword}%"
        
        with get_connection() as conn:
            cursor = conn.execute(
                """SELECT id, feed_id, title, link, content, summary, category, 
                          keywords, published_at, created_at
                   FROM articles 
                   WHERE title LIKE ? OR content LIKE ?
                   ORDER BY published_at DESC
                   LIMIT ? OFFSET ?""",
                (search_pattern, search_pattern, limit, offset)
            )
            rows = cursor.fetchall()
            return [Article.from_row(row) for row in rows]
    
    def count_search_results(self, keyword: str) -> int:
        """统计搜索结果数量
        
        Args:
            keyword: 搜索关键词
            
        Returns:
            匹配的文章数量
        """
        search_pattern = f"%{keyword}%"
        
        with get_connection() as conn:
            cursor = conn.execute(
                """SELECT COUNT(*) 
                   FROM articles 
                   WHERE title LIKE ? OR content LIKE ?""",
                (search_pattern, search_pattern)
            )
            return cursor.fetchone()[0]
    
    def update_article_llm_fields(
        self,
        article_id: int,
        summary: Optional[str] = None,
        category: Optional[str] = None,
        keywords: Optional[str] = None,
    ) -> bool:
        """更新文章的 LLM 分析结果
        
        Args:
            article_id: 文章 ID
            summary: 摘要
            category: 分类
            keywords: 关键词
            
        Returns:
            True 如果更新成功
        """
        # 检查文章是否存在
        if self.get_article(article_id) is None:
            logger.warning(f"文章不存在: {article_id}")
            return False
        
        try:
            with get_connection() as conn:
                conn.execute(
                    """UPDATE articles 
                       SET summary = ?, category = ?, keywords = ?
                       WHERE id = ?""",
                    (summary, category, keywords, article_id)
                )
            logger.debug(f"更新文章 LLM 字段: {article_id}")
            return True
        except Exception as e:
            logger.error(f"更新文章失败: {e}")
            return False
    
    def update_article_llm_fields_by_model(
        self,
        article_id: int,
        update_data: ArticleLLMUpdate,
    ) -> bool:
        """使用模型对象更新文章的 LLM 分析结果
        
        Args:
            article_id: 文章 ID
            update_data: 更新数据模型
            
        Returns:
            True 如果更新成功
        """
        if not update_data.has_updates():
            logger.debug(f"没有需要更新的字段: {article_id}")
            return True
        
        return self.update_article_llm_fields(
            article_id=article_id,
            summary=update_data.summary,
            category=update_data.category,
            keywords=update_data.keywords,
        )
    
    def get_articles_without_summary(
        self,
        limit: int = 100,
    ) -> list[Article]:
        """获取没有摘要的文章（排除标题文章）
        
        用于 LLM 批量处理。标题文章（content 为空）不参与 LLM 处理。
        
        Args:
            limit: 返回数量限制
            
        Returns:
            未处理的文章列表（不含标题文章）
        """
        with get_connection() as conn:
            cursor = conn.execute(
                """SELECT id, feed_id, title, link, content, summary, category, 
                          keywords, published_at, created_at
                   FROM articles 
                   WHERE summary IS NULL AND content != ''
                   ORDER BY published_at DESC
                   LIMIT ?""",
                (limit,)
            )
            rows = cursor.fetchall()
            return [Article.from_row(row) for row in rows]
    
    def fetch_content(self, article_id: int) -> tuple[bool, str]:
        """获取文章原文（预留接口）
        
        对于标题源的文章，尝试获取原文内容。
        当前为预留接口，返回未实现提示。
        
        Args:
            article_id: 文章 ID
            
        Returns:
            (成功标志, 消息)
        """
        article = self.get_article(article_id)
        if not article:
            return False, f"文章不存在: ID={article_id}"
        
        if article.content:
            return False, "文章已有内容，无需重新获取"
        
        # 预留接口：此处应调用爬虫/浏览器自动化工具获取原文
        # 当前返回未实现提示
        return False, "原文获取功能尚未实现，请稍后重试"
    
    def is_title_article(self, article_id: int) -> bool:
        """判断文章是否为标题文章
        
        Args:
            article_id: 文章 ID
            
        Returns:
            True 如果是标题文章（content 为空）
        """
        article = self.get_article(article_id)
        if not article:
            return False
        return not article.content
    
    def delete_article(self, article_id: int) -> bool:
        """删除文章
        
        Args:
            article_id: 文章 ID
            
        Returns:
            True 如果删除成功
        """
        with get_connection() as conn:
            cursor = conn.execute(
                "DELETE FROM articles WHERE id = ?",
                (article_id,)
            )
            return cursor.rowcount > 0
    
    def delete_articles_by_feed(self, feed_id: int) -> int:
        """删除指定订阅源的所有文章
        
        Args:
            feed_id: 订阅源 ID
            
        Returns:
            删除的文章数量
        """
        with get_connection() as conn:
            cursor = conn.execute(
                "DELETE FROM articles WHERE feed_id = ?",
                (feed_id,)
            )
            return cursor.rowcount
    
    def get_today_articles(self, limit: int = 100) -> list[Article]:
        """获取今日新闻
        
        查询发布时间为今天的所有新闻文章。
        
        Args:
            limit: 返回数量限制
            
        Returns:
            今日新闻列表
        """
        today = date.today().isoformat()
        
        with get_connection() as conn:
            cursor = conn.execute(
                """SELECT id, feed_id, title, link, content, summary, category, 
                          keywords, published_at, created_at
                   FROM articles 
                   WHERE DATE(published_at) = ? OR DATE(created_at) = ?
                   ORDER BY published_at DESC
                   LIMIT ?""",
                (today, today, limit)
            )
            rows = cursor.fetchall()
            return [Article.from_row(row) for row in rows]


# 全局服务实例
_service: Optional[ArticleService] = None


def get_article_service() -> ArticleService:
    """获取全局文章服务实例
    
    Returns:
        ArticleService 实例
    """
    global _service
    if _service is None:
        _service = ArticleService()
    return _service
