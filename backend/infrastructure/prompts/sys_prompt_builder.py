"""
系统提示词构建器
负责在运行时构建系统提示词，替换占位符
"""
import json
import logging
import re
from typing import Dict, Any, Optional
from langchain_core.messages import SystemMessage

from backend.domain.state import FlowState
from backend.infrastructure.prompts.manager import prompt_manager

logger = logging.getLogger(__name__)


def build_system_message(
    prompt_cache_key: str,
    state: FlowState
) -> SystemMessage:
    """
    构建系统消息，替换提示词中的占位符
    
    该方法会：
    1. 从 FlowState 中提取 prompt_vars
    2. 从提示词缓存中获取系统提示词模板
    3. 使用 prompt_vars 字典中的值替换占位符
    4. 将替换后的提示词封装为 SystemMessage
    
    支持的占位符格式：
    - {current_date}: 当前日期时间
    - {user_info}: 患者基础信息
    - 其他在 prompt_vars 中定义的占位符
    
    注意：只替换在 prompt_vars 中明确存在的占位符。
    如果占位符不在 prompt_vars 中，将保留原样（不进行替换）。
    
    Args:
        prompt_cache_key: 提示词缓存键（通过 prompt_manager.cached_prompt 获取）
        state: 流程状态，从中提取 prompt_vars 字典
        
    Returns:
        SystemMessage: 封装后的系统消息对象
        
    Example:
        >>> state = {"prompt_vars": {"current_date": "2024-01-01 10:00:00", "user_info": {...}}}
        >>> sys_msg = build_system_message("prompt_key", state)
    """
    # 从 FlowState 中提取 prompt_vars
    prompt_vars = state.get("prompt_vars")
    if prompt_vars is None:
        prompt_vars = {}
    
    # 获取系统提示词模板
    system_prompt_template = prompt_manager.get_prompt_by_key(prompt_cache_key)
    
    # 将 prompt_vars 中的值转换为字符串（None 转换为空字符串）
    safe_vars = {}
    for key, value in prompt_vars.items():
        if value is None:
            safe_vars[key] = ""
        elif isinstance(value, (dict, list)):
            # 如果是字典或列表，格式化为 JSON 字符串
            safe_vars[key] = json.dumps(value, ensure_ascii=False, indent=2)
        else:
            safe_vars[key] = str(value)
    
    # 使用正则表达式替换占位符（支持 {variable} 格式）
    # 只替换在 safe_vars 中存在的占位符，其他保留原样
    def replace_placeholder(match):
        """替换占位符的回调函数"""
        placeholder_name = match.group(1)  # 提取占位符名称（不含花括号）
        # 从 safe_vars 中获取值，如果不存在则保留原占位符
        if placeholder_name in safe_vars:
            return safe_vars[placeholder_name]
        else:
            # 不在 prompt_vars 中的占位符，保留原样
            return match.group(0)
    
    # 匹配 {variable} 格式的占位符
    pattern = r'\{([^}]+)\}'
    system_prompt = re.sub(pattern, replace_placeholder, system_prompt_template)
    
    logger.debug(
        f"构建系统消息: prompt_cache_key={prompt_cache_key}, "
        f"占位符数量={len(safe_vars)}, "
        f"提示词长度={len(system_prompt)}"
    )
    
    # 将系统提示词封装为 SystemMessage
    sys_msg = SystemMessage(content=system_prompt)
    
    return sys_msg

