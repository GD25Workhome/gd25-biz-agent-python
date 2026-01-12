"""
用户信息：用户相关信息
用于存储用户信息、偏好和设置
"""
import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class UserInfo:
    """
    用户信息：用户相关信息
    
    用于存储用户基本信息、偏好设置等，
    支持提示词个性化和用户信息访问。
    """
    
    def __init__(self, user_id: str):
        """
        初始化用户信息
        
        Args:
            user_id: 用户ID
        """
        self.user_id = user_id
        self._data: Dict[str, Any] = {
            "user_id": user_id,
            "preferences": {},
            "settings": {},
            "user_info": None,  # 用户基本信息（JSON格式）
        }
        logger.debug(f"创建UserInfo实例: user_id={user_id}")
    
    def set_preference(self, key: str, value: Any) -> None:
        """
        设置用户偏好
        
        Args:
            key: 偏好键
            value: 偏好值
        """
        self._data["preferences"][key] = value
        logger.debug(f"UserInfo设置偏好: user_id={self.user_id}, key={key}")
    
    def get_preference(self, key: str, default: Any = None) -> Any:
        """
        获取用户偏好
        
        Args:
            key: 偏好键
            default: 默认值（如果键不存在）
            
        Returns:
            偏好值，如果键不存在则返回默认值
        """
        return self._data["preferences"].get(key, default)
    
    def set_setting(self, key: str, value: Any) -> None:
        """
        设置用户设置
        
        Args:
            key: 设置键
            value: 设置值
        """
        self._data["settings"][key] = value
        logger.debug(f"UserInfo设置设置: user_id={self.user_id}, key={key}")
    
    def get_setting(self, key: str, default: Any = None) -> Any:
        """
        获取用户设置
        
        Args:
            key: 设置键
            default: 默认值（如果键不存在）
            
        Returns:
            设置值，如果键不存在则返回默认值
        """
        return self._data["settings"].get(key, default)
    
    def set_user_info(self, user_info: Optional[Dict[str, Any]]) -> None:
        """
        设置用户基本信息
        
        Args:
            user_info: 用户基本信息字典（JSON格式）
        """
        self._data["user_info"] = user_info
        logger.debug(f"UserInfo设置用户信息: user_id={self.user_id}")
    
    def get_user_info(self) -> Optional[Dict[str, Any]]:
        """
        获取用户基本信息
        
        Returns:
            用户基本信息字典，如果未设置则返回None
        """
        return self._data.get("user_info")
    
    def update(self, data: Dict[str, Any]) -> None:
        """
        批量更新数据
        
        Args:
            data: 要更新的数据字典
        """
        # 特殊处理preferences和settings
        if "preferences" in data and isinstance(data["preferences"], dict):
            self._data["preferences"].update(data["preferences"])
            data = {k: v for k, v in data.items() if k != "preferences"}
        
        if "settings" in data and isinstance(data["settings"], dict):
            self._data["settings"].update(data["settings"])
            data = {k: v for k, v in data.items() if k != "settings"}
        
        # 更新其他数据
        self._data.update(data)
        logger.debug(f"UserInfo批量更新数据: user_id={self.user_id}, keys={list(data.keys())}")
    
    @property
    def data(self) -> Dict[str, Any]:
        """
        获取所有数据的副本
        
        Returns:
            所有数据的字典副本
        """
        return self._data.copy()
    
    @property
    def preferences(self) -> Dict[str, Any]:
        """
        获取所有用户偏好
        
        Returns:
            用户偏好字典
        """
        return self._data["preferences"].copy()
    
    @property
    def settings(self) -> Dict[str, Any]:
        """
        获取所有用户设置
        
        Returns:
            用户设置字典
        """
        return self._data["settings"].copy()
    
    def __repr__(self) -> str:
        """返回对象的字符串表示"""
        return f"UserInfo(user_id={self.user_id}, preferences={len(self._data['preferences'])}, settings={len(self._data['settings'])})"

