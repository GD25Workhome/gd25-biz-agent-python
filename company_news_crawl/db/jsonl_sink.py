"""
JSONL 输出模块
"""
import json
import os
from typing import List
from ..models import CrawlResult


class JSONLSink:
    """JSONL 文件输出器"""
    
    @staticmethod
    def write_results(results: List[CrawlResult], output_path: str):
        """
        将爬取结果写入 JSONL 文件
        
        Args:
            results: 爬取结果列表
            output_path: 输出文件路径
        """
        # 确保输出目录存在
        output_dir = os.path.dirname(output_path)
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)
        
        with open(output_path, "w", encoding="utf-8") as f:
            for result in results:
                # 写入 profile
                if result.profile:
                    profile_line = {
                        "type": "profile",
                        "data": result.profile.to_dict()
                    }
                    f.write(json.dumps(profile_line, ensure_ascii=False) + "\n")
                
                # 写入 articles
                for article in result.articles:
                    article_line = {
                        "type": "article",
                        "data": article.to_dict()
                    }
                    f.write(json.dumps(article_line, ensure_ascii=False) + "\n")
                
                # 写入 errors（如果有）
                if result.errors:
                    error_line = {
                        "type": "errors",
                        "stock_code": result.profile.stock_code if result.profile else "unknown",
                        "errors": result.errors
                    }
                    f.write(json.dumps(error_line, ensure_ascii=False) + "\n")
    
    @staticmethod
    def write_summary(results: List[CrawlResult], output_path: str):
        """
        写入汇总统计信息
        
        Args:
            results: 爬取结果列表
            output_path: 输出文件路径
        """
        total_companies = len(results)
        total_articles = sum(len(r.articles) for r in results)
        successful_companies = sum(1 for r in results if r.articles)
        total_errors = sum(len(r.errors) for r in results)
        
        summary = {
            "total_companies": total_companies,
            "successful_companies": successful_companies,
            "total_articles": total_articles,
            "total_errors": total_errors,
            "companies": [
                {
                    "stock_code": r.profile.stock_code if r.profile else "unknown",
                    "company_name": r.profile.company_name if r.profile else "unknown",
                    "article_count": len(r.articles),
                    "error_count": len(r.errors),
                    "site_type": r.profile.site_type.value if r.profile else "unknown",
                    "list_url": r.profile.list_url if r.profile else "",
                }
                for r in results
            ]
        }
        
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)
