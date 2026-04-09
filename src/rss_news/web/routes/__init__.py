"""路由模块"""

from rss_news.web.routes.wiki import wiki_bp
from rss_news.web.routes.api import api_bp

__all__ = ["wiki_bp", "api_bp"]
