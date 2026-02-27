"""
Feishu Excel 导入 Langfuse Datasets - 委托入口

主入口已迁移至 import_feishu_excel.py，本文件保留以兼容旧调用方式。
"""
import sys
from pathlib import Path

# 确保项目根目录在路径中（import_feishu_excel 使用完整包路径）
project_root = Path(__file__).resolve().parent.parent.parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from scripts.import_to_datasets.feishu_ceshi_case.import_feishu_excel import main

if __name__ == "__main__":
    main()
