"""政治实体数据模型"""

from dataclasses import dataclass, field
from enum import Enum


class PoliticalEntityType(Enum):
    """政治实体类型"""
    COUNTRY = "country"
    ORGANIZATION = "organization"
    REGION = "region"


@dataclass
class PoliticalEntityInfo:
    """政治实体信息
    
    Attributes:
        name: 实体名称
        entity_type: 实体类型
        description: 简介
        related_people: 相关人物
        article_ids: 相关文章ID
        timeline: 时间线
    """
    name: str
    entity_type: PoliticalEntityType
    description: str = ""
    related_people: list[str] = field(default_factory=list)
    article_ids: list[int] = field(default_factory=list)
    timeline: list[dict] = field(default_factory=list)
    
    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "name": self.name,
            "entity_type": self.entity_type.value,
            "description": self.description,
            "related_people": self.related_people,
            "article_ids": self.article_ids,
            "timeline": self.timeline,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "PoliticalEntityInfo":
        """从字典创建"""
        return cls(
            name=data.get("name", ""),
            entity_type=PoliticalEntityType(data.get("entity_type", "country")),
            description=data.get("description", ""),
            related_people=data.get("related_people", []),
            article_ids=data.get("article_ids", []),
            timeline=data.get("timeline", []),
        )
