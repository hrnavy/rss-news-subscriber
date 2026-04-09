"""人名映射命令模块

提供人名映射的管理命令。
"""

import json
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from rss_news.models.name_mapping import MappingSource, VariantType
from rss_news.services.name_mapping_service import NameMappingService

app = typer.Typer(help="人名映射管理命令")
console = Console()


@app.command("lookup")
def lookup_name(
    name: str = typer.Argument(..., help="要查询的名字"),
):
    """查询名字的映射关系
    
    示例:
        rss-news name-mapping lookup 特朗普
    """
    service = NameMappingService()
    service.initialize()
    
    # 查询主名称
    primary = service.get_primary_name(name)
    
    if primary:
        console.print(f"[green]主名称:[/green] {primary}")
        
        # 获取所有变体
        variants = service.get_all_variants(primary)
        if variants:
            console.print(f"[blue]所有变体:[/blue] {', '.join(variants)}")
    else:
        console.print(f"[yellow]未找到映射关系[/yellow]")
        
        # 检查是否是主名称
        variants = service.get_all_variants(name)
        if variants:
            console.print(f"[blue]该名称是主名称，变体有:[/blue] {', '.join(variants)}")


@app.command("add")
def add_mapping(
    primary_name: str = typer.Argument(..., help="主名称"),
    variant_name: str = typer.Argument(..., help="变体名称"),
    variant_type: str = typer.Option(
        "chinese_translation",
        "--type", "-t",
        help="变体类型: chinese_translation, spelling_variant, alias, full_name, mixed"
    ),
    verified: bool = typer.Option(
        True,
        "--verified/--unverified",
        help="是否已验证"
    ),
):
    """手动添加映射关系
    
    示例:
        rss-news name-mapping add "Donald Trump" "特朗普" -t chinese_translation
    """
    service = NameMappingService()
    service.initialize()
    
    # 解析变体类型
    try:
        v_type = VariantType(variant_type)
    except ValueError:
        console.print(f"[red]无效的变体类型: {variant_type}[/red]")
        console.print("有效类型: chinese_translation, spelling_variant, alias, full_name, mixed")
        raise typer.Exit(1)
    
    from rss_news.models.name_mapping import NameMapping
    mapping = NameMapping(
        primary_name=primary_name,
        variant_name=variant_name,
        variant_type=v_type,
        confidence=1.0,
        source=MappingSource.MANUAL_ENTRY,
        verified=verified,
    )
    
    if service.add_mapping(mapping):
        console.print(f"[green]已添加映射:[/green] {variant_name} -> {primary_name}")
    else:
        console.print(f"[yellow]映射已存在或添加失败[/yellow]")


@app.command("list")
def list_mappings(
    verified_only: bool = typer.Option(
        False,
        "--verified-only",
        help="只显示已验证的映射"
    ),
    source: Optional[str] = typer.Option(
        None,
        "--source", "-s",
        help="按来源筛选: llm_analysis, user_confirmed, manual_entry, predefined"
    ),
    limit: int = typer.Option(
        50,
        "--limit", "-l",
        help="显示数量限制"
    ),
):
    """列出所有映射
    
    示例:
        rss-news name-mapping list
        rss-news name-mapping list --verified-only
        rss-news name-mapping list --source predefined
    """
    service = NameMappingService()
    service.initialize()
    
    # 解析来源
    source_filter = None
    if source:
        try:
            source_filter = MappingSource(source)
        except ValueError:
            console.print(f"[red]无效的来源: {source}[/red]")
            raise typer.Exit(1)
    
    mappings = service.list_mappings(verified_only=verified_only, source=source_filter)
    
    if not mappings:
        console.print("[yellow]没有找到映射[/yellow]")
        return
    
    # 创建表格
    table = Table(title=f"人名映射列表 (共 {len(mappings)} 条)")
    table.add_column("ID", style="dim")
    table.add_column("主名称", style="green")
    table.add_column("变体名称", style="blue")
    table.add_column("类型", style="yellow")
    table.add_column("置信度", style="magenta")
    table.add_column("来源", style="cyan")
    table.add_column("验证", style="dim")
    
    for mapping in mappings[:limit]:
        table.add_row(
            str(mapping.id),
            mapping.primary_name,
            mapping.variant_name,
            mapping.variant_type.value,
            f"{mapping.confidence:.2f}",
            mapping.source.value,
            "✓" if mapping.verified else "✗",
        )
    
    console.print(table)


@app.command("verify")
def verify_mapping(
    mapping_id: int = typer.Argument(..., help="映射 ID"),
):
    """验证映射关系
    
    示例:
        rss-news name-mapping verify 1
    """
    service = NameMappingService()
    service.initialize()
    
    if service.confirm_mapping(mapping_id):
        console.print(f"[green]已验证映射 ID: {mapping_id}[/green]")
    else:
        console.print(f"[red]验证失败，映射 ID 不存在: {mapping_id}[/red]")


@app.command("delete")
def delete_mapping(
    mapping_id: int = typer.Argument(..., help="映射 ID"),
):
    """删除映射关系
    
    示例:
        rss-news name-mapping delete 1
    """
    service = NameMappingService()
    service.initialize()
    
    if service.delete_mapping(mapping_id):
        console.print(f"[green]已删除映射 ID: {mapping_id}[/green]")
    else:
        console.print(f"[red]删除失败，映射 ID 不存在: {mapping_id}[/red]")


@app.command("export")
def export_mappings(
    output: str = typer.Option(
        "name_mappings.json",
        "--output", "-o",
        help="输出文件路径"
    ),
):
    """导出映射到 JSON 文件
    
    示例:
        rss-news name-mapping export -o mappings.json
    """
    service = NameMappingService()
    service.initialize()
    
    mappings = service.export_mappings()
    
    with open(output, "w", encoding="utf-8") as f:
        json.dump(mappings, f, ensure_ascii=False, indent=2)
    
    console.print(f"[green]已导出 {len(mappings)} 条映射到 {output}[/green]")


@app.command("import")
def import_mappings_cmd(
    file: str = typer.Argument(..., help="JSON 文件路径"),
    overwrite: bool = typer.Option(
        False,
        "--overwrite",
        help="覆盖已存在的映射"
    ),
):
    """从 JSON 文件导入映射
    
    示例:
        rss-news name-mapping import mappings.json
        rss-news name-mapping import mappings.json --overwrite
    """
    service = NameMappingService()
    service.initialize()
    
    with open(file, "r", encoding="utf-8") as f:
        mappings = json.load(f)
    
    success, failed = service.import_mappings(mappings, overwrite=overwrite)
    
    console.print(f"[green]成功导入: {success}[/green]")
    if failed > 0:
        console.print(f"[yellow]导入失败: {failed}[/yellow]")


if __name__ == "__main__":
    app()
