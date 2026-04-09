"""RSS 新闻阅读器命令行入口

提供统一的命令行接口，包含订阅管理、新闻抓取、文章查看和 LLM 处理等功能。
"""

import asyncio
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel

from rss_news.cli import feed, article, llm, fetch_cmd, play_cmd, daemon_cmd, db_cmd, wiki_cmd, name_mapping_cmd, web_cmd
from rss_news.db.connection import init_database

app = typer.Typer(
    name="rss-news",
    help="RSS 新闻阅读器 - 订阅、抓取、智能分析",
    add_completion=False,
)
console = Console()


@app.callback()
def main(
    version: bool = typer.Option(
        False, "--version", "-v", help="显示版本信息"
    ),
):
    """RSS 新闻阅读器命令行工具
    
    支持订阅管理、新闻抓取、文章查看和 LLM 智能分析。
    """
    if version:
        console.print(Panel.fit(
            "[bold blue]RSS 新闻阅读器[/bold blue]\n"
            "[green]版本: 0.1.0[/green]",
            title="关于",
            border_style="blue",
        ))
        raise typer.Exit()
    
    init_database()


app.add_typer(feed.app, name="feed", help="订阅源管理")
app.add_typer(article.app, name="article", help="文章管理")
app.add_typer(llm.app, name="llm", help="LLM 智能处理")
app.add_typer(play_cmd.app, name="play", help="新闻播放器")
app.add_typer(daemon_cmd.app, name="daemon", help="后台服务")
app.add_typer(db_cmd.app, name="db", help="数据库查询")
app.add_typer(wiki_cmd.app, name="wiki", help="Wiki 知识库")
app.add_typer(name_mapping_cmd.app, name="name-mapping", help="人名映射管理")
app.add_typer(web_cmd.app, name="web", help="Web 服务")


@app.command("fetch")
def fetch_command(
    feed_id: Optional[int] = typer.Argument(
        None, help="订阅源 ID（不指定则抓取所有活跃订阅源）"
    ),
    concurrency: int = typer.Option(
        3, "--concurrency", "-c", help="并发抓取数量"
    ),
):
    """抓取新闻
    
    从指定的订阅源或所有活跃订阅源抓取最新新闻。
    
    示例:
        rss-news fetch          # 抓取所有活跃订阅源
        rss-news fetch 1        # 抓取 ID 为 1 的订阅源
        rss-news fetch -c 5     # 使用 5 个并发抓取
    """
    asyncio.run(fetch_cmd.fetch_feed(feed_id, concurrency))


@app.command("init")
def init_command():
    """初始化数据库
    
    创建数据库表结构，如果已存在则不会重复创建。
    """
    try:
        init_database()
        console.print("[green]✓[/green] 数据库初始化成功")
    except Exception as e:
        console.print(f"[red]✗[/red] 数据库初始化失败: {e}")
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
