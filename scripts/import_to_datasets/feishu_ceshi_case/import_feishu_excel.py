#!/usr/bin/env python
"""
Feishu Excel 导入 Langfuse Datasets 主入口

功能：
1. 读取 static/rag_source/uat_data/ 下的 Excel 文件
2. 按 feishu/excelName/sheetName 创建 DataSet
3. 设置 input/expected_output 的 JSON Schema
4. 按 Sheet 类型选择解析策略，解析数据并写入 DataSet Items

运行方式：
    cd 项目根目录
    python scripts/import_to_datasets/feishu_ceshi_case/import_feishu_excel.py

配置：所有参数在 scripts/import_to_datasets/feishu_ceshi_case/config.py 中设置
"""
import sys
from pathlib import Path

# 添加项目根目录到路径（用于完整包路径导入，便于 IDE 跳转）
project_root = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv

load_dotenv(project_root / ".env")

import logging

from langfuse import Langfuse

from scripts.import_to_datasets.feishu_ceshi_case.config import Config
from scripts.import_to_datasets.feishu_ceshi_case.dataset import DatasetCreator, DatasetItemWriter
from scripts.import_to_datasets.feishu_ceshi_case.parsers.canonical import canonical_to_dataset_item
from scripts.import_to_datasets.feishu_ceshi_case.parsers.cleaners import get_cleaner_by_type
from scripts.import_to_datasets.feishu_ceshi_case.utils import ExcelReader

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def main() -> None:
    """主流程"""
    logger.info("=" * 60)
    logger.info("Feishu Excel 导入 Langfuse Datasets")
    logger.info("=" * 60)

    langfuse = Langfuse()
    creator = DatasetCreator(langfuse)
    writer = DatasetItemWriter(langfuse)

    total_stats = {"success": 0, "fail": 0, "skipped": 0}

    for excel_filename in Config.excel_files:
        excel_path = Config.get_excel_path(excel_filename)
        if not excel_path.exists():
            logger.warning("文件不存在，跳过: %s", excel_path)
            continue

        excel_name = excel_path.stem  # 不含扩展名的文件名
        if not Config.should_process_excel(excel_name):
            logger.info("Excel '%s' 已配置跳过（sheet_include_mapping 中未包含）", excel_filename)
            continue

        logger.info("")
        logger.info("=" * 60)
        logger.info("处理 Excel: %s", excel_filename)
        logger.info("=" * 60)

        reader = ExcelReader(excel_path)

        for sheet_name, df in reader.iter_sheets():
            if not Config.should_process_sheet(excel_name, sheet_name):
                logger.info("  Sheet '%s' 已配置跳过（sheet_include_mapping）", sheet_name)
                continue
            if df.empty:
                logger.warning("  Sheet '%s' 为空，跳过", sheet_name)
                continue

            # 选择清洗器（parser_type 复用为 cleaner_type）
            cleaner_type = Config.get_parser_type(excel_name, sheet_name)
            cleaner = get_cleaner_by_type(cleaner_type)

            # DataSet 名称
            dataset_name = Config.get_dataset_name(excel_name, sheet_name)

            # 创建 DataSet 并设置 Schema
            creator.create_or_update_dataset(
                dataset_name=dataset_name,
                excel_name=excel_name,
                sheet_name=sheet_name,
                parser_type=cleaner_type,
            )

            # 重复导入：清空已有 Items（覆盖而非追加）
            if Config.clear_before_import:
                creator.clear_dataset_items(dataset_name)

            # 清洗 → 规范格式 → 转换 → 写入
            sheet_stats = {"success": 0, "fail": 0, "skipped": 0}
            for idx, row in df.iterrows():
                try:
                    if cleaner.is_empty_row(row, df):
                        sheet_stats["skipped"] += 1
                        continue

                    canonical_items = cleaner.clean(row, df)
                    for item in canonical_items:
                        dataset_item = canonical_to_dataset_item(item)
                        writer.write_item(dataset_name, dataset_item)
                        sheet_stats["success"] += 1

                except Exception as e:
                    sheet_stats["fail"] += 1
                    logger.error("  第 %d 行处理失败: %s", idx + 2, e)

            total_stats["success"] += sheet_stats["success"]
            total_stats["fail"] += sheet_stats["fail"]
            total_stats["skipped"] += sheet_stats["skipped"]

            logger.info(
                "  Sheet '%s' 完成: 成功 %d, 失败 %d, 跳过 %d",
                sheet_name,
                sheet_stats["success"],
                sheet_stats["fail"],
                sheet_stats["skipped"],
            )

    logger.info("")
    logger.info("=" * 60)
    logger.info("导入结果汇总")
    logger.info("=" * 60)
    logger.info("总计 - 成功: %d 条", total_stats["success"])
    logger.info("总计 - 失败: %d 条", total_stats["fail"])
    logger.info("总计 - 跳过: %d 条", total_stats["skipped"])
    logger.info("=" * 60)

    if total_stats["fail"] > 0:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
