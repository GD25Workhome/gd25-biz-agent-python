"""
运行脚本
用于启动 FastAPI 应用

使用方式：
    方式1：从项目根目录运行
        cd 01_Agent
        python run.py
    
    方式2：从任意目录运行（使用绝对路径）
        python /path/to/01_Agent/run.py
    
    方式3：使用 uvicorn 直接运行
        cd 01_Agent
        uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
"""
import sys
import os
from pathlib import Path

# 添加项目根目录到 Python 路径（使用绝对路径，确保从任意目录运行都能工作）
_file_path = Path(__file__).resolve()  # 获取文件的绝对路径
project_root = _file_path.parent  # run.py -> 01_Agent

# 确保项目根目录在 sys.path 中（避免重复添加）
project_root_str = str(project_root)
if project_root_str not in sys.path:
    sys.path.insert(0, project_root_str)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "backend.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )

