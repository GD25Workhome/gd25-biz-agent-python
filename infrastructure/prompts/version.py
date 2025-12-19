"""
版本管理器
管理提示词版本，支持版本保存、查询和回滚
"""
from typing import Dict, List, Optional, Any
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class VersionManager:
    """版本管理器"""
    
    def __init__(self):
        """初始化版本管理器"""
        self._versions: Dict[str, List[Dict[str, Any]]] = {}
        logger.info("版本管理器已初始化")
    
    def save_version(
        self,
        agent_key: str,
        prompt: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> int:
        """
        保存提示词版本
        
        Args:
            agent_key: Agent键名
            prompt: 提示词内容
            metadata: 元数据（可选）
        
        Returns:
            版本号（从1开始）
        """
        if agent_key not in self._versions:
            self._versions[agent_key] = []
        
        version_number = len(self._versions[agent_key]) + 1
        
        version_info = {
            "version": version_number,
            "prompt": prompt,
            "timestamp": datetime.now().isoformat(),
            "metadata": metadata or {}
        }
        
        self._versions[agent_key].append(version_info)
        logger.info(f"保存提示词版本: {agent_key}, 版本: {version_number}")
        
        return version_number
    
    def get_version(self, agent_key: str, version: int) -> Optional[str]:
        """
        获取指定版本的提示词
        
        Args:
            agent_key: Agent键名
            version: 版本号（从1开始）
        
        Returns:
            提示词内容，如果版本不存在则返回None
        """
        if agent_key not in self._versions:
            return None
        
        versions = self._versions[agent_key]
        if 0 < version <= len(versions):
            return versions[version - 1]["prompt"]
        
        return None
    
    def get_version_info(self, agent_key: str, version: int) -> Optional[Dict[str, Any]]:
        """
        获取指定版本的完整信息
        
        Args:
            agent_key: Agent键名
            version: 版本号
        
        Returns:
            版本信息字典，如果版本不存在则返回None
        """
        if agent_key not in self._versions:
            return None
        
        versions = self._versions[agent_key]
        if 0 < version <= len(versions):
            return versions[version - 1]
        
        return None
    
    def list_versions(self, agent_key: str) -> List[Dict[str, Any]]:
        """
        列出所有版本
        
        Args:
            agent_key: Agent键名
        
        Returns:
            版本信息列表
        """
        if agent_key not in self._versions:
            return []
        
        # 返回版本列表（不包含完整的prompt内容，只包含元数据）
        return [
            {
                "version": v["version"],
                "timestamp": v["timestamp"],
                "metadata": v["metadata"],
                "prompt_length": len(v["prompt"])
            }
            for v in self._versions[agent_key]
        ]
    
    def get_latest_version(self, agent_key: str) -> Optional[int]:
        """
        获取最新版本号
        
        Args:
            agent_key: Agent键名
        
        Returns:
            最新版本号，如果没有版本则返回None
        """
        if agent_key not in self._versions or not self._versions[agent_key]:
            return None
        
        return len(self._versions[agent_key])
    
    def rollback(self, agent_key: str, version: int) -> bool:
        """
        回滚到指定版本（标记为回滚操作）
        
        注意：此方法只记录回滚操作，实际的回滚需要调用者重新加载模板
        
        Args:
            agent_key: Agent键名
            version: 目标版本号
        
        Returns:
            是否成功
        """
        version_info = self.get_version_info(agent_key, version)
        if not version_info:
            logger.warning(f"无法回滚: {agent_key}, 版本 {version} 不存在")
            return False
        
        logger.info(f"回滚提示词: {agent_key}, 到版本: {version}")
        # 这里可以添加回滚逻辑，比如通知PromptManager重新加载
        return True
    
    def clear_versions(self, agent_key: str):
        """
        清除所有版本记录
        
        Args:
            agent_key: Agent键名
        """
        if agent_key in self._versions:
            del self._versions[agent_key]
            logger.info(f"已清除版本记录: {agent_key}")
