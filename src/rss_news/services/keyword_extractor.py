"""关键词提取模块"""

from .llm_client import LLMClient, get_llm_client


class KeywordExtractor:
    """关键词提取器，使用 LLM 从新闻文章中提取关键词"""

    def __init__(self, llm_client: LLMClient | None = None):
        """
        初始化关键词提取器

        Args:
            llm_client: LLM 客户端实例，如果为 None 则使用全局实例
        """
        self.client = llm_client or get_llm_client()

    async def extract(
        self,
        title: str,
        content: str,
        min_keywords: int = 3,
        max_keywords: int = 5,
    ) -> str:
        """
        从新闻文章中提取关键词

        Args:
            title: 文章标题
            content: 文章内容
            min_keywords: 最小关键词数量
            max_keywords: 最大关键词数量

        Returns:
            关键词字符串，用逗号分隔
        """
        # 构建系统提示词
        system_prompt = (
            "你是一个专业的关键词提取助手。"
            "你的任务是从新闻文章中提取最能代表文章主题的关键词。"
            f"关键词数量应在 {min_keywords}-{max_keywords} 个之间。"
            "关键词应该具有代表性和区分度，能够准确概括文章的核心内容。"
        )

        # 构建用户提示词
        user_prompt = f"""请从以下新闻文章中提取关键词：

标题：{title}

内容：
{content}

要求：
1. 提取 {min_keywords}-{max_keywords} 个关键词
2. 关键词应该能够准确概括文章的核心内容
3. 优先选择实体名词、专业术语和重要概念
4. 关键词之间用中文逗号（，）分隔
5. 不要输出编号或其他格式，只输出关键词

示例输出：
人工智能，机器学习，深度学习，神经网络

请输出关键词："""

        # 调用 LLM 提取关键词
        keywords = await self.client.call_llm(
            prompt=user_prompt,
            system_prompt=system_prompt,
            temperature=0.3,  # 使用较低温度以获得稳定的关键词
            max_tokens=100,  # 关键词通常较短
        )

        # 清理关键词格式
        keywords = keywords.strip()

        # 统一分隔符为中文逗号
        keywords = keywords.replace(",", "，")
        keywords = keywords.replace("、", "，")

        # 移除可能的编号和多余空格
        keywords_list = []
        for keyword in keywords.split("，"):
            keyword = keyword.strip()
            # 移除编号（如 "1."、"1、"等）
            if keyword and not keyword.isdigit():
                # 移除开头的数字和标点
                while keyword and (keyword[0].isdigit() or keyword[0] in ".、:："):
                    keyword = keyword[1:].strip()
                if keyword:
                    keywords_list.append(keyword)

        # 限制关键词数量
        if len(keywords_list) > max_keywords:
            keywords_list = keywords_list[:max_keywords]

        # 如果关键词数量不足，返回提取到的关键词
        if len(keywords_list) < min_keywords and len(keywords_list) > 0:
            pass  # 保持现有关键词

        return "，".join(keywords_list)

    async def extract_as_list(
        self,
        title: str,
        content: str,
        min_keywords: int = 3,
        max_keywords: int = 5,
    ) -> list[str]:
        """
        从新闻文章中提取关键词，返回列表形式

        Args:
            title: 文章标题
            content: 文章内容
            min_keywords: 最小关键词数量
            max_keywords: 最大关键词数量

        Returns:
            关键词列表
        """
        keywords_str = await self.extract(
            title=title,
            content=content,
            min_keywords=min_keywords,
            max_keywords=max_keywords,
        )

        # 分割并清理关键词
        keywords_list = []
        for keyword in keywords_str.split("，"):
            keyword = keyword.strip()
            if keyword:
                keywords_list.append(keyword)

        return keywords_list

    async def batch_extract(
        self,
        articles: list[dict[str, str]],
        min_keywords: int = 3,
        max_keywords: int = 5,
    ) -> list[str]:
        """
        批量提取关键词

        Args:
            articles: 文章列表，每篇文章包含 title 和 content 字段
            min_keywords: 最小关键词数量
            max_keywords: 最大关键词数量

        Returns:
            关键词字符串列表，与输入文章顺序对应
        """
        import asyncio

        tasks = [
            self.extract(
                title=article["title"],
                content=article["content"],
                min_keywords=min_keywords,
                max_keywords=max_keywords,
            )
            for article in articles
        ]

        keywords_list = await asyncio.gather(*tasks, return_exceptions=True)

        # 处理可能的异常
        result = []
        for keywords in keywords_list:
            if isinstance(keywords, Exception):
                result.append("")
            else:
                result.append(keywords)

        return result

    async def extract_with_weights(
        self,
        title: str,
        content: str,
        min_keywords: int = 3,
        max_keywords: int = 5,
    ) -> dict[str, float]:
        """
        提取关键词并返回权重

        Args:
            title: 文章标题
            content: 文章内容
            min_keywords: 最小关键词数量
            max_keywords: 最大关键词数量

        Returns:
            字典，键为关键词，值为权重（0-1）
        """
        system_prompt = (
            "你是一个专业的关键词提取助手。"
            "你的任务是从新闻文章中提取关键词，并评估每个关键词的重要性。"
            f"关键词数量应在 {min_keywords}-{max_keywords} 个之间。"
        )

        user_prompt = f"""请从以下新闻文章中提取关键词并评估重要性：

标题：{title}

内容：
{content}

要求：
1. 提取 {min_keywords}-{max_keywords} 个关键词
2. 为每个关键词给出一个 0-100 的重要性评分
3. 按照以下格式输出，每行一个关键词：
   关键词:评分

示例输出：
人工智能:90
机器学习:85
深度学习:80

请输出关键词和评分："""

        response = await self.client.call_llm(
            prompt=user_prompt,
            system_prompt=system_prompt,
            temperature=0.3,
            max_tokens=150,
        )

        # 解析响应，提取关键词和权重
        keyword_weights: dict[str, float] = {}
        for line in response.strip().split("\n"):
            if ":" in line:
                parts = line.split(":")
                if len(parts) == 2:
                    keyword = parts[0].strip()
                    try:
                        weight = float(parts[1].strip())
                        # 归一化为 0-1 范围
                        keyword_weights[keyword] = weight / 100.0
                    except ValueError:
                        continue

        return keyword_weights


# 全局关键词提取器实例
_extractor_instance: KeywordExtractor | None = None


def get_keyword_extractor(llm_client: LLMClient | None = None) -> KeywordExtractor:
    """
    获取关键词提取器实例（单例模式）

    Args:
        llm_client: LLM 客户端实例

    Returns:
        KeywordExtractor 实例
    """
    global _extractor_instance
    if _extractor_instance is None:
        _extractor_instance = KeywordExtractor(llm_client)
    return _extractor_instance
