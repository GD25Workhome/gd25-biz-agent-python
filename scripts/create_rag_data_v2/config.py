"""
create_rag_data_v2 脚本配置模块。

本模块负责集中管理脚本级配置，避免在业务逻辑中出现硬编码。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List

from backend.app.config import find_project_root


@dataclass
class CreateRagDataConfig:
    """
    create_rag_data_v2 脚本运行配置。
    """

    base_dir: Path
    """原始 md 文件根目录，例如 cursor_docs/012802-QA场景独立记录。"""

    include_files: List[str]
    """需要处理的文件名称白名单，空列表表示处理目录下所有 .md 文件。"""

    exclude_files: List[str]
    """需要显式排除的文件名称列表。"""

    max_concurrency: int
    """最大并发处理的文件数量。"""

    retry_times: int
    """单个文件失败时的最大重试次数。"""

    flow_key: str
    """FlowManager 中的流程 key，例如 create_rag_agent。"""

    dry_run: bool = False
    """是否只跑流程不真正入库（调试时使用）。"""


def _get_project_root() -> Path:
    """
    获取项目根目录。

    Returns:
        Path: 项目根路径。
    """

    return find_project_root()


def load_config() -> CreateRagDataConfig:
    """
    加载 create_rag_data_v2 运行配置。

    注意：
    - 所有配置均在代码中固定，不依赖环境变量；
    - 若需调整范围或并发参数，请直接修改本函数中的常量并提交代码。
    """

    project_root = _get_project_root()

    # 基础目录：固定为 QA 场景独立记录目录
    base_dir = project_root / "cursor_docs/012802-QA场景独立记录"

    # 仅处理的文件白名单：默认只跑示例文件，避免误处理大量文件
    # include_files = ["01-诊疗-场景1-疾病诊断与费用等.md"]
    include_files = None

    # 显式排除列表：当前为空，如需排除部分文件可在此处追加文件名
    exclude_files: List[str] = []

    # 并发与重试策略：固定配置
    max_concurrency = 3
    retry_times = 0

    # 流程 key 与 dry_run：与 flow.yaml 中的 name 保持一致
    flow_key = "create_rag_agent"
    dry_run = False

    return CreateRagDataConfig(
        base_dir=base_dir,
        include_files=include_files,
        exclude_files=exclude_files,
        max_concurrency=max_concurrency,
        retry_times=retry_times,
        flow_key=flow_key,
        dry_run=dry_run,
    )


__all__ = [
    "CreateRagDataConfig",
    "load_config",
]

