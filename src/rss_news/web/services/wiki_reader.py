"""Wiki 读取服务

读取和解析 Wiki Markdown 文件。
"""

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional


@dataclass
class PersonInfo:
    """人物信息"""
    name: str
    description: str = ""
    related_people: list[str] = None
    news: list[dict] = None
    timeline: list[dict] = None
    generated_at: str = ""
    
    def __post_init__(self):
        if self.related_people is None:
            self.related_people = []
        if self.news is None:
            self.news = []
        if self.timeline is None:
            self.timeline = []


@dataclass
class EntityInfo:
    """政治实体信息"""
    name: str
    entity_type: str = ""
    description: str = ""
    news: list[dict] = None
    timeline: list[dict] = None
    generated_at: str = ""
    
    def __post_init__(self):
        if self.news is None:
            self.news = []
        if self.timeline is None:
            self.timeline = []


class WikiReader:
    """Wiki 读取器
    
    读取和解析 Wiki 目录下的 Markdown 文件。
    """
    
    def __init__(self, wiki_dir: str | Path = "wiki"):
        """初始化读取器
        
        Args:
            wiki_dir: Wiki 目录路径
        """
        self.wiki_dir = Path(wiki_dir)
        self.people_dir = self.wiki_dir / "people"
        self.entities_dir = self.wiki_dir / "political_entities"
    
    def get_all_people(self) -> list[dict]:
        """获取所有人物列表
        
        Returns:
            人物列表，每项包含 name 和 description
        """
        people = []
        
        if not self.people_dir.exists():
            return people
        
        for file_path in sorted(self.people_dir.glob("*.md")):
            name = file_path.stem
            # 读取简介
            content = file_path.read_text(encoding="utf-8")
            description = self._extract_description(content)
            
            people.append({
                "name": name,
                "description": description[:100] + "..." if len(description) > 100 else description,
            })
        
        return people
    
    def get_person(self, name: str) -> Optional[PersonInfo]:
        """获取人物详情
        
        Args:
            name: 人物名称
            
        Returns:
            人物信息，不存在返回 None
        """
        file_path = self.people_dir / f"{name}.md"
        
        if not file_path.exists():
            return None
        
        content = file_path.read_text(encoding="utf-8")
        return self._parse_person_content(name, content)
    
    def get_all_entities(self) -> list[dict]:
        """获取所有政治实体列表
        
        Returns:
            政治实体列表，每项包含 name, type 和 description
        """
        entities = []
        
        if not self.entities_dir.exists():
            return entities
        
        for file_path in sorted(self.entities_dir.glob("*.md")):
            name = file_path.stem
            content = file_path.read_text(encoding="utf-8")
            entity_type = self._extract_entity_type(content)
            description = self._extract_description(content)
            
            entities.append({
                "name": name,
                "type": entity_type,
                "description": description[:100] + "..." if len(description) > 100 else description,
            })
        
        return entities
    
    def get_entity(self, name: str) -> Optional[EntityInfo]:
        """获取政治实体详情
        
        Args:
            name: 实体名称
            
        Returns:
            实体信息，不存在返回 None
        """
        file_path = self.entities_dir / f"{name}.md"
        
        if not file_path.exists():
            return None
        
        content = file_path.read_text(encoding="utf-8")
        return self._parse_entity_content(name, content)
    
    def get_stats(self) -> dict:
        """获取 Wiki 统计信息
        
        Returns:
            统计信息字典
        """
        people_count = len(list(self.people_dir.glob("*.md"))) if self.people_dir.exists() else 0
        entities_count = len(list(self.entities_dir.glob("*.md"))) if self.entities_dir.exists() else 0
        
        return {
            "people_count": people_count,
            "entities_count": entities_count,
        }
    
    def _parse_person_content(self, name: str, content: str) -> PersonInfo:
        """解析人物页面内容
        
        Args:
            name: 人物名称
            content: Markdown 内容
            
        Returns:
            人物信息
        """
        return PersonInfo(
            name=name,
            description=self._extract_description(content),
            related_people=self._extract_related_people(content),
            news=self._extract_news(content),
            timeline=self._extract_timeline(content),
            generated_at=self._extract_generated_at(content),
        )
    
    def _parse_entity_content(self, name: str, content: str) -> EntityInfo:
        """解析政治实体页面内容
        
        Args:
            name: 实体名称
            content: Markdown 内容
            
        Returns:
            实体信息
        """
        return EntityInfo(
            name=name,
            entity_type=self._extract_entity_type(content),
            description=self._extract_description(content),
            news=self._extract_news(content),
            timeline=self._extract_timeline(content),
            generated_at=self._extract_generated_at(content),
        )
    
    def _extract_description(self, content: str) -> str:
        """提取简介"""
        match = re.search(r'## 简介\s*\n(.+?)(?=\n##|\Z)', content, re.DOTALL)
        return match.group(1).strip() if match else ""
    
    def _extract_entity_type(self, content: str) -> str:
        """提取实体类型"""
        match = re.search(r'## 类型\s*\n(.+?)(?=\n##|\Z)', content, re.DOTALL)
        return match.group(1).strip() if match else ""
    
    def _extract_related_people(self, content: str) -> list[str]:
        """提取相关人物"""
        match = re.search(r'## 相关人物\s*\n(.+?)(?=\n##|\Z)', content, re.DOTALL)
        if not match:
            return []
        
        people_text = match.group(1)
        return re.findall(r'\[\[([^\]]+)\]\]', people_text)
    
    def _extract_news(self, content: str) -> list[dict]:
        """提取相关新闻"""
        match = re.search(r'## 相关新闻\s*\n(.+?)(?=\n##|\Z)', content, re.DOTALL)
        if not match:
            return []
        
        news_text = match.group(1)
        news_list = []
        
        # 匹配格式: [标题](article://ID) [来源] - 日期
        pattern = r'- \[([^\]]+)\]\(article://(\d+)\)(?:\s+\[([^\]]+)\])?\s*-\s*(\d{4}-\d{2}-\d{2})'
        for m in re.finditer(pattern, news_text):
            news_list.append({
                "title": m.group(1),
                "article_id": int(m.group(2)),
                "source": m.group(3) or "",
                "date": m.group(4),
            })
        
        return news_list
    
    def _extract_timeline(self, content: str) -> list[dict]:
        """提取时间线"""
        match = re.search(r'## 时间线\s*\n(.+?)(?=\n##|\Z)', content, re.DOTALL)
        if not match:
            return []
        
        timeline_text = match.group(1)
        timeline = []
        
        # 匹配格式: - **日期**: 内容
        pattern = r'- \*\*(\d{4}-\d{2}-\d{2})\*\*:\s*(.+)'
        for m in re.finditer(pattern, timeline_text):
            timeline.append({
                "date": m.group(1),
                "content": m.group(2).strip(),
            })
        
        return timeline
    
    def _extract_generated_at(self, content: str) -> str:
        """提取生成时间"""
        match = re.search(r'\*生成时间:\s*(.+)\*', content)
        return match.group(1).strip() if match else ""
