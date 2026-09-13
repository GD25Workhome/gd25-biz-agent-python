"""
单公司爬取逻辑
"""
from typing import Dict, Any
from datetime import datetime
from ..models import (
    SiteProfile, ArticleRecord, CrawlResult,
    SiteType, FetchMethod, SourceLevel
)
from ..config import CrawlConfig
from ..adapters import (
    HTTPClient, ListExtractor, ContentExtractor, SiteProfiler
)


async def crawl_one_company(
    company: Dict[str, Any],
    config: CrawlConfig
) -> CrawlResult:
    """
    爬取单个公司的新闻
    
    Args:
        company: 公司信息字典 {stock_code, company_name, news_list_url, site?}
        config: 爬虫配置
        
    Returns:
        CrawlResult
    """
    # 验证必需字段
    try:
        stock_code = str(company.get("stock_code", "")).strip()
        company_name = str(company.get("company_name", "")).strip()
        list_url = str(company.get("news_list_url", "")).strip()
        
        if not stock_code or not company_name or not list_url:
            raise ValueError("Missing required fields: stock_code, company_name, or news_list_url")
    except Exception as e:
        # 返回错误结果
        error_profile = SiteProfile(
            stock_code=company.get("stock_code", "unknown"),
            company_name=company.get("company_name", "unknown"),
            list_url=company.get("news_list_url", ""),
        )
        return CrawlResult(
            profile=error_profile,
            articles=[],
            errors=[f"Invalid company data: {str(e)}"]
        )
    
    profile = SiteProfile(
        stock_code=stock_code,
        company_name=company_name,
        list_url=list_url,
    )
    
    articles = []
    errors = []
    
    async with HTTPClient(config) as client:
        # 步骤 1: 获取列表页（支持分页）
        all_list_items = []
        visited_urls = set()
        pages_to_crawl = [list_url]
        pages_crawled = 0
        
        while pages_to_crawl and pages_crawled < config.max_pages:
            current_url = pages_to_crawl.pop(0)
            
            # 避免重复爬取
            if current_url in visited_urls:
                continue
            visited_urls.add(current_url)
            pages_crawled += 1
            
            html, status_code, error = await client.fetch(current_url)
            
            if pages_crawled == 1:
                profile.last_http_status = status_code
            
            if error or not html:
                if pages_crawled == 1:
                    profile.fail_streak += 1
                    profile.notes = error or "Empty response"
                    errors.append(f"Failed to fetch list page: {error}")
                    return CrawlResult(profile=profile, articles=[], errors=errors)
                else:
                    # 分页失败不致命，继续处理已获取的项
                    errors.append(f"Failed to fetch page {current_url}: {error}")
                    break
            
            # 步骤 2: 识别站点类型（仅第一页）
            if pages_crawled == 1:
                site_type = SiteProfiler.profile(html, current_url, status_code)
                profile.site_type = site_type
                
                if site_type in [SiteType.BLOCKED, SiteType.API]:
                    profile.notes = f"Site type {site_type.value} - skipped"
                    errors.append(f"Site type {site_type.value} not supported in HTTP-only mode")
                    return CrawlResult(profile=profile, articles=[], errors=errors)
                
                if site_type == SiteType.SPA:
                    profile.notes = "SPA detected - requires browser (not implemented in MVP)"
                    errors.append("SPA site requires browser automation")
                    return CrawlResult(profile=profile, articles=[], errors=errors)
            
            # 步骤 3: 提取文章列表项（结构化）
            page_items = ListExtractor.extract_list_items(
                html, current_url, same_domain_only=config.same_domain_only
            )
            all_list_items.extend(page_items)
            
            # 步骤 4: 提取分页链接（如果还未达到最大页数）
            if pages_crawled < config.max_pages and len(all_list_items) < config.max_articles_per_company:
                pagination_links = ListExtractor.extract_pagination_links(html, current_url)
                for pag_link in pagination_links:
                    if pag_link not in visited_urls and pag_link not in pages_to_crawl:
                        pages_to_crawl.append(pag_link)
        
        if not all_list_items:
            profile.notes = "No article links found"
            errors.append("No article links extracted from list page(s)")
            return CrawlResult(profile=profile, articles=[], errors=errors)
        
        profile.last_article_link_count = len(all_list_items)
        
        # 限制数量
        all_list_items = all_list_items[:config.max_articles_per_company]
        
        # 步骤 5: 爬取文章详情
        for list_item in all_list_items:
            article_html, article_status, article_error = await client.fetch(list_item.url)
            
            if article_error or not article_html:
                errors.append(f"Failed to fetch {list_item.url}: {article_error}")
                continue
            
            # 提取内容（传入列表页提供的元数据作为回退）
            title, published_at, content = ContentExtractor.extract(
                article_html, 
                list_item.url,
                list_title=list_item.title,
                list_date=list_item.published_at
            )
            
            if not title or not content:
                errors.append(f"Failed to extract content from {list_item.url}")
                continue
            
            # 创建记录
            url_norm = ListExtractor.normalize_url(list_item.url)
            content_hash = ArticleRecord.compute_content_hash(content)
            summary = ContentExtractor.generate_summary(content, max_length=200)
            
            article = ArticleRecord(
                stock_code=stock_code,
                company_name=company_name,
                source_level=SourceLevel.P0_OFFICIAL_SITE,
                list_url=list_url,
                article_url=list_item.url,
                url_norm=url_norm,
                title=title,
                published_at=published_at,
                fetched_at=datetime.now(),
                content_text=content,
                content_hash=content_hash,
                summary=summary,
                http_status=article_status,
                fetch_method=FetchMethod.HTTP,
                template_id="generic",
                site_type=profile.site_type,
            )
            
            articles.append(article)
        
        # 更新 profile
        if articles:
            profile.last_success_at = datetime.now()
            profile.fail_streak = 0
        else:
            profile.fail_streak += 1
            profile.notes = "No articles successfully extracted"
    
    return CrawlResult(profile=profile, articles=articles, errors=errors)
