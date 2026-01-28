"""
Markdown 文件加载模块。

负责根据配置扫描目录、过滤目标文件，并读取 Markdown 内容，
为后续 state 构建与 Flow 调用提供输入。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List

from .config import CreateRagDataConfig


@dataclass
class MarkdownSource:
    """
    单个 Markdown 源文件的信息封装。

    Attributes:
        source_path: 以项目根目录为基准的相对路径，用于写入 source_meta.source_file。
        abs_path:    文件的绝对路径，用于实际读取内容。
        raw_markdown: 文件完整内容，用于 raw_material_full_text 与 scene_record_content。
    """

    source_path: str
    abs_path: Path
    raw_markdown: str


def list_markdown_files(cfg: CreateRagDataConfig) -> List[Path]:
    """
    根据配置枚举需要处理的 Markdown 文件绝对路径列表。

    过滤规则：
        - 仅保留扩展名为 .md 的文件；
        - 若 include_files 非空，仅保留文件名在白名单中的文件；
        - 再排除 exclude_files 中的文件名。
    """

    base_dir = cfg.base_dir
    if not base_dir.exists() or not base_dir.is_dir():
        raise FileNotFoundError(f"场景记录目录不存在或不是目录: {base_dir}")

    all_md_files: List[Path] = [p for p in base_dir.glob("*.md") if p.is_file()]

    # 按 include / exclude 做过滤
    include_set = set(cfg.include_files) if cfg.include_files else set()
    exclude_set = set(cfg.exclude_files) if cfg.exclude_files else set()

    filtered: List[Path] = []
    for path in all_md_files:
        name = path.name
        if include_set and name not in include_set:
            continue
        if name in exclude_set:
            continue
        filtered.append(path)

    return filtered


def load_markdown(path: Path, project_root: Path) -> MarkdownSource:
    """
    读取单个 Markdown 文件并构造 MarkdownSource。

    Args:
        path:         Markdown 文件绝对路径。
        project_root: 项目根目录，用于计算相对路径。

    Returns:
        MarkdownSource: 包含相对路径和完整内容的封装对象。
    """

    if not path.exists():
        raise FileNotFoundError(f"Markdown 文件不存在: {path}")
    if not path.is_file():
        raise IsADirectoryError(f"路径不是文件: {path}")

    relative_path = path.relative_to(project_root)
    raw_text = path.read_text(encoding="utf-8")

    return MarkdownSource(
        source_path=str(relative_path),
        abs_path=path,
        raw_markdown=raw_text,
    )


def load_all_markdowns(cfg: CreateRagDataConfig, project_root: Path) -> List[MarkdownSource]:
    """
    读取配置指定目录下的所有 Markdown 文件。

    Args:
        cfg:           运行配置。
        project_root:  项目根目录。

    Returns:
        List[MarkdownSource]: MarkdownSource 列表。
    """

    paths = list_markdown_files(cfg)
    return [load_markdown(path, project_root) for path in paths]


__all__ = [
    "MarkdownSource",
    "list_markdown_files",
    "load_markdown",
    "load_all_markdowns",
]

