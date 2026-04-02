"""LLM 智能处理命令组

提供摘要生成、分类、关键词提取和批量处理功能。
"""

import asyncio
from typing import Optional

import typer
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.panel import Panel
from rich.table import Table

from rss_news.services.article_service import ArticleService
from rss_news.services.llm_client import get_llm_client
from rss_news.services.summarizer import get_summarizer
from rss_news.services.classifier import get_classifier
from rss_news.services.keyword_extractor import get_keyword_extractor

app = typer.Typer(help="LLM 智能处理命令")
console = Console()


@app.command("summarize")
def summarize_article(
    article_id: int = typer.Argument(..., help="文章 ID"),
    min_length: int = typer.Option(
        100, "--min", help="最小摘要长度"
    ),
    max_length: int = typer.Option(
        200, "--max", help="最大摘要长度"
    ),
):
    """生成文章摘要
    
    使用 LLM 为指定文章生成摘要。
    
    示例:
        rss-news llm summarize 1
        rss-news llm summarize 1 --min 50 --max 150
    """
    article_service = ArticleService()
    summarizer = get_summarizer()
    
    article = article_service.get_article(article_id)
    if not article:
        console.print(f"[red]✗[/red] 文章不存在: ID={article_id}")
        raise typer.Exit(1)
    
    console.print(f"[bold]正在为文章生成摘要:[/bold] {article.title}")
    
    async def _summarize():
        with console.status("[bold blue]LLM 处理中..."):
            summary = await summarizer.summarize(
                title=article.title,
                content=article.content,
                min_length=min_length,
                max_length=max_length,
            )
        
        article_service.update_article_llm_fields(
            article_id=article_id,
            summary=summary,
        )
        return summary
    
    try:
        summary = asyncio.run(_summarize())
        
        console.print(f"\n[green]✓[/green] 摘要生成成功:\n")
        console.print(Panel.fit(
            summary,
            title="文章摘要",
            border_style="green",
        ))
        
    except Exception as e:
        console.print(f"[red]✗[/red] 摘要生成失败: {e}")
        raise typer.Exit(1)


@app.command("classify")
def classify_article(
    article_id: int = typer.Argument(..., help="文章 ID"),
):
    """对文章进行分类
    
    使用 LLM 对指定文章进行分类。
    
    示例:
        rss-news llm classify 1
    """
    article_service = ArticleService()
    classifier = get_classifier()
    
    article = article_service.get_article(article_id)
    if not article:
        console.print(f"[red]✗[/red] 文章不存在: ID={article_id}")
        raise typer.Exit(1)
    
    console.print(f"[bold]正在对文章进行分类:[/bold] {article.title}")
    
    async def _classify():
        with console.status("[bold blue]LLM 处理中..."):
            category = await classifier.classify(
                title=article.title,
                content=article.content,
            )
        
        article_service.update_article_llm_fields(
            article_id=article_id,
            category=category,
        )
        return category
    
    try:
        category = asyncio.run(_classify())
        
        console.print(f"\n[green]✓[/green] 分类结果: [cyan]{category}[/cyan]")
        
    except Exception as e:
        console.print(f"[red]✗[/red] 分类失败: {e}")
        raise typer.Exit(1)


@app.command("keywords")
def extract_keywords(
    article_id: int = typer.Argument(..., help="文章 ID"),
    min_keywords: int = typer.Option(
        3, "--min", help="最小关键词数量"
    ),
    max_keywords: int = typer.Option(
        5, "--max", help="最大关键词数量"
    ),
):
    """提取文章关键词
    
    使用 LLM 从指定文章中提取关键词。
    
    示例:
        rss-news llm keywords 1
        rss-news llm keywords 1 --min 5 --max 10
    """
    article_service = ArticleService()
    extractor = get_keyword_extractor()
    
    article = article_service.get_article(article_id)
    if not article:
        console.print(f"[red]✗[/red] 文章不存在: ID={article_id}")
        raise typer.Exit(1)
    
    console.print(f"[bold]正在提取关键词:[/bold] {article.title}")
    
    async def _extract():
        with console.status("[bold blue]LLM 处理中..."):
            keywords = await extractor.extract(
                title=article.title,
                content=article.content,
                min_keywords=min_keywords,
                max_keywords=max_keywords,
            )
        
        article_service.update_article_llm_fields(
            article_id=article_id,
            keywords=keywords,
        )
        return keywords
    
    try:
        keywords = asyncio.run(_extract())
        
        console.print(f"\n[green]✓[/green] 关键词提取成功:")
        keywords_list = [k.strip() for k in keywords.split("，") if k.strip()]
        console.print(f"  [yellow]{', '.join(keywords_list)}[/yellow]")
        
    except Exception as e:
        console.print(f"[red]✗[/red] 关键词提取失败: {e}")
        raise typer.Exit(1)


@app.command("process-all")
def process_all_articles(
    limit: int = typer.Option(
        10, "--limit", "-l", help="处理文章数量限制"
    ),
    skip_summary: bool = typer.Option(
        False, "--skip-summary", help="跳过摘要生成"
    ),
    skip_classify: bool = typer.Option(
        False, "--skip-classify", help="跳过分类"
    ),
    skip_keywords: bool = typer.Option(
        False, "--skip-keywords", help="跳过关键词提取"
    ),
):
    """批量处理未处理的文章
    
    对所有未进行 LLM 分析的文章进行摘要生成、分类和关键词提取。
    
    示例:
        rss-news llm process-all
        rss-news llm process-all -l 20
        rss-news llm process-all --skip-summary
    """
    article_service = ArticleService()
    summarizer = get_summarizer()
    classifier = get_classifier()
    extractor = get_keyword_extractor()
    
    articles = article_service.get_articles_without_summary(limit=limit)
    
    if not articles:
        console.print("[green]✓[/green] 没有需要处理的文章")
        return
    
    console.print(f"[bold]找到 {len(articles)} 篇待处理文章[/bold]\n")
    
    async def _process_one(article):
        summary = None
        category = None
        keywords = None
        
        if not skip_summary:
            summary = await summarizer.summarize(
                title=article.title,
                content=article.content,
            )
        
        if not skip_classify:
            category = await classifier.classify(
                title=article.title,
                content=article.content,
            )
        
        if not skip_keywords:
            keywords = await extractor.extract(
                title=article.title,
                content=article.content,
            )
        
        article_service.update_article_llm_fields(
            article_id=article.id,
            summary=summary,
            category=category,
            keywords=keywords,
        )
        
        return {
            "id": article.id,
            "title": article.title,
            "summary": summary,
            "category": category,
            "keywords": keywords,
        }
    
    async def _process_all():
        results = []
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=console,
        ) as progress:
            task = progress.add_task("处理文章...", total=len(articles))
            
            for article in articles:
                progress.update(task, description=f"处理: {article.title[:30]}...")
                
                try:
                    result = await _process_one(article)
                    results.append(result)
                except Exception as e:
                    console.print(f"[red]✗[/red] 处理失败 (ID={article.id}): {e}")
                
                progress.advance(task)
        
        return results
    
    try:
        results = asyncio.run(_process_all())
        
        table = Table(title="处理结果", show_header=True, header_style="bold blue")
        table.add_column("ID", style="cyan", justify="right", width=5)
        table.add_column("标题", width=30)
        table.add_column("分类", width=8)
        table.add_column("关键词", width=25)
        
        for r in results:
            title = r["title"][:30] + ("..." if len(r["title"]) > 30 else "")
            category = r["category"] or "-"
            keywords = (r["keywords"] or "")[:25]
            
            table.add_row(
                str(r["id"]),
                title,
                category,
                keywords,
            )
        
        console.print(table)
        console.print(f"\n[green]✓[/green] 成功处理 {len(results)} 篇文章")
        
    except Exception as e:
        console.print(f"[red]✗[/red] 批量处理失败: {e}")
        raise typer.Exit(1)


@app.command("analyze")
def analyze_article(
    article_id: int = typer.Argument(..., help="文章 ID"),
):
    """对文章进行完整分析
    
    一次性完成摘要生成、分类和关键词提取。
    
    示例:
        rss-news llm analyze 1
    """
    article_service = ArticleService()
    summarizer = get_summarizer()
    classifier = get_classifier()
    extractor = get_keyword_extractor()
    
    article = article_service.get_article(article_id)
    if not article:
        console.print(f"[red]✗[/red] 文章不存在: ID={article_id}")
        raise typer.Exit(1)
    
    console.print(f"[bold]正在分析文章:[/bold] {article.title}\n")
    
    async def _analyze():
        results = {}
        
        with console.status("[bold blue]生成摘要..."):
            results["summary"] = await summarizer.summarize(
                title=article.title,
                content=article.content,
            )
        
        with console.status("[bold blue]进行分类..."):
            results["category"] = await classifier.classify(
                title=article.title,
                content=article.content,
            )
        
        with console.status("[bold blue]提取关键词..."):
            results["keywords"] = await extractor.extract(
                title=article.title,
                content=article.content,
            )
        
        article_service.update_article_llm_fields(
            article_id=article_id,
            summary=results["summary"],
            category=results["category"],
            keywords=results["keywords"],
        )
        
        return results
    
    try:
        results = asyncio.run(_analyze())
        
        console.print(Panel.fit(
            f"[bold]分类:[/bold] [cyan]{results['category']}[/cyan]\n"
            f"[bold]关键词:[/bold] [yellow]{results['keywords']}[/yellow]\n\n"
            f"[bold]摘要:[/bold]\n{results['summary']}",
            title="分析结果",
            border_style="green",
        ))
        
        console.print(f"\n[green]✓[/green] 文章分析完成")
        
    except Exception as e:
        console.print(f"[red]✗[/red] 分析失败: {e}")
        raise typer.Exit(1)
