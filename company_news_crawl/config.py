"""
配置管理模块
"""
import os
from dataclasses import dataclass
from typing import Optional


@dataclass
class CrawlConfig:
    """爬虫配置"""
    
    # HTTP 请求配置
    timeout: int = 20
    max_retries: int = 2
    request_interval: float = 1.0
    user_agent: str = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    
    # 爬取限制
    max_articles_per_company: int = 20
    max_concurrent_requests: int = 1
    max_pages: int = 3
    
    # URL 处理
    same_domain_only: bool = True
    normalize_urls: bool = True
    
    # 输出配置
    output_dir: str = "/tmp/company_news_crawl"
    
    # 数据库配置（可选）
    db_enabled: bool = False
    db_host: str = "localhost"
    db_port: int = 3306
    db_user: str = "root"
    db_password: str = ""
    db_name: str = "company_news"
    
    @classmethod
    def from_env(cls) -> "CrawlConfig":
        """从环境变量加载配置"""
        return cls(
            timeout=int(os.getenv("CRAWL_TIMEOUT", "20")),
            max_retries=int(os.getenv("CRAWL_MAX_RETRIES", "2")),
            request_interval=float(os.getenv("CRAWL_REQUEST_INTERVAL", "1.0")),
            max_articles_per_company=int(os.getenv("CRAWL_MAX_ARTICLES", "20")),
            max_concurrent_requests=int(os.getenv("CRAWL_MAX_CONCURRENT", "1")),
            max_pages=int(os.getenv("CRAWL_MAX_PAGES", "3")),
            output_dir=os.getenv("CRAWL_OUTPUT_DIR", "/tmp/company_news_crawl"),
            db_enabled=os.getenv("CRAWL_DB_ENABLED", "false").lower() == "true",
            db_host=os.getenv("DB_HOST", "localhost"),
            db_port=int(os.getenv("DB_PORT", "3306")),
            db_user=os.getenv("DB_USER", "root"),
            db_password=os.getenv("DB_PASSWORD", ""),
            db_name=os.getenv("DB_NAME", "company_news"),
        )
