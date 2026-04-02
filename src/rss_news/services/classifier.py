"""新闻分类模块"""

from .llm_client import LLMClient, get_llm_client


# 预定义分类列表
NEWS_CATEGORIES = [
    "科技",
    "财经",
    "体育",
    "娱乐",
    "政治",
    "社会",
    "教育",
    "健康",
    "文化",
    "军事",
    "国际",
    "环境",
    "汽车",
    "房产",
    "旅游",
    "其他",
]


class NewsClassifier:
    """新闻分类器，使用 LLM 对新闻进行分类"""

    def __init__(self, llm_client: LLMClient | None = None):
        """
        初始化分类器

        Args:
            llm_client: LLM 客户端实例，如果为 None 则使用全局实例
        """
        self.client = llm_client or get_llm_client()
        self.categories = NEWS_CATEGORIES

    async def classify(self, title: str, content: str) -> str:
        """
        对新闻文章进行分类

        Args:
            title: 文章标题
            content: 文章内容

        Returns:
            分类标签
        """
        # 构建分类列表描述
        categories_str = "、".join(self.categories)

        # 构建系统提示词
        system_prompt = (
            "你是一个专业的新闻分类助手。"
            "你的任务是根据新闻文章的标题和内容，将其归类到最合适的分类中。"
            f"可选的分类包括：{categories_str}。"
            "你只需要输出一个分类标签，不需要任何解释或说明。"
        )

        # 构建用户提示词
        user_prompt = f"""请对以下新闻文章进行分类：

标题：{title}

内容：
{content}

可选分类：{categories_str}

要求：
1. 只输出一个分类标签
2. 从给定的分类列表中选择最合适的一个
3. 不要输出任何解释或说明文字
4. 如果文章内容不明确，选择"其他"

请直接输出分类标签："""

        # 调用 LLM 进行分类
        category = await self.client.call_llm(
            prompt=user_prompt,
            system_prompt=system_prompt,
            temperature=0.1,  # 使用极低温度以获得稳定的分类结果
            max_tokens=20,  # 分类标签很短
        )

        # 清理并验证分类结果
        category = category.strip()

        # 如果 LLM 输出的分类不在预定义列表中，尝试匹配最接近的
        if category not in self.categories:
            # 尝试在输出中查找匹配的分类
            for valid_category in self.categories:
                if valid_category in category:
                    return valid_category
            # 如果无法匹配，返回"其他"
            return "其他"

        return category

    async def classify_with_confidence(
        self,
        title: str,
        content: str,
    ) -> dict[str, float]:
        """
        对新闻文章进行分类，并返回各分类的置信度

        Args:
            title: 文章标题
            content: 文章内容

        Returns:
            字典，键为分类标签，值为置信度（0-1）
        """
        categories_str = "、".join(self.categories)

        system_prompt = (
            "你是一个专业的新闻分类助手。"
            "你的任务是根据新闻文章的标题和内容，评估它属于各个分类的可能性。"
            f"可选的分类包括：{categories_str}。"
        )

        user_prompt = f"""请评估以下新闻文章属于各个分类的可能性：

标题：{title}

内容：
{content}

可选分类：{categories_str}

要求：
1. 为每个分类给出一个 0-100 的可能性评分
2. 所有评分的总和应该等于 100
3. 按照以下格式输出，每行一个分类：
   分类名:评分

示例输出：
科技:60
财经:20
其他:20

请输出评分："""

        response = await self.client.call_llm(
            prompt=user_prompt,
            system_prompt=system_prompt,
            temperature=0.3,
            max_tokens=200,
        )

        # 解析响应，提取置信度
        confidence_scores: dict[str, float] = {}
        for line in response.strip().split("\n"):
            if ":" in line:
                parts = line.split(":")
                if len(parts) == 2:
                    category = parts[0].strip()
                    try:
                        score = float(parts[1].strip())
                        # 归一化为 0-1 范围
                        confidence_scores[category] = score / 100.0
                    except ValueError:
                        continue

        # 确保所有分类都有值
        for category in self.categories:
            if category not in confidence_scores:
                confidence_scores[category] = 0.0

        return confidence_scores

    async def batch_classify(
        self,
        articles: list[dict[str, str]],
    ) -> list[str]:
        """
        批量对新闻文章进行分类

        Args:
            articles: 文章列表，每篇文章包含 title 和 content 字段

        Returns:
            分类标签列表，与输入文章顺序对应
        """
        import asyncio

        tasks = [
            self.classify(
                title=article["title"],
                content=article["content"],
            )
            for article in articles
        ]

        categories = await asyncio.gather(*tasks, return_exceptions=True)

        # 处理可能的异常
        result = []
        for category in categories:
            if isinstance(category, Exception):
                result.append("其他")
            else:
                result.append(category)

        return result


# 全局分类器实例
_classifier_instance: NewsClassifier | None = None


def get_classifier(llm_client: LLMClient | None = None) -> NewsClassifier:
    """
    获取分类器实例（单例模式）

    Args:
        llm_client: LLM 客户端实例

    Returns:
        NewsClassifier 实例
    """
    global _classifier_instance
    if _classifier_instance is None:
        _classifier_instance = NewsClassifier(llm_client)
    return _classifier_instance
