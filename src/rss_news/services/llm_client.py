"""LM Studio API 客户端模块

使用 requests 库与本地 LM Studio 服务交互，解决 httpx 兼容性问题。
"""

import asyncio
import logging
from typing import Any

import requests

from rss_news.services.config import load_config

logger = logging.getLogger(__name__)


class LLMClient:
    """LM Studio API 客户端，用于与本地 LM Studio 服务交互"""

    def __init__(
        self,
        base_url: str = "http://localhost:1234/v1",
        api_key: str = "lm-studio",
        model: str = "local-model",
        max_retries: int = 3,
        retry_delay: float = 1.0,
        timeout: int = 60,
    ):
        """
        初始化 LM Studio 客户端

        Args:
            base_url: LM Studio API 地址
            api_key: API 密钥（本地服务通常不需要真实密钥）
            model: 模型名称
            max_retries: 最大重试次数
            retry_delay: 重试延迟（秒）
            timeout: 请求超时时间（秒）
        """
        self.base_url = base_url.rstrip('/')
        self.model = model
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.timeout = timeout
        self.api_key = api_key

    def _call_api(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 1000,
    ) -> str:
        """同步调用 API

        Args:
            messages: 消息列表
            temperature: 温度参数
            max_tokens: 最大生成 token 数

        Returns:
            LLM 生成的文本内容
        """
        url = f"{self.base_url}/chat/completions"
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        
        last_exception: Exception | None = None
        
        for attempt in range(self.max_retries):
            try:
                response = requests.post(
                    url,
                    json=payload,
                    headers=headers,
                    timeout=self.timeout,
                )
                
                response.raise_for_status()
                
                data = response.json()
                if data.get("choices") and len(data["choices"]) > 0:
                    message = data["choices"][0].get("message", {})
                    content = message.get("content", "")
                    if not content:
                        content = message.get("reasoning_content", "")
                    return content.strip() if content else ""
                
                return ""
                
            except requests.exceptions.RequestException as e:
                last_exception = e
                logger.warning(f"LLM API 调用失败 (尝试 {attempt + 1}/{self.max_retries}): {e}")
                if attempt < self.max_retries - 1:
                    import time
                    time.sleep(self.retry_delay * (attempt + 1))
        
        if last_exception:
            raise last_exception
        raise RuntimeError("LLM 调用失败，未知错误")

    async def call_llm(
        self,
        prompt: str,
        system_prompt: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 1000,
    ) -> str:
        """
        调用 LLM 的通用方法，支持重试机制

        Args:
            prompt: 用户提示词
            system_prompt: 系统提示词（可选）
            temperature: 温度参数，控制随机性
            max_tokens: 最大生成 token 数

        Returns:
            LLM 生成的文本内容
        """
        messages: list[dict[str, str]] = []

        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        messages.append({"role": "user", "content": prompt})

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            self._call_api,
            messages,
            temperature,
            max_tokens,
        )

    async def call_llm_with_history(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 1000,
    ) -> str:
        """
        调用 LLM 并支持对话历史

        Args:
            messages: 对话历史消息列表
            temperature: 温度参数
            max_tokens: 最大生成 token 数

        Returns:
            LLM 生成的文本内容
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            self._call_api,
            messages,
            temperature,
            max_tokens,
        )

    async def close(self) -> None:
        """关闭客户端连接（兼容性保留）"""
        pass


# 全局客户端实例（单例模式）
_client_instance: LLMClient | None = None


def get_llm_client(
    base_url: str | None = None,
    model: str | None = None,
    **kwargs: Any,
) -> LLMClient:
    """
    获取 LLM 客户端实例（单例模式）
    
    如果未提供参数，则从配置文件加载。

    Args:
        base_url: LM Studio API 地址
        model: 模型名称
        **kwargs: 其他初始化参数

    Returns:
        LLMClient 实例
    """
    global _client_instance
    if _client_instance is None:
        config = load_config()
        _client_instance = LLMClient(
            base_url=base_url or config.llm.api_base,
            model=model or config.llm.model,
            timeout=config.llm.timeout,
            **kwargs
        )
    return _client_instance
