"""Wiki 知识库命令模块

提供 Wiki 初始化、人物页面生成、事件页面生成等功能。
支持全文处理、并行调用和处理状态管理。
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from rss_news.models.health_check import CheckType, CheckStatus
from rss_news.services.wiki_health_check_service import WikiHealthCheckService
from rss_news.services.wiki_service import WikiService

app = typer.Typer(help="Wiki 知识库管理")
console = Console()


@app.command("init")
def init_wiki():
    """初始化 Wiki 目录结构
    
    创建 wiki/ 目录及子目录：people/、political_entities/
    
    示例:
        rss-news wiki init
    """
    service = WikiService()
    
    if service.init_wiki():
        console.print("[green]✓[/green] Wiki 初始化成功")
        console.print(f"  目录: {service.wiki_dir}")
        console.print(f"  - people/              人物页面")
        console.print(f"  - political_entities/  政治实体页面")
    else:
        console.print("[red]✗[/red] Wiki 初始化失败")
        raise typer.Exit(1)


@app.command("build-people")
def build_people(
    limit: int = typer.Option(
        100, "--limit", "-l", help="处理文章数量限制"
    ),
    force: bool = typer.Option(
        False, "--force", "-f", help="强制重新处理所有文章"
    ),
    workers: int = typer.Option(
        1, "--workers", "-w", help="并行请求数（默认串行）"
    ),
):
    """构建人物页面
    
    从新闻中提取关键人物，生成人物 Wiki 页面。
    默认只处理未处理的文章，使用 --force 强制重新处理。
    
    示例:
        rss-news wiki build-people
        rss-news wiki build-people -l 100
        rss-news wiki build-people --force
        rss-news wiki build-people -w 4  # 并行处理
    """
    service = WikiService()
    
    if not service.wiki_dir.exists():
        console.print("[red]✗[/red] Wiki 未初始化，请先运行: rss-news wiki init")
        raise typer.Exit(1)
    
    # 获取文章
    if force:
        console.print("[yellow]强制模式：重新处理所有文章[/yellow]")
        articles = service.get_all_articles(limit=limit)
    else:
        articles = service.get_unprocessed_articles(limit=limit)
    
    if not articles:
        if force:
            console.print("[yellow]没有文章可处理[/yellow]")
        else:
            console.print("[yellow]没有未处理的文章，使用 --force 强制重新处理[/yellow]")
        return
    
    # 计算批次数
    batches = service.batch_articles_by_tokens(articles)
    mode = "串行" if workers <= 1 else f"并行({workers})"
    
    console.print(f"[bold blue]正在提取人物...[/bold blue]")
    console.print(f"  文章数量: {len(articles)}")
    console.print(f"  批次数量: {len(batches)}")
    console.print(f"  处理模式: {mode}")
    
    # 提取人物
    people, processed_ids = service.extract_people_parallel(articles, workers=workers)
    
    if not people:
        console.print("[yellow]未提取到人物[/yellow]")
        service.mark_articles_processed(processed_ids)
        return
    
    console.print(f"提取到 {len(people)} 个人物")
    
    # 初始化名字映射服务
    service.name_mapping_service.initialize()
    
    # 生成人物页面
    saved_count = 0
    for person in people:
        name = person.get("name", "未知")
        article_ids = person.get("article_ids", [])
        
        if article_ids:
            # 规范化名字（使用映射库中的主名称）
            normalized_name = service.name_mapping_service.normalize_name(name)
            if normalized_name != name:
                console.print(f"  [blue]名字规范化:[/blue] {name} -> {normalized_name}")
                person["name"] = normalized_name
                name = normalized_name
            
            articles_for_person = service._get_articles_by_ids(article_ids)
            content = service.generate_person_page(person, articles_for_person)
            file_path = service.save_person_page(name, content)
            console.print(f"  [green]✓[/green] {name} -> {file_path.name}")
            saved_count += 1
    
    # 标记文章为已处理
    service.mark_articles_processed(processed_ids)
    
    console.print(f"\n[green]✓[/green] 人物页面生成完成")
    console.print(f"  生成页面: {saved_count} 个")
    console.print(f"  处理文章: {len(set(processed_ids))} 篇")


@app.command("build-political-entities")
def build_political_entities(
    limit: int = typer.Option(
        100, "--limit", "-l", help="处理文章数量限制"
    ),
    force: bool = typer.Option(
        False, "--force", "-f", help="强制重新处理所有文章"
    ),
    workers: int = typer.Option(
        1, "--workers", "-w", help="并行请求数（默认串行）"
    ),
):
    """构建政治实体页面
    
    从新闻中提取政治实体（国家、组织、地区），生成政治实体 Wiki 页面。
    默认只处理未处理的文章，使用 --force 强制重新处理。
    
    示例:
        rss-news wiki build-political-entities
        rss-news wiki build-political-entities -l 100
        rss-news wiki build-political-entities --force
        rss-news wiki build-political-entities -w 4  # 并行处理
    """
    from rss_news.services.political_entity_service import PoliticalEntityService
    
    service = PoliticalEntityService()
    
    if not service.political_entities_dir.exists():
        console.print("[red]✗[/red] Wiki 未初始化，请先运行: rss-news wiki init")
        raise typer.Exit(1)
    
    # 获取文章
    if force:
        console.print("[yellow]强制模式：重新处理所有文章[/yellow]")
        articles = service.get_all_articles(limit=limit)
    else:
        articles = service.get_unprocessed_articles(limit=limit)
    
    if not articles:
        if force:
            console.print("[yellow]没有文章可处理[/yellow]")
        else:
            console.print("[yellow]没有未处理的文章，使用 --force 强制重新处理[/yellow]")
        return
    
    # 计算批次数
    batches = service.batch_articles_by_tokens(articles)
    mode = "串行" if workers <= 1 else f"并行({workers})"
    
    console.print(f"[bold blue]正在提取政治实体...[/bold blue]")
    console.print(f"  文章数量: {len(articles)}")
    console.print(f"  批次数量: {len(batches)}")
    console.print(f"  处理模式: {mode}")
    
    # 提取政治实体
    entities, processed_ids = service.extract_political_entities_parallel(articles, workers=workers)
    
    if not entities:
        console.print("[yellow]未提取到政治实体[/yellow]")
        service.mark_articles_processed(processed_ids)
        return
    
    console.print(f"提取到 {len(entities)} 个政治实体")
    
    # 生成政治实体页面
    saved_count = 0
    for entity in entities:
        name = entity.get("name", "未知")
        article_ids = entity.get("article_ids", [])
        
        if article_ids:
            articles_for_entity = service.get_articles_by_ids(article_ids)
            content = service.generate_political_entity_page(entity, articles_for_entity)
            file_path = service.save_political_entity_page(name, content)
            console.print(f"  [green]✓[/green] {name} -> {file_path.name}")
            saved_count += 1
    
    # 标记文章为已处理
    service.mark_articles_processed(processed_ids)
    
    console.print(f"\n[green]✓[/green] 政治实体页面生成完成")
    console.print(f"  生成页面: {saved_count} 个")
    console.print(f"  处理文章: {len(set(processed_ids))} 篇")


@app.command("update")
def update_wiki(
    limit: int = typer.Option(
        100, "--limit", "-l", help="处理文章数量限制"
    ),
    workers: int = typer.Option(
        1, "--workers", "-w", help="并行请求数（默认串行）"
    ),
):
    """增量更新 Wiki
    
    只处理未处理的文章，更新相关人物页面。
    
    示例:
        rss-news wiki update
        rss-news wiki update -l 50
        rss-news wiki update -w 4  # 并行处理
    """
    service = WikiService()
    
    if not service.wiki_dir.exists():
        console.print("[red]✗[/red] Wiki 未初始化，请先运行: rss-news wiki init")
        raise typer.Exit(1)
    
    status = service.get_wiki_status()
    unprocessed = status.get("unprocessed_articles", 0)
    
    if unprocessed == 0:
        console.print("[green]✓[/green] 所有文章已处理完成")
        return
    
    console.print(f"[bold blue]正在更新 Wiki...[/bold blue]")
    console.print(f"  未处理文章: {unprocessed} 篇")
    
    # 提取人物
    console.print("\n[bold]提取人物[/bold]")
    build_people(limit=limit, force=False, workers=workers)


@app.command("status")
def show_status():
    """显示 Wiki 状态
    
    示例:
        rss-news wiki status
    """
    service = WikiService()
    status = service.get_wiki_status()
    
    table = Table(title="Wiki 状态")
    table.add_column("项目", style="cyan")
    table.add_column("值", style="green")
    
    table.add_row("Wiki 目录", status["wiki_dir"])
    table.add_row("已初始化", "是" if status["initialized"] else "否")
    table.add_row("人物页面", str(status["people_count"]))
    table.add_row("政治实体页面", str(status["political_entities_count"]))
    table.add_row("数据库文章", str(status["total_articles"]))
    table.add_row("已处理文章", str(status["processed_articles"]))
    table.add_row("未处理文章", str(status["unprocessed_articles"]))
    
    console.print(table)


@app.command("reset-processed")
def reset_processed():
    """重置所有文章的处理状态
    
    将所有文章标记为未处理，以便重新处理。
    
    示例:
        rss-news wiki reset-processed
    """
    service = WikiService()
    
    count = service.reset_processed_status()
    
    if count > 0:
        console.print(f"[green]✓[/green] 已重置 {count} 篇文章的处理状态")
    else:
        console.print("[yellow]没有文章需要重置[/yellow]")


@app.command("stats")
def show_stats():
    """显示处理统计信息
    
    示例:
        rss-news wiki stats
    """
    service = WikiService()
    status = service.get_wiki_status()
    
    # 计算处理进度
    total = status["total_articles"]
    processed = status["processed_articles"]
    progress_pct = (processed / total * 100) if total > 0 else 0
    
    console.print("\n[bold]Wiki 处理统计[/bold]\n")
    
    # 进度条
    bar_width = 40
    filled = int(bar_width * progress_pct / 100)
    bar = "█" * filled + "░" * (bar_width - filled)
    console.print(f"处理进度: [{bar}] {progress_pct:.1f}%")
    
    console.print(f"\n  总文章数: {total}")
    console.print(f"  已处理: {processed}")
    console.print(f"  未处理: {status['unprocessed_articles']}")
    console.print(f"\n  人物页面: {status['people_count']}")
    console.print(f"  事件页面: {status['events_count']}")


@app.command("health-check")
def health_check(
    check: str = typer.Option(
        "all",
        "--check", "-c",
        help="检查类型: names, political_entities, timeline, source, non_person, all"
    ),
    interactive: bool = typer.Option(
        True,
        "--interactive/--no-interactive",
        help="交互式选择修复建议（默认开启）"
    ),
    apply_all: bool = typer.Option(
        False,
        "--apply-all",
        help="自动应用所有修复建议（跳过交互式选择）"
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
    
    检查人物页面和政治实体页面的各种问题，包括：
    - 名字重复/合并问题
    - 政治实体重复/合并问题
    - 时间线质量问题
    - 新闻来源缺失
    - 非人物实体
    
    支持交互式选择修复建议，或使用 --apply-all 自动应用所有修复。
    
    示例:
        rss-news wiki health-check                    # 交互式选择修复
        rss-news wiki health-check -c names           # 只检查名字问题
        rss-news wiki health-check -c political_entities  # 只检查政治实体问题
        rss-news wiki health-check --apply-all        # 自动应用所有修复
        rss-news wiki health-check --no-interactive   # 只显示报告，不修复
        rss-news wiki health-check --report           # 生成报告文件
    """
    from rss_news.services.interactive_fix_selector import (
        create_suggestions_from_candidates,
        create_suggestions_from_political_entity_candidates,
        InteractiveFixSelector,
    )
    
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
    _display_health_report(report_data)
    
    # 收集所有修复建议
    all_suggestions = []
    
    # 检测名字合并候选
    if any(ct in check_types for ct in [CheckType.NAMES, CheckType.ALL]):
        merge_candidates = service.detect_all_merge_candidates()
        if merge_candidates:
            console.print(f"\n[bold cyan]检测到 {len(merge_candidates)} 个名字合并候选[/bold cyan]")
            suggestions = create_suggestions_from_candidates(merge_candidates)
            all_suggestions.extend(suggestions)
    
    # 检测政治实体合并候选
    if any(ct in check_types for ct in [CheckType.POLITICAL_ENTITIES, CheckType.ALL]):
        pe_merge_candidates = service.detect_political_entity_merge_candidates()
        if pe_merge_candidates:
            console.print(f"\n[bold cyan]检测到 {len(pe_merge_candidates)} 个政治实体合并候选[/bold cyan]")
            pe_suggestions = create_suggestions_from_political_entity_candidates(pe_merge_candidates)
            all_suggestions.extend(pe_suggestions)
    
    if all_suggestions:
        if apply_all:
            # 自动应用所有修复
            console.print(f"\n[bold yellow]自动应用所有 {len(all_suggestions)} 个修复...[/bold yellow]")
            selected = all_suggestions
        elif interactive:
            # 交互式选择
            selector = InteractiveFixSelector(all_suggestions)
            selected = selector.interactive_select()
            
            if not selected:
                console.print("\n[yellow]已取消修复[/yellow]")
                return
        else:
            # 只显示，不修复
            console.print("\n[yellow]使用 --interactive 或 --apply-all 来应用修复[/yellow]")
            selected = []
        
        # 执行选中的修复
        if selected:
            console.print(f"\n[bold green]将执行 {len(selected)} 个修复操作[/bold green]")
            _execute_fixes(selected, service)
    
    # 生成报告文件
    if report:
        report_path = output or f"wiki_health_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        _save_health_report(report_data, report_path)
        console.print(f"\n[green]报告已保存: {report_path}[/green]")


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


def _display_health_report(report):
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


def _save_health_report(report, path: str):
    """保存报告到文件
    
    Args:
        report: 健康检查报告
        path: 文件路径
    """
    report_data = report.to_dict()
    
    with open(path, "w", encoding="utf-8") as f:
        json.dump(report_data, f, ensure_ascii=False, indent=2)


def _merge_person_content(primary_content: str, other_content: str) -> str:
    """合并两个人物页面的内容
    
    合并策略：
    1. 合并相关新闻（去重）
    2. 合并时间线（去重）
    3. 合并相关人物（去重）
    4. 合并简介（保留更长的）
    
    Args:
        primary_content: 主文件内容
        other_content: 其他文件内容
        
    Returns:
        合并后的内容
    """
    import re
    
    result = primary_content
    
    # 1. 合并相关新闻
    other_news_match = re.search(r'## 相关新闻\s*\n(.+?)(?=\n##|\Z)', other_content, re.DOTALL)
    if other_news_match:
        other_news = other_news_match.group(1).strip()
        other_article_ids = set(re.findall(r'\[article://(\d+)\]', other_news))
        primary_article_ids = set(re.findall(r'\[article://(\d+)\]', result))
        
        # 找出主文件中没有的新闻
        new_article_ids = other_article_ids - primary_article_ids
        if new_article_ids:
            # 提取新新闻的行
            other_news_lines = other_news.split('\n')
            new_news_lines = []
            for line in other_news_lines:
                line_ids = set(re.findall(r'\[article://(\d+)\]', line))
                if line_ids & new_article_ids:
                    new_news_lines.append(line)
            
            if new_news_lines:
                news_section_match = re.search(r'(## 相关新闻\s*\n)', result)
                if news_section_match:
                    insert_pos = news_section_match.end()
                    new_news_text = '\n'.join(new_news_lines) + '\n'
                    result = result[:insert_pos] + new_news_text + result[insert_pos:]
    
    # 2. 合并时间线
    other_timeline_match = re.search(r'## 时间线\s*\n(.+?)(?=\n##|\Z)', other_content, re.DOTALL)
    if other_timeline_match:
        other_timeline = other_timeline_match.group(1).strip()
        other_timeline_items = set(re.findall(r'- \*\*\d{4}-\d{2}-\d{2}\*\*: (.+)', other_timeline))
        primary_timeline_items = set(re.findall(r'- \*\*\d{4}-\d{2}-\d{2}\*\*: (.+)', result))
        
        # 找出主文件中没有的时间线项
        new_timeline_items = other_timeline_items - primary_timeline_items
        if new_timeline_items:
            # 提取完整的时间线行
            other_timeline_lines = other_timeline.split('\n')
            new_timeline_lines = []
            for line in other_timeline_lines:
                match = re.search(r'- \*\*\d{4}-\d{2}-\d{2}\*\*: (.+)', line)
                if match and match.group(1) in new_timeline_items:
                    new_timeline_lines.append(line)
            
            if new_timeline_lines:
                timeline_section_match = re.search(r'(## 时间线\s*\n)', result)
                if timeline_section_match:
                    insert_pos = timeline_section_match.end()
                    new_timeline_text = '\n'.join(new_timeline_lines) + '\n'
                    result = result[:insert_pos] + new_timeline_text + result[insert_pos:]
    
    # 3. 合并相关人物
    other_people_match = re.search(r'## 相关人物\s*\n(.+?)(?=\n##|\Z)', other_content, re.DOTALL)
    if other_people_match:
        other_people = other_people_match.group(1).strip()
        other_people_names = set(re.findall(r'- \[\[([^\]]+)\]\]', other_people))
        primary_people_names = set(re.findall(r'- \[\[([^\]]+)\]\]', result))
        
        # 找出主文件中没有的人物
        new_people_names = other_people_names - primary_people_names
        if new_people_names:
            # 提取完整的人物行
            other_people_lines = other_people.split('\n')
            new_people_lines = []
            for line in other_people_lines:
                match = re.search(r'- \[\[([^\]]+)\]\]', line)
                if match and match.group(1) in new_people_names:
                    new_people_lines.append(line)
            
            if new_people_lines:
                people_section_match = re.search(r'(## 相关人物\s*\n)', result)
                if people_section_match:
                    insert_pos = people_section_match.end()
                    new_people_text = '\n'.join(new_people_lines) + '\n'
                    result = result[:insert_pos] + new_people_text + result[insert_pos:]
    
    # 4. 合并简介（保留更长的）
    other_intro_match = re.search(r'## 简介\s*\n(.+?)(?=\n##|\Z)', other_content, re.DOTALL)
    primary_intro_match = re.search(r'## 简介\s*\n(.+?)(?=\n##|\Z)', result, re.DOTALL)
    
    if other_intro_match and primary_intro_match:
        other_intro = other_intro_match.group(1).strip()
        primary_intro = primary_intro_match.group(1).strip()
        
        # 如果其他文件的简介更长，替换
        if len(other_intro) > len(primary_intro):
            result = re.sub(
                r'(## 简介\s*\n).+?(?=\n##|\Z)',
                r'\1' + other_intro + '\n',
                result,
                count=1,
                flags=re.DOTALL
            )
    elif other_intro_match and not primary_intro_match:
        # 主文件没有简介，添加
        other_intro = other_intro_match.group(1).strip()
        title_match = re.search(r'^# .+\n', result)
        if title_match:
            insert_pos = title_match.end()
            result = result[:insert_pos] + f"\n## 简介\n\n{other_intro}\n" + result[insert_pos:]
    
    return result


def _execute_fixes(suggestions: list, service: WikiHealthCheckService) -> None:
    """执行选中的修复建议
    
    Args:
        suggestions: 选中的修复建议列表
        service: Wiki 健康检查服务
    """
    from pathlib import Path
    import re
    
    wiki_service = WikiService()
    
    for suggestion in suggestions:
        if suggestion.fix_type.value == "name_merge":
            # 执行名字合并
            primary_name = suggestion.data.get("primary_name")
            variant_names = suggestion.data.get("variant_names", [])
            files = suggestion.data.get("files", [])
            
            console.print(f"\n[cyan]合并:[/cyan] {suggestion.title}")
            
            # 确定主文件（优先英文名）
            primary_file = None
            for f_name in files:
                if all(c.isascii() or c in " -_" for c in f_name.replace(".md", "")):
                    primary_file = wiki_service.people_dir / f_name
                    break
            
            if not primary_file:
                primary_file = wiki_service.people_dir / files[0]
            
            # 读取主文件内容
            primary_content = primary_file.read_text(encoding="utf-8")
            
            # 合并统计
            merged_stats = {
                "news": 0,
                "timeline": 0,
                "people": 0,
            }
            
            # 合并其他文件
            for f_name in files:
                file_path = wiki_service.people_dir / f_name
                if file_path == primary_file:
                    continue
                
                other_content = file_path.read_text(encoding="utf-8")
                
                # 统计合并前的内容
                before_news = len(re.findall(r'\[article://(\d+)\]', primary_content))
                before_timeline = len(re.findall(r'- \*\*\d{4}-\d{2}-\d{2}\*\*:', primary_content))
                before_people = len(re.findall(r'- \[\[([^\]]+)\]\]', primary_content))
                
                # 合并内容
                primary_content = _merge_person_content(primary_content, other_content)
                
                # 统计合并后的内容
                after_news = len(re.findall(r'\[article://(\d+)\]', primary_content))
                after_timeline = len(re.findall(r'- \*\*\d{4}-\d{2}-\d{2}\*\*:', primary_content))
                after_people = len(re.findall(r'- \[\[([^\]]+)\]\]', primary_content))
                
                merged_stats["news"] += after_news - before_news
                merged_stats["timeline"] += after_timeline - before_timeline
                merged_stats["people"] += after_people - before_people
                
                # 删除重复文件
                file_path.unlink()
                console.print(f"  [dim]删除: {f_name}[/dim]")
            
            # 更新主文件标题
            primary_content = re.sub(
                r'^# .+$',
                f'# {primary_name}',
                primary_content,
                count=1,
                flags=re.MULTILINE
            )
            
            # 重命名主文件（如果需要）
            safe_name = "".join(c for c in primary_name if c.isalnum() or c in " -_").strip()
            new_path = wiki_service.people_dir / f"{safe_name}.md"
            
            if primary_file != new_path:
                primary_file.rename(new_path)
                console.print(f"  [dim]重命名: {primary_file.name} -> {new_path.name}[/dim]")
            
            # 保存合并后的内容
            new_path.write_text(primary_content, encoding="utf-8")
            
            # 显示合并统计
            console.print(f"  [green]✓ 完成[/green]")
            if merged_stats["news"] > 0:
                console.print(f"    [dim]合并新闻: +{merged_stats['news']} 条[/dim]")
            if merged_stats["timeline"] > 0:
                console.print(f"    [dim]合并时间线: +{merged_stats['timeline']} 条[/dim]")
            if merged_stats["people"] > 0:
                console.print(f"    [dim]合并相关人物: +{merged_stats['people']} 个[/dim]")
        
        elif suggestion.fix_type.value == "political_entity_merge":
            # 执行政治实体合并
            from rss_news.services.political_entity_service import PoliticalEntityService
            
            primary_name = suggestion.data.get("primary_name")
            variant_names = suggestion.data.get("variant_names", [])
            files = suggestion.data.get("files", [])
            
            console.print(f"\n[cyan]合并:[/cyan] {suggestion.title}")
            
            pe_service = PoliticalEntityService()
            
            # 确定主文件（优先英文名）
            primary_file = None
            for f_name in files:
                if all(c.isascii() or c in " -_" for c in f_name.replace(".md", "")):
                    primary_file = pe_service.political_entities_dir / f_name
                    break
            
            if not primary_file:
                primary_file = pe_service.political_entities_dir / files[0]
            
            # 读取主文件内容
            primary_content = primary_file.read_text(encoding="utf-8")
            
            # 合并统计
            merged_stats = {
                "news": 0,
                "timeline": 0,
                "people": 0,
            }
            
            # 合并其他文件
            for f_name in files:
                file_path = pe_service.political_entities_dir / f_name
                if file_path == primary_file:
                    continue
                
                other_content = file_path.read_text(encoding="utf-8")
                
                # 统计合并前的内容
                before_news = len(re.findall(r'\[article://(\d+)\]', primary_content))
                before_timeline = len(re.findall(r'- \*\*\d{4}-\d{2}-\d{2}\*\*:', primary_content))
                before_people = len(re.findall(r'- \[\[([^\]]+)\]\]', primary_content))
                
                # 合并内容
                primary_content = _merge_person_content(primary_content, other_content)
                
                # 统计合并后的内容
                after_news = len(re.findall(r'\[article://(\d+)\]', primary_content))
                after_timeline = len(re.findall(r'- \*\*\d{4}-\d{2}-\d{2}\*\*:', primary_content))
                after_people = len(re.findall(r'- \[\[([^\]]+)\]\]', primary_content))
                
                merged_stats["news"] += after_news - before_news
                merged_stats["timeline"] += after_timeline - before_timeline
                merged_stats["people"] += after_people - before_people
                
                # 删除重复文件
                file_path.unlink()
                console.print(f"  [dim]删除: {f_name}[/dim]")
            
            # 更新主文件标题
            primary_content = re.sub(
                r'^# .+$',
                f'# {primary_name}',
                primary_content,
                count=1,
                flags=re.MULTILINE
            )
            
            # 重命名主文件（如果需要）
            safe_name = "".join(c for c in primary_name if c.isalnum() or c in " -_").strip()
            new_path = pe_service.political_entities_dir / f"{safe_name}.md"
            
            if primary_file != new_path:
                primary_file.rename(new_path)
                console.print(f"  [dim]重命名: {primary_file.name} -> {new_path.name}[/dim]")
            
            # 保存合并后的内容
            new_path.write_text(primary_content, encoding="utf-8")
            
            # 显示合并统计
            console.print(f"  [green]✓ 完成[/green]")
            if merged_stats["news"] > 0:
                console.print(f"    [dim]合并新闻: +{merged_stats['news']} 条[/dim]")
            if merged_stats["timeline"] > 0:
                console.print(f"    [dim]合并时间线: +{merged_stats['timeline']} 条[/dim]")
            if merged_stats["people"] > 0:
                console.print(f"    [dim]合并相关人物: +{merged_stats['people']} 个[/dim]")
        
        else:
            console.print(f"\n[yellow]跳过:[/yellow] {suggestion.title}（暂不支持）")
