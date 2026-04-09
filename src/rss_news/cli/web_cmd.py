"""Web 服务命令模块

提供启动本地 Web 服务的命令。
"""

import webbrowser

import typer
from rich.console import Console

from rss_news.web.app import create_app

app = typer.Typer(help="Web 服务管理")
console = Console()


@app.callback(invoke_without_command=True)
def web(
    ctx: typer.Context,
):
    """Web 服务管理
    
    启动本地 Web 服务，展示 Wiki 知识库。
    
    示例:
        rss-news web          # 启动服务
        rss-news web start    # 启动服务
    """
    if ctx.invoked_subcommand is None:
        start_web()


@app.command("start")
def start_web(
    port: int = typer.Option(8080, "--port", "-p", help="服务端口"),
    host: str = typer.Option("127.0.0.1", "--host", "-h", help="服务主机"),
    open_browser: bool = typer.Option(True, "--open/--no-open", help="是否自动打开浏览器"),
):
    """启动 Web 服务
    
    启动本地 HTTP 服务，展示 Wiki 知识库内容。
    
    示例:
        rss-news web start
        rss-news web start -p 3000
        rss-news web start --no-open
    """
    flask_app = create_app()
    
    url = f"http://{host}:{port}"
    
    console.print(f"[bold green]启动 Web 服务...[/bold green]")
    console.print(f"  访问地址: [cyan]{url}[/cyan]")
    console.print(f"  按 Ctrl+C 停止服务\n")
    
    if open_browser:
        webbrowser.open(url)
    
    flask_app.run(host=host, port=port, debug=False)
