"""人名映射数据模型

定义人名映射相关的数据结构和枚举类型。
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class VariantType(Enum):
    """名字变体类型"""
    CHINESE_TRANSLATION = "chinese_translation"  # 中文译名
    SPELLING_VARIANT = "spelling_variant"        # 拼写变体
    ALIAS = "alias"                              # 别名/昵称
    FULL_NAME = "full_name"                      # 全名 vs 简称
    MIXED = "mixed"                              # 中英文混合名


class MappingSource(Enum):
    """映射来源"""
    LLM_ANALYSIS = "llm_analysis"      # LLM 分析得出
    USER_CONFIRMED = "user_confirmed"  # 用户确认
    MANUAL_ENTRY = "manual_entry"      # 手动录入
    PREDEFINED = "predefined"          # 预定义规则


@dataclass
class NameMapping:
    """人名映射关系
    
    存储一个变体名称到主名称的映射关系。
    """
    primary_name: str                              # 主名称（规范名称）
    variant_name: str                              # 变体名称
    variant_type: VariantType                      # 变体类型
    confidence: float                              # 置信度 (0.0-1.0)
    source: MappingSource                          # 来源
    evidence: list[str] = field(default_factory=list)  # 证据（新闻摘要/来源）
    article_ids: list[int] = field(default_factory=list)  # 相关文章 ID
    id: Optional[int] = None                       # 主键
    created_at: Optional[datetime] = None          # 创建时间
    updated_at: Optional[datetime] = None          # 更新时间
    verified: bool = False                         # 是否已人工验证
    
    def __post_init__(self):
        """初始化后处理"""
        if self.created_at is None:
            self.created_at = datetime.now()
        if self.updated_at is None:
            self.updated_at = datetime.now()
    
    def to_dict(self) -> dict:
        """转换为字典
        
        Returns:
            字典表示
        """
        return {
            "id": self.id,
            "primary_name": self.primary_name,
            "variant_name": self.variant_name,
            "variant_type": self.variant_type.value,
            "confidence": self.confidence,
            "source": self.source.value,
            "evidence": self.evidence,
            "article_ids": self.article_ids,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "verified": self.verified,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "NameMapping":
        """从字典创建实例
        
        Args:
            data: 字典数据
            
        Returns:
            NameMapping 实例
        """
        return cls(
            id=data.get("id"),
            primary_name=data["primary_name"],
            variant_name=data["variant_name"],
            variant_type=VariantType(data["variant_type"]),
            confidence=data["confidence"],
            source=MappingSource(data["source"]),
            evidence=data.get("evidence", []),
            article_ids=data.get("article_ids", []),
            created_at=datetime.fromisoformat(data["created_at"]) if data.get("created_at") else None,
            updated_at=datetime.fromisoformat(data["updated_at"]) if data.get("updated_at") else None,
            verified=data.get("verified", False),
        )
    
    def to_db_row(self) -> tuple:
        """转换为数据库行
        
        Returns:
            数据库行元组
        """
        import json
        return (
            self.primary_name,
            self.variant_name,
            self.variant_type.value,
            self.confidence,
            self.source.value,
            json.dumps(self.evidence, ensure_ascii=False) if self.evidence else None,
            json.dumps(self.article_ids) if self.article_ids else None,
            self.created_at.isoformat() if self.created_at else datetime.now().isoformat(),
            self.updated_at.isoformat() if self.updated_at else datetime.now().isoformat(),
            1 if self.verified else 0,
        )
    
    @classmethod
    def from_db_row(cls, row: tuple) -> "NameMapping":
        """从数据库行创建实例
        
        Args:
            row: 数据库行元组
            
        Returns:
            NameMapping 实例
        """
        import json
        return cls(
            id=row[0],
            primary_name=row[1],
            variant_name=row[2],
            variant_type=VariantType(row[3]),
            confidence=row[4],
            source=MappingSource(row[5]),
            evidence=json.loads(row[6]) if row[6] else [],
            article_ids=json.loads(row[7]) if row[7] else [],
            created_at=datetime.fromisoformat(row[8]) if row[8] else None,
            updated_at=datetime.fromisoformat(row[9]) if row[9] else None,
            verified=bool(row[10]),
        )


# 预定义的常见人名映射
PREDEFINED_MAPPINGS: list[tuple[str, str, VariantType]] = [
    # 美国政要
    ("Donald Trump", "特朗普", VariantType.CHINESE_TRANSLATION),
    ("Donald Trump", "川普", VariantType.CHINESE_TRANSLATION),
    ("Donald Trump", "Trump", VariantType.ALIAS),
    ("Joe Biden", "拜登", VariantType.CHINESE_TRANSLATION),
    ("Joe Biden", "Biden", VariantType.ALIAS),
    ("Barack Obama", "奥巴马", VariantType.CHINESE_TRANSLATION),
    ("Hillary Clinton", "希拉里", VariantType.CHINESE_TRANSLATION),
    ("Bill Clinton", "克林顿", VariantType.CHINESE_TRANSLATION),
    
    # 俄罗斯
    ("Vladimir Putin", "普京", VariantType.CHINESE_TRANSLATION),
    
    # 乌克兰
    ("Volodymyr Zelensky", "泽连斯基", VariantType.CHINESE_TRANSLATION),
    ("Volodymyr Zelensky", "Volodymyr Zelenskyy", VariantType.SPELLING_VARIANT),
    
    # 中国
    ("Xi Jinping", "习近平", VariantType.CHINESE_TRANSLATION),
    
    # 其他国家领导人
    ("Kim Jong-un", "金正恩", VariantType.CHINESE_TRANSLATION),
    ("Recep Tayyip Erdogan", "埃尔多安", VariantType.CHINESE_TRANSLATION),
    ("Benjamin Netanyahu", "内塔尼亚胡", VariantType.CHINESE_TRANSLATION),
    ("Emmanuel Macron", "马克龙", VariantType.CHINESE_TRANSLATION),
    ("Angela Merkel", "默克尔", VariantType.CHINESE_TRANSLATION),
    ("Boris Johnson", "约翰逊", VariantType.CHINESE_TRANSLATION),
    ("Rishi Sunak", "苏纳克", VariantType.CHINESE_TRANSLATION),
    ("Narendra Modi", "莫迪", VariantType.CHINESE_TRANSLATION),
    ("Shinzo Abe", "安倍", VariantType.CHINESE_TRANSLATION),
    ("Ali Khamenei", "哈梅内伊", VariantType.CHINESE_TRANSLATION),
    
    # 商界人物
    ("Elon Musk", "马斯克", VariantType.CHINESE_TRANSLATION),
    ("Bill Gates", "比尔盖茨", VariantType.CHINESE_TRANSLATION),
    ("Mark Zuckerberg", "扎克伯格", VariantType.CHINESE_TRANSLATION),
    ("Jeff Bezos", "贝索斯", VariantType.CHINESE_TRANSLATION),
    ("Tim Cook", "库克", VariantType.CHINESE_TRANSLATION),
    
    # 娱乐界
    ("Kanye West", "Ye", VariantType.ALIAS),
    ("Kanye West", "侃爷", VariantType.CHINESE_TRANSLATION),
    
    # 其他
    ("Henry Kissinger", "基辛格", VariantType.CHINESE_TRANSLATION),
    ("Pope Francis", "方济各", VariantType.CHINESE_TRANSLATION),
    ("Pope Francis", "教皇方济各", VariantType.CHINESE_TRANSLATION),
]
