"""新闻抓取命令模块

提供从订阅源抓取新闻的功能。
"""

from typing import Optional

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.table import Table

from rss_news.services.fetcher import FeedFetcher, get_fetcher, close_fetcher

console = Console()


async def fetch_feed(feed_id: Optional[int], concurrency: int):
    """抓取新闻
    
    Args:
        feed_id: 订阅源 ID，为 None 时抓取所有活跃订阅源
        concurrency: 并发数量
    """
    fetcher = get_fetcher()
    
    try:
        if feed_id is not None:
            result = await _fetch_single(fetcher, feed_id)
            _display_single_result(result)
        else:
            results = await _fetch_all(fetcher, concurrency)
            _display_batch_results(results)
    finally:
        await close_fetcher()


async def _fetch_single(fetcher: FeedFetcher, feed_id: int):
    """抓取单个订阅源"""
    with console.status("[bold blue]正在抓取新闻..."):
        result = await fetcher.fetch_feed(feed_id)
    return result


async def _fetch_all(fetcher: FeedFetcher, concurrency: int):
    """抓取所有活跃订阅源"""
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("抓取订阅源...", total=None)
        
        results = await fetcher.fetch_all_feeds(concurrency=concurrency)
        
        progress.update(task, total=len(results), completed=len(results))
    
    return results


def _display_single_result(result):
    """显示单个抓取结果"""
    if result.success:
        console.print(f"[green]✓[/green] 抓取成功")
        console.print(f"  新文章: [bold green]{result.new_articles}[/bold green] 篇")
        console.print(f"  总文章: {result.total_articles} 篇")
    else:
        console.print(f"[red]✗[/red] 抓取失败: {result.error_message}")


def _display_batch_results(results):
    """显示批量抓取结果"""
    if not results:
        console.print("[yellow]没有活跃的订阅源[/yellow]")
        return
    
    success_count = sum(1 for r in results if r.success)
    total_new = sum(r.new_articles for r in results)
    total_articles = sum(r.total_articles for r in results)
    
    table = Table(title="抓取结果", show_header=True, header_style="bold blue")
    table.add_column("订阅源 ID", style="cyan", justify="right", width=10)
    table.add_column("状态", justify="center", width=8)
    table.add_column("新文章", justify="right", width=8)
    table.add_column("总文章", justify="right", width=8)
    table.add_column("备注", width=30)
    
    for result in results:
        status = "[green]成功[/green]" if result.success else "[red]失败[/red]"
        new_count = str(result.new_articles) if result.success else "-"
        total_count = str(result.total_articles) if result.success else "-"
        note = result.error_message[:30] if result.error_message else "-"
        
        table.add_row(
            str(result.feed_id),
            status,
            new_count,
            total_count,
            note,
        )
    
    console.print(table)
    
    console.print(
        f"\n[bold]统计:[/bold] "
        f"{success_count}/{len(results)} 成功, "
        f"[green]{total_new}[/green] 篇新文章, "
        f"{total_articles} 篇总文章"
    )
