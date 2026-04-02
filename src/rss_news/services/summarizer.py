"""新闻摘要生成模块"""

from .llm_client import LLMClient, get_llm_client


class NewsSummarizer:
    """新闻摘要生成器，使用 LLM 生成简洁的中文摘要"""

    def __init__(self, llm_client: LLMClient | None = None):
        """
        初始化摘要生成器

        Args:
            llm_client: LLM 客户端实例，如果为 None 则使用全局实例
        """
        self.client = llm_client or get_llm_client()

    async def summarize(
        self,
        title: str,
        content: str,
        min_length: int = 100,
        max_length: int = 200,
    ) -> str:
        """
        生成新闻摘要

        Args:
            title: 文章标题
            content: 文章内容
            min_length: 最小摘要长度（字数）
            max_length: 最大摘要长度（字数）

        Returns:
            生成的中文摘要
        """
        # 构建系统提示词
        system_prompt = (
            "你是一个专业的新闻摘要助手。"
            "你的任务是为新闻文章生成简洁、准确、客观的中文摘要。"
            f"摘要长度应控制在 {min_length}-{max_length} 字之间。"
            "摘要应该包含文章的核心信息和关键要点。"
        )

        # 构建用户提示词
        user_prompt = f"""请为以下新闻文章生成摘要：

标题：{title}

内容：
{content}

要求：
1. 摘要长度在 {min_length}-{max_length} 字之间
2. 突出文章的核心信息和关键要点
3. 语言简洁、准确、客观
4. 使用中文撰写
5. 不要添加个人观点或评价

请直接输出摘要内容，不需要其他说明文字。"""

        # 调用 LLM 生成摘要
        summary = await self.client.call_llm(
            prompt=user_prompt,
            system_prompt=system_prompt,
            temperature=0.3,  # 使用较低温度以获得更稳定的输出
            max_tokens=300,  # 预留足够的 token 空间
        )

        return summary

    async def batch_summarize(
        self,
        articles: list[dict[str, str]],
        min_length: int = 100,
        max_length: int = 200,
    ) -> list[str]:
        """
        批量生成新闻摘要

        Args:
            articles: 文章列表，每篇文章包含 title 和 content 字段
            min_length: 最小摘要长度
            max_length: 最大摘要长度

        Returns:
            摘要列表，与输入文章顺序对应
        """
        import asyncio

        # 并发处理所有文章
        tasks = [
            self.summarize(
                title=article["title"],
                content=article["content"],
                min_length=min_length,
                max_length=max_length,
            )
            for article in articles
        ]

        summaries = await asyncio.gather(*tasks, return_exceptions=True)

        # 处理可能的异常，将异常转换为错误消息
        result = []
        for i, summary in enumerate(summaries):
            if isinstance(summary, Exception):
                result.append(f"摘要生成失败: {str(summary)}")
            else:
                result.append(summary)

        return result


# 全局摘要器实例
_summarizer_instance: NewsSummarizer | None = None


def get_summarizer(llm_client: LLMClient | None = None) -> NewsSummarizer:
    """
    获取摘要生成器实例（单例模式）

    Args:
        llm_client: LLM 客户端实例

    Returns:
        NewsSummarizer 实例
    """
    global _summarizer_instance
    if _summarizer_instance is None:
        _summarizer_instance = NewsSummarizer(llm_client)
    return _summarizer_instance
