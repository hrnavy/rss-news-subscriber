"""新闻播放器命令模块

提供可视化新闻播放功能。
"""

import asyncio

import typer
from rich.console import Console

from rss_news.services.player import run_player

app = typer.Typer(help="新闻播放器命令")
console = Console()


@app.callback(invoke_without_command=True)
def play(
    interval: float = typer.Option(
        5.0, "--interval", "-i", help="每条新闻展示时间（秒）"
    ),
    show_summary: bool = typer.Option(
        True, "--summary/--no-summary", help="是否显示摘要"
    ),
):
    """可视化新闻播放器
    
    循环播放今日新闻，支持键盘控制。
    
    控制键:
        空格 - 暂停/继续
        N    - 跳到下一条
        Q    - 退出播放器
    
    示例:
        rss-news play
        rss-news play -i 10
        rss-news play --no-summary
    """
    console.print("[bold blue]正在启动新闻播放器...[/bold blue]")
    console.print("[dim]按空格暂停，N下一条，Q退出[/dim]\n")
    
    asyncio.run(run_player(interval=interval, show_summary=show_summary))
