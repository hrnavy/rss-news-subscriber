"""Wiki 页面路由

提供 Wiki 页面的 Web 界面。
"""

from flask import Blueprint, render_template, abort

from rss_news.web.services.wiki_reader import WikiReader
from rss_news.web.services.article_reader import ArticleReader

wiki_bp = Blueprint("wiki", __name__)

# 初始化服务
wiki_reader = WikiReader()
article_reader = ArticleReader()


@wiki_bp.route("/")
def index():
    """首页"""
    stats = wiki_reader.get_stats()
    people = wiki_reader.get_all_people()[:10]  # 最近 10 个人物
    entities = wiki_reader.get_all_entities()[:10]  # 最近 10 个实体
    
    return render_template(
        "index.html",
        stats=stats,
        recent_people=people,
        recent_entities=entities,
    )


@wiki_bp.route("/people")
def people_list():
    """人物列表页"""
    people = wiki_reader.get_all_people()
    return render_template("people_list.html", people=people)


@wiki_bp.route("/people/<name>")
def person_detail(name: str):
    """人物详情页"""
    person = wiki_reader.get_person(name)
    
    if not person:
        abort(404)
    
    return render_template("person_detail.html", person=person)


@wiki_bp.route("/political-entities")
def entity_list():
    """政治实体列表页"""
    entities = wiki_reader.get_all_entities()
    
    # 按类型分组
    grouped = {}
    for entity in entities:
        entity_type = entity.get("type", "其他")
        if entity_type not in grouped:
            grouped[entity_type] = []
        grouped[entity_type].append(entity)
    
    return render_template("entity_list.html", entities=entities, grouped=grouped)


@wiki_bp.route("/political-entities/<name>")
def entity_detail(name: str):
    """政治实体详情页"""
    entity = wiki_reader.get_entity(name)
    
    if not entity:
        abort(404)
    
    return render_template("entity_detail.html", entity=entity)


@wiki_bp.route("/article/<int:article_id>")
def article_detail(article_id: int):
    """新闻详情页"""
    article = article_reader.get_article(article_id)
    
    if not article:
        abort(404)
    
    return render_template("article.html", article=article)
