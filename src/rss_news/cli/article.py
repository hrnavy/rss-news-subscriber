"""文章管理命令组

提供文章列表查看、详情查看和搜索功能。
"""

from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from rss_news.services.article_service import ArticleService
from rss_news.services.feed_service import FeedService

app = typer.Typer(help="文章管理命令")
console = Console()


@app.command("list")
def list_articles(
    feed_id: Optional[int] = typer.Argument(
        None, help="订阅源 ID（不指定则显示所有文章）"
    ),
    limit: int = typer.Option(
        20, "--limit", "-l", help="显示数量"
    ),
    offset: int = typer.Option(
        0, "--offset", "-o", help="偏移量（用于分页）"
    ),
):
    """列出文章
    
    显示文章列表，支持按订阅源筛选和分页。
    
    示例:
        rss-news article list
        rss-news article list 1
        rss-news article list -l 50
        rss-news article list -o 20 -l 20
    """
    article_service = ArticleService()
    feed_service = FeedService()
    
    if feed_id is not None:
        try:
            feed = feed_service.get_feed(feed_id)
            feed_title = feed.title
        except Exception:
            console.print(f"[red]✗[/red] 订阅源不存在: ID={feed_id}")
            raise typer.Exit(1)
    else:
        feed_title = None
    
    articles = article_service.list_articles(
        feed_id=feed_id,
        limit=limit,
        offset=offset,
    )
    
    total = article_service.count_articles(feed_id=feed_id)
    
    if not articles:
        console.print("[yellow]暂无文章[/yellow]")
        return
    
    title = f"文章列表 - {feed_title}" if feed_title else "文章列表"
    table = Table(title=title, show_header=True, header_style="bold blue")
    table.add_column("ID", style="cyan", justify="right", width=5)
    table.add_column("标题", width=40)
    table.add_column("分类", width=8)
    table.add_column("发布时间", width=19)
    table.add_column("LLM", justify="center", width=6)
    
    for article in articles:
        title_text = article.title[:40] + ("..." if len(article.title) > 40 else "")
        category = article.category or "-"
        published = article.published_at[:19] if article.published_at else "-"
        
        llm_status = "[green]✓[/green]" if article.has_llm_analysis() else "[dim]-[/dim]"
        
        table.add_row(
            str(article.id),
            title_text,
            category,
            published,
            llm_status,
        )
    
    console.print(table)
    
    page_info = f"显示 {len(articles)} 条，共 {total} 条"
    if offset > 0 or total > limit:
        page_num = (offset // limit) + 1
        total_pages = (total + limit - 1) // limit
        page_info += f" (第 {page_num}/{total_pages} 页)"
    console.print(f"\n[dim]{page_info}[/dim]")


@app.command("show")
def show_article(
    article_id: int = typer.Argument(..., help="文章 ID"),
):
    """显示文章详情
    
    显示文章的完整信息，包括标题、内容、摘要、分类、关键词等。
    
    示例:
        rss-news article show 1
    """
    article_service = ArticleService()
    feed_service = FeedService()
    
    article = article_service.get_article(article_id)
    
    if not article:
        console.print(f"[red]✗[/red] 文章不存在: ID={article_id}")
        raise typer.Exit(1)
    
    try:
        feed = feed_service.get_feed(article.feed_id)
        feed_title = feed.title
    except Exception:
        feed_title = "未知订阅源"
    
    content_lines = [
        f"[bold]ID:[/bold] {article.id}",
        f"[bold]标题:[/bold] {article.title}",
        f"[bold]订阅源:[/bold] {feed_title}",
        f"[bold]链接:[/bold] {article.link}",
        f"[bold]发布时间:[/bold] {article.published_at or '-'}",
        f"[bold]创建时间:[/bold] {article.created_at}",
    ]
    
    if article.category:
        content_lines.append(f"[bold]分类:[/bold] [cyan]{article.category}[/cyan]")
    
    if article.keywords:
        content_lines.append(f"[bold]关键词:[/bold] [yellow]{article.keywords}[/yellow]")
    
    if article.summary:
        content_lines.append(f"\n[bold]摘要:[/bold]\n{article.summary}")
    
    content_lines.append(f"\n[bold]内容:[/bold]")
    content_preview = article.content[:500] + ("..." if len(article.content) > 500 else "")
    content_lines.append(content_preview)
    
    console.print(Panel.fit(
        "\n".join(content_lines),
        title="文章详情",
        border_style="blue",
    ))


@app.command("search")
def search_articles(
    keyword: str = typer.Argument(..., help="搜索关键词"),
    limit: int = typer.Option(
        20, "--limit", "-l", help="显示数量"
    ),
):
    """搜索文章
    
    在文章标题和内容中搜索关键词。
    
    示例:
        rss-news article search 人工智能
        rss-news article search Python -l 50
    """
    article_service = ArticleService()
    
    articles = article_service.search_articles(
        keyword=keyword,
        limit=limit,
    )
    
    total = article_service.count_search_results(keyword)
    
    if not articles:
        console.print(f"[yellow]未找到包含 '{keyword}' 的文章[/yellow]")
        return
    
    table = Table(
        title=f"搜索结果: '{keyword}'",
        show_header=True,
        header_style="bold blue"
    )
    table.add_column("ID", style="cyan", justify="right", width=5)
    table.add_column("标题", width=45)
    table.add_column("发布时间", width=19)
    
    for article in articles:
        title_text = article.title[:45] + ("..." if len(article.title) > 45 else "")
        published = article.published_at[:19] if article.published_at else "-"
        
        table.add_row(
            str(article.id),
            title_text,
            published,
        )
    
    console.print(table)
    console.print(f"\n找到 [bold]{total}[/bold] 篇相关文章")


@app.command("count")
def count_articles(
    feed_id: Optional[int] = typer.Argument(
        None, help="订阅源 ID（不指定则统计所有文章）"
    ),
):
    """统计文章数量
    
    示例:
        rss-news article count
        rss-news article count 1
    """
    article_service = ArticleService()
    feed_service = FeedService()
    
    if feed_id is not None:
        try:
            feed = feed_service.get_feed(feed_id)
            feed_title = feed.title
        except Exception:
            console.print(f"[red]✗[/red] 订阅源不存在: ID={feed_id}")
            raise typer.Exit(1)
    else:
        feed_title = None
    
    count = article_service.count_articles(feed_id=feed_id)
    
    if feed_title:
        console.print(f"订阅源 '[cyan]{feed_title}[/cyan]' 共有 [bold]{count}[/bold] 篇文章")
    else:
        console.print(f"共有 [bold]{count}[/bold] 篇文章")
