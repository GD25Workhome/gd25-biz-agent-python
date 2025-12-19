"""
数据加载器模块
支持从不同数据源加载提示词模块内容
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


class DataLoader(ABC):
    """数据加载器基类"""
    
    @abstractmethod
    def load(self, source: str, context: Optional[Dict[str, Any]] = None) -> str:
        """
        加载数据
        
        Args:
            source: 数据源（文件路径、数据库URI等）
            context: 上下文信息（用于动态加载）
        
        Returns:
            加载的内容字符串
        """
        pass
    
    @abstractmethod
    def supports(self, source: str) -> bool:
        """
        检查是否支持该数据源
        
        Args:
            source: 数据源字符串
        
        Returns:
            是否支持该数据源
        """
        pass


class ConfigLoader(DataLoader):
    """配置文件加载器"""
    
    def load(self, source: str, context: Optional[Dict[str, Any]] = None) -> str:
        """
        从配置文件加载内容
        
        Args:
            source: 文件路径（相对或绝对路径）
            context: 上下文信息（未使用）
        
        Returns:
            文件内容
        """
        file_path = Path(source)
        
        # 如果是相对路径，尝试从项目根目录查找
        if not file_path.is_absolute():
            # 尝试从当前工作目录查找
            if not file_path.exists():
                # 尝试从config目录查找
                config_path = Path("config") / file_path
                if config_path.exists():
                    file_path = config_path
                else:
                    # 尝试从项目根目录查找
                    root_path = Path.cwd() / file_path
                    if root_path.exists():
                        file_path = root_path
        
        if not file_path.exists():
            raise FileNotFoundError(f"文件不存在: {source} (尝试路径: {file_path})")
        
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
            logger.debug(f"成功加载文件: {file_path}")
            return content
        except Exception as e:
            logger.error(f"加载文件失败: {file_path}, 错误: {str(e)}")
            raise
    
    def supports(self, source: str) -> bool:
        """检查是否支持该数据源"""
        # ConfigLoader只支持config/开头的路径
        # 不匹配普通文件路径，避免与FileLoader冲突
        return source.startswith("config/")


class FileLoader(DataLoader):
    """文件加载器（通用文件路径）"""
    
    def load(self, source: str, context: Optional[Dict[str, Any]] = None) -> str:
        """
        从文件路径加载内容
        
        Args:
            source: 文件路径
            context: 上下文信息（未使用）
        
        Returns:
            文件内容
        """
        file_path = Path(source)
        
        if not file_path.exists():
            raise FileNotFoundError(f"文件不存在: {source}")
        
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
            logger.debug(f"成功加载文件: {file_path}")
            return content
        except Exception as e:
            logger.error(f"加载文件失败: {file_path}, 错误: {str(e)}")
            raise
    
    def supports(self, source: str) -> bool:
        """检查是否支持该数据源"""
        # 检查是否是有效的文件路径
        # 如果包含斜杠或反斜杠，且不是以特殊协议开头，认为是文件路径
        # 但是config/开头的路径应该由ConfigLoader处理
        # 排除所有以协议形式开头的路径（如 custom://, database:// 等）
        if "/" in source or "\\" in source:
            # 检查是否以协议形式开头（包含 ://）
            if "://" in source:
                return False
            # 排除特殊协议和config路径
            if not source.startswith(("http://", "https://", "database://", "runtime", "config/", "custom://")):
                return True
        return False


class DynamicLoader(DataLoader):
    """动态加载器（运行时构建）"""
    
    def load(self, source: str, context: Optional[Dict[str, Any]] = None) -> str:
        """
        根据上下文动态构建内容
        
        Args:
            source: 数据源标识（如 "runtime"）
            context: 上下文信息
        
        Returns:
            动态构建的内容
        """
        if source == "runtime" and context:
            return self._build_from_context(context)
        return ""
    
    def supports(self, source: str) -> bool:
        """检查是否支持该数据源"""
        return source == "runtime"
    
    def _build_from_context(self, context: Dict[str, Any]) -> str:
        """
        根据上下文构建内容
        
        Args:
            context: 上下文信息
        
        Returns:
            构建的内容
        """
        # 基础的用户信息构建
        user_id = context.get("user_id")
        if user_id:
            # 如果有表单信息，构建更详细的内容
            collected_fields = context.get("collected_fields", "")
            missing_fields = context.get("missing_fields", "")
            
            if collected_fields or missing_fields:
                # 血压表单上下文
                parts = [f"系统提供的用户ID：{user_id}。"]
                if collected_fields:
                    parts.append(f"已收集字段：{collected_fields}。")
                if missing_fields:
                    parts.append(f"待补全字段（必填优先）：{missing_fields}。")
                parts.append("请只询问缺失字段，字段齐全时直接调用工具，不要重复询问已提供的数据。")
                return "\n".join(parts)
            else:
                # 简单的用户ID提示
                return f"系统提供的用户ID：{user_id}。调用工具时直接使用该 user_id，无需向用户索取。"
        
        return ""


class DatabaseLoader(DataLoader):
    """数据库加载器（预留扩展）"""
    
    def load(self, source: str, context: Optional[Dict[str, Any]] = None) -> str:
        """
        从数据库加载内容（当前版本未实现）
        
        Args:
            source: 数据库URI（如 database://prompts/blood_pressure/role）
            context: 上下文信息
        
        Returns:
            数据库中的内容
        
        Raises:
            NotImplementedError: 当前版本未实现
        """
        # TODO: 实现数据库加载逻辑
        logger.warning(f"数据库加载器当前版本未实现，尝试加载: {source}")
        raise NotImplementedError("数据库加载器当前版本未实现，请使用配置文件加载器")
    
    def supports(self, source: str) -> bool:
        """检查是否支持该数据源"""
        return source.startswith("database://")
