"""
扫描场景记录目录，返回待处理的 md 文件路径列表（支持白名单过滤）。
"""
import re
from pathlib import Path
from typing import List, Optional

from scripts.create_rag_data.core.config import (
    get_scene_records_absolute_dir,
    INCLUDE_FILES,
    get_project_root,
)


# 匹配以数字开头的 md 文件名，如 01-xxx.md、02-xxx.md（排除 00-索引-xxx.md）
_NUM_PREFIX_PATTERN = re.compile(r"^(\d{2})-.+\.md$")


def get_md_paths() -> List[Path]:
    """
    获取待处理的 md 文件绝对路径列表。

    若 INCLUDE_FILES 非空，仅返回白名单中的文件（按文件名匹配）；
    否则返回目录下所有匹配 NN-*.md 的文件（N 为数字），排除 00- 开头的索引文件。

    Returns:
        待处理 md 的绝对路径列表，按文件名排序。
    """
    base_dir = get_scene_records_absolute_dir()
    if not base_dir.exists():
        return []

    if INCLUDE_FILES:
        paths = []
        for name in INCLUDE_FILES:
            p = base_dir / name
            if p.exists() and p.suffix.lower() == ".md":
                paths.append(p)
        return sorted(paths)

    paths = []
    for f in base_dir.iterdir():
        if not f.is_file() or f.suffix.lower() != ".md":
            continue
        if _NUM_PREFIX_PATTERN.match(f.name) and not f.name.startswith("00-"):
            paths.append(f)
    return sorted(paths)


def path_to_relative(path: Path) -> str:
    """
    将绝对路径转为相对于项目根的路径（用于 source_meta.source_file）。

    Args:
        path: 文件绝对路径。

    Returns:
        相对路径字符串，使用 / 分隔。
    """
    root = get_project_root()
    try:
        rel = path.resolve().relative_to(root.resolve())
    except ValueError:
        return str(path)
    return str(rel).replace("\\", "/")
