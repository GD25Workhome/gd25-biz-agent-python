"""
create_rag_data_v2 脚本包

本包用于将 QA 场景独立记录（Markdown 文件）通过 create_rag_agent 流程
转换为结构化 cases，并写入知识库表。

注意：
- 仅复用 scripts/embedding_import 的设计思路，不直接导入其内部实现；
- 具体业务节点（insert_rag_data_node）在 backend.domain.flows.implementations 中实现。
"""

from __future__ import annotations

__all__ = [
    "config",
    "file_loader",
    "state_builder",
    "parser",
    "repository",
    "flow_runner",
]

