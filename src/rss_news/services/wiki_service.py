"""Wiki 知识库服务模块

通过 LLM 从新闻中提取人物和事件，生成结构化的 Markdown 知识库。
支持全文处理、并行调用和关联关系提取。
"""

import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Optional

from rss_news.db.connection import get_connection
from rss_news.services.llm_client import get_llm_client
from rss_news.services.name_mapping_service import NameMappingService

logger = logging.getLogger(__name__)

WIKI_DIR = Path("wiki")

# LLM 配置
MAX_CONTEXT_TOKENS = 22296  # 用户上下文窗口大小
RESERVED_TOKENS = 2000  # 预留给 prompt 和输出的 tokens
MAX_WORKERS = 1  # 默认串行处理
MAX_ARTICLE_CHARS = 4000  # 单篇文章最大字符数（减少以防止超时）
BATCH_MAX_TOKENS = 8000  # 每批最大 token 数（减少以防止超时）


class WikiService:
    """Wiki 知识库服务
    
    管理人物页面、事件页面的生成和更新。
    支持全文处理、并行调用和关联关系提取。
    """
    
    def __init__(self, wiki_dir: Path | None = None):
        self.wiki_dir = wiki_dir or WIKI_DIR
        self.people_dir = self.wiki_dir / "people"
        self.political_entities_dir = self.wiki_dir / "political_entities"
        self.llm_client = get_llm_client()
        self.name_mapping_service = NameMappingService()
    
    def init_wiki(self) -> bool:
        """初始化 Wiki 目录结构
        
        Returns:
            True 如果初始化成功
        """
        try:
            self.wiki_dir.mkdir(parents=True, exist_ok=True)
            self.people_dir.mkdir(exist_ok=True)
            self.political_entities_dir.mkdir(exist_ok=True)
            
            config_file = self.wiki_dir / "config.yaml"
            if not config_file.exists():
                config_file.write_text(f"""# Wiki 配置
created_at: {datetime.now().isoformat()}
last_updated: {datetime.now().isoformat()}
stats:
  people_count: 0
  events_count: 0
  articles_processed: 0
""")
            
            logger.info(f"Wiki 初始化完成: {self.wiki_dir}")
            return True
            
        except Exception as e:
            logger.error(f"Wiki 初始化失败: {e}")
            return False
    
    def estimate_tokens(self, text: str) -> int:
        """估算文本的 token 数量
        
        中文约 1.5 字/token，英文约 4 字符/token。
        使用混合估算策略。
        
        Args:
            text: 输入文本
            
        Returns:
            估算的 token 数量
        """
        if not text:
            return 0
        
        # 统计中文字符
        chinese_chars = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
        # 非中文字符
        other_chars = len(text) - chinese_chars
        
        # 中文 tokens + 英文 tokens
        tokens = int(chinese_chars / 1.5) + int(other_chars / 4)
        return max(tokens, 1)
    
    def batch_articles_by_tokens(
        self, 
        articles: list[tuple], 
        max_tokens: int = BATCH_MAX_TOKENS
    ) -> list[list[tuple]]:
        """按 token 数量将文章分批
        
        Args:
            articles: 文章列表 [(id, title, content, published_at), ...]
            max_tokens: 每批最大 token 数
            
        Returns:
            分批后的文章列表
        """
        batches = []
        current_batch = []
        current_tokens = 0
        
        for article in articles:
            article_id, title, content, published_at = article
            # 使用全文内容，如果为空则使用标题，并限制最大长度
            text = content if content and len(content.strip()) > 0 else title
            if len(text) > MAX_ARTICLE_CHARS:
                text = text[:MAX_ARTICLE_CHARS] + "..."
            article_tokens = self.estimate_tokens(text)
            
            # 如果单篇文章超过限制，单独成批
            if article_tokens > max_tokens:
                if current_batch:
                    batches.append(current_batch)
                    current_batch = []
                    current_tokens = 0
                batches.append([article])
                continue
            
            # 检查是否需要新开一批
            if current_tokens + article_tokens > max_tokens:
                if current_batch:
                    batches.append(current_batch)
                current_batch = [article]
                current_tokens = article_tokens
            else:
                current_batch.append(article)
                current_tokens += article_tokens
        
        if current_batch:
            batches.append(current_batch)
        
        return batches
    
    def get_unprocessed_articles(self, limit: int = 100) -> list[tuple]:
        """获取未处理的文章
        
        Args:
            limit: 数量限制
            
        Returns:
            文章列表 [(id, title, content, published_at), ...]
        """
        with get_connection() as conn:
            cursor = conn.execute(
                """SELECT id, title, content, published_at 
                   FROM articles 
                   WHERE wiki_processed = 0 OR wiki_processed IS NULL
                   ORDER BY published_at DESC 
                   LIMIT ?""",
                (limit,)
            )
            return cursor.fetchall()
    
    def get_all_articles(self, limit: int = 100) -> list[tuple]:
        """获取所有文章（包括已处理）
        
        Args:
            limit: 数量限制
            
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
    
    def mark_articles_processed(self, article_ids: list[int]) -> bool:
        """标记文章为已处理
        
        Args:
            article_ids: 文章 ID 列表
            
        Returns:
            True 如果成功
        """
        if not article_ids:
            return True
        
        try:
            with get_connection() as conn:
                placeholders = ",".join("?" * len(article_ids))
                conn.execute(
                    f"UPDATE articles SET wiki_processed = 1 WHERE id IN ({placeholders})",
                    article_ids
                )
                conn.commit()
            return True
        except Exception as e:
            logger.error(f"标记文章已处理失败: {e}")
            return False
    
    def reset_processed_status(self) -> int:
        """重置所有文章的处理状态
        
        Returns:
            重置的文章数量
        """
        try:
            with get_connection() as conn:
                cursor = conn.execute("UPDATE articles SET wiki_processed = 0")
                conn.commit()
                return cursor.rowcount
        except Exception as e:
            logger.error(f"重置处理状态失败: {e}")
            return 0
    
    def _extract_people_from_batch(self, batch: list[tuple]) -> list[dict]:
        """从一批文章中提取人物（单次 LLM 调用）
        
        Args:
            batch: 文章列表 [(id, title, content, published_at), ...]
            
        Returns:
            人物信息列表
        """
        # 构建文章数据，使用全文或标题，并限制长度
        articles_data = []
        for article in batch:
            article_id, title, content, _ = article
            text = content if content and len(content.strip()) > 0 else title
            # 限制单篇文章最大长度
            if len(text) > MAX_ARTICLE_CHARS:
                text = text[:MAX_ARTICLE_CHARS] + "..."
            articles_data.append({
                "id": article_id,
                "title": title,
                "content": text
            })
        
        prompt = f"""从以下新闻中提取关键人物及其关系。返回 JSON 格式：

{json.dumps(articles_data, ensure_ascii=False, indent=2)}

请提取新闻中出现的重要人物，返回格式：
{{
  "people": [
    {{
      "name": "人物名称",
      "description": "简短描述（一句话）",
      "article_ids": [相关文章ID列表],
      "related_people": ["相关人物名称列表"]
    }}
  ]
}}

注意：
1. related_people 列出与该人物相关的其他人物
2. 只返回 JSON，不要其他内容"""

        try:
            response = self.llm_client._call_api(
                messages=[{"role": "user", "content": prompt}],
                max_tokens=3000,
            )
            
            # 清理响应内容，移除可能的 markdown 代码块标记
            response = response.strip()
            if response.startswith("```json"):
                response = response[7:]
            if response.startswith("```"):
                response = response[3:]
            if response.endswith("```"):
                response = response[:-3]
            response = response.strip()
            
            result = json.loads(response)
            return result.get("people", [])
            
        except json.JSONDecodeError as e:
            logger.error(f"JSON 解析失败: {e}, 响应内容: {response[:200] if response else 'empty'}")
            return []
        except Exception as e:
            logger.error(f"提取人物失败: {e}")
            return []
    
    def extract_people_parallel(
        self, 
        articles: list[tuple], 
        workers: int = MAX_WORKERS
    ) -> tuple[list[dict], list[int]]:
        """提取人物（支持串行或并行）
        
        Args:
            articles: 文章列表
            workers: 并行数，1 为串行
            
        Returns:
            (人物列表, 处理的文章ID列表)
        """
        batches = self.batch_articles_by_tokens(articles)
        all_people = []
        all_article_ids = []
        
        if workers <= 1:
            # 串行处理
            for i, batch in enumerate(batches):
                try:
                    people = self._extract_people_from_batch(batch)
                    all_people.extend(people)
                    for article in batch:
                        all_article_ids.append(article[0])
                    logger.info(f"批次 {i+1}/{len(batches)} 完成")
                except Exception as e:
                    logger.error(f"串行提取人物失败 (批次 {i+1}): {e}")
        else:
            # 并行处理
            with ThreadPoolExecutor(max_workers=workers) as executor:
                future_to_batch = {
                    executor.submit(self._extract_people_from_batch, batch): batch
                    for batch in batches
                }
                
                for future in as_completed(future_to_batch):
                    batch = future_to_batch[future]
                    try:
                        people = future.result()
                        all_people.extend(people)
                        for article in batch:
                            all_article_ids.append(article[0])
                    except Exception as e:
                        logger.error(f"并行提取人物失败: {e}")
        
        return all_people, all_article_ids
    
    def generate_person_page(self, person: dict, articles: list[tuple]) -> str:
        """生成人物 Markdown 页面
        
        Args:
            person: 人物信息
            articles: 相关文章列表 [(id, title, content, published_at, source_name), ...]
            
        Returns:
            Markdown 内容
        """
        name = person.get("name", "未知人物")
        description = person.get("description", "")
        related_people = person.get("related_people", [])
        
        content = f"""# {name}

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
            # 兼容新旧格式：5 元组或 4 元组
            if len(article) >= 5:
                article_id, title, _, published_at, source_name = article[:5]
            else:
                article_id, title, _, published_at = article[:4]
                source_name = "未知来源"
            date_str = published_at[:10] if published_at else "未知日期"
            source_display = f" [{source_name}]" if source_name and source_name != "未知来源" else ""
            content += f"- [{title}](article://{article_id}){source_display} - {date_str}\n"
        
        # 生成时间线（使用 LLM 总结）
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
    
    def _generate_timeline_entries(self, person_name: str, articles: list[tuple]) -> list[dict]:
        """生成时间线条目（使用 LLM 总结人物行为）
        
        Args:
            person_name: 人物名称
            articles: 相关文章列表
            
        Returns:
            时间线条目列表
        """
        entries = []
        
        for article in sorted(articles, key=lambda x: x[3] or ""):
            # 兼容新旧格式
            if len(article) >= 5:
                article_id, title, content, published_at, source_name = article[:5]
            else:
                article_id, title, content, published_at = article[:4]
                source_name = "未知来源"
            
            date_str = published_at[:10] if published_at else "未知日期"
            
            # 使用 LLM 生成人物行为总结
            summary = self._summarize_person_action(person_name, title, content or "")
            
            entries.append({
                "date": date_str,
                "summary": summary,
                "article_id": article_id,
            })
        
        return entries
    
    def _summarize_person_action(self, person_name: str, title: str, content: str) -> str:
        """使用 LLM 总结人物在新闻中的行为
        
        Args:
            person_name: 人物名称
            title: 新闻标题
            content: 新闻内容
            
        Returns:
            人物行为总结
        """
        # 如果内容为空，直接返回标题
        if not content or not content.strip():
            return title
        
        # 限制内容长度
        content_limited = content[:2000] if len(content) > 2000 else content
        
        prompt = f"""请基于以下新闻，用一句话总结 {person_name} 在这个事件中的行为或表态。

新闻标题：{title}
新闻内容：
{content_limited}

要求：
1. 只返回一句话的总结
2. 如果新闻中没有提到 {person_name} 的具体行为，返回"在该事件中被提及"
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
    
    def save_person_page(self, name: str, content: str) -> Path:
        """保存人物页面
        
        会自动查询人名映射库，使用规范化的名称保存页面。
        
        Args:
            name: 人物名称
            content: Markdown 内容
            
        Returns:
            文件路径
        """
        # 初始化映射服务
        self.name_mapping_service.initialize()
        
        # 规范化名字
        normalized_name = self.name_mapping_service.normalize_name(name)
        
        # 如果名字被规范化了，检查是否已有该页面
        if normalized_name != name:
            logger.info(f"名字规范化: {name} -> {normalized_name}")
            
            # 检查是否已有该页面
            safe_normalized = "".join(c for c in normalized_name if c.isalnum() or c in " -_").strip()
            existing_path = self.people_dir / f"{safe_normalized}.md"
            
            if existing_path.exists():
                # 合并内容到现有页面
                logger.info(f"合并到现有页面: {existing_path}")
                existing_content = existing_path.read_text(encoding="utf-8")
                merged_content = self._merge_person_pages(existing_content, content, normalized_name)
                existing_path.write_text(merged_content, encoding="utf-8")
                return existing_path
            
            name = normalized_name
        
        safe_name = "".join(c for c in name if c.isalnum() or c in " -_").strip()
        file_path = self.people_dir / f"{safe_name}.md"
        file_path.write_text(content, encoding="utf-8")
        return file_path
    
    def _merge_person_pages(self, existing: str, new: str, name: str) -> str:
        """合并两个人物页面
        
        Args:
            existing: 现有页面内容
            new: 新页面内容
            name: 人物名称
            
        Returns:
            合并后的内容
        """
        import re
        
        # 提取现有页面的相关新闻
        existing_news_match = re.search(r'## 相关新闻\s*\n(.+?)(?=\n##|\Z)', existing, re.DOTALL)
        existing_news = existing_news_match.group(1) if existing_news_match else ""
        
        # 提取新页面的相关新闻
        new_news_match = re.search(r'## 相关新闻\s*\n(.+?)(?=\n##|\Z)', new, re.DOTALL)
        new_news = new_news_match.group(1) if new_news_match else ""
        
        # 合并新闻（去重）
        existing_links = set(re.findall(r'\[article://(\d+)\]', existing_news))
        new_links = set(re.findall(r'\[article://(\d+)\]', new_news))
        
        # 如果有新的新闻，追加到现有页面
        if new_links - existing_links:
            # 找到相关新闻章节的位置
            news_section_match = re.search(r'(## 相关新闻\s*\n)', existing)
            if news_section_match:
                insert_pos = news_section_match.end()
                merged = existing[:insert_pos] + new_news + existing[insert_pos:]
                return merged
        
        return existing
    
    def _get_articles_by_ids(self, article_ids: list[int]) -> list[tuple]:
        """根据 ID 获取文章（包含来源信息）
        
        Args:
            article_ids: 文章 ID 列表
            
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
    
    def get_wiki_status(self) -> dict:
        """获取 Wiki 状态
        
        Returns:
            状态信息
        """
        people_count = len(list(self.people_dir.glob("*.md"))) if self.people_dir.exists() else 0
        political_entities_count = len(list(self.political_entities_dir.glob("*.md"))) if self.political_entities_dir.exists() else 0
        
        with get_connection() as conn:
            cursor = conn.execute("SELECT COUNT(*) FROM articles")
            total_articles = cursor.fetchone()[0]
            
            cursor = conn.execute("SELECT COUNT(*) FROM articles WHERE wiki_processed = 1")
            processed_articles = cursor.fetchone()[0]
        
        return {
            "wiki_dir": str(self.wiki_dir),
            "people_count": people_count,
            "political_entities_count": political_entities_count,
            "total_articles": total_articles,
            "processed_articles": processed_articles,
            "unprocessed_articles": total_articles - processed_articles,
            "initialized": self.wiki_dir.exists(),
        }
    
    def merge_people_pages(self, dry_run: bool = True) -> dict:
        """合并重复的人物页面
        
        根据名字映射库规范化文件名，合并重复的页面内容。
        
        Args:
            dry_run: 是否只预览不执行
            
        Returns:
            合并结果
        """
        import re
        
        # 初始化映射服务
        self.name_mapping_service.initialize()
        
        # 扫描所有人物文件
        if not self.people_dir.exists():
            return {"error": "人物目录不存在"}
        
        files = list(self.people_dir.glob("*.md"))
        
        # 按规范化名称分组
        name_groups: dict[str, list[Path]] = {}
        
        for file_path in files:
            # 从文件名提取名字（去掉 .md 后缀）
            file_name = file_path.stem
            
            # 规范化名字
            normalized_name = self.name_mapping_service.normalize_name(file_name)
            
            if normalized_name not in name_groups:
                name_groups[normalized_name] = []
            name_groups[normalized_name].append(file_path)
        
        # 找出需要合并的组（多于一个文件的）
        merge_groups = {
            name: files 
            for name, files in name_groups.items() 
            if len(files) > 1
        }
        
        if not merge_groups:
            return {"merged": 0, "message": "没有需要合并的页面"}
        
        results = {
            "merged": 0,
            "deleted": 0,
            "groups": [],
            "dry_run": dry_run,
        }
        
        for normalized_name, file_paths in merge_groups.items():
            group_result = {
                "name": normalized_name,
                "files": [f.name for f in file_paths],
                "actions": [],
            }
            
            if dry_run:
                # 只预览
                results["merged"] += 1
                results["deleted"] += len(file_paths) - 1
                results["groups"].append(group_result)
                continue
            
            # 确定主文件（优先选择英文名称的）
            primary_file = None
            for fp in file_paths:
                stem = fp.stem
                # 优先选择纯英文文件名
                if all(c.isascii() or c in " -_" for c in stem):
                    primary_file = fp
                    break
            
            if not primary_file:
                primary_file = file_paths[0]
            
            # 读取主文件内容
            primary_content = primary_file.read_text(encoding="utf-8")
            
            # 合并其他文件的内容
            for fp in file_paths:
                if fp == primary_file:
                    continue
                
                other_content = fp.read_text(encoding="utf-8")
                
                # 提取相关新闻链接
                other_news_match = re.search(r'## 相关新闻\s*\n(.+?)(?=\n##|\Z)', other_content, re.DOTALL)
                if other_news_match:
                    other_news = other_news_match.group(1)
                    
                    # 提取文章 ID
                    other_article_ids = set(re.findall(r'\[article://(\d+)\]', other_news))
                    primary_article_ids = set(re.findall(r'\[article://(\d+)\]', primary_content))
                    
                    # 如果有新的文章，追加到主文件
                    if other_article_ids - primary_article_ids:
                        news_section_match = re.search(r'(## 相关新闻\s*\n)', primary_content)
                        if news_section_match:
                            insert_pos = news_section_match.end()
                            primary_content = primary_content[:insert_pos] + other_news + primary_content[insert_pos:]
                            group_result["actions"].append(f"合并 {fp.name} 的新闻到 {primary_file.name}")
                
                # 删除重复文件
                fp.unlink()
                group_result["actions"].append(f"删除 {fp.name}")
                results["deleted"] += 1
            
            # 更新主文件内容（确保标题是规范化名称）
            primary_content = re.sub(
                r'^# .+$',
                f'# {normalized_name}',
                primary_content,
                count=1,
                flags=re.MULTILINE
            )
            
            # 重命名主文件（如果需要）
            safe_name = "".join(c for c in normalized_name if c.isalnum() or c in " -_").strip()
            new_path = self.people_dir / f"{safe_name}.md"
            
            if primary_file != new_path:
                primary_file.rename(new_path)
                group_result["actions"].append(f"重命名 {primary_file.name} -> {new_path.name}")
            
            # 保存合并后的内容
            new_path.write_text(primary_content, encoding="utf-8")
            
            results["merged"] += 1
            results["groups"].append(group_result)
        
        return results
