"""
提示词加载器
负责从本地文件加载提示词
"""
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class PromptLoader:
    """提示词加载器"""
    
    @staticmethod
    def load_from_file(file_path: Path) -> str:
        """
        从文件加载提示词
        
        Args:
            file_path: 提示词文件路径
            
        Returns:
            str: 提示词内容
            
        Raises:
            FileNotFoundError: 文件不存在
            IOError: 文件读取失败
        """
        if not file_path.exists():
            raise FileNotFoundError(f"提示词文件不存在: {file_path}")
        
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read().strip()
            
            logger.debug(f"成功加载提示词文件: {file_path}")
            return content
            
        except Exception as e:
            raise IOError(f"读取提示词文件失败: {file_path}, 错误: {e}")
    
    @staticmethod
    def resolve_path(prompt_path: str, flow_dir: str) -> Path:
        """
        解析提示词路径（将相对路径解析为绝对路径）
        
        Args:
            prompt_path: 提示词路径（相对于流程目录）
            flow_dir: 流程目录路径
            
        Returns:
            Path: 解析后的绝对路径
        """
        flow_dir_path = Path(flow_dir)
        prompt_path_obj = Path(prompt_path)
        
        # 如果是绝对路径，直接返回
        if prompt_path_obj.is_absolute():
            return prompt_path_obj
        
        # 否则，相对于流程目录解析
        resolved_path = flow_dir_path / prompt_path_obj
        return resolved_path.resolve()

