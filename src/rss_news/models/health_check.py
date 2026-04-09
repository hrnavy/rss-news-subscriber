"""Wiki 健康检查数据模型

定义健康检查结果和建议的数据结构。
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class CheckType(str, Enum):
    """检查类型枚举"""
    NAMES = "names"
    POLITICAL_ENTITIES = "political_entities"
    TIMELINE = "timeline"
    SOURCE = "source"
    NON_PERSON = "non_person"
    ALL = "all"


class CheckStatus(str, Enum):
    """检查状态枚举"""
    PASS = "pass"
    WARNING = "warning"
    ERROR = "error"


class EntityType(str, Enum):
    """实体类型枚举"""
    PERSON = "person"
    COUNTRY = "country"
    ORGANIZATION = "organization"
    UNKNOWN = "unknown"


@dataclass
class NameMergeSuggestion:
    """名字合并建议
    
    当检测到可能重复的人物名称时，提供合并建议。
    
    Attributes:
        names: 可能重复的名字列表
        is_same_person: 是否为同一人
        confidence: 置信度 (0.0-1.0)
        reason: 基于新闻的理由
        evidence: 证据列表（新闻引用）
        suggested_primary_name: 建议的主名称
        article_ids: 相关文章 ID 列表
    """
    names: list[str]
    is_same_person: bool
    confidence: float
    reason: str
    evidence: list[str] = field(default_factory=list)
    suggested_primary_name: str = ""
    article_ids: list[int] = field(default_factory=list)
    
    def to_dict(self) -> dict:
        """转换为字典格式"""
        return {
            "names": self.names,
            "is_same_person": self.is_same_person,
            "confidence": self.confidence,
            "reason": self.reason,
            "evidence": self.evidence,
            "suggested_primary_name": self.suggested_primary_name,
            "article_ids": self.article_ids,
        }


@dataclass
class TimelineImprovement:
    """时间线改进建议
    
    当时间线只是新闻标题时，提供改进建议。
    
    Attributes:
        person_name: 人物名称
        date: 日期
        original: 原始内容（新闻标题）
        improved: 改进后内容（人物行为总结）
        article_id: 关联文章 ID
        source: 新闻来源
    """
    person_name: str
    date: str
    original: str
    improved: str
    article_id: int
    source: str = ""
    
    def to_dict(self) -> dict:
        """转换为字典格式"""
        return {
            "person_name": self.person_name,
            "date": self.date,
            "original": self.original,
            "improved": self.improved,
            "article_id": self.article_id,
            "source": self.source,
        }


@dataclass
class NewsSourceInfo:
    """新闻来源信息
    
    Attributes:
        article_id: 文章 ID
        title: 文章标题
        source: 新闻来源（如 Reuters, BBC）
        date: 发布日期
        link: 文章链接
    """
    article_id: int
    title: str
    source: str
    date: str
    link: str = ""
    
    def to_dict(self) -> dict:
        """转换为字典格式"""
        return {
            "article_id": self.article_id,
            "title": self.title,
            "source": self.source,
            "date": self.date,
            "link": self.link,
        }


@dataclass
class NonPersonEntity:
    """非人物实体
    
    检测被错误分类为人物的非人物实体。
    
    Attributes:
        name: 实体名称
        entity_type: 实体类型
        suggested_action: 建议的处理方式
        reason: 判断理由
        article_ids: 相关文章 ID 列表
    """
    name: str
    entity_type: EntityType
    suggested_action: str
    reason: str = ""
    article_ids: list[int] = field(default_factory=list)
    
    def to_dict(self) -> dict:
        """转换为字典格式"""
        return {
            "name": self.name,
            "entity_type": self.entity_type.value,
            "suggested_action": self.suggested_action,
            "reason": self.reason,
            "article_ids": self.article_ids,
        }


@dataclass
class HealthCheckResult:
    """健康检查结果
    
    单项检查的结果数据结构。
    
    Attributes:
        check_type: 检查类型
        status: 检查状态
        issues: 问题列表
        suggestions: 建议列表
        timestamp: 检查时间
        message: 概要消息
    """
    check_type: CheckType
    status: CheckStatus
    issues: list[dict] = field(default_factory=list)
    suggestions: list[dict] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    message: str = ""
    
    def to_dict(self) -> dict:
        """转换为字典格式"""
        return {
            "check_type": self.check_type.value,
            "status": self.status.value,
            "issues": self.issues,
            "suggestions": self.suggestions,
            "timestamp": self.timestamp,
            "message": self.message,
        }
    
    @property
    def issue_count(self) -> int:
        """问题数量"""
        return len(self.issues)
    
    @property
    def suggestion_count(self) -> int:
        """建议数量"""
        return len(self.suggestions)


@dataclass
class FullHealthReport:
    """完整健康检查报告
    
    包含所有检查类型的结果。
    
    Attributes:
        results: 各项检查结果
        summary: 摘要信息
        timestamp: 报告生成时间
        wiki_dir: Wiki 目录路径
    """
    results: dict[str, HealthCheckResult] = field(default_factory=dict)
    summary: dict[str, int] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    wiki_dir: str = ""
    
    def add_result(self, result: HealthCheckResult) -> None:
        """添加检查结果"""
        self.results[result.check_type.value] = result
    
    def calculate_summary(self) -> None:
        """计算摘要信息"""
        total_issues = sum(r.issue_count for r in self.results.values())
        total_suggestions = sum(r.suggestion_count for r in self.results.values())
        
        status_counts = {"pass": 0, "warning": 0, "error": 0}
        for result in self.results.values():
            status_counts[result.status.value] += 1
        
        self.summary = {
            "total_issues": total_issues,
            "total_suggestions": total_suggestions,
            "pass_count": status_counts["pass"],
            "warning_count": status_counts["warning"],
            "error_count": status_counts["error"],
        }
    
    def to_dict(self) -> dict:
        """转换为字典格式"""
        self.calculate_summary()
        return {
            "timestamp": self.timestamp,
            "wiki_dir": self.wiki_dir,
            "summary": self.summary,
            "results": {k: v.to_dict() for k, v in self.results.items()},
        }
    
    @property
    def overall_status(self) -> CheckStatus:
        """获取整体状态"""
        if any(r.status == CheckStatus.ERROR for r in self.results.values()):
            return CheckStatus.ERROR
        if any(r.status == CheckStatus.WARNING for r in self.results.values()):
            return CheckStatus.WARNING
        return CheckStatus.PASS


@dataclass
class PersonWikiInfo:
    """人物 Wiki 信息
    
    解析 Wiki 人物页面得到的信息。
    
    Attributes:
        file_path: 文件路径
        name: 人物名称
        description: 简介
        related_people: 相关人物列表
        article_ids: 相关文章 ID 列表
        timeline: 时间线条目列表
    """
    file_path: str
    name: str
    description: str = ""
    related_people: list[str] = field(default_factory=list)
    article_ids: list[int] = field(default_factory=list)
    timeline: list[dict] = field(default_factory=list)
    
    def to_dict(self) -> dict:
        """转换为字典格式"""
        return {
            "file_path": self.file_path,
            "name": self.name,
            "description": self.description,
            "related_people": self.related_people,
            "article_ids": self.article_ids,
            "timeline": self.timeline,
        }
