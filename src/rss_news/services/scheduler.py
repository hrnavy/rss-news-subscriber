"""定时任务调度模块

提供后台定时执行 fetch 和 LLM 处理任务的功能。
"""

import asyncio
import logging
import signal
import sys
from datetime import datetime
from pathlib import Path
from typing import Callable

from rss_news.services.config import load_config, DaemonConfig
from rss_news.services.fetcher import FeedFetcher
from rss_news.services.feed_service import FeedService
from rss_news.services.llm_client import get_llm_client
from rss_news.services.summarizer import NewsSummarizer
from rss_news.services.classifier import NewsClassifier
from rss_news.services.keyword_extractor import KeywordExtractor
from rss_news.services.article_service import ArticleService


logger = logging.getLogger(__name__)


class TaskScheduler:
    """定时任务调度器
    
    按配置的时间间隔自动执行 fetch 和 LLM 处理任务。
    """
    
    def __init__(self, config: DaemonConfig | None = None):
        """初始化调度器
        
        Args:
            config: 后台服务配置，为 None 时从配置文件加载
        """
        if config is None:
            app_config = load_config()
            config = app_config.daemon
        
        self.config = config
        self._is_running = False
        self._tasks: list[asyncio.Task] = []
        
        self._setup_logging()
    
    def _setup_logging(self):
        """配置日志"""
        log_file = Path(self.config.log_file)
        log_file.parent.mkdir(parents=True, exist_ok=True)
        
        file_handler = logging.FileHandler(
            log_file,
            encoding='utf-8',
        )
        file_handler.setLevel(logging.INFO)
        file_handler.setFormatter(logging.Formatter(
            '%(asctime)s - %(levelname)s - %(message)s'
        ))
        
        root_logger = logging.getLogger()
        root_logger.addHandler(file_handler)
        root_logger.setLevel(logging.INFO)
    
    async def _run_fetch_task(self):
        """执行抓取任务"""
        logger.info("开始执行抓取任务")
        start_time = datetime.now()
        
        try:
            fetcher = FeedFetcher()
            
            results = await fetcher.fetch_all_feeds(concurrency=3)
            
            total_new = sum(r.new_articles for r in results)
            elapsed = (datetime.now() - start_time).total_seconds()
            
            logger.info(
                f"抓取完成: {len(results)} 个源, {total_new} 篇新文章, "
                f"耗时 {elapsed:.1f} 秒"
            )
            
        except Exception as e:
            logger.error(f"抓取任务失败: {e}")
    
    async def _run_llm_task(self):
        """执行 LLM 处理任务"""
        logger.info("开始执行 LLM 处理任务")
        start_time = datetime.now()
        
        try:
            article_service = ArticleService()
            articles = article_service.get_articles_without_summary(limit=100)
            
            if not articles:
                logger.info("没有待处理的文章，跳过 LLM 处理")
                return
            
            llm_client = get_llm_client()
            summarizer = NewsSummarizer(llm_client)
            classifier = NewsClassifier(llm_client)
            keyword_extractor = KeywordExtractor(llm_client)
            
            processed = 0
            for article in articles:
                try:
                    title = article.title
                    content = article.content or ""
                    
                    summary = await summarizer.summarize(title, content)
                    category = await classifier.classify(title, content)
                    keywords = await keyword_extractor.extract(title, content)
                    
                    article_service.update_article_llm_fields(
                        article.id,
                        summary=summary,
                        category=category,
                        keywords=keywords,
                    )
                    processed += 1
                    
                except Exception as e:
                    logger.warning(f"处理文章 {article.id} 失败: {e}")
            
            elapsed = (datetime.now() - start_time).total_seconds()
            logger.info(
                f"LLM 处理完成: {processed}/{len(articles)} 篇文章, "
                f"耗时 {elapsed:.1f} 秒"
            )
            
        except Exception as e:
            logger.error(f"LLM 处理任务失败: {e}")
    
    async def _fetch_loop(self):
        """抓取任务循环"""
        while self._is_running:
            await self._run_fetch_task()
            
            for _ in range(self.config.fetch_interval):
                if not self._is_running:
                    break
                await asyncio.sleep(1)
    
    async def _llm_loop(self):
        """LLM 处理任务循环"""
        await asyncio.sleep(30)  # 启动后延迟 30 秒再执行
        
        while self._is_running:
            await self._run_llm_task()
            
            for _ in range(self.config.llm_interval):
                if not self._is_running:
                    break
                await asyncio.sleep(1)
    
    def start(self):
        """启动调度器"""
        if self._is_running:
            return
        
        self._is_running = True
        logger.info("定时任务调度器启动")
        logger.info(
            f"配置: 抓取间隔 {self.config.fetch_interval} 秒, "
            f"LLM 间隔 {self.config.llm_interval} 秒"
        )
        
        loop = asyncio.get_event_loop()
        
        self._tasks = [
            loop.create_task(self._fetch_loop()),
            loop.create_task(self._llm_loop()),
        ]
        
        def signal_handler(sig, frame):
            logger.info("收到停止信号")
            self.stop()
            sys.exit(0)
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        try:
            loop.run_until_complete(asyncio.gather(*self._tasks))
        except asyncio.CancelledError:
            pass
    
    def stop(self):
        """停止调度器"""
        if not self._is_running:
            return
        
        self._is_running = False
        logger.info("定时任务调度器停止")
        
        for task in self._tasks:
            task.cancel()
        
        self._tasks.clear()
    
    @property
    def is_running(self) -> bool:
        """调度器是否正在运行"""
        return self._is_running


def run_daemon():
    """运行后台服务"""
    scheduler = TaskScheduler()
    scheduler.start()
