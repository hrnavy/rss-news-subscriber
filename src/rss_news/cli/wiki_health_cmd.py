"""Wiki 健康检查命令模块

提供 Wiki 人物页面的健康检查命令行工具。
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.tree import Tree

from rss_news.models.health_check import CheckType, CheckStatus
from rss_news.services.wiki_health_check_service import WikiHealthCheckService

app = typer.Typer(help="Wiki 健康检查工具")
console = Console()


@app.command("run")
def run_health_check(
    check: str = typer.Option(
        "all",
        "--check", "-c",
        help="检查类型: names, timeline, source, non_person, all"
    ),
    fix: bool = typer.Option(
        False,
        "--fix",
        help="自动修复检测到的问题"
    ),
    report: bool = typer.Option(
        False,
        "--report", "-r",
        help="生成详细报告文件"
    ),
    output: Optional[str] = typer.Option(
        None,
        "--output", "-o",
        help="报告输出路径"
    ),
):
    """运行 Wiki 健康检查
    
    检查人物页面的各种问题，包括：
    - 名字重复/合并问题
    - 时间线质量问题
    - 新闻来源缺失
    - 非人物实体
    
    示例:
        rss-news wiki-health run
        rss-news wiki-health run -c names
        rss-news wiki-health run --fix
        rss-news wiki-health run --report
    """
    service = WikiHealthCheckService()
    
    # 解析检查类型
    check_types = _parse_check_types(check)
    
    console.print(Panel.fit(
        "[bold blue]Wiki 健康检查[/bold blue]\n"
        f"检查类型: {', '.join([c.value for c in check_types])}",
        title="开始检查",
    ))
    
    # 运行检查
    report_data = service.run_full_check(check_types)
    
    # 显示结果
    _display_report(report_data)
    
    # 修复问题
    if fix:
        console.print("\n[bold yellow]正在修复问题...[/bold yellow]")
        fixes = service.fix_issues(report_data, dry_run=False)
        console.print(f"[green]修复完成: {fixes}[/green]")
    
    # 生成报告文件
    if report:
        report_path = output or f"wiki_health_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        _save_report(report_data, report_path)
        console.print(f"\n[green]报告已保存: {report_path}[/green]")


@app.command("names")
def check_names():
    """只检查名字合并问题
    
    示例:
        rss-news wiki-health names
    """
    service = WikiHealthCheckService()
    result = service.check_names()
    _display_single_result(result)


@app.command("timeline")
def check_timeline():
    """只检查时间线质量问题
    
    示例:
        rss-news wiki-health timeline
    """
    service = WikiHealthCheckService()
    result = service.check_timeline()
    _display_single_result(result)


@app.command("source")
def check_source():
    """只检查新闻来源问题
    
    示例:
        rss-news wiki-health source
    """
    service = WikiHealthCheckService()
    result = service.check_source()
    _display_single_result(result)


@app.command("non-person")
def check_non_person():
    """只检查非人物实体
    
    示例:
        rss-news wiki-health non-person
    """
    service = WikiHealthCheckService()
    result = service.check_non_person_entities()
    _display_single_result(result)


@app.command("merge-preview")
def merge_preview():
    """预览名字合并建议
    
    显示所有检测到的可能重复的名字及其合并建议。
    
    示例:
        rss-news wiki-health merge-preview
    """
    service = WikiHealthCheckService()
    result = service.check_names()
    
    if not result.suggestions:
        console.print("[green]没有发现需要合并的名字[/green]")
        return
    
    console.print(f"\n[bold]发现 {len(result.suggestions)} 组可能重复的名字[/bold]\n")
    
    for i, suggestion in enumerate(result.suggestions, 1):
        names = suggestion.get("names", [])
        is_same = suggestion.get("is_same_person", False)
        confidence = suggestion.get("confidence", 0)
        reason = suggestion.get("reason", "")
        primary = suggestion.get("suggested_primary_name", "")
        
        status = "[green]✓ 同一人[/green]" if is_same else "[yellow]? 需确认[/yellow]"
        
        console.print(f"\n[bold]{i}. {status} (置信度: {confidence:.0%})[/bold]")
        console.print(f"   名字: {', '.join(names)}")
        if primary:
            console.print(f"   建议主名称: [cyan]{primary}[/cyan]")
        if reason:
            console.print(f"   理由: {reason}")


def _parse_check_types(check: str) -> list[CheckType]:
    """解析检查类型参数
    
    Args:
        check: 检查类型字符串
        
    Returns:
        检查类型列表
    """
    type_map = {
        "names": CheckType.NAMES,
        "timeline": CheckType.TIMELINE,
        "source": CheckType.SOURCE,
        "non_person": CheckType.NON_PERSON,
        "all": None,
    }
    
    if check == "all":
        return [CheckType.NAMES, CheckType.TIMELINE, CheckType.SOURCE, CheckType.NON_PERSON]
    
    if check in type_map:
        return [type_map[check]]
    
    # 支持逗号分隔的多个类型
    types = []
    for t in check.split(","):
        t = t.strip()
        if t in type_map and type_map[t]:
            types.append(type_map[t])
    
    return types if types else [CheckType.NAMES]


def _display_report(report):
    """显示完整报告
    
    Args:
        report: 健康检查报告
    """
    # 显示摘要
    summary_table = Table(title="检查摘要")
    summary_table.add_column("指标", style="cyan")
    summary_table.add_column("值", style="green")
    
    summary = report.summary
    summary_table.add_row("总问题数", str(summary.get("total_issues", 0)))
    summary_table.add_row("总建议数", str(summary.get("total_suggestions", 0)))
    summary_table.add_row("通过检查", str(summary.get("pass_count", 0)))
    summary_table.add_row("警告检查", str(summary.get("warning_count", 0)))
    summary_table.add_row("错误检查", str(summary.get("error_count", 0)))
    
    console.print(summary_table)
    
    # 显示各项检查结果
    for check_type, result in report.results.items():
        _display_single_result(result)


def _display_single_result(result):
    """显示单项检查结果
    
    Args:
        result: 检查结果
    """
    status_colors = {
        CheckStatus.PASS: "green",
        CheckStatus.WARNING: "yellow",
        CheckStatus.ERROR: "red",
    }
    
    status_icons = {
        CheckStatus.PASS: "✓",
        CheckStatus.WARNING: "⚠",
        CheckStatus.ERROR: "✗",
    }
    
    color = status_colors.get(result.status, "white")
    icon = status_icons.get(result.status, "?")
    
    console.print(f"\n[bold {color}]{icon} {result.check_type.value}[/bold {color}]")
    console.print(f"   状态: [{color}]{result.status.value}[/{color}]")
    console.print(f"   消息: {result.message}")
    
    if result.issues:
        console.print(f"   问题数: {len(result.issues)}")
        for issue in result.issues[:5]:  # 只显示前5个
            console.print(f"   - {issue}")
        if len(result.issues) > 5:
            console.print(f"   ... 还有 {len(result.issues) - 5} 个问题")
    
    if result.suggestions:
        console.print(f"   建议数: {len(result.suggestions)}")


def _save_report(report, path: str):
    """保存报告到文件
    
    Args:
        report: 健康检查报告
        path: 文件路径
    """
    report_data = report.to_dict()
    
    with open(path, "w", encoding="utf-8") as f:
        json.dump(report_data, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    app()
