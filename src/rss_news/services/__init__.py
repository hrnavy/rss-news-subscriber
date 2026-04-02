"""业务服务模块"""

from .article_service import ArticleService, get_article_service
from .classifier import NEWS_CATEGORIES, NewsClassifier, get_classifier
from .feed_service import (
    FeedService,
    FeedServiceError,
    FeedNotFoundError,
    FeedAlreadyExistsError,
    FeedValidationError,
    get_feed_service,
)
from .feed_validator import FeedValidator, ValidationResult, get_validator
from .fetcher import FeedFetcher, FetchResult, close_fetcher, get_fetcher
from .keyword_extractor import KeywordExtractor, get_keyword_extractor
from .llm_client import LLMClient, get_llm_client
from .rss_parser import (
    ParsedArticle,
    ParsedFeed,
    RSSParseError,
    RSSParser,
    close_parser,
    get_parser,
)
from .summarizer import NewsSummarizer, get_summarizer
from .player import NewsPlayer, run_player
from rss_news.services.config import (
    Config,
    DatabaseConfig,
    DisplayConfig,
    FetchConfig,
    LLMConfig,
    get_database_path,
    load_config,
)

__all__ = [
    # RSS 解析
    "RSSParser",
    "get_parser",
    "close_parser",
    "ParsedArticle",
    "ParsedFeed",
    "RSSParseError",
    # 新闻抓取
    "FeedFetcher",
    "get_fetcher",
    "close_fetcher",
    "FetchResult",
    # 文章服务
    "ArticleService",
    "get_article_service",
    # 订阅源服务
    "FeedService",
    "get_feed_service",
    "FeedServiceError",
    "FeedNotFoundError",
    "FeedAlreadyExistsError",
    "FeedValidationError",
    # 订阅源验证
    "FeedValidator",
    "ValidationResult",
    "get_validator",
    # LLM 相关
    "LLMClient",
    "get_llm_client",
    "NewsSummarizer",
    "get_summarizer",
    "NewsClassifier",
    "get_classifier",
    "NEWS_CATEGORIES",
    "KeywordExtractor",
    "get_keyword_extractor",
    # 播放器
    "NewsPlayer",
    "run_player",
    # 配置
    "Config",
    "LLMConfig",
    "FetchConfig",
    "DatabaseConfig",
    "DisplayConfig",
    "load_config",
    "get_database_path",
]
