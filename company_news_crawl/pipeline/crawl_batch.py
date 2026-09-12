"""
批量爬取逻辑
"""
from typing import List, Dict, Any
import asyncio
from ..models import CrawlResult
from ..config import CrawlConfig
from .crawl_one import crawl_one_company


async def crawl_batch(
    companies: List[Dict[str, Any]],
    config: CrawlConfig
) -> List[CrawlResult]:
    """
    批量爬取公司新闻
    
    Args:
        companies: 公司列表
        config: 爬虫配置
        
    Returns:
        爬取结果列表
    """
    # MVP: 顺序执行（避免并发问题）
    # 未来可改为 asyncio.gather 或 semaphore 限流
    results = []
    
    for company in companies:
        try:
            result = await crawl_one_company(company, config)
            results.append(result)
        except Exception as e:
            # 记录失败但继续处理其他公司
            from ..models import SiteProfile
            error_profile = SiteProfile(
                stock_code=company.get("stock_code", "unknown"),
                company_name=company.get("company_name", "unknown"),
                list_url=company.get("news_list_url", ""),
            )
            error_result = CrawlResult(
                profile=error_profile,
                articles=[],
                errors=[f"Unexpected error: {str(e)}"]
            )
            results.append(error_result)
    
    return results
