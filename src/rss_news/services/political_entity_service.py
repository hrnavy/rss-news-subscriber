"""政治实体 Wiki 服务模块

从新闻中提取政治实体（国家、组织、地区），生成结构化的 Markdown 知识库。
"""

import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Optional

from rss_news.db.connection import get_connection
from rss_news.models.political_entity import PoliticalEntityInfo, PoliticalEntityType
from rss_news.services.llm_client import get_llm_client

logger = logging.getLogger(__name__)

WIKI_DIR = Path("wiki")

# LLM 配置
MAX_CONTEXT_TOKENS = 22296
RESERVED_TOKENS = 2000
MAX_WORKERS = 1
MAX_ARTICLE_CHARS = 4000
BATCH_MAX_TOKENS = 8000


class PoliticalEntityService:
    """政治实体 Wiki 服务
    
    管理政治实体页面的生成和更新。
    """
    
    def __init__(self, wiki_dir: Path | None = None):
        self.wiki_dir = wiki_dir or WIKI_DIR
        self.political_entities_dir = self.wiki_dir / "political_entities"
        self.llm_client = get_llm_client()
    
    def init_political_entities(self) -> bool:
        """初始化政治实体目录
        
        Returns:
            True 如果初始化成功
        """
        try:
            self.political_entities_dir.mkdir(parents=True, exist_ok=True)
            return True
        except Exception as e:
            logger.error(f"初始化政治实体目录失败: {e}")
            return False
    
    def get_all_articles(self, limit: int = 100) -> list[tuple]:
        """获取所有文章
        
        Args:
            limit: 最大数量
            
        Returns:
            文章列表 [(id, title, content, published_at), ...]
        """
        with get_connection() as conn:
            cursor = conn.execute(
                """SELECT id, title, content, published_at 
                   FROM articles 
                   ORDER BY published_at DESC 
                   LIMIT ?""",
                (limit,)
            )
            return cursor.fetchall()
    
    def get_unprocessed_articles(self, limit: int = 100) -> list[tuple]:
        """获取未处理的文章
        
        Args:
            limit: 最大数量
            
        Returns:
            文章列表
        """
        with get_connection() as conn:
            cursor = conn.execute(
                """SELECT id, title, content, published_at 
                   FROM articles 
                   WHERE wiki_processed = 0 
                   ORDER BY published_at DESC 
                   LIMIT ?""",
                (limit,)
            )
            return cursor.fetchall()
    
    def batch_articles_by_tokens(self, articles: list[tuple]) -> list[list[tuple]]:
        """按 token 数分批
        
        Args:
            articles: 文章列表
            
        Returns:
            批次列表
        """
        batches = []
        current_batch = []
        current_tokens = 0
        
        for article in articles:
            _, title, content, _ = article
            text = content if content and len(content.strip()) > 0 else title
            
            # 估算 token 数（中文约 1.5 字/token，英文约 4 字/token）
            estimated_tokens = len(text) // 3
            
            if current_tokens + estimated_tokens > BATCH_MAX_TOKENS and current_batch:
                batches.append(current_batch)
                current_batch = []
                current_tokens = 0
            
            current_batch.append(article)
            current_tokens += estimated_tokens
        
        if current_batch:
            batches.append(current_batch)
        
        return batches
    
    def _extract_political_entities_from_batch(self, batch: list[tuple]) -> list[dict]:
        """从一批文章中提取政治实体
        
        Args:
            batch: 文章列表
            
        Returns:
            政治实体信息列表
        """
        articles_data = []
        for article in batch:
            article_id, title, content, _ = article
            text = content if content and len(content.strip()) > 0 else title
            if len(text) > MAX_ARTICLE_CHARS:
                text = text[:MAX_ARTICLE_CHARS] + "..."
            articles_data.append({
                "id": article_id,
                "title": title,
                "content": text
            })
        
        prompt = f"""从以下新闻中提取政治实体（国家、组织、地区）。返回 JSON 格式：

{json.dumps(articles_data, ensure_ascii=False, indent=2)}

请提取新闻中出现的政治实体，返回格式：
{{
  "entities": [
    {{
      "name": "实体名称",
      "type": "country/organization/region",
      "description": "实体简述",
      "article_ids": [相关文章ID列表],
      "related_people": ["相关人物"]
    }}
  ]
}}

注意：
1. type 只能是: country（国家）、organization（组织）、region（地区）
2. country 包括：Iran, Israel, China, USA 等
3. organization 包括：UN, NATO, EU, WHO 等国际组织
4. region 包括：Hong Kong, Vatican, Taiwan 等地区
5. 只返回 JSON，不要其他内容"""

        try:
            response = self.llm_client._call_api(
                messages=[{"role": "user", "content": prompt}],
                max_tokens=3000,
            )
            
            response = response.strip()
            if response.startswith("```json"):
                response = response[7:]
            if response.startswith("```"):
                response = response[3:]
            if response.endswith("```"):
                response = response[:-3]
            response = response.strip()
            
            result = json.loads(response)
            return result.get("entities", [])
            
        except json.JSONDecodeError as e:
            logger.error(f"JSON 解析失败: {e}, 响应内容: {response[:200] if response else 'empty'}")
            return []
        except Exception as e:
            logger.error(f"提取政治实体失败: {e}")
            return []
    
    def extract_political_entities_parallel(
        self, 
        articles: list[tuple], 
        workers: int = MAX_WORKERS
    ) -> tuple[list[dict], list[int]]:
        """提取政治实体（支持串行或并行）
        
        Args:
            articles: 文章列表
            workers: 并行数
            
        Returns:
            (政治实体列表, 处理的文章ID列表)
        """
        batches = self.batch_articles_by_tokens(articles)
        all_entities = []
        all_article_ids = []
        
        if workers <= 1:
            for i, batch in enumerate(batches):
                try:
                    entities = self._extract_political_entities_from_batch(batch)
                    all_entities.extend(entities)
                    for article in batch:
                        all_article_ids.append(article[0])
                    logger.info(f"批次 {i+1}/{len(batches)} 完成")
                except Exception as e:
                    logger.error(f"串行提取政治实体失败 (批次 {i+1}): {e}")
        else:
            with ThreadPoolExecutor(max_workers=workers) as executor:
                future_to_batch = {
                    executor.submit(self._extract_political_entities_from_batch, batch): batch
                    for batch in batches
                }
                
                for future in as_completed(future_to_batch):
                    batch = future_to_batch[future]
                    try:
                        entities = future.result()
                        all_entities.extend(entities)
                        for article in batch:
                            all_article_ids.append(article[0])
                    except Exception as e:
                        logger.error(f"并行提取政治实体失败: {e}")
        
        return all_entities, all_article_ids
    
    def generate_political_entity_page(
        self, 
        entity: dict, 
        articles: list[tuple]
    ) -> str:
        """生成政治实体 Markdown 页面
        
        Args:
            entity: 政治实体信息
            articles: 相关文章列表
            
        Returns:
            Markdown 内容
        """
        name = entity.get("name", "未知实体")
        entity_type = entity.get("type", "country")
        description = entity.get("description", "")
        related_people = entity.get("related_people", [])
        
        # 类型映射
        type_names = {
            "country": "国家",
            "organization": "组织",
            "region": "地区",
        }
        type_display = type_names.get(entity_type, entity_type)
        
        content = f"""# {name}

## 类型

{type_display}

## 简介

{description}

"""
        # 添加相关人物章节
        if related_people:
            content += """## 相关人物

"""
            for person_name in related_people:
                content += f"- [[{person_name}]]\n"
            content += "\n"
        
        content += """## 相关新闻

"""
        for article in articles:
            if len(article) >= 5:
                article_id, title, _, published_at, source_name = article[:5]
            else:
                article_id, title, _, published_at = article[:4]
                source_name = "未知来源"
            date_str = published_at[:10] if published_at else "未知日期"
            source_display = f" [{source_name}]" if source_name and source_name != "未知来源" else ""
            content += f"- [{title}](article://{article_id}){source_display} - {date_str}\n"
        
        # 生成时间线
        content += f"""
## 时间线

"""
        timeline_entries = self._generate_timeline_entries(name, articles)
        for entry in timeline_entries:
            content += f"- **{entry['date']}**: {entry['summary']}\n"
        
        content += f"""
---
*生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}*
"""
        
        return content
    
    def _generate_timeline_entries(
        self, 
        entity_name: str, 
        articles: list[tuple]
    ) -> list[dict]:
        """生成时间线条目
        
        Args:
            entity_name: 实体名称
            articles: 相关文章列表
            
        Returns:
            时间线条目列表
        """
        entries = []
        
        for article in sorted(articles, key=lambda x: x[3] or ""):
            if len(article) >= 5:
                article_id, title, content, published_at, source_name = article[:5]
            else:
                article_id, title, content, published_at = article[:4]
                source_name = "未知来源"
            
            date_str = published_at[:10] if published_at else "未知日期"
            
            # 使用 LLM 生成实体相关总结
            summary = self._summarize_entity_action(entity_name, title, content or "")
            
            entries.append({
                "date": date_str,
                "summary": summary,
                "article_id": article_id,
            })
        
        return entries
    
    def _summarize_entity_action(
        self, 
        entity_name: str, 
        title: str, 
        content: str
    ) -> str:
        """使用 LLM 总结实体在新闻中的行为
        
        Args:
            entity_name: 实体名称
            title: 新闻标题
            content: 新闻内容
            
        Returns:
            实体行为总结
        """
        if not content or not content.strip():
            return title
        
        content_limited = content[:2000] if len(content) > 2000 else content
        
        prompt = f"""请基于以下新闻，用一句话总结 {entity_name} 在这个事件中的角色或行为。

新闻标题：{title}
新闻内容：
{content_limited}

要求：
1. 只返回一句话的总结
2. 如果新闻中没有提到 {entity_name} 的具体行为，返回"在该事件中被提及"
3. 不要返回其他内容"""

        try:
            response = self.llm_client._call_api(
                messages=[{"role": "user", "content": prompt}],
                max_tokens=200,
            )
            summary = response.strip()
            return summary if summary else title
        except Exception as e:
            logger.warning(f"LLM 时间线总结失败: {e}，使用标题")
            return title
    
    def save_political_entity_page(self, name: str, content: str) -> Path:
        """保存政治实体页面
        
        Args:
            name: 实体名称
            content: Markdown 内容
            
        Returns:
            文件路径
        """
        safe_name = "".join(c for c in name if c.isalnum() or c in " -_").strip()
        file_path = self.political_entities_dir / f"{safe_name}.md"
        file_path.write_text(content, encoding="utf-8")
        return file_path
    
    def mark_articles_processed(self, article_ids: list[int]) -> None:
        """标记文章为已处理
        
        Args:
            article_ids: 文章ID列表
        """
        if not article_ids:
            return
        
        with get_connection() as conn:
            placeholders = ",".join("?" * len(article_ids))
            conn.execute(
                f"UPDATE articles SET wiki_processed = 1 WHERE id IN ({placeholders})",
                article_ids
            )
            conn.commit()
    
    def get_articles_by_ids(self, article_ids: list[int]) -> list[tuple]:
        """根据 ID 获取文章（包含来源信息）
        
        Args:
            article_ids: 文章ID列表
            
        Returns:
            文章列表 [(id, title, content, published_at, source_name), ...]
        """
        if not article_ids:
            return []
        
        with get_connection() as conn:
            placeholders = ",".join("?" * len(article_ids))
            cursor = conn.execute(
                f"""SELECT a.id, a.title, a.content, a.published_at, f.title as source_name
                    FROM articles a
                    LEFT JOIN feeds f ON a.feed_id = f.id
                    WHERE a.id IN ({placeholders})""",
                article_ids
            )
            return cursor.fetchall()
    
    def get_all_political_entity_files(self) -> list[Path]:
        """获取所有政治实体文件
        
        Returns:
            文件路径列表
        """
        if not self.political_entities_dir.exists():
            return []
        return list(self.political_entities_dir.glob("*.md"))
    
    def parse_political_entity_page(self, file_path: Path) -> PoliticalEntityInfo:
        """解析政治实体页面
        
        Args:
            file_path: 文件路径
            
        Returns:
            政治实体信息
        """
        import re
        
        content = file_path.read_text(encoding="utf-8")
        
        # 提取名称
        name_match = re.search(r'^# (.+)$', content, re.MULTILINE)
        name = name_match.group(1).strip() if name_match else file_path.stem
        
        # 提取类型
        type_match = re.search(r'## 类型\s*\n(.+?)(?=\n##|\Z)', content, re.DOTALL)
        type_str = type_match.group(1).strip() if type_match else "country"
        
        # 映射类型
        type_map = {
            "国家": "country",
            "组织": "organization",
            "地区": "region",
        }
        entity_type = PoliticalEntityType(type_map.get(type_str, type_str))
        
        # 提取简介
        desc_match = re.search(r'## 简介\s*\n(.+?)(?=\n##|\Z)', content, re.DOTALL)
        description = desc_match.group(1).strip() if desc_match else ""
        
        # 提取相关人物
        people_match = re.search(r'## 相关人物\s*\n(.+?)(?=\n##|\Z)', content, re.DOTALL)
        related_people = []
        if people_match:
            related_people = re.findall(r'- \[\[([^\]]+)\]\]', people_match.group(1))
        
        # 提取文章ID
        article_ids = [int(id) for id in re.findall(r'\[article://(\d+)\]', content)]
        
        return PoliticalEntityInfo(
            name=name,
            entity_type=entity_type,
            description=description,
            related_people=related_people,
            article_ids=article_ids,
        )
