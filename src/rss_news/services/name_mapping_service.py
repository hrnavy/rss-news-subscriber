"""人名映射服务模块

提供人名映射的存储、查询和分析功能。
"""

import json
import logging
from datetime import datetime
from typing import Optional

from rss_news.db.connection import get_connection
from rss_news.models.name_mapping import (
    MappingSource,
    NameMapping,
    PREDEFINED_MAPPINGS,
    VariantType,
)
from rss_news.services.llm_client import get_llm_client

logger = logging.getLogger(__name__)


class NameMappingService:
    """人名映射服务
    
    提供人名映射的 CRUD 操作和分析功能。
    """
    
    def __init__(self):
        """初始化服务"""
        self.llm_client = get_llm_client()
        self._initialized = False
    
    def initialize(self) -> None:
        """初始化服务，加载预定义映射"""
        if self._initialized:
            return
        
        self._load_predefined_mappings()
        self._initialized = True
    
    def _load_predefined_mappings(self) -> None:
        """加载预定义的人名映射"""
        with get_connection() as conn:
            cursor = conn.cursor()
            
            for primary_name, variant_name, variant_type in PREDEFINED_MAPPINGS:
                # 检查是否已存在
                cursor.execute(
                    "SELECT id FROM name_mappings WHERE primary_name = ? AND variant_name = ?",
                    (primary_name, variant_name)
                )
                if cursor.fetchone():
                    continue
                
                # 添加预定义映射
                now = datetime.now().isoformat()
                cursor.execute(
                    """INSERT INTO name_mappings 
                       (primary_name, variant_name, variant_type, confidence, source, 
                        evidence, article_ids, created_at, updated_at, verified)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        primary_name,
                        variant_name,
                        variant_type.value,
                        1.0,  # 预定义映射置信度为 1.0
                        MappingSource.PREDEFINED.value,
                        None,
                        None,
                        now,
                        now,
                        1,  # 预定义映射默认已验证
                    )
                )
            
            conn.commit()
            logger.info(f"已加载 {len(PREDEFINED_MAPPINGS)} 条预定义映射")
    
    def get_primary_name(self, name: str) -> Optional[str]:
        """查询变体名称对应的主名称
        
        Args:
            name: 变体名称
            
        Returns:
            主名称，如果不存在返回 None
        """
        self.initialize()
        
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT primary_name FROM name_mappings WHERE variant_name = ?",
                (name,)
            )
            row = cursor.fetchone()
            return row[0] if row else None
    
    def get_all_variants(self, primary_name: str) -> list[str]:
        """获取主名称的所有变体
        
        Args:
            primary_name: 主名称
            
        Returns:
            变体名称列表
        """
        self.initialize()
        
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT variant_name FROM name_mappings WHERE primary_name = ?",
                (primary_name,)
            )
            return [row[0] for row in cursor.fetchall()]
    
    def get_mapping(self, variant_name: str) -> Optional[NameMapping]:
        """获取完整的映射关系
        
        Args:
            variant_name: 变体名称
            
        Returns:
            NameMapping 对象，如果不存在返回 None
        """
        self.initialize()
        
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM name_mappings WHERE variant_name = ?",
                (variant_name,)
            )
            row = cursor.fetchone()
            return NameMapping.from_db_row(row) if row else None
    
    def add_mapping(self, mapping: NameMapping) -> bool:
        """添加新的映射关系
        
        Args:
            mapping: 映射关系
            
        Returns:
            是否添加成功
        """
        self.initialize()
        
        with get_connection() as conn:
            cursor = conn.cursor()
            
            # 检查是否已存在
            cursor.execute(
                "SELECT id FROM name_mappings WHERE primary_name = ? AND variant_name = ?",
                (mapping.primary_name, mapping.variant_name)
            )
            if cursor.fetchone():
                logger.warning(f"映射已存在: {mapping.variant_name} -> {mapping.primary_name}")
                return False
            
            # 添加映射
            now = datetime.now().isoformat()
            cursor.execute(
                """INSERT INTO name_mappings 
                   (primary_name, variant_name, variant_type, confidence, source, 
                    evidence, article_ids, created_at, updated_at, verified)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    mapping.primary_name,
                    mapping.variant_name,
                    mapping.variant_type.value,
                    mapping.confidence,
                    mapping.source.value,
                    json.dumps(mapping.evidence, ensure_ascii=False) if mapping.evidence else None,
                    json.dumps(mapping.article_ids) if mapping.article_ids else None,
                    mapping.created_at.isoformat() if mapping.created_at else now,
                    mapping.updated_at.isoformat() if mapping.updated_at else now,
                    1 if mapping.verified else 0,
                )
            )
            
            conn.commit()
            logger.info(f"已添加映射: {mapping.variant_name} -> {mapping.primary_name}")
            return True
    
    def confirm_mapping(self, mapping_id: int) -> bool:
        """确认映射关系（用户验证）
        
        Args:
            mapping_id: 映射 ID
            
        Returns:
            是否确认成功
        """
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE name_mappings SET verified = 1, updated_at = ? WHERE id = ?",
                (datetime.now().isoformat(), mapping_id)
            )
            conn.commit()
            return cursor.rowcount > 0
    
    def delete_mapping(self, mapping_id: int) -> bool:
        """删除映射关系
        
        Args:
            mapping_id: 映射 ID
            
        Returns:
            是否删除成功
        """
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM name_mappings WHERE id = ?", (mapping_id,))
            conn.commit()
            return cursor.rowcount > 0
    
    def list_mappings(
        self,
        verified_only: bool = False,
        source: Optional[MappingSource] = None,
    ) -> list[NameMapping]:
        """列出所有映射
        
        Args:
            verified_only: 是否只列出已验证的映射
            source: 按来源筛选
            
        Returns:
            映射列表
        """
        self.initialize()
        
        with get_connection() as conn:
            cursor = conn.cursor()
            
            query = "SELECT * FROM name_mappings WHERE 1=1"
            params = []
            
            if verified_only:
                query += " AND verified = 1"
            
            if source:
                query += " AND source = ?"
                params.append(source.value)
            
            query += " ORDER BY created_at DESC"
            
            cursor.execute(query, params)
            return [NameMapping.from_db_row(row) for row in cursor.fetchall()]
    
    def normalize_name(self, name: str) -> str:
        """规范化人名
        
        查询映射库，返回主名称。如果不存在映射，返回原名称。
        
        Args:
            name: 原始名称
            
        Returns:
            规范化后的名称
        """
        primary = self.get_primary_name(name)
        return primary if primary else name
    
    def analyze_name_relationship(
        self,
        name1: str,
        name2: str,
        articles: list[dict],
    ) -> Optional[NameMapping]:
        """使用 LLM 分析两个名字是否指向同一个人
        
        Args:
            name1: 第一个名字
            name2: 第二个名字
            articles: 相关文章列表
            
        Returns:
            NameMapping 如果确认是同一人，否则返回 None
        """
        if not articles:
            logger.warning("没有文章内容，无法分析名字关系")
            return None
        
        # 构建文章内容字符串
        articles_text = ""
        for article in articles[:5]:  # 限制文章数量
            articles_text += f"\n---\n文章 ID: {article.get('id', '未知')}\n"
            articles_text += f"标题: {article.get('title', '未知')}\n"
            content = article.get('content', '') or ''
            articles_text += f"内容: {content[:1500]}\n"  # 限制单篇长度
        
        prompt = f"""你是一个实体识别专家。请基于以下新闻全文，判断这两个名字是否指向同一个人。

名字1: {name1}
名字2: {name2}

相关新闻全文：
{articles_text}

请回答以下问题，以 JSON 格式返回：
{{
  "is_same_person": true/false,
  "confidence": 0.0-1.0,
  "variant_type": "chinese_translation/spelling_variant/alias/full_name/mixed",
  "primary_name": "建议使用的主名称（通常是更正式或更常用的名称）",
  "reason": "基于新闻原文的理由，必须引用具体内容",
  "evidence": ["证据1", "证据2"]
}}

重要：
1. 不要臆测，必须基于新闻原文给出理由
2. 如果新闻中没有足够信息判断，confidence 设为较低值
3. 如果两个人名明显不同（如 Judd Trump 和 Donald Trump），is_same_person 必须为 false
4. 只返回 JSON，不要其他内容"""

        try:
            response = self.llm_client._call_api(
                messages=[{"role": "user", "content": prompt}],
                max_tokens=1000,
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
            
            # 提取 JSON
            json_start = response.find('{')
            json_end = response.rfind('}')
            if json_start != -1 and json_end != -1:
                json_str = response[json_start:json_end+1]
                try:
                    data = json.loads(json_str)
                except json.JSONDecodeError:
                    json_str = json_str.replace("'", '"')
                    data = json.loads(json_str)
            else:
                raise ValueError("无法在响应中找到 JSON 对象")
            
            # 如果不是同一人，返回 None
            if not data.get("is_same_person", False):
                logger.info(f"LLM 判断 '{name1}' 和 '{name2}' 不是同一人")
                return None
            
            # 确定变体类型
            variant_type_str = data.get("variant_type", "mixed")
            try:
                variant_type = VariantType(variant_type_str)
            except ValueError:
                variant_type = VariantType.MIXED
            
            # 创建映射
            primary_name = data.get("primary_name", name1)
            variant_name = name2 if primary_name == name1 else name1
            
            return NameMapping(
                primary_name=primary_name,
                variant_name=variant_name,
                variant_type=variant_type,
                confidence=data.get("confidence", 0.5),
                source=MappingSource.LLM_ANALYSIS,
                evidence=data.get("evidence", []),
                article_ids=[a.get("id") for a in articles if a.get("id")],
            )
            
        except Exception as e:
            logger.error(f"LLM 分析失败: {e}")
            return None
    
    def analyze_and_add(
        self,
        names: list[str],
        article_ids: list[int],
        auto_confirm_threshold: float = 0.8,
    ) -> Optional[NameMapping]:
        """分析名字关联并添加映射
        
        Args:
            names: 名字列表（通常是两个）
            article_ids: 相关文章 ID 列表
            auto_confirm_threshold: 自动确认的置信度阈值
            
        Returns:
            添加的映射，如果分析失败返回 None
        """
        if len(names) < 2:
            return None
        
        # 获取文章内容
        articles = self._get_articles_content(article_ids)
        if not articles:
            return None
        
        # 分析名字关系
        mapping = self.analyze_name_relationship(names[0], names[1], articles)
        if not mapping:
            return None
        
        # 高置信度自动验证
        if mapping.confidence >= auto_confirm_threshold:
            mapping.verified = True
        
        # 添加映射
        if self.add_mapping(mapping):
            return mapping
        
        return None
    
    def _get_articles_content(self, article_ids: list[int]) -> list[dict]:
        """获取文章内容
        
        Args:
            article_ids: 文章 ID 列表
            
        Returns:
            文章数据列表
        """
        if not article_ids:
            return []
        
        with get_connection() as conn:
            placeholders = ",".join("?" * len(article_ids))
            cursor = conn.execute(
                f"""SELECT id, title, content 
                    FROM articles 
                    WHERE id IN ({placeholders})""",
                article_ids
            )
            rows = cursor.fetchall()
            
            return [
                {
                    "id": row[0],
                    "title": row[1],
                    "content": row[2] or "",
                }
                for row in rows
            ]
    
    def export_mappings(self) -> list[dict]:
        """导出所有映射为字典列表
        
        Returns:
            映射字典列表
        """
        mappings = self.list_mappings()
        return [m.to_dict() for m in mappings]
    
    def import_mappings(
        self,
        mappings: list[dict],
        overwrite: bool = False,
    ) -> tuple[int, int]:
        """导入映射
        
        Args:
            mappings: 映射字典列表
            overwrite: 是否覆盖已存在的映射
            
        Returns:
            (成功数量, 失败数量)
        """
        success = 0
        failed = 0
        
        for data in mappings:
            try:
                mapping = NameMapping.from_dict(data)
                
                if overwrite:
                    # 先删除已存在的映射
                    with get_connection() as conn:
                        cursor = conn.cursor()
                        cursor.execute(
                            "DELETE FROM name_mappings WHERE primary_name = ? AND variant_name = ?",
                            (mapping.primary_name, mapping.variant_name)
                        )
                        conn.commit()
                
                if self.add_mapping(mapping):
                    success += 1
                else:
                    failed += 1
            except Exception as e:
                logger.error(f"导入映射失败: {e}")
                failed += 1
        
        return success, failed
