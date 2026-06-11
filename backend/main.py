"""
FastAPI 应用入口（组合根）

开发环境运行方式（均启用 reload，代码变更自动重启）：
    方式1：直接运行
        python backend/main.py

    方式2：模块方式运行
        python -m backend.main

    方式3：uvicorn 命令行
        uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000

访问地址：
    http://localhost:8000/static/index.html

说明：
    应用组装逻辑见 backend.app.factory.create_app()。
    以上方式均为开发模式，生产环境请去掉 --reload 并配置多 worker，
    例如：uvicorn backend.main:app --host 0.0.0.0 --port 8000 --workers 4
"""
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径（必须在导入 backend 模块之前）
_file_path = Path(__file__).resolve()
project_root = _file_path.parent.parent
project_root_str = str(project_root)
if project_root_str not in sys.path:
    sys.path.insert(0, project_root_str)

from backend.app.factory import create_app

app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "backend.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info",
        reload_dirs=[str(project_root)] if project_root.exists() else None,
    )
