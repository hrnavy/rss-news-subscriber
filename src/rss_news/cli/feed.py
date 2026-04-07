"""订阅源管理命令组

提供订阅源的添加、删除、列表查看和状态切换功能。
"""

import asyncio
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from rss_news.services.feed_service import (
    FeedService,
    FeedNotFoundError,
    FeedAlreadyExistsError,
    FeedValidationError,
)

app = typer.Typer(help="订阅源管理命令")
console = Console()


@app.command("add")
def add_feed(
    url: str = typer.Argument(..., help="RSS 订阅源 URL"),
    title: Optional[str] = typer.Argument(
        None, help="订阅源标题（可选，默认使用 RSS 源标题）"
    ),
    description: Optional[str] = typer.Option(
        None, "--description", "-d", help="订阅源描述"
    ),
    note: str = typer.Option(
        "", "--note", "-n", help="来源说明（如'标题来源'、'全文来源'）"
    ),
    skip_validation: bool = typer.Option(
        False, "--skip-validation", help="跳过 RSS 源验证"
    ),
):
    """添加新的订阅源
    
    验证 URL 可访问性和 RSS 格式，然后添加到数据库。
    
    示例:
        rss-news feed add https://example.com/feed.xml
        rss-news feed add https://example.com/feed.xml "我的订阅"
        rss-news feed add https://example.com/feed.xml "我的订阅" -d "描述信息"
        rss-news feed add https://example.com/feed.xml --note "标题来源"
    """
    service = FeedService()
    
    async def _add():
        try:
            with console.status("[bold blue]正在验证订阅源..."):
                feed = await service.add_feed(
                    url=url,
                    title=title,
                    description=description,
                    source_note=note,
                    skip_validation=skip_validation,
                )
            
            console.print(f"[green]✓[/green] 订阅源添加成功")
            console.print(f"  ID: [cyan]{feed.id}[/cyan]")
            console.print(f"  标题: [bold]{feed.title}[/bold]")
            console.print(f"  URL: {feed.url}")
            if feed.description:
                console.print(f"  描述: {feed.description}")
            if feed.source_note:
                console.print(f"  来源说明: [yellow]{feed.source_note}[/yellow]")
                
        except FeedAlreadyExistsError:
            console.print(f"[red]✗[/red] 订阅源已存在: {url}")
            raise typer.Exit(1)
        except FeedValidationError as e:
            console.print(f"[red]✗[/red] 验证失败: {e}")
            raise typer.Exit(1)
        except Exception as e:
            console.print(f"[red]✗[/red] 添加失败: {e}")
            raise typer.Exit(1)
    
    asyncio.run(_add())


@app.command("list")
def list_feeds(
    active_only: bool = typer.Option(
        False, "--active", "-a", help="仅显示活跃的订阅源"
    ),
):
    """列出所有订阅源
    
    显示订阅源的详细信息，包括 ID、标题、URL、状态等。
    
    示例:
        rss-news feed list
        rss-news feed list --active
    """
    service = FeedService()
    
    is_active = True if active_only else None
    feeds = service.list_feeds(is_active=is_active)
    
    if not feeds:
        console.print("[yellow]暂无订阅源[/yellow]")
        return
    
    table = Table(title="订阅源列表", show_header=True, header_style="bold blue")
    table.add_column("ID", style="cyan", justify="right", width=4)
    table.add_column("标题", width=25)
    table.add_column("来源说明", width=15)
    table.add_column("状态", justify="center", width=6)
    table.add_column("最后抓取", width=19)
    
    for feed in feeds:
        status = "[green]活跃[/green]" if feed.is_active_bool else "[red]停用[/red]"
        last_fetched = feed.last_fetched[:19] if feed.last_fetched else "-"
        source_note = feed.source_note[:15] if feed.source_note else "-"
        
        table.add_row(
            str(feed.id),
            feed.title[:25] + ("..." if len(feed.title) > 25 else ""),
            source_note,
            status,
            last_fetched,
        )
    
    console.print(table)
    console.print(f"\n共 [bold]{len(feeds)}[/bold] 个订阅源")


@app.command("remove")
def remove_feed(
    feed_id: int = typer.Argument(..., help="订阅源 ID"),
    force: bool = typer.Option(
        False, "--force", "-f", help="强制删除，不进行确认"
    ),
):
    """删除订阅源
    
    删除指定的订阅源及其关联的所有文章。
    
    示例:
        rss-news feed remove 1
        rss-news feed remove 1 --force
    """
    service = FeedService()
    
    try:
        feed = service.get_feed(feed_id)
    except FeedNotFoundError:
        console.print(f"[red]✗[/red] 订阅源不存在: ID={feed_id}")
        raise typer.Exit(1)
    
    if not force:
        confirm = typer.confirm(
            f"确定要删除订阅源 '{feed.title}' 及其所有文章吗？"
        )
        if not confirm:
            console.print("[yellow]已取消[/yellow]")
            return
    
    try:
        service.remove_feed(feed_id)
        console.print(f"[green]✓[/green] 订阅源已删除: {feed.title}")
    except FeedNotFoundError:
        console.print(f"[red]✗[/red] 订阅源不存在: ID={feed_id}")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]✗[/red] 删除失败: {e}")
        raise typer.Exit(1)


@app.command("toggle")
def toggle_feed(
    feed_id: int = typer.Argument(..., help="订阅源 ID"),
):
    """切换订阅源活跃状态
    
    在活跃和停用状态之间切换。
    
    示例:
        rss-news feed toggle 1
    """
    service = FeedService()
    
    try:
        feed = service.toggle_feed(feed_id)
        status = "[green]活跃[/green]" if feed.is_active_bool else "[red]停用[/red]"
        console.print(f"[green]✓[/green] 订阅源状态已切换: {feed.title} -> {status}")
    except FeedNotFoundError:
        console.print(f"[red]✗[/red] 订阅源不存在: ID={feed_id}")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]✗[/red] 切换失败: {e}")
        raise typer.Exit(1)


@app.command("show")
def show_feed(
    feed_id: int = typer.Argument(..., help="订阅源 ID"),
):
    """显示订阅源详细信息
    
    示例:
        rss-news feed show 1
    """
    service = FeedService()
    
    try:
        feed = service.get_feed(feed_id)
        
        status = "[green]活跃[/green]" if feed.is_active_bool else "[red]停用[/red]"
        
        console.print(Panel.fit(
            f"[bold]ID:[/bold] {feed.id}\n"
            f"[bold]标题:[/bold] {feed.title}\n"
            f"[bold]URL:[/bold] {feed.url}\n"
            f"[bold]描述:[/bold] {feed.description or '-'}\n"
            f"[bold]状态:[/bold] {status}\n"
            f"[bold]最后抓取:[/bold] {feed.last_fetched or '-'}\n"
            f"[bold]创建时间:[/bold] {feed.created_at}",
            title=f"订阅源详情",
            border_style="blue",
        ))
        
    except FeedNotFoundError:
        console.print(f"[red]✗[/red] 订阅源不存在: ID={feed_id}")
        raise typer.Exit(1)


from rich.panel import Panel
