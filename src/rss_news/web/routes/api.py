"""API 路由

提供 RESTful API 接口。
"""

from flask import Blueprint, jsonify

from rss_news.web.services.wiki_reader import WikiReader
from rss_news.web.services.article_reader import ArticleReader

api_bp = Blueprint("api", __name__)

# 初始化服务
wiki_reader = WikiReader()
article_reader = ArticleReader()


@api_bp.route("/people")
def get_people():
    """获取所有人物列表"""
    people = wiki_reader.get_all_people()
    return jsonify(people)


@api_bp.route("/people/<name>")
def get_person(name: str):
    """获取人物详情"""
    person = wiki_reader.get_person(name)
    
    if not person:
        return jsonify({"error": "Person not found"}), 404
    
    return jsonify({
        "name": person.name,
        "description": person.description,
        "related_people": person.related_people,
        "news": person.news,
        "timeline": person.timeline,
        "generated_at": person.generated_at,
    })


@api_bp.route("/political-entities")
def get_entities():
    """获取所有政治实体列表"""
    entities = wiki_reader.get_all_entities()
    return jsonify(entities)


@api_bp.route("/political-entities/<name>")
def get_entity(name: str):
    """获取政治实体详情"""
    entity = wiki_reader.get_entity(name)
    
    if not entity:
        return jsonify({"error": "Entity not found"}), 404
    
    return jsonify({
        "name": entity.name,
        "type": entity.entity_type,
        "description": entity.description,
        "news": entity.news,
        "timeline": entity.timeline,
        "generated_at": entity.generated_at,
    })


@api_bp.route("/articles/<int:article_id>")
def get_article(article_id: int):
    """获取新闻详情"""
    article = article_reader.get_article(article_id)
    
    if not article:
        return jsonify({"error": "Article not found"}), 404
    
    return jsonify({
        "id": article.id,
        "title": article.title,
        "content": article.content,
        "source": article.source,
        "published_at": article.published_at,
        "link": article.link,
        "summary": article.summary,
    })


@api_bp.route("/stats")
def get_stats():
    """获取统计信息"""
    stats = wiki_reader.get_stats()
    return jsonify(stats)
