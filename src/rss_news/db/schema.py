"""数据库表结构定义和初始化脚本

包含创建数据库表的 SQL 语句和初始化函数。
"""

import sqlite3
from typing import List


# RSS 订阅源表创建 SQL
CREATE_FEEDS_TABLE: str = """
CREATE TABLE IF NOT EXISTS feeds (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    url TEXT UNIQUE NOT NULL,
    description TEXT DEFAULT '',
    is_active INTEGER DEFAULT 1,
    last_fetched TEXT,
    created_at TEXT NOT NULL
);
"""

# 新闻文章表创建 SQL
CREATE_ARTICLES_TABLE: str = """
CREATE TABLE IF NOT EXISTS articles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    feed_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    link TEXT UNIQUE NOT NULL,
    content TEXT DEFAULT '',
    summary TEXT,
    category TEXT,
    keywords TEXT,
    published_at TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (feed_id) REFERENCES feeds(id) ON DELETE CASCADE
);
"""

# 订阅源 URL 索引（加速 URL 查询）
CREATE_FEEDS_URL_INDEX: str = """
CREATE INDEX IF NOT EXISTS idx_feeds_url ON feeds(url);
"""

# 订阅源活跃状态索引（加速活跃订阅源查询）
CREATE_FEEDS_ACTIVE_INDEX: str = """
CREATE INDEX IF NOT EXISTS idx_feeds_is_active ON feeds(is_active);
"""

# 文章链接索引（加速链接查重）
CREATE_ARTICLES_LINK_INDEX: str = """
CREATE INDEX IF NOT EXISTS idx_articles_link ON articles(link);
"""

# 文章订阅源 ID 索引（加速按订阅源查询）
CREATE_ARTICLES_FEED_ID_INDEX: str = """
CREATE INDEX IF NOT EXISTS idx_articles_feed_id ON articles(feed_id);
"""

# 文章分类索引（加速按分类查询）
CREATE_ARTICLES_CATEGORY_INDEX: str = """
CREATE INDEX IF NOT EXISTS idx_articles_category ON articles(category);
"""

# 文章发布时间索引（加速按时间排序）
CREATE_ARTICLES_PUBLISHED_AT_INDEX: str = """
CREATE INDEX IF NOT EXISTS idx_articles_published_at ON articles(published_at);
"""


def get_all_create_statements() -> List[str]:
    """获取所有创建表和索引的 SQL 语句
    
    Returns:
        SQL 语句列表
    """
    return [
        CREATE_FEEDS_TABLE,
        CREATE_ARTICLES_TABLE,
        CREATE_FEEDS_URL_INDEX,
        CREATE_FEEDS_ACTIVE_INDEX,
        CREATE_ARTICLES_LINK_INDEX,
        CREATE_ARTICLES_FEED_ID_INDEX,
        CREATE_ARTICLES_CATEGORY_INDEX,
        CREATE_ARTICLES_PUBLISHED_AT_INDEX,
    ]


def create_tables(conn: sqlite3.Connection) -> None:
    """创建所有数据库表和索引
    
    如果表或索引已存在，则不会重新创建。
    
    Args:
        conn: 数据库连接对象
    """
    cursor = conn.cursor()
    
    for statement in get_all_create_statements():
        cursor.execute(statement)
    
    conn.commit()


def drop_all_tables(conn: sqlite3.Connection) -> None:
    """删除所有表（仅用于测试或重置）
    
    警告：此操作不可逆，会删除所有数据！
    
    Args:
        conn: 数据库连接对象
    """
    cursor = conn.cursor()
    
    # 先删除文章表（因为有外键约束）
    cursor.execute("DROP TABLE IF EXISTS articles")
    cursor.execute("DROP TABLE IF EXISTS feeds")
    
    conn.commit()


def get_table_info(conn: sqlite3.Connection, table_name: str) -> List[tuple]:
    """获取表结构信息
    
    Args:
        conn: 数据库连接对象
        table_name: 表名
        
    Returns:
        表结构信息列表
    """
    cursor = conn.cursor()
    cursor.execute(f"PRAGMA table_info({table_name})")
    return cursor.fetchall()


def verify_schema(conn: sqlite3.Connection) -> bool:
    """验证数据库表结构是否正确
    
    检查必要的表是否存在。
    
    Args:
        conn: 数据库连接对象
        
    Returns:
        True 如果表结构正确
    """
    cursor = conn.cursor()
    
    # 检查 feeds 表
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='feeds'"
    )
    if not cursor.fetchone():
        return False
    
    # 检查 articles 表
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='articles'"
    )
    if not cursor.fetchone():
        return False
    
    return True
