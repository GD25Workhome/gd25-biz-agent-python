"""
TokenId 数据转换工具
将 tokenId 转换为用户信息
"""
from typing import Dict, Optional
from dataclasses import dataclass


@dataclass
class UserInfo:
    """
    用户信息数据类
    
    当前阶段：只包含 user_id
    未来阶段：可以扩展更多属性（如用户姓名、年龄、病史等）
    """
    user_id: str


def convert_token_to_user_info(token_id: str) -> UserInfo:
    """
    将 tokenId 转换为用户信息
    
    当前场景：直接返回 UserInfo(user_id=token_id)
    未来场景：通过 token_id 查询业务系统，获取完整的用户信息
    
    Args:
        token_id: 令牌ID
        
    Returns:
        UserInfo 对象，包含用户信息
        
    示例：
        # 当前阶段
        user_info = convert_token_to_user_info("user123")
        # user_info.user_id == "user123"
        
        # 未来阶段（示例）
        # user_info = convert_token_to_user_info("token_abc123")
        # user_info.user_id == "user123"  # 从业务系统获取
        # user_info.name == "张三"  # 从业务系统获取
        # user_info.age == 45  # 从业务系统获取
    """
    # 当前实现：直接返回 UserInfo(user_id=token_id)
    return UserInfo(user_id=token_id)
    
    # 未来实现示例：
    # from infrastructure.business_system.client import BusinessSystemClient
    # client = BusinessSystemClient()
    # user_data = client.get_user_by_token(token_id)
    # return UserInfo(
    #     user_id=user_data.user_id,
    #     name=user_data.name,
    #     age=user_data.age,
    #     # ... 更多属性
    # )


def convert_token_to_user_id(token_id: str) -> str:
    """
    将 tokenId 转换为 userId（便捷方法）
    
    Args:
        token_id: 令牌ID
        
    Returns:
        用户ID
    """
    user_info = convert_token_to_user_info(token_id)
    return user_info.user_id

