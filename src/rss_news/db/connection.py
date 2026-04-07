"""数据库连接管理模块

提供 SQLite 数据库连接的上下文管理器和初始化功能。
"""

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Generator

# 数据库文件路径：项目根目录下的 data/rss_news.db
DB_PATH: Path = Path(__file__).parent.parent.parent.parent / "data" / "rss_news.db"


def get_db_path() -> Path:
    """获取数据库文件路径
    
    Returns:
        数据库文件的完整路径
    """
    return DB_PATH


def ensure_db_directory() -> None:
    """确保数据库目录存在
    
    如果数据库目录不存在，则创建它。
    """
    db_dir = DB_PATH.parent
    if not db_dir.exists():
        db_dir.mkdir(parents=True, exist_ok=True)


@contextmanager
def get_connection() -> Generator[sqlite3.Connection, None, None]:
    """获取数据库连接的上下文管理器
    
    自动处理连接的创建和关闭，支持事务管理。
    
    Yields:
        sqlite3.Connection: 数据库连接对象
        
    Example:
        with get_connection() as conn:
            cursor = conn.execute("SELECT * FROM feeds")
            feeds = cursor.fetchall()
    """
    ensure_db_directory()
    conn = sqlite3.connect(str(DB_PATH))
    # 启用外键约束
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_database() -> None:
    """初始化数据库
    
    创建数据库文件和所有必要的表结构。
    如果表已存在，则不会重新创建。
    同时运行数据库迁移。
    """
    from rss_news.db.schema import create_tables, run_migrations
    
    ensure_db_directory()
    with get_connection() as conn:
        create_tables(conn)
        run_migrations(conn)
