"""
CLI 入口点
"""
import argparse
import asyncio
import json
import sys
import os
from typing import List, Dict, Any
from .config import CrawlConfig
from .pipeline import crawl_batch
from .db import JSONLSink


def load_seed_file(seed_path: str) -> List[Dict[str, Any]]:
    """加载种子文件（支持 JSON 和 JSONL）"""
    with open(seed_path, "r", encoding="utf-8") as f:
        content = f.read().strip()
        
        # 尝试解析为 JSON
        try:
            data = json.loads(content)
            if isinstance(data, list):
                return data
            else:
                return [data]
        except json.JSONDecodeError:
            pass
        
        # 尝试解析为 JSONL
        companies = []
        for line in content.split("\n"):
            line = line.strip()
            if line:
                companies.append(json.loads(line))
        return companies


async def run_crawl(seed_path: str, output_path: str, config: CrawlConfig):
    """运行爬虫"""
    print(f"加载种子文件: {seed_path}")
    companies = load_seed_file(seed_path)
    print(f"  - 共 {len(companies)} 家公司")
    
    print(f"\n开始爬取...")
    results = await crawl_batch(companies, config)
    
    print(f"\n爬取完成，写入结果...")
    JSONLSink.write_results(results, output_path)
    
    # 写入摘要
    summary_path = output_path.replace(".jsonl", "_summary.json")
    JSONLSink.write_summary(results, summary_path)
    
    # 打印统计
    total_articles = sum(len(r.articles) for r in results)
    successful = sum(1 for r in results if r.articles)
    
    print(f"\n=== 统计 ===")
    print(f"公司总数: {len(results)}")
    print(f"成功公司: {successful}")
    print(f"文章总数: {total_articles}")
    print(f"\n结果文件: {output_path}")
    print(f"摘要文件: {summary_path}")


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description="A股上市公司官网新闻爬虫 MVP",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例用法:
  # 基础用法
  python -m company_news_crawl once --seed examples/seed_sample.json --out /tmp/out.jsonl
  
  # 自定义配置
  python -m company_news_crawl once --seed data.json --out result.jsonl --max-articles 10
  
  # 使用环境变量
  export CRAWL_MAX_ARTICLES=30
  export CRAWL_TIMEOUT=15
  python -m company_news_crawl once --seed data.json --out result.jsonl
        """
    )
    
    subparsers = parser.add_subparsers(dest="command", help="子命令")
    
    # once 命令
    once_parser = subparsers.add_parser("once", help="执行一次爬取")
    once_parser.add_argument("--seed", required=True, help="种子文件路径 (JSON/JSONL)")
    once_parser.add_argument("--out", required=True, help="输出文件路径 (JSONL)")
    once_parser.add_argument("--max-articles", type=int, help="每家公司最大文章数")
    once_parser.add_argument("--max-pages", type=int, help="每家公司最大爬取页数（分页）")
    once_parser.add_argument("--timeout", type=int, help="HTTP 超时时间（秒）")
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(1)
    
    # 加载配置
    config = CrawlConfig.from_env()
    
    # 覆盖命令行参数
    if hasattr(args, "max_articles") and args.max_articles:
        config.max_articles_per_company = args.max_articles
    if hasattr(args, "max_pages") and args.max_pages:
        config.max_pages = args.max_pages
    if hasattr(args, "timeout") and args.timeout:
        config.timeout = args.timeout
    
    if args.command == "once":
        asyncio.run(run_crawl(args.seed, args.out, config))


if __name__ == "__main__":
    main()
