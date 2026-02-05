"""
数据导入流程模块

实现「读取器 → 清洗器 → 入库执行器」三阶段导入流程。
设计文档：cursor_docs/020402-数据导入流程技术设计.md
"""
from backend.pipeline.import_service import execute_import, ImportResult

__all__ = ["execute_import", "ImportResult"]
