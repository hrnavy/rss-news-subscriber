"""Wiki 健康检查服务模块

提供 Wiki 人物页面的健康检查功能，包括：
- 名字合并检查：检测重复的人物名称
- 时间线质量检查：改进时间线内容
- 新闻来源检查：补充新闻来源信息
- 非人物实体检测：识别错误分类的实体
"""

import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Optional

from rss_news.db.connection import get_connection
from rss_news.models.health_check import (
    CheckStatus,
    CheckType,
    EntityType,
    FullHealthReport,
    HealthCheckResult,
    NameMergeSuggestion,
    NonPersonEntity,
    PersonWikiInfo,
    TimelineImprovement,
)
from rss_news.services.llm_client import get_llm_client
from rss_news.services.name_mapping_service import NameMappingService

logger = logging.getLogger(__name__)

# 常见国家名列表
COMMON_COUNTRIES = {
    "iran", "israel", "bahrain", "kuwait", "china", "usa", "russia", "ukraine",
    "japan", "korea", "india", "pakistan", "saudi", "uae", "qatar", "turkey",
    "egypt", "syria", "lebanon", "jordan", "iraq", "afghanistan", "yemen",
    "以色列", "伊朗", "中国", "美国", "俄罗斯", "乌克兰", "日本", "韩国",
}

# 常见尊称/头衔
HONORIFICS = {
    "ayatollah", "president", "prime minister", "king", "queen", "prince",
    "princess", "sheikh", "emir", "sultan", "pope", "cardinal", "bishop",
    "dr.", "prof.", "mr.", "mrs.", "ms.", "miss", "sir", "lord", "lady",
    "总统", "总理", "国王", "女王", "王子", "公主", "教皇", "主教",
}

# 常见别名映射
KNOWN_ALIASES = {
    "ye": "kanye west",
    "kanye west ye": "kanye west",
}


def levenshtein_distance(s1: str, s2: str) -> int:
    """计算两个字符串的 Levenshtein 距离
    
    Args:
        s1: 第一个字符串
        s2: 第二个字符串
        
    Returns:
        编辑距离
    """
    if len(s1) < len(s2):
        return levenshtein_distance(s2, s1)
    
    if len(s2) == 0:
        return len(s1)
    
    previous_row = range(len(s2) + 1)
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row
    
    return previous_row[-1]


def string_similarity(s1: str, s2: str) -> float:
    """计算两个字符串的相似度 (0.0-1.0)
    
    基于 Levenshtein 距离计算相似度。
    
    Args:
        s1: 第一个字符串
        s2: 第二个字符串
        
    Returns:
        相似度分数
    """
    if not s1 or not s2:
        return 0.0
    
    s1_lower = s1.lower().strip()
    s2_lower = s2.lower().strip()
    
    if s1_lower == s2_lower:
        return 1.0
    
    max_len = max(len(s1_lower), len(s2_lower))
    distance = levenshtein_distance(s1_lower, s2_lower)
    
    return 1.0 - (distance / max_len)


def normalize_name(name: str) -> str:
    """规范化名字
    
    移除尊称、多余空格等。
    
    Args:
        name: 原始名字
        
    Returns:
        规范化后的名字
    """
    name = name.strip()
    
    # 移除常见尊称
    name_lower = name.lower()
    for honorific in HONORIFICS:
        if name_lower.startswith(honorific.lower() + " "):
            name = name[len(honorific) + 1:]
            break
        if name_lower.startswith(honorific):
            name = name[len(honorific):]
            break
    
    return name.strip()


def is_chinese_name(name: str) -> bool:
    """判断是否为中文名
    
    Args:
        name: 名字
        
    Returns:
        是否为中文名
    """
    chinese_count = sum(1 for c in name if '\u4e00' <= c <= '\u9fff')
    return chinese_count > len(name) * 0.5


def is_mixed_chinese_english_name(name: str) -> bool:
    """判断是否为中英文混合名
    
    例如: "克里斯蒂娜科赫 Christina Koch"
    
    Args:
        name: 名字
        
    Returns:
        是否为中英文混合名
    """
    chinese_count = sum(1 for c in name if '\u4e00' <= c <= '\u9fff')
    alpha_count = sum(1 for c in name if c.isalpha() and not ('\u4e00' <= c <= '\u9fff'))
    total_alpha = chinese_count + alpha_count
    
    # 同时包含中文和英文字符，且占比都不太低
    if total_alpha == 0:
        return False
    chinese_ratio = chinese_count / total_alpha
    return 0.2 < chinese_ratio < 0.8


def extract_chinese_english_parts(name: str) -> tuple[str, str]:
    """从中英文混合名中提取中文部分和英文部分
    
    Args:
        name: 混合名，如 "克里斯蒂娜科赫 Christina Koch"
        
    Returns:
        (中文部分, 英文部分)
    """
    chinese_chars = []
    english_chars = []
    
    current_english = []
    for c in name:
        if '\u4e00' <= c <= '\u9fff':
            chinese_chars.append(c)
            if current_english:
                english_chars.append(''.join(current_english))
                current_english = []
        elif c.isalpha():
            current_english.append(c)
        elif current_english:
            english_chars.append(''.join(current_english))
            current_english = []
    
    if current_english:
        english_chars.append(''.join(current_english))
    
    chinese_part = ''.join(chinese_chars)
    english_part = ' '.join(english_chars)
    
    return chinese_part, english_part


class WikiHealthCheckService:
    """Wiki 健康检查服务
    
    提供全面的 Wiki 人物页面健康检查功能。
    """
    
    def __init__(self, wiki_dir: Path | None = None):
        """初始化服务
        
        Args:
            wiki_dir: Wiki 目录路径
        """
        self.wiki_dir = wiki_dir or Path("wiki")
        self.people_dir = self.wiki_dir / "people"
        self.llm_client = get_llm_client()
        self.name_mapping_service = NameMappingService()
    
    def run_full_check(
        self,
        check_types: list[CheckType] | None = None,
    ) -> FullHealthReport:
        """运行完整健康检查
        
        Args:
            check_types: 要检查的类型列表，None 表示全部检查
            
        Returns:
            完整健康检查报告
        """
        if check_types is None:
            check_types = [
                CheckType.NAMES,
                CheckType.POLITICAL_ENTITIES,
                CheckType.TIMELINE,
                CheckType.SOURCE,
                CheckType.NON_PERSON,
            ]
        
        report = FullHealthReport(wiki_dir=str(self.wiki_dir))
        
        for check_type in check_types:
            logger.info(f"运行检查: {check_type.value}")
            
            if check_type == CheckType.NAMES:
                result = self.check_names()
            elif check_type == CheckType.POLITICAL_ENTITIES:
                result = self.check_political_entities()
            elif check_type == CheckType.TIMELINE:
                result = self.check_timeline()
            elif check_type == CheckType.SOURCE:
                result = self.check_source()
            elif check_type == CheckType.NON_PERSON:
                result = self.check_non_person_entities()
            else:
                continue
            
            report.add_result(result)
        
        report.calculate_summary()
        return report
    
    def get_all_person_files(self) -> list[Path]:
        """获取所有人物 Wiki 文件
        
        Returns:
            文件路径列表
        """
        if not self.people_dir.exists():
            return []
        return list(self.people_dir.glob("*.md"))
    
    def parse_person_page(self, file_path: Path) -> PersonWikiInfo:
        """解析人物 Wiki 页面
        
        Args:
            file_path: 文件路径
            
        Returns:
            人物信息
        """
        content = file_path.read_text(encoding="utf-8")
        
        # 提取名字（第一个标题）
        name_match = re.search(r'^#\s+(.+)$', content, re.MULTILINE)
        name = name_match.group(1).strip() if name_match else file_path.stem
        
        # 提取简介
        desc_match = re.search(r'## 简介\s*\n\n(.+?)(?=\n##|\Z)', content, re.DOTALL)
        description = desc_match.group(1).strip() if desc_match else ""
        
        # 提取相关人物
        related_people = []
        related_match = re.search(r'## 相关人物\s*\n(.+?)(?=\n##|\Z)', content, re.DOTALL)
        if related_match:
            related_people = re.findall(r'\[\[([^\]]+)\]\]', related_match.group(1))
        
        # 提取文章 ID
        article_ids = []
        # 匹配 [标题](article://ID) 格式
        article_pattern = r'\[.*?\]\(article://(\d+)\)'
        article_ids = [int(aid) for aid in re.findall(article_pattern, content)]
        
        # 提取时间线
        timeline = []
        timeline_match = re.search(r'## 时间线\s*\n(.+?)(?=\n---|\Z)', content, re.DOTALL)
        if timeline_match:
            timeline_text = timeline_match.group(1)
            # 匹配时间线条目: - **日期**: 内容
            timeline_pattern = r'-\s*\*\*([^*]+)\*\*:\s*(.+)$'
            for match in re.finditer(timeline_pattern, timeline_text, re.MULTILINE):
                timeline.append({
                    "date": match.group(1).strip(),
                    "content": match.group(2).strip(),
                })
        
        return PersonWikiInfo(
            file_path=str(file_path),
            name=name,
            description=description,
            related_people=related_people,
            article_ids=article_ids,
            timeline=timeline,
        )
    
    def check_names(self) -> HealthCheckResult:
        """检查名字合并问题
        
        Returns:
            检查结果
        """
        result = HealthCheckResult(
            check_type=CheckType.NAMES,
            status=CheckStatus.PASS,
            message="名字检查完成",
        )
        
        person_files = self.get_all_person_files()
        if not person_files:
            result.message = "没有找到人物页面"
            return result
        
        # 解析所有人物信息
        persons = [self.parse_person_page(f) for f in person_files]
        
        # 构建名字到文章 ID 的映射
        name_to_article_ids = {p.name: set(p.article_ids) for p in persons}
        
        # 检测潜在重复
        potential_duplicates = self._find_potential_duplicates(list(name_to_article_ids.keys()), name_to_article_ids)
        
        if not potential_duplicates:
            result.message = "没有发现名字重复问题"
            return result
        
        # 初始化映射服务
        self.name_mapping_service.initialize()
        
        # 使用 LLM 分析每对潜在重复
        suggestions = []
        for dup_group in potential_duplicates:
            # 检查映射库中是否已确认
            already_confirmed = False
            for name in dup_group:
                mapping = self.name_mapping_service.get_mapping(name)
                if mapping and mapping.verified:
                    # 已确认的映射，跳过
                    already_confirmed = True
                    logger.info(f"跳过已确认的映射: {name} -> {mapping.primary_name}")
                    break
            
            if already_confirmed:
                continue
            
            # 获取相关文章全文
            article_ids = []
            for person in persons:
                if person.name in dup_group:
                    article_ids.extend(person.article_ids)
            
            articles_data = self._get_articles_full_content(list(set(article_ids)))
            
            if not articles_data:
                continue
            
            # 使用 NameMappingService 分析并添加映射
            mapping = self.name_mapping_service.analyze_and_add(
                list(dup_group),
                list(set(article_ids)),
                auto_confirm_threshold=0.85,
            )
            
            if mapping:
                # 转换为建议格式
                suggestion = NameMergeSuggestion(
                    names=list(dup_group),
                    is_same_person=True,
                    confidence=mapping.confidence,
                    reason=mapping.evidence[0] if mapping.evidence else "LLM 分析确认",
                    evidence=mapping.evidence,
                    suggested_primary_name=mapping.primary_name,
                    article_ids=mapping.article_ids,
                )
                suggestions.append(suggestion.to_dict())
                result.issues.append({
                    "names": list(dup_group),
                    "type": "potential_duplicate",
                    "verified": mapping.verified,
                })
        
        result.suggestions = suggestions
        if suggestions:
            result.status = CheckStatus.WARNING
            result.message = f"发现 {len(suggestions)} 组可能重复的名字"
        
        return result
    
    def _find_potential_duplicates(
        self,
        names: list[str],
        name_to_article_ids: dict[str, set[int]] | None = None,
        threshold: float = 0.85,
    ) -> list[list[str]]:
        """查找潜在重复的名字组
        
        Args:
            names: 名字列表
            name_to_article_ids: 名字到文章 ID 的映射
            threshold: 相似度阈值
            
        Returns:
            潜在重复的名字组列表
        """
        groups = []
        used = set()
        
        # 预处理：解析所有名字的类型和组成部分
        name_info = {}
        for name in names:
            info = {
                "is_chinese": is_chinese_name(name),
                "is_english": not is_chinese_name(name) and not is_mixed_chinese_english_name(name),
                "is_mixed": is_mixed_chinese_english_name(name),
                "chinese_part": "",
                "english_part": "",
            }
            if info["is_mixed"]:
                info["chinese_part"], info["english_part"] = extract_chinese_english_parts(name)
            name_info[name] = info
        
        for i, name1 in enumerate(names):
            if name1 in used:
                continue
            
            group = [name1]
            info1 = name_info[name1]
            
            for j, name2 in enumerate(names):
                if i != j and name2 not in used:
                    info2 = name_info[name2]
                    sim = self._calculate_name_similarity(
                        name1, name2, info1, info2, name_to_article_ids
                    )
                    
                    # 检查已知别名
                    n1_lower = name1.lower()
                    n2_lower = name2.lower()
                    if n1_lower in KNOWN_ALIASES or n2_lower in KNOWN_ALIASES:
                        if KNOWN_ALIASES.get(n1_lower) == n2_lower or KNOWN_ALIASES.get(n2_lower) == n1_lower:
                            sim = 0.95
                    
                    if sim >= threshold:
                        group.append(name2)
                        used.add(name2)
            
            if len(group) > 1:
                groups.append(group)
                used.add(name1)
        
        return groups
    
    def _calculate_name_similarity(
        self,
        name1: str,
        name2: str,
        info1: dict,
        info2: dict,
        name_to_article_ids: dict[str, set[int]] | None = None,
    ) -> float:
        """计算两个名字的相似度，考虑中英文混合情况
        
        Args:
            name1: 第一个名字
            name2: 第二一个名字
            info1: 第一个名字的解析信息
            info2: 第二个名字的解析信息
            name_to_article_ids: 名字到文章 ID 的映射
            
        Returns:
            相似度分数 (0.0-1.0)
        """
        import re
        
        # 预处理：移除括号内容进行比较
        def remove_parentheses(name: str) -> tuple[str, str]:
            """移除名字中的括号内容
            
            Returns:
                (清理后的名字, 括号内容)
            """
            match = re.search(r'^(.+?)\s*\((.+)\)$', name)
            if match:
                return match.group(1).strip(), match.group(2).strip()
            return name, ""
        
        clean_name1, paren1 = remove_parentheses(name1)
        clean_name2, paren2 = remove_parentheses(name2)
        
        # 如果清理后的名字完全相同，返回高相似度
        if clean_name1.lower() == clean_name2.lower():
            return 0.95
        
        # 基础字符串相似度（使用清理后的名字）
        base_sim = string_similarity(clean_name1, clean_name2)
        
        # 如果一个名字包含另一个（如 "Kanye West" 和 "Kanye West Ye"）
        if clean_name1 in clean_name2 or clean_name2 in clean_name1:
            # 计算包含关系的相似度
            shorter = min(len(clean_name1), len(clean_name2))
            longer = max(len(clean_name1), len(clean_name2))
            containment_sim = shorter / longer
            if containment_sim > 0.8:
                return max(base_sim, 0.85)
        
        # 检查是否一个名字是另一个名字的一部分（如 "Leo XIV" 和 "Pope Leo XIV"）
        # 移除常见前缀后比较
        common_prefixes = ["Pope ", "President ", "King ", "Queen ", "Prince ", "Princess ", "Dr. ", "Mr. ", "Mrs. ", "Ms. "]
        for prefix in common_prefixes:
            if clean_name1.startswith(prefix):
                stripped1 = clean_name1[len(prefix):]
                if stripped1.lower() == clean_name2.lower():
                    return 0.95
                stripped_sim = string_similarity(stripped1, clean_name2)
                if stripped_sim > 0.8:
                    return max(base_sim, stripped_sim)
            if clean_name2.startswith(prefix):
                stripped2 = clean_name2[len(prefix):]
                if stripped2.lower() == clean_name1.lower():
                    return 0.95
                stripped_sim = string_similarity(clean_name1, stripped2)
                if stripped_sim > 0.8:
                    return max(base_sim, stripped_sim)
        
        # 检查是否有共同的文章 ID
        has_common_articles = False
        if name_to_article_ids:
            ids1 = name_to_article_ids.get(name1, set())
            ids2 = name_to_article_ids.get(name2, set())
            has_common_articles = bool(ids1 & ids2)
        
        # 情况1: 两个都是普通名字（纯中文或纯英文）
        if not info1["is_mixed"] and not info2["is_mixed"]:
            # 如果一个是纯中文，一个是纯英文，需要检查是否有共同文章
            if info1["is_chinese"] and info2["is_english"]:
                # 有共同文章，很可能是同一人
                if has_common_articles:
                    return 0.88
                # 检查是否是音译对应（如 "特朗普" 和 "Trump"）
                if self._is_transliteration_pair(name1, name2):
                    return 0.86
                return base_sim
            if info1["is_english"] and info2["is_chinese"]:
                if has_common_articles:
                    return 0.88
                if self._is_transliteration_pair(name2, name1):
                    return 0.86
                return base_sim
            return base_sim
        
        # 情况2: name1 是混合名，name2 是普通名
        if info1["is_mixed"] and not info2["is_mixed"]:
            # 混合名的英文部分与纯英文名比较
            if info2["is_english"] and info1["english_part"]:
                eng_sim = string_similarity(info1["english_part"], clean_name2)
                if eng_sim > 0.7:
                    return max(base_sim, eng_sim)
            # 混合名的中文部分与纯中文名比较
            if info2["is_chinese"] and info1["chinese_part"]:
                cn_sim = string_similarity(info1["chinese_part"], name2)
                if cn_sim > 0.7:
                    return max(base_sim, cn_sim)
            return base_sim
        
        # 情况3: name2 是混合名，name1 是普通名
        if info2["is_mixed"] and not info1["is_mixed"]:
            if info1["is_english"] and info2["english_part"]:
                # 移除英文部分的前缀
                english_part = info2["english_part"]
                for prefix in common_prefixes:
                    if english_part.startswith(prefix):
                        english_part = english_part[len(prefix):]
                        break
                
                # 检查是否完全匹配
                if clean_name1.lower() == english_part.lower():
                    return 0.95
                
                eng_sim = string_similarity(clean_name1, english_part)
                if eng_sim > 0.7:
                    return max(base_sim, eng_sim)
            if info1["is_chinese"] and info2["chinese_part"]:
                cn_sim = string_similarity(name1, info2["chinese_part"])
                if cn_sim > 0.7:
                    return max(base_sim, cn_sim)
            return base_sim
        
        # 情况4: 两个都是混合名
        if info1["is_mixed"] and info2["is_mixed"]:
            # 比较英文部分
            if info1["english_part"] and info2["english_part"]:
                eng_sim = string_similarity(info1["english_part"], info2["english_part"])
                if eng_sim > 0.7:
                    return max(base_sim, eng_sim)
            # 比较中文部分
            if info1["chinese_part"] and info2["chinese_part"]:
                cn_sim = string_similarity(info1["chinese_part"], info2["chinese_part"])
                if cn_sim > 0.7:
                    return max(base_sim, cn_sim)
        
        return base_sim
    
    def _is_transliteration_pair(self, chinese_name: str, english_name: str) -> bool:
        """检查中文名是否是英文名的音译
        
        Args:
            chinese_name: 中文名
            english_name: 英文名
            
        Returns:
            是否可能是音译对应
        """
        # 常见英文名到中文音译的映射（姓氏/名字）
        TRANSLITERATIONS = {
            "trump": ["特朗普", "川普"],
            "biden": ["拜登"],
            "obama": ["奥巴马"],
            "putin": ["普京"],
            "xi jinping": ["习近平"],
            "jinping": ["近平"],
            "zelensky": ["泽连斯基"],
            "zelenskyy": ["泽连斯基"],
            "musk": ["马斯克"],
            "kim jong-un": ["金正恩"],
            "jong-un": ["正恩"],
            "erdogan": ["埃尔多安"],
            "netanyahu": ["内塔尼亚胡"],
            "macron": ["马克龙"],
            "merkel": ["默克尔"],
            "johnson": ["约翰逊"],
            "sunak": ["苏纳克"],
            "modi": ["莫迪"],
            "abe": ["安倍"],
            "khamenei": ["哈梅内伊"],
            "kissinger": ["基辛格"],
            "pope francis": ["方济各", "教皇方济各"],
            "leo xiv": ["莱奥十四世", "教皇莱奥十四世"],
            "christina koch": ["克里斯蒂娜·科赫", "克里斯蒂娜科赫"],
            "judd frieling": ["朱德·弗利林", "朱德弗利林"],
            "koch": ["科赫"],
            "frieling": ["弗利林"],
        }
        
        eng_lower = english_name.lower().strip()
        cn_name = chinese_name.strip()
        
        # 检查英文名是否在映射表中
        for eng_key, cn_variants in TRANSLITERATIONS.items():
            # 检查英文名是否包含关键词，或关键词是否是英文名的一部分
            eng_words = eng_lower.split()
            key_words = eng_key.split()
            
            # 如果英文名包含关键词
            if eng_key in eng_lower:
                for cn_variant in cn_variants:
                    if cn_variant in cn_name or cn_name in cn_variant:
                        return True
            
            # 如果英文名的某个单词匹配关键词
            for word in eng_words:
                if word == eng_key or eng_key in word or word in eng_key:
                    for cn_variant in cn_variants:
                        if cn_variant in cn_name or cn_name in cn_variant:
                            return True
        
        return False
    
    def _get_articles_full_content(
        self,
        article_ids: list[int],
    ) -> list[dict]:
        """获取文章全文内容
        
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
                f"""SELECT a.id, a.title, a.content, a.link, f.title as source_name
                    FROM articles a
                    LEFT JOIN feeds f ON a.feed_id = f.id
                    WHERE a.id IN ({placeholders})""",
                article_ids
            )
            rows = cursor.fetchall()
            
            return [
                {
                    "id": row[0],
                    "title": row[1],
                    "content": row[2] or "",
                    "link": row[3],
                    "source": row[4] or "未知来源",
                }
                for row in rows
            ]
    
    def _llm_analyze_name_merge(
        self,
        names: list[str],
        articles: list[dict],
    ) -> Optional[NameMergeSuggestion]:
        """使用 LLM 分析名字是否应该合并
        
        Args:
            names: 名字列表
            articles: 相关文章全文
            
        Returns:
            合并建议
        """
        # 构建文章内容字符串
        articles_text = ""
        for article in articles[:5]:  # 限制文章数量
            articles_text += f"\n---\n文章 ID: {article['id']}\n"
            articles_text += f"标题: {article['title']}\n"
            articles_text += f"内容: {article['content'][:2000]}\n"  # 限制单篇长度
        
        prompt = f"""你是一个实体识别专家。请基于以下新闻全文，判断这些名字是否指向同一个人。

名字列表：{', '.join(names)}

相关新闻全文：
{articles_text}

请回答以下问题，以 JSON 格式返回：
{{
  "is_same_person": true/false,
  "confidence": 0.0-1.0,
  "reason": "基于新闻原文的理由，必须引用具体内容",
  "evidence": ["证据1", "证据2"],
  "suggested_primary_name": "建议使用的主名称"
}}

重要：
1. 不要臆测，必须基于新闻原文给出理由
2. 如果新闻中没有足够信息判断，confidence 设为较低值
3. 只返回 JSON，不要其他内容"""

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
            
            # 尝试多种方式提取 JSON
            # 方法1: 查找第一个 { 和最后一个 }
            json_start = response.find('{')
            json_end = response.rfind('}')
            if json_start != -1 and json_end != -1:
                json_str = response[json_start:json_end+1]
                try:
                    data = json.loads(json_str)
                except json.JSONDecodeError:
                    # 方法2: 尝试修复常见的 JSON 格式问题
                    # 替换单引号为双引号
                    json_str = json_str.replace("'", '"')
                    # 尝试解析
                    data = json.loads(json_str)
            else:
                raise ValueError("无法在响应中找到 JSON 对象")
            
            return NameMergeSuggestion(
                names=names,
                is_same_person=data.get("is_same_person", False),
                confidence=data.get("confidence", 0.0),
                reason=data.get("reason", ""),
                evidence=data.get("evidence", []),
                suggested_primary_name=data.get("suggested_primary_name", names[0]),
                article_ids=[a["id"] for a in articles],
            )
            
        except json.JSONDecodeError as e:
            logger.error(f"JSON 解析失败: {e}")
            return None
        except Exception as e:
            logger.error(f"LLM 分析失败: {e}")
            return None
    
    def check_timeline(self) -> HealthCheckResult:
        """检查时间线质量问题
        
        Returns:
            检查结果
        """
        result = HealthCheckResult(
            check_type=CheckType.TIMELINE,
            status=CheckStatus.PASS,
            message="时间线检查完成",
        )
        
        person_files = self.get_all_person_files()
        if not person_files:
            result.message = "没有找到人物页面"
            return result
        
        improvements = []
        
        for file_path in person_files:
            person = self.parse_person_page(file_path)
            
            for entry in person.timeline:
                # 检查时间线是否只是新闻标题
                if self._is_timeline_just_title(entry["content"], person.article_ids):
                    # 获取对应文章全文
                    article_id = self._find_article_by_title(entry["content"], person.article_ids)
                    if article_id:
                        articles = self._get_articles_full_content([article_id])
                        if articles:
                            improved = self._llm_improve_timeline(
                                person.name,
                                entry["date"],
                                entry["content"],
                                articles[0],
                            )
                            if improved:
                                improvements.append(improved.to_dict())
                                result.issues.append({
                                    "person": person.name,
                                    "date": entry["date"],
                                    "type": "timeline_is_title",
                                })
        
        result.suggestions = improvements
        if improvements:
            result.status = CheckStatus.WARNING
            result.message = f"发现 {len(improvements)} 条时间线需要改进"
        
        return result
    
    def _is_timeline_just_title(self, content: str, article_ids: list[int]) -> bool:
        """判断时间线内容是否只是新闻标题
        
        Args:
            content: 时间线内容
            article_ids: 相关文章 ID
            
        Returns:
            是否只是标题
        """
        if not article_ids:
            return False
        
        with get_connection() as conn:
            placeholders = ",".join("?" * len(article_ids))
            cursor = conn.execute(
                f"SELECT title FROM articles WHERE id IN ({placeholders})",
                article_ids
            )
            titles = [row[0] for row in cursor.fetchall()]
            
            # 如果内容与某个标题完全匹配或高度相似
            content_lower = content.lower().strip()
            for title in titles:
                if content_lower == title.lower().strip():
                    return True
                if string_similarity(content, title) > 0.9:
                    return True
        
        return False
    
    def _find_article_by_title(self, title: str, article_ids: list[int]) -> Optional[int]:
        """根据标题查找文章 ID
        
        Args:
            title: 标题
            article_ids: 候选文章 ID
            
        Returns:
            文章 ID 或 None
        """
        if not article_ids:
            return None
        
        with get_connection() as conn:
            placeholders = ",".join("?" * len(article_ids))
            cursor = conn.execute(
                f"SELECT id, title FROM articles WHERE id IN ({placeholders})",
                article_ids
            )
            
            for row in cursor.fetchall():
                if string_similarity(title, row[1]) > 0.9:
                    return row[0]
        
        return None
    
    def _llm_improve_timeline(
        self,
        person_name: str,
        date: str,
        original: str,
        article: dict,
    ) -> Optional[TimelineImprovement]:
        """使用 LLM 改进时间线内容
        
        Args:
            person_name: 人物名称
            date: 日期
            original: 原始内容
            article: 文章全文
            
        Returns:
            时间线改进建议
        """
        prompt = f"""请基于以下新闻全文，总结 {person_name} 在这个事件中做了什么。

新闻标题：{article['title']}
新闻全文：
{article['content'][:3000]}

要求：
1. 用一句话总结 {person_name} 的行为或表态
2. 不要只复述新闻标题
3. 必须基于新闻原文
4. 如果新闻中没有提到 {person_name} 的具体行为，说明"在该事件中被提及"

请直接返回总结内容，不要其他说明。"""

        try:
            response = self.llm_client._call_api(
                messages=[{"role": "user", "content": prompt}],
                max_tokens=200,
            )
            
            improved = response.strip()
            if improved and improved != original:
                return TimelineImprovement(
                    person_name=person_name,
                    date=date,
                    original=original,
                    improved=improved,
                    article_id=article["id"],
                    source=article.get("source", ""),
                )
            
        except Exception as e:
            logger.error(f"LLM 时间线改进失败: {e}")
        
        return None
    
    def check_source(self) -> HealthCheckResult:
        """检查新闻来源信息
        
        Returns:
            检查结果
        """
        result = HealthCheckResult(
            check_type=CheckType.SOURCE,
            status=CheckStatus.PASS,
            message="新闻来源检查完成",
        )
        
        person_files = self.get_all_person_files()
        if not person_files:
            result.message = "没有找到人物页面"
            return result
        
        missing_source_count = 0
        
        for file_path in person_files:
            person = self.parse_person_page(file_path)
            
            # 检查文章是否有来源信息
            if person.article_ids:
                articles = self._get_articles_full_content(person.article_ids)
                for article in articles:
                    if article["source"] == "未知来源" or not article["source"]:
                        missing_source_count += 1
                        result.issues.append({
                            "person": person.name,
                            "article_id": article["id"],
                            "type": "missing_source",
                        })
        
        if missing_source_count > 0:
            result.status = CheckStatus.WARNING
            result.message = f"发现 {missing_source_count} 篇文章缺少来源信息"
        
        return result
    
    def check_non_person_entities(self) -> HealthCheckResult:
        """检查非人物实体
        
        Returns:
            检查结果
        """
        result = HealthCheckResult(
            check_type=CheckType.NON_PERSON,
            status=CheckStatus.PASS,
            message="非人物实体检查完成",
        )
        
        person_files = self.get_all_person_files()
        if not person_files:
            result.message = "没有找到人物页面"
            return result
        
        non_persons = []
        
        for file_path in person_files:
            person = self.parse_person_page(file_path)
            name_lower = person.name.lower().strip()
            
            # 检查是否是国家名（完全匹配）
            for country in COMMON_COUNTRIES:
                if name_lower == country:
                    non_persons.append(NonPersonEntity(
                        name=person.name,
                        entity_type=EntityType.COUNTRY,
                        suggested_action="移至事件页面或删除",
                        reason=f"名称是国家名 '{country}'",
                        article_ids=person.article_ids,
                    ))
                    break
            
            # 检查是否是组织名（包含 PBC, Inc, Corp 等）
            org_patterns = ["pbc", "inc", "corp", "ltd", "llc", "company"]
            for pattern in org_patterns:
                if pattern in name_lower:
                    non_persons.append(NonPersonEntity(
                        name=person.name,
                        entity_type=EntityType.ORGANIZATION,
                        suggested_action="移至组织页面或删除",
                        reason=f"名称包含组织标识 '{pattern}'",
                        article_ids=person.article_ids,
                    ))
                    break
        
        if non_persons:
            result.status = CheckStatus.WARNING
            result.message = f"发现 {len(non_persons)} 个非人物实体"
            result.issues = [np.to_dict() for np in non_persons]
        
        return result
    
    def check_political_entities(self) -> HealthCheckResult:
        """检查政治实体
        
        Returns:
            检查结果
        """
        result = HealthCheckResult(
            check_type=CheckType.POLITICAL_ENTITIES,
            status=CheckStatus.PASS,
            message="政治实体检查完成",
        )
        
        # 检测政治实体合并候选
        merge_candidates = self.detect_political_entity_merge_candidates()
        
        if merge_candidates:
            result.status = CheckStatus.WARNING
            result.message = f"发现 {len(merge_candidates)} 组可能重复的政治实体"
            result.issues = [
                {
                    "names": cand["variant_names"],
                    "type": "potential_duplicate",
                    "verified": False,
                }
                for cand in merge_candidates
            ]
            result.suggestions_count = len(merge_candidates)
        
        return result
    
    def detect_political_entity_merge_candidates(self) -> list[dict]:
        """检测所有潜在的政治实体重复页面
        
        使用多种策略检测：
        1. 相似度检测（拼写变体）
        2. 中英文混合检测
        3. 文章重叠检测
        
        Returns:
            合并建议列表
        """
        from rss_news.services.political_entity_service import PoliticalEntityService
        
        service = PoliticalEntityService()
        
        # 获取所有政治实体文件
        entity_files = service.get_all_political_entity_files()
        if not entity_files:
            return []
        
        # 解析所有政治实体信息
        entities = [service.parse_political_entity_page(f) for f in entity_files]
        
        # 构建名字到文件和文章的映射
        name_to_file = {e.name: f for e, f in zip(entities, entity_files)}
        name_to_article_ids = {e.name: set(e.article_ids) for e in entities}
        
        candidates = []
        candidate_id = 0
        used = set()
        
        # 使用相似度检测
        names = [e.name for e in entities]
        name_info = {}
        for name in names:
            info = {
                "is_chinese": is_chinese_name(name),
                "is_english": not is_chinese_name(name) and not is_mixed_chinese_english_name(name),
                "is_mixed": is_mixed_chinese_english_name(name),
                "chinese_part": "",
                "english_part": "",
            }
            if info["is_mixed"]:
                info["chinese_part"], info["english_part"] = extract_chinese_english_parts(name)
            name_info[name] = info
        
        for i, name1 in enumerate(names):
            if name1 in used:
                continue
            
            group = [name1]
            info1 = name_info[name1]
            
            for j, name2 in enumerate(names):
                if i != j and name2 not in used:
                    info2 = name_info[name2]
                    sim = self._calculate_name_similarity(
                        name1, name2, info1, info2, name_to_article_ids
                    )
                    
                    if sim >= 0.75:
                        group.append(name2)
                        used.add(name2)
            
            if len(group) > 1:
                used.add(name1)
                
                # 确定主名称（优先英文名）
                primary = self._select_primary_name(group, name_info)
                
                # 收集文章ID
                article_ids = []
                for n in group:
                    article_ids.extend(name_to_article_ids.get(n, []))
                
                candidate_id += 1
                candidates.append({
                    "id": f"political_entity_merge_{candidate_id}",
                    "primary_name": primary,
                    "variant_names": group,
                    "confidence": 0.8,
                    "evidence": ["政治实体名字相似度检测"],
                    "article_ids": list(set(article_ids)),
                    "files": [name_to_file[n].name for n in group],
                })
        
        return candidates
    
    def detect_all_merge_candidates(self) -> list[dict]:
        """检测所有潜在的重复页面
        
        使用多种策略检测：
        1. 映射库检测（已知变体）
        2. 相似度检测（拼写变体）
        3. 中英文混合检测
        4. 文章重叠检测
        
        Returns:
            合并建议列表，每项包含：
            - id: 建议ID
            - primary_name: 建议的主名称
            - variant_names: 变体名称列表
            - confidence: 置信度
            - evidence: 证据
            - article_ids: 相关文章ID
            - files: 相关文件列表
        """
        # 初始化映射服务
        self.name_mapping_service.initialize()
        
        # 扫描所有人物文件
        person_files = self.get_all_person_files()
        if not person_files:
            return []
        
        # 解析所有人物信息
        persons = [self.parse_person_page(f) for f in person_files]
        
        # 构建名字到文件和文章的映射
        name_to_file = {p.name: f for p, f in zip(persons, person_files)}
        name_to_article_ids = {p.name: set(p.article_ids) for p in persons}
        
        candidates = []
        candidate_id = 0
        
        # 策略1: 使用映射库检测已知变体
        mapping_candidates = self._detect_by_mapping(persons, name_to_file)
        for cand in mapping_candidates:
            candidate_id += 1
            cand["id"] = f"merge_{candidate_id}"
            cand["detection_type"] = "mapping"
            candidates.append(cand)
        
        # 策略2: 使用相似度检测拼写变体
        similarity_candidates = self._detect_by_similarity(
            persons, name_to_file, name_to_article_ids, threshold=0.75
        )
        for cand in similarity_candidates:
            # 检查是否已经在 mapping_candidates 中
            if not self._is_duplicate_candidate(cand, candidates):
                candidate_id += 1
                cand["id"] = f"merge_{candidate_id}"
                cand["detection_type"] = "similarity"
                candidates.append(cand)
        
        # 策略3: 使用文章重叠检测
        overlap_candidates = self._detect_by_article_overlap(persons, name_to_file, name_to_article_ids)
        for cand in overlap_candidates:
            if not self._is_duplicate_candidate(cand, candidates):
                candidate_id += 1
                cand["id"] = f"merge_{candidate_id}"
                cand["detection_type"] = "article_overlap"
                candidates.append(cand)
        
        return candidates
    
    def _detect_by_mapping(
        self,
        persons: list[PersonWikiInfo],
        name_to_file: dict[str, Path],
    ) -> list[dict]:
        """使用映射库检测已知变体
        
        Args:
            persons: 人物信息列表
            name_to_file: 名字到文件的映射
            
        Returns:
            合并建议列表
        """
        candidates = []
        
        # 按主名称分组
        primary_to_variants: dict[str, list[str]] = {}
        
        for person in persons:
            name = person.name
            
            # 查询映射库
            mapping = self.name_mapping_service.get_mapping(name)
            if mapping:
                primary = mapping.primary_name
                if primary not in primary_to_variants:
                    primary_to_variants[primary] = []
                if name not in primary_to_variants[primary]:
                    primary_to_variants[primary].append(name)
            else:
                # 检查是否是主名称
                variants = self.name_mapping_service.get_all_variants(name)
                if variants:
                    if name not in primary_to_variants:
                        primary_to_variants[name] = [name]
                    for v in variants:
                        if v not in primary_to_variants[name]:
                            primary_to_variants[name].append(v)
        
        # 只保留有多个文件的组
        for primary, names in primary_to_variants.items():
            # 检查实际存在的文件
            existing_names = [n for n in names if n in name_to_file]
            if len(existing_names) > 1:
                candidates.append({
                    "primary_name": primary,
                    "variant_names": existing_names,
                    "confidence": 1.0,
                    "evidence": ["映射库中已确认的对应关系"],
                    "article_ids": [],
                    "files": [name_to_file[n].name for n in existing_names],
                })
        
        return candidates
    
    def _detect_by_similarity(
        self,
        persons: list[PersonWikiInfo],
        name_to_file: dict[str, Path],
        name_to_article_ids: dict[str, set[int]],
        threshold: float = 0.75,
    ) -> list[dict]:
        """使用相似度检测拼写变体
        
        Args:
            persons: 人物信息列表
            name_to_file: 名字到文件的映射
            name_to_article_ids: 名字到文章ID的映射
            threshold: 相似度阈值
            
        Returns:
            合并建议列表
        """
        candidates = []
        names = [p.name for p in persons]
        used = set()
        
        # 预处理名字信息
        name_info = {}
        for name in names:
            info = {
                "is_chinese": is_chinese_name(name),
                "is_english": not is_chinese_name(name) and not is_mixed_chinese_english_name(name),
                "is_mixed": is_mixed_chinese_english_name(name),
                "chinese_part": "",
                "english_part": "",
            }
            if info["is_mixed"]:
                info["chinese_part"], info["english_part"] = extract_chinese_english_parts(name)
            name_info[name] = info
        
        for i, name1 in enumerate(names):
            if name1 in used:
                continue
            
            group = [name1]
            info1 = name_info[name1]
            
            for j, name2 in enumerate(names):
                if i != j and name2 not in used:
                    info2 = name_info[name2]
                    sim = self._calculate_name_similarity(
                        name1, name2, info1, info2, name_to_article_ids
                    )
                    
                    if sim >= threshold:
                        group.append(name2)
                        used.add(name2)
            
            if len(group) > 1:
                used.add(name1)
                
                # 确定主名称（优先英文名）
                primary = self._select_primary_name(group, name_info)
                
                # 收集文章ID
                article_ids = []
                for n in group:
                    article_ids.extend(name_to_article_ids.get(n, []))
                
                candidates.append({
                    "primary_name": primary,
                    "variant_names": group,
                    "confidence": 0.8,  # 相似度检测的置信度较低
                    "evidence": [f"名字相似度检测，相似度 >= {threshold}"],
                    "article_ids": list(set(article_ids)),
                    "files": [name_to_file[n].name for n in group],
                })
        
        return candidates
    
    def _detect_by_article_overlap(
        self,
        persons: list[PersonWikiInfo],
        name_to_file: dict[str, Path],
        name_to_article_ids: dict[str, set[int]],
        min_overlap: int = 3,
    ) -> list[dict]:
        """使用文章重叠检测潜在重复
        
        Args:
            persons: 人物信息列表
            name_to_file: 名字到文件的映射
            name_to_article_ids: 名字到文章ID的映射
            min_overlap: 最小重叠文章数
            
        Returns:
            合并建议列表
        """
        candidates = []
        names = [p.name for p in persons]
        used = set()
        
        for i, name1 in enumerate(names):
            if name1 in used:
                continue
            
            ids1 = name_to_article_ids.get(name1, set())
            group = [name1]
            
            for j, name2 in enumerate(names):
                if i != j and name2 not in used:
                    ids2 = name_to_article_ids.get(name2, set())
                    overlap = ids1 & ids2
                    
                    if len(overlap) >= min_overlap:
                        group.append(name2)
                        used.add(name2)
            
            if len(group) > 1:
                used.add(name1)
                
                # 确定主名称
                primary = self._select_primary_name(group, {})
                
                # 收集文章ID
                article_ids = []
                for n in group:
                    article_ids.extend(name_to_article_ids.get(n, []))
                
                candidates.append({
                    "primary_name": primary,
                    "variant_names": group,
                    "confidence": 0.7,  # 文章重叠检测的置信度更低
                    "evidence": [f"共享 {min_overlap}+ 篇相同文章"],
                    "article_ids": list(set(article_ids)),
                    "files": [name_to_file[n].name for n in group],
                })
        
        return candidates
    
    def _is_duplicate_candidate(self, new_cand: dict, existing: list[dict]) -> bool:
        """检查是否是重复的候选
        
        Args:
            new_cand: 新候选
            existing: 已存在的候选列表
            
        Returns:
            是否重复
        """
        new_names = set(new_cand["variant_names"])
        for cand in existing:
            existing_names = set(cand["variant_names"])
            # 如果有超过一半的名字重叠，认为是重复
            overlap = len(new_names & existing_names)
            if overlap > len(new_names) * 0.5:
                return True
        return False
    
    def _select_primary_name(self, names: list[str], name_info: dict) -> str:
        """选择主名称
        
        优先级：
        1. 纯英文名称
        2. 更长的名称
        3. 第一个名称
        
        Args:
            names: 名称列表
            name_info: 名称信息字典
            
        Returns:
            主名称
        """
        # 优先选择纯英文名称
        for name in names:
            info = name_info.get(name, {})
            if info.get("is_english"):
                return name
        
        # 其次选择更长的名称
        sorted_names = sorted(names, key=len, reverse=True)
        return sorted_names[0]
    
    def fix_issues(
        self,
        report: FullHealthReport,
        dry_run: bool = True,
    ) -> dict:
        """修复检测到的问题
        
        Args:
            report: 健康检查报告
            dry_run: 是否只预览不执行
            
        Returns:
            修复结果
        """
        fixes = {
            "merged": [],
            "timeline_improved": [],
            "non_person_moved": [],
        }
        
        if dry_run:
            return fixes
        
        # TODO: 实现实际修复逻辑
        
        return fixes
