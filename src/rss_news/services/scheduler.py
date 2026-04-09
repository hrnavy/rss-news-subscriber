"""定时任务调度模块

提供后台定时执行 fetch、Wiki 构建和健康检查任务的功能。
"""

import asyncio
import logging
import signal
import sys
from datetime import datetime
from pathlib import Path

from rss_news.services.config import load_config, DaemonConfig
from rss_news.services.fetcher import FeedFetcher


logger = logging.getLogger(__name__)


class TaskScheduler:
    """定时任务调度器
    
    按配置的时间间隔自动执行 fetch、Wiki 构建和健康检查任务。
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
    
    async def _run_wiki_task(self):
        """执行 Wiki 构建任务
        
        依次执行：
        1. 构建人物页面
        2. 构建政治实体页面
        """
        logger.info("开始执行 Wiki 构建任务")
        start_time = datetime.now()
        
        try:
            # 1. 构建人物页面
            from rss_news.services.wiki_service import WikiService
            wiki_service = WikiService()
            
            # 初始化名字映射服务
            wiki_service.name_mapping_service.initialize()
            
            articles = wiki_service.get_unprocessed_articles(limit=100)
            people_count = 0
            
            if articles:
                people, processed_ids = wiki_service.extract_people_parallel(articles, workers=1)
                
                for person in people:
                    name = person.get("name", "未知")
                    article_ids = person.get("article_ids", [])
                    
                    if article_ids:
                        # 规范化名字
                        normalized_name = wiki_service.name_mapping_service.normalize_name(name)
                        person["name"] = normalized_name
                        
                        articles_for_person = wiki_service._get_articles_by_ids(article_ids)
                        content = wiki_service.generate_person_page(person, articles_for_person)
                        wiki_service.save_person_page(normalized_name, content)
                        people_count += 1
                
                wiki_service.mark_articles_processed(processed_ids)
            
            logger.info(f"人物页面构建完成: {people_count} 个")
            
            # 2. 构建政治实体页面
            from rss_news.services.political_entity_service import PoliticalEntityService
            entity_service = PoliticalEntityService()
            
            articles = entity_service.get_unprocessed_articles(limit=100)
            entity_count = 0
            
            if articles:
                entities, processed_ids = entity_service.extract_political_entities_parallel(articles, workers=1)
                
                for entity in entities:
                    name = entity.get("name", "未知")
                    article_ids = entity.get("article_ids", [])
                    
                    if article_ids:
                        articles_for_entity = entity_service.get_articles_by_ids(article_ids)
                        content = entity_service.generate_political_entity_page(entity, articles_for_entity)
                        entity_service.save_political_entity_page(name, content)
                        entity_count += 1
                
                entity_service.mark_articles_processed(processed_ids)
            
            logger.info(f"政治实体页面构建完成: {entity_count} 个")
            
            elapsed = (datetime.now() - start_time).total_seconds()
            logger.info(f"Wiki 构建完成: 人物 {people_count} 个, 政治实体 {entity_count} 个, 耗时 {elapsed:.1f} 秒")
            
        except Exception as e:
            logger.error(f"Wiki 构建任务失败: {e}")
    
    async def _run_health_check_task(self):
        """执行健康检查任务"""
        logger.info("开始执行健康检查任务")
        start_time = datetime.now()
        
        try:
            from rss_news.services.wiki_health_check_service import WikiHealthCheckService
            health_service = WikiHealthCheckService()
            
            # 执行健康检查
            report = health_service.run_full_check()
            
            # 记录结果
            elapsed = (datetime.now() - start_time).total_seconds()
            total_issues = report.summary.get("total_issues", 0)
            logger.info(
                f"健康检查完成: 状态={report.overall_status.value}, "
                f"问题数={total_issues}, 耗时 {elapsed:.1f} 秒"
            )
            
            # 如果发现问题，记录详情
            if total_issues > 0:
                for result in report.results.values():
                    if result.issues:
                        logger.warning(f"{result.check_type.value}: {len(result.issues)} 个问题")
        
        except Exception as e:
            logger.error(f"健康检查任务失败: {e}")
    
    async def _fetch_loop(self):
        """抓取任务循环"""
        while self._is_running:
            await self._run_fetch_task()
            
            for _ in range(self.config.fetch_interval):
                if not self._is_running:
                    break
                await asyncio.sleep(1)
    
    async def _wiki_loop(self):
        """Wiki 构建任务循环"""
        await asyncio.sleep(60)  # 启动后延迟 60 秒再执行
        
        while self._is_running:
            await self._run_wiki_task()
            
            for _ in range(self.config.wiki_interval):
                if not self._is_running:
                    break
                await asyncio.sleep(1)
    
    async def _health_check_loop(self):
        """健康检查任务循环"""
        await asyncio.sleep(120)  # 启动后延迟 120 秒再执行
        
        while self._is_running:
            await self._run_health_check_task()
            
            for _ in range(self.config.health_check_interval):
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
            f"Wiki 间隔 {self.config.wiki_interval} 秒, "
            f"健康检查间隔 {self.config.health_check_interval} 秒"
        )
        
        loop = asyncio.get_event_loop()
        
        self._tasks = [
            loop.create_task(self._fetch_loop()),
            loop.create_task(self._wiki_loop()),
            loop.create_task(self._health_check_loop()),
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
