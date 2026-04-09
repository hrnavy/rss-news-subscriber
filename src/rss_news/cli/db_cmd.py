"""数据库命令模块

提供数据库搜索和统计功能。
"""

from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from rss_news.db.connection import get_connection
from rss_news.services.article_service import ArticleService

app = typer.Typer(help="数据库查询工具")
console = Console()


@app.command("search")
def search_articles(
    keywords: str = typer.Argument(..., help="搜索关键词"),
    field: str = typer.Option(
        "title", "--field", "-f",
        help="搜索字段：title（默认）、 content、 all",
    ),
    category: Optional[str] = typer.Option(
        None, "--category", "-c", help="按分类筛选"
    ),
    date_from: Optional[str] = typer.Option(
        None, "--from", help="开始日期 (YYYY-MM-DD)"
    ),
    date_to: Optional[str] = typer.Option(
        None, "--to", help="结束日期 (YYYY-MM-DD)"
    ),
    limit: int = typer.Option(
        50, "--limit", "-l", help="返回数量限制",
    ),
):
    """搜索文章
    
    在标题和正文中搜索关键词，支持模糊匹配和多词搜索。
    
    示例:
        rss-news db search "特朗普"
        rss-news db search "人工智能" --field content
        rss-news db search "特朗普 伊朗" --category 政治
    """
    service = ArticleService()
    
    articles = service.search_articles(
        keywords=keywords,
        field=field,
        category=category,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
    )
    
    if not articles:
        console.print("[yellow]未找到匹配的文章[/yellow]")
        return
    
    table = Table(title=f"搜索结果: \"{keywords}\"")
    table.add_column("ID", style="cyan", justify="right", width=6)
    table.add_column("标题", width=50)
    table.add_column("分类", width=8)
    table.add_column("发布时间", width=19)
    
    for article in articles:
        title_text = article.title[:50] + ("..." if len(article.title) > 50 else "")
        category_text = article.category or "-"
        published = article.published_at[:19] if article.published_at else "-"
        
        table.add_row(
            str(article.id),
            title_text,
            category_text,
            published,
        )
    
    console.print(table)
    console.print(f"\n找到 [bold]{len(articles)}[/bold] 篇文章")


@app.command("stats")
def show_stats():
    """显示数据库统计信息
    
    示例:
        rss-news db stats
    """
    with get_connection() as conn:
        # 订阅源统计
        cursor = conn.execute("SELECT COUNT(*) FROM feeds")
        feed_count = cursor.fetchone()[0]
        
        cursor.execute("""
            SELECT 
                CASE 
                    WHEN source_note LIKE '%标题%' THEN '标题源'
                    WHEN source_note LIKE '%全文%' THEN '全文源'
                    ELSE '未设置'
                END as type,
                COUNT(*) 
            FROM feeds 
            GROUP BY type
        """)
        feed_types = cursor.fetchall()
        
        # 文章统计
        cursor = conn.execute("SELECT COUNT(*) FROM articles")
        article_count = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM articles WHERE content = ''")
        title_only = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM articles WHERE content != ''")
        full_content = cursor.fetchone()[0]
        
        # LLM 处理状态
        cursor.execute("SELECT COUNT(*) FROM articles WHERE summary IS NOT NULL AND content != ''")
        llm_done = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM articles WHERE summary IS NULL AND content != ''")
        llm_pending = cursor.fetchone()[0]
        
        # 分类统计
        cursor.execute("""
            SELECT category, COUNT(*) as cnt 
            FROM articles 
            WHERE category IS NOT NULL 
            GROUP BY category 
            ORDER BY cnt DESC 
            LIMIT 10
        """)
        categories = cursor.fetchall()
    
    # 显示统计信息
    console.print(f"\n[bold blue]RSS News 数据库统计[/bold blue]\n")
    console.print(f"[bold]📰 订阅源:[/bold] {feed_count} 个")
    for feed_type, count in feed_types:
        console.print(f"   - {feed_type}: {count} 个")
    
    console.print(f"\n[bold]📄 文章:[/bold] {article_count} 篇")
    console.print(f"   - 标题源文章: {title_only} 篇")
    console.print(f"   - 全文源文章: {full_content} 篔")
    
    console.print(f"\n[bold]🤖 LLM 处理:[/bold]")
    console.print(f"   - 已处理: {llm_done} 篇")
    console.print(f"   - 待处理: {llm_pending} 篇")
    
    if categories:
        console.print(f"\n[bold]📊 分类分布 (Top 10):[/bold]")
        for category, count in categories:
            console.print(f"   - {category}: {count} 篇")
