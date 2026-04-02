"""新闻可视化播放器模块

提供终端可视化界面循环播放今日新闻。
"""

import asyncio
import sys
from datetime import datetime
from typing import Optional

from rich.console import Console
from rich.panel import Panel
from rich.layout import Layout
from rich.text import Text
from rich.style import Style

from rss_news.models.article import Article
from rss_news.services.article_service import ArticleService


class NewsPlayer:
    """新闻播放器
    
    在终端中以可视化方式循环播放新闻。
    """
    
    def __init__(
        self,
        interval: float = 5.0,
        show_summary: bool = True,
    ):
        """初始化播放器
        
        Args:
            interval: 每条新闻展示时间（秒）
            show_summary: 是否显示摘要
        """
        self.interval = interval
        self.show_summary = show_summary
        self.console = Console()
        
        self._is_paused = False
        self._is_running = False
        self._current_index = 0
        self._articles: list[Article] = []
    
    def _clear_screen(self):
        """清空屏幕"""
        self.console.clear()
    
    def _render_news_card(self, article: Article, index: int, total: int) -> Panel:
        """渲染新闻卡片
        
        Args:
            article: 文章对象
            index: 当前索引
            total: 总数
            
        Returns:
            Rich Panel 对象
        """
        content_lines = []
        
        title_text = Text()
        title_text.append(article.title, style=Style(bold=True, color="cyan"))
        content_lines.append(title_text)
        content_lines.append("")
        
        if article.category:
            content_lines.append(Text(f"分类: {article.category}", style="yellow"))
        
        if article.keywords:
            content_lines.append(Text(f"关键词: {article.keywords}", style="green"))
        
        if article.published_at:
            pub_time = article.published_at[:19].replace("T", " ")
            content_lines.append(Text(f"发布时间: {pub_time}", style="dim"))
        
        content_lines.append("")
        
        if self.show_summary and article.summary:
            content_lines.append(Text("摘要:", style="bold"))
            content_lines.append(Text(article.summary))
        elif self.show_summary and article.content:
            content_preview = article.content[:300]
            if len(article.content) > 300:
                content_preview += "..."
            content_lines.append(Text("内容预览:", style="bold"))
            content_lines.append(Text(content_preview))
        
        content_lines.append("")
        content_lines.append(Text(f"链接: {article.link}", style="dim blue"))
        
        subtitle = f"第 {index + 1}/{total} 条"
        
        return Panel(
            "\n".join(str(line) for line in content_lines),
            title="📰 今日新闻",
            subtitle=subtitle,
            border_style="blue",
            padding=(1, 2),
        )
    
    def _render_status_bar(self) -> Panel:
        """渲染状态栏
        
        Returns:
            状态栏 Panel
        """
        status = "⏸ 已暂停" if self._is_paused else "▶ 播放中"
        status_style = "yellow" if self._is_paused else "green"
        
        controls = Text()
        controls.append("控制: ", style="dim")
        controls.append("[空格]", style="bold")
        controls.append("暂停/继续  ", style="dim")
        controls.append("[N]", style="bold")
        controls.append("下一条  ", style="dim")
        controls.append("[Q]", style="bold")
        controls.append("退出", style="dim")
        
        content = Text()
        content.append(status + "  ", style=status_style)
        content.append(controls)
        
        return Panel(content, border_style="dim")
    
    def _render_no_news(self) -> Panel:
        """渲染无新闻提示
        
        Returns:
            提示 Panel
        """
        return Panel(
            "[yellow]暂无今日新闻[/yellow]\n\n"
            "请先使用 [bold]rss-news fetch[/bold] 命令抓取新闻",
            title="📰 今日新闻",
            border_style="yellow",
            padding=(2, 4),
        )
    
    async def _read_key(self) -> Optional[str]:
        """读取键盘输入（非阻塞）
        
        Returns:
            按键字符，无输入返回 None
        """
        try:
            if sys.platform == "win32":
                import msvcrt
                if msvcrt.kbhit():
                    key = msvcrt.getch()
                    if key == b' ':
                        return ' '
                    elif key.lower() == b'n':
                        return 'n'
                    elif key.lower() == b'q':
                        return 'q'
            else:
                import termios
                import tty
                import select
                if select.select([sys.stdin], [], [], 0)[0]:
                    key = sys.stdin.read(1)
                    return key.lower()
        except Exception:
            pass
        return None
    
    async def _handle_input(self):
        """处理用户输入"""
        key = await self._read_key()
        
        if key == ' ':
            self._is_paused = not self._is_paused
        elif key == 'n':
            self._current_index = (self._current_index + 1) % len(self._articles)
        elif key == 'q':
            self._is_running = False
    
    async def play(self):
        """开始播放新闻"""
        article_service = ArticleService()
        self._articles = article_service.get_today_articles()
        
        if not self._articles:
            self._clear_screen()
            self.console.print(self._render_no_news())
            return
        
        self._is_running = True
        self._current_index = 0
        
        try:
            while self._is_running:
                self._clear_screen()
                
                article = self._articles[self._current_index]
                self.console.print(self._render_news_card(
                    article, 
                    self._current_index, 
                    len(self._articles)
                ))
                self.console.print(self._render_status_bar())
                
                if not self._is_paused:
                    elapsed = 0.0
                    while elapsed < self.interval and self._is_running:
                        await self._handle_input()
                        if not self._is_running:
                            break
                        await asyncio.sleep(0.1)
                        elapsed += 0.1
                    
                    if self._is_running and not self._is_paused:
                        self._current_index = (self._current_index + 1) % len(self._articles)
                else:
                    while self._is_paused and self._is_running:
                        await self._handle_input()
                        await asyncio.sleep(0.1)
        
        except KeyboardInterrupt:
            pass
        finally:
            self._clear_screen()
            self.console.print("[green]感谢使用新闻播放器！[/green]")


async def run_player(interval: float = 5.0, show_summary: bool = True):
    """运行新闻播放器
    
    Args:
        interval: 每条新闻展示时间（秒）
        show_summary: 是否显示摘要
    """
    player = NewsPlayer(interval=interval, show_summary=show_summary)
    await player.play()
