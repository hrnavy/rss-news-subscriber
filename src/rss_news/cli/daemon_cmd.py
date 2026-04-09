"""后台服务命令模块

提供定时任务的启动、安装、卸载等功能。
"""

import subprocess
import sys
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from rss_news.services.config import load_config
from rss_news.services.scheduler import TaskScheduler

app = typer.Typer(help="后台服务管理")
console = Console()

TASK_NAME = "RSS-News-Daemon"


@app.callback(invoke_without_command=True)
def daemon(
    ctx: typer.Context,
):
    """后台服务管理
    
    启动定时任务服务，自动执行 fetch、Wiki 构建和健康检查。
    
    示例:
        rss-news daemon          # 启动服务（前台运行）
        rss-news daemon install  # 安装为系统任务
        rss-news daemon status   # 查看状态
    """
    if ctx.invoked_subcommand is None:
        start_daemon()


@app.command("start")
def start_daemon():
    """启动后台服务（前台运行）
    
    服务将在前台运行，按配置间隔自动执行任务。
    按 Ctrl+C 停止服务。
    """
    config = load_config()
    
    if not config.daemon.enabled:
        console.print("[red]后台服务已在配置中禁用[/red]")
        raise typer.Exit(1)
    
    console.print("[bold blue]启动后台服务...[/bold blue]")
    console.print(f"  抓取间隔: {config.daemon.fetch_interval} 秒")
    console.print(f"  Wiki 间隔: {config.daemon.wiki_interval} 秒")
    console.print(f"  健康检查间隔: {config.daemon.health_check_interval} 秒")
    console.print(f"  日志文件: {config.daemon.log_file}")
    console.print("\n[dim]按 Ctrl+C 停止服务[/dim]\n")
    
    try:
        scheduler = TaskScheduler(config.daemon)
        scheduler.start()
    except KeyboardInterrupt:
        console.print("\n[yellow]服务已停止[/yellow]")


@app.command("stop")
def stop_daemon():
    """停止后台服务
    
    注意：仅对通过 install 安装的任务计划有效。
    """
    try:
        result = subprocess.run(
            ["powershell", "-Command", f"Stop-ScheduledTask -TaskName '{TASK_NAME}'"],
            capture_output=True,
            text=True,
        )
        
        if result.returncode == 0:
            console.print("[green]✓[/green] 后台服务已停止")
        else:
            console.print("[red]✗[/red] 停止失败: 任务可能未在运行")
            
    except Exception as e:
        console.print(f"[red]✗[/red] 停止失败: {e}")


@app.command("status")
def status_daemon():
    """查看后台服务状态"""
    config = load_config()
    
    table = Table(title="后台服务状态")
    table.add_column("项目", style="cyan")
    table.add_column("值", style="green")
    
    table.add_row("配置状态", "启用" if config.daemon.enabled else "禁用")
    table.add_row("抓取间隔", f"{config.daemon.fetch_interval} 秒")
    table.add_row("Wiki 间隔", f"{config.daemon.wiki_interval} 秒")
    table.add_row("健康检查间隔", f"{config.daemon.health_check_interval} 秒")
    table.add_row("日志文件", config.daemon.log_file)
    
    try:
        result = subprocess.run(
            ["powershell", "-Command", 
             f"Get-ScheduledTask -TaskName '{TASK_NAME}' -ErrorAction SilentlyContinue | "
             "Select-Object -ExpandProperty State"],
            capture_output=True,
            text=True,
        )
        
        if result.returncode == 0 and result.stdout.strip():
            task_state = result.stdout.strip()
            table.add_row("任务计划", f"已安装 ({task_state})")
        else:
            table.add_row("任务计划", "未安装")
    except Exception:
        table.add_row("任务计划", "无法检测")
    
    console.print(table)


@app.command("install")
def install_daemon():
    """安装为 Windows 任务计划
    
    创建 Windows 任务计划，开机自动启动后台服务。
    """
    project_dir = Path(__file__).parent.parent.parent.parent
    python_exe = sys.executable
    
    command = f'cd /d "{project_dir}" && uv run rss-news daemon start'
    
    ps_script = f'''
$action = New-ScheduledTaskAction -Execute "cmd.exe" -Argument '/c "{command}"' -WorkingDirectory "{project_dir}"
$trigger = New-ScheduledTaskTrigger -AtStartup
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable
Register-ScheduledTask -TaskName "{TASK_NAME}" -Action $action -Trigger $trigger -Settings $settings -RunLevel Highest -Force
'''
    
    try:
        console.print("[bold blue]正在安装任务计划...[/bold blue]")
        
        result = subprocess.run(
            ["powershell", "-Command", ps_script],
            capture_output=True,
            text=True,
        )
        
        if result.returncode == 0:
            console.print(f"[green]✓[/green] 任务计划已安装: {TASK_NAME}")
            console.print("\n服务将在下次开机时自动启动。")
            console.print("立即启动: uv run rss-news daemon start")
        else:
            console.print(f"[red]✗[/red] 安装失败: {result.stderr}")
            console.print("[dim]提示: 可能需要管理员权限[/dim]")
            
    except Exception as e:
        console.print(f"[red]✗[/red] 安装失败: {e}")


@app.command("uninstall")
def uninstall_daemon():
    """卸载 Windows 任务计划"""
    try:
        console.print("[bold blue]正在卸载任务计划...[/bold blue]")
        
        result = subprocess.run(
            ["powershell", "-Command", 
             f"Unregister-ScheduledTask -TaskName '{TASK_NAME}' -Confirm:$false"],
            capture_output=True,
            text=True,
        )
        
        if result.returncode == 0:
            console.print(f"[green]✓[/green] 任务计划已卸载: {TASK_NAME}")
        else:
            console.print(f"[red]✗[/red] 卸载失败: {result.stderr}")
            
    except Exception as e:
        console.print(f"[red]✗[/red] 卸载失败: {e}")


@app.command("logs")
def view_logs(
    lines: int = typer.Option(50, "--lines", "-n", help="显示的日志行数"),
    follow: bool = typer.Option(False, "--follow", "-f", help="实时跟踪日志"),
):
    """查看后台服务日志
    
    示例:
        rss-news daemon logs
        rss-news daemon logs -n 100
        rss-news daemon logs -f
    """
    config = load_config()
    log_file = Path(config.daemon.log_file)
    
    if not log_file.exists():
        console.print(f"[yellow]日志文件不存在: {log_file}[/yellow]")
        console.print("[dim]服务启动后将自动创建日志文件[/dim]")
        return
    
    if follow:
        try:
            subprocess.run(["powershell", "-Command", f"Get-Content '{log_file}' -Wait"])
        except KeyboardInterrupt:
            pass
    else:
        try:
            result = subprocess.run(
                ["powershell", "-Command", 
                 f"Get-Content '{log_file}' -Tail {lines}"],
                capture_output=True,
                text=True,
            )
            console.print(result.stdout)
        except Exception as e:
            console.print(f"[red]✗[/red] 读取日志失败: {e}")


@app.command("run")
def run_once(
    task: str = typer.Argument(
        "all",
        help="要执行的任务: fetch, wiki, health-check, all"
    ),
):
    """立即执行一次任务
    
    示例:
        rss-news daemon run fetch           # 只执行抓取
        rss-news daemon run wiki            # 只执行 Wiki 构建
        rss-news daemon run health-check    # 只执行健康检查
        rss-news daemon run all             # 执行所有任务
    """
    import asyncio
    from rss_news.services.scheduler import TaskScheduler
    
    config = load_config()
    scheduler = TaskScheduler(config.daemon)
    
    async def run_tasks():
        if task in ("fetch", "all"):
            console.print("[bold blue]执行抓取任务...[/bold blue]")
            await scheduler._run_fetch_task()
        
        if task in ("wiki", "all"):
            console.print("[bold blue]执行 Wiki 构建任务...[/bold blue]")
            await scheduler._run_wiki_task()
        
        if task in ("health-check", "all"):
            console.print("[bold blue]执行健康检查任务...[/bold blue]")
            await scheduler._run_health_check_task()
    
    try:
        asyncio.run(run_tasks())
        console.print("[green]✓[/green] 任务执行完成")
    except Exception as e:
        console.print(f"[red]✗[/red] 任务执行失败: {e}")
