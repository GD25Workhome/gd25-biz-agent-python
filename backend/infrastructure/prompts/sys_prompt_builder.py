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


# edges_var 中用于提示词占位符的专属 key，仅遍历其下级属性参与替换
EDGES_PROMPT_VARS_KEY = "edges_prompt_vars"

def build_system_message(
    prompt_cache_key: str,
    state: FlowState
) -> SystemMessage:
    """
    构建系统消息，替换提示词中的占位符
    
    该方法会：
    1. 从 FlowState 中提取 prompt_vars
    2. 从 edges_var[edges_prompt_vars] 中提取节点专属、临时变量（通常来自上一节点）
    3. 从提示词缓存中获取系统提示词模板
    4. 使用上述变量替换占位符（同名时 edges_prompt_vars 优先于 prompt_vars）
    5. 将替换后的提示词封装为 SystemMessage
    
    占位符来源：
    - prompt_vars：全局/会话级变量（如 current_date、user_info）
    - edges_var["edges_prompt_vars"]：仅遍历该 key 的下级属性，用于节点专属临时值
    
    注意：只替换在解析池中存在的占位符，未匹配的保留原样。
    
    Args:
        prompt_cache_key: 提示词缓存键（通过 prompt_manager.cached_prompt 获取）
        state: 流程状态，从中提取 prompt_vars 与 edges_var
        
    Returns:
        SystemMessage: 封装后的系统消息对象
    """
    # 1. 提取 prompt_vars 并转为安全字典
    prompt_vars = state.get("prompt_vars")
    if not isinstance(prompt_vars, dict):
        prompt_vars = {}
    safe_vars = _to_safe_vars(prompt_vars)
    
    # 2. 提取 edges_var[edges_prompt_vars] 的下级属性并转为安全字典，覆盖同名 key
    edges_var = state.get("edges_var")
    if isinstance(edges_var, dict):
        edges_prompt_vars = edges_var.get(EDGES_PROMPT_VARS_KEY)
        if isinstance(edges_prompt_vars, dict):
            safe_edges = _to_safe_vars(edges_prompt_vars)
            safe_vars = {**safe_vars, **safe_edges}
    
    # 3. 获取系统提示词模板
    system_prompt_template = prompt_manager.get_prompt_by_key(prompt_cache_key)
    
    # 4. 替换占位符：仅替换解析池中存在的，其余保留原样
    def replace_placeholder(match):
        placeholder_name = match.group(1)
        if placeholder_name in safe_vars:
            return safe_vars[placeholder_name]
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



def _to_safe_vars(raw: Dict[str, Any]) -> Dict[str, str]:
    """将原始变量字典转为占位符可用的安全字符串字典。"""
    if not isinstance(raw, dict):
        return {}
    out: Dict[str, str] = {}
    for key, value in raw.items():
        if value is None:
            out[key] = ""
        elif isinstance(value, (dict, list)):
            out[key] = json.dumps(value, ensure_ascii=False, indent=2)
        else:
            out[key] = str(value)
    return out
