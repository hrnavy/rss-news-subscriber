"""交互式修复选择模块

提供交互式的修复建议选择界面。
"""

import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table

console = Console()


class FixType(Enum):
    """修复类型"""
    NAME_MERGE = "name_merge"
    POLITICAL_ENTITY_MERGE = "political_entity_merge"
    TIMELINE_IMPROVE = "timeline_improve"
    SOURCE_ADD = "source_add"
    NON_PERSON_REMOVE = "non_person_remove"


@dataclass
class FixSuggestion:
    """修复建议
    
    存储一个修复建议的所有信息。
    """
    id: str                                    # 建议ID
    fix_type: FixType                          # 修复类型
    title: str                                 # 标题
    description: str                           # 描述
    confidence: float                          # 置信度 (0.0-1.0)
    evidence: list[str] = field(default_factory=list)  # 证据
    data: dict = field(default_factory=dict)   # 额外数据
    selected: bool = True                      # 是否选中（默认选中）
    
    def get_display_title(self) -> str:
        """获取显示标题
        
        Returns:
            显示标题
        """
        checkbox = "[x]" if self.selected else "[ ]"
        confidence_str = f"{self.confidence:.0%}"
        return f"{checkbox} {self.title} ({confidence_str})"
    
    def toggle(self) -> None:
        """切换选中状态"""
        self.selected = not self.selected


class InteractiveFixSelector:
    """交互式修复选择器
    
    提供交互式的修复建议选择界面。
    """
    
    def __init__(self, suggestions: list[FixSuggestion]):
        """初始化选择器
        
        Args:
            suggestions: 修复建议列表
        """
        self.suggestions = suggestions
        self.current_index = 0
        self.filtered_type: Optional[FixType] = None
    
    def display_all(self) -> None:
        """显示所有修复建议"""
        if not self.suggestions:
            console.print("[yellow]没有修复建议[/yellow]")
            return
        
        # 按类型分组
        type_groups: dict[FixType, list[FixSuggestion]] = {}
        for s in self.suggestions:
            if s.fix_type not in type_groups:
                type_groups[s.fix_type] = []
            type_groups[s.fix_type].append(s)
        
        # 显示统计
        total = len(self.suggestions)
        selected = sum(1 for s in self.suggestions if s.selected)
        console.print(Panel.fit(
            f"[bold blue]修复建议[/bold blue]\n"
            f"总计: {total} 项\n"
            f"已选: {selected} 项",
            title="健康检查结果",
        ))
        
        # 显示每组的建议
        type_names = {
            FixType.NAME_MERGE: "名字合并",
            FixType.TIMELINE_IMPROVE: "时间线改进",
            FixType.SOURCE_ADD: "新闻来源补充",
            FixType.NON_PERSON_REMOVE: "非人物实体移除",
        }
        
        for fix_type, group in type_groups.items():
            type_name = type_names.get(fix_type, fix_type.value)
            selected_in_group = sum(1 for s in group if s.selected)
            
            console.print(f"\n[bold cyan]{type_name}[/bold cyan] ({selected_in_group}/{len(group)} 已选)")
            
            table = Table(show_header=False, box=None, padding=(0, 2))
            table.add_column("状态", width=3)
            table.add_column("标题")
            table.add_column("置信度", width=6)
            
            for s in group:
                checkbox = "[green]✓[/green]" if s.selected else "[dim]○[/dim]"
                confidence_color = "green" if s.confidence >= 0.9 else "yellow" if s.confidence >= 0.7 else "red"
                table.add_row(
                    checkbox,
                    s.title,
                    f"[{confidence_color}]{s.confidence:.0%}[/{confidence_color}]",
                )
            
            console.print(table)
    
    def display_detail(self, index: int) -> None:
        """显示单个建议的详情
        
        Args:
            index: 建议索引
        """
        if not 0 <= index < len(self.suggestions):
            return
        
        s = self.suggestions[index]
        
        # 构建详情面板
        lines = [
            f"[bold]类型:[/bold] {s.fix_type.value}",
            f"[bold]置信度:[/bold] {s.confidence:.0%}",
            f"[bold]描述:[/bold] {s.description}",
        ]
        
        if s.evidence:
            lines.append("[bold]证据:[/bold]")
            for e in s.evidence:
                lines.append(f"  • {e}")
        
        if s.data:
            lines.append("[bold]详细信息:[/bold]")
            for key, value in s.data.items():
                if isinstance(value, list):
                    lines.append(f"  • {key}: {', '.join(str(v) for v in value)}")
                else:
                    lines.append(f"  • {key}: {value}")
        
        status = "[green]已选中[/green]" if s.selected else "[dim]未选中[/dim]"
        console.print(Panel(
            "\n".join(lines),
            title=f"{s.title} - {status}",
            border_style="green" if s.selected else "dim",
        ))
    
    def interactive_select(self) -> list[FixSuggestion]:
        """交互式选择修复建议
        
        Returns:
            选中的修复建议列表
        """
        if not self.suggestions:
            return []
        
        while True:
            # 显示所有建议
            console.clear()
            self.display_all()
            
            # 显示操作提示
            console.print("\n[bold]操作:[/bold]")
            console.print("  [cyan]数字[/cyan] - 切换对应建议的选中状态")
            console.print("  [cyan]a[/cyan] - 全选")
            console.print("  [cyan]n[/cyan] - 取消全选")
            console.print("  [cyan]d <数字>[/cyan] - 查看详情")
            console.print("  [cyan]f <类型>[/cyan] - 按类型筛选 (name/timeline/source/nonperson)")
            console.print("  [cyan]l <指令>[/cyan] - 使用自然语言选择（如: l 合并所有特朗普相关的）")
            console.print("  [cyan]Enter[/cyan] - 确认选择")
            console.print("  [cyan]q[/cyan] - 取消")
            
            # 获取用户输入
            choice = Prompt.ask("\n请选择", default="")
            
            if not choice:
                # 确认选择
                break
            
            if choice.lower() == "q":
                # 取消
                return []
            
            if choice.lower() == "a":
                # 全选
                for s in self.suggestions:
                    s.selected = True
                continue
            
            if choice.lower() == "n":
                # 取消全选
                for s in self.suggestions:
                    s.selected = False
                continue
            
            if choice.lower().startswith("d "):
                # 查看详情
                try:
                    index = int(choice[2:]) - 1
                    if 0 <= index < len(self.suggestions):
                        console.clear()
                        self.display_detail(index)
                        Prompt.ask("\n按 Enter 继续")
                except ValueError:
                    pass
                continue
            
            if choice.lower().startswith("f "):
                # 按类型筛选
                filter_map = {
                    "name": FixType.NAME_MERGE,
                    "timeline": FixType.TIMELINE_IMPROVE,
                    "source": FixType.SOURCE_ADD,
                    "nonperson": FixType.NON_PERSON_REMOVE,
                }
                filter_type = choice[2:].lower()
                if filter_type in filter_map:
                    self.filtered_type = filter_map[filter_type]
                continue
            
            if choice.lower().startswith("l "):
                # 使用 LLM 解析自然语言指令
                self._apply_llm_instruction(choice[2:])
                continue
            
            # 切换单个建议的选中状态
            try:
                index = int(choice) - 1
                if 0 <= index < len(self.suggestions):
                    self.suggestions[index].toggle()
            except ValueError:
                pass
        
        # 返回选中的建议
        return [s for s in self.suggestions if s.selected]
    
    def _apply_llm_instruction(self, instruction: str) -> None:
        """使用 LLM 解析并应用自然语言指令
        
        Args:
            instruction: 自然语言指令
        """
        from rss_news.services.llm_client import get_llm_client
        
        # 构建建议摘要
        suggestions_summary = []
        for i, s in enumerate(self.suggestions, 1):
            suggestions_summary.append({
                "index": i,
                "id": s.id,
                "type": s.fix_type.value,
                "title": s.title,
                "description": s.description,
                "confidence": s.confidence,
                "data": s.data,
            })
        
        prompt = f"""你是一个修复建议选择助手。用户会给出自然语言指令，你需要根据指令选择相应的修复建议。

可用的修复建议：
{json.dumps(suggestions_summary, ensure_ascii=False, indent=2)}

用户指令：{instruction}

请返回 JSON 格式的响应：
{{
  "selected_indices": [要选中的建议索引列表],
  "deselected_indices": [要取消选中的建议索引列表],
  "reason": "选择理由"
}}

注意：
1. 索引从 1 开始
2. 只返回 JSON，不要其他内容
3. 如果指令不明确，返回空列表
4. 支持的指令示例：
   - "合并所有特朗普相关的" -> 选中所有包含"特朗普"的名字合并建议
   - "取消所有低置信度的" -> 取消选中置信度低于 0.8 的建议
   - "只保留名字合并" -> 只选中类型为 name_merge 的建议
"""
        
        try:
            llm_client = get_llm_client()
            response = llm_client._call_api(
                messages=[{"role": "user", "content": prompt}],
                max_tokens=500,
            )
            
            # 清理响应
            response = response.strip()
            if response.startswith("```json"):
                response = response[7:]
            if response.startswith("```"):
                response = response[3:]
            if response.endswith("```"):
                response = response[:-3]
            response = response.strip()
            
            # 解析 JSON
            json_start = response.find('{')
            json_end = response.rfind('}')
            if json_start != -1 and json_end != -1:
                json_str = response[json_start:json_end+1]
                data = json.loads(json_str)
                
                # 应用选择
                selected_indices = data.get("selected_indices", [])
                deselected_indices = data.get("deselected_indices", [])
                reason = data.get("reason", "")
                
                # 选中
                for idx in selected_indices:
                    if 1 <= idx <= len(self.suggestions):
                        self.suggestions[idx - 1].selected = True
                
                # 取消选中
                for idx in deselected_indices:
                    if 1 <= idx <= len(self.suggestions):
                        self.suggestions[idx - 1].selected = False
                
                # 显示结果
                console.print(f"\n[green]LLM 解析成功:[/green] {reason}")
                console.print(f"  选中: {len(selected_indices)} 项")
                console.print(f"  取消: {len(deselected_indices)} 项")
                Prompt.ask("\n按 Enter 继续")
            
        except Exception as e:
            console.print(f"\n[red]LLM 解析失败: {e}[/red]")
            Prompt.ask("\n按 Enter 继续")


def create_suggestions_from_candidates(candidates: list[dict]) -> list[FixSuggestion]:
    """从合并候选创建修复建议
    
    Args:
        candidates: 合并候选列表
        
    Returns:
        修复建议列表
    """
    suggestions = []
    
    for i, cand in enumerate(candidates):
        primary = cand.get("primary_name", "未知")
        variants = cand.get("variant_names", [])
        confidence = cand.get("confidence", 0.5)
        evidence = cand.get("evidence", [])
        files = cand.get("files", [])
        
        # 创建标题
        if len(variants) > 2:
            title = f"合并 {primary} 等 {len(variants)} 个页面"
        else:
            title = f"合并 {primary} 和 {variants[-1] if variants[-1] != primary else variants[0]}"
        
        # 创建描述
        description = f"将 {', '.join(variants)} 合并到 {primary}"
        
        suggestion = FixSuggestion(
            id=cand.get("id", f"merge_{i+1}"),
            fix_type=FixType.NAME_MERGE,
            title=title,
            description=description,
            confidence=confidence,
            evidence=evidence,
            data={
                "primary_name": primary,
                "variant_names": variants,
                "files": files,
                "article_ids": cand.get("article_ids", []),
            },
        )
        suggestions.append(suggestion)
    
    return suggestions


def create_suggestions_from_political_entity_candidates(
    candidates: list[dict]
) -> list[FixSuggestion]:
    """从政治实体合并候选创建修复建议
    
    Args:
        candidates: 合并候选列表
        
    Returns:
        修复建议列表
    """
    suggestions = []
    
    for i, cand in enumerate(candidates):
        primary = cand.get("primary_name", "未知")
        variants = cand.get("variant_names", [])
        confidence = cand.get("confidence", 0.5)
        evidence = cand.get("evidence", [])
        files = cand.get("files", [])
        
        # 创建标题
        if len(variants) > 2:
            title = f"合并政治实体 {primary} 等 {len(variants)} 个页面"
        else:
            other = [v for v in variants if v != primary]
            title = f"合并政治实体 {primary} 和 {other[0] if other else variants[0]}"
        
        # 创建描述
        description = f"将 {', '.join(variants)} 合并到 {primary}"
        
        suggestion = FixSuggestion(
            id=cand.get("id", f"political_entity_merge_{i+1}"),
            fix_type=FixType.POLITICAL_ENTITY_MERGE,
            title=title,
            description=description,
            confidence=confidence,
            evidence=evidence,
            data={
                "primary_name": primary,
                "variant_names": variants,
                "files": files,
                "article_ids": cand.get("article_ids", []),
            },
        )
        suggestions.append(suggestion)
    
    return suggestions
