"""
测试配置和共享 Fixtures
"""
import sys
import os
from pathlib import Path

# 将项目根目录添加到 Python 路径
# 获取 conftest.py 所在目录的父目录的父目录（项目根目录）
project_root = Path(__file__).parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

