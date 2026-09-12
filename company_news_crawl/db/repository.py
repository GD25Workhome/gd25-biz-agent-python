"""
数据库存储接口（未来扩展）
"""
from typing import List
from ..models import SiteProfile, ArticleRecord


class Repository:
    """
    数据库存储接口
    
    当前为占位实现，未来可接入 MySQL
    """
    
    def __init__(self, config):
        self.config = config
        self.enabled = config.db_enabled
    
    def save_profile(self, profile: SiteProfile):
        """保存站点配置档案"""
        if not self.enabled:
            return
        # TODO: 实现 MySQL INSERT/UPDATE
        pass
    
    def save_articles(self, articles: List[ArticleRecord]):
        """批量保存文章"""
        if not self.enabled:
            return
        # TODO: 实现 MySQL BATCH INSERT（去重 content_hash 或 url_norm）
        pass
    
    def get_profile(self, stock_code: str, list_url: str) -> SiteProfile:
        """查询站点配置档案"""
        if not self.enabled:
            return None
        # TODO: 实现 MySQL SELECT
        pass
    
    def article_exists(self, content_hash: str) -> bool:
        """检查文章是否已存在"""
        if not self.enabled:
            return False
        # TODO: 实现 MySQL SELECT COUNT
        pass
