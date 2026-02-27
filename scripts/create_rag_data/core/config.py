"""
create_rag_data 脚本常量与配置

流程 key、场景记录目录、并发数、待处理文件白名单等；模型由 flow yaml 决定。
"""
from pathlib import Path
from typing import List, Optional

# 单节点 flow 的 name，用于 FlowManager.get_flow
CREATE_RAG_AGENT_FLOW_KEY: str = "create_rag_agent"

# 场景记录目录（相对于项目根）
SCENE_RECORDS_DIR: str = "cursor_docs/012802-QA场景独立记录"

# 最大并发处理文件数
MAX_CONCURRENT: int = 3

# 待处理文件白名单：仅处理列表中的文件名；空或 None 表示处理目录下所有 NN-*.md
# 示例：INCLUDE_FILES = ["01-诊疗-场景1-疾病诊断与费用等.md", "16-危重症-01-胸痛.md"]
# INCLUDE_FILES: Optional[List[str]] = None
INCLUDE_FILES = ["01-诊疗-场景1-疾病诊断与费用等.md"]

# 提示词模板路径（相对于项目根，供文档/脚本读模板用；flow 内已配置则以此为准）
PROMPT_TEMPLATE_PATH: str = "scripts/create_rag_data/create_rag_agent.md"


def get_project_root() -> Path:
    """获取项目根目录。"""
    from backend.app.config import find_project_root
    return find_project_root()


def get_scene_records_absolute_dir() -> Path:
    """场景记录目录的绝对路径。"""
    return get_project_root() / SCENE_RECORDS_DIR
