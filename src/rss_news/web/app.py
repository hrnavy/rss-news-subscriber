"""Flask 应用入口

创建和配置 Flask 应用。
"""

from pathlib import Path

from flask import Flask


def create_app() -> Flask:
    """创建 Flask 应用
    
    Returns:
        配置好的 Flask 应用实例
    """
    # 获取模板和静态文件目录
    web_dir = Path(__file__).parent
    template_dir = web_dir / "templates"
    static_dir = web_dir / "static"
    
    app = Flask(
        __name__,
        template_folder=str(template_dir),
        static_folder=str(static_dir),
    )
    
    # 注册蓝图
    from rss_news.web.routes import wiki_bp, api_bp
    app.register_blueprint(wiki_bp)
    app.register_blueprint(api_bp, url_prefix="/api")
    
    return app
