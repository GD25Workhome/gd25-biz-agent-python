"""
LangChain reasoning_content 提取补丁

通过 monkey patch 的方式，让 LangChain 保留 reasoning_content 字段
"""
import logging
from typing import Mapping, Any

logger = logging.getLogger(__name__)

# 全局标志，确保只应用一次
_patch_applied = False


def apply_reasoning_patch() -> bool:
    """
    应用 reasoning_content 提取补丁
    
    必须在导入 ChatOpenAI 之前调用
    
    Returns:
        bool: 是否成功应用补丁
    """
    global _patch_applied
    
    if _patch_applied:
        logger.debug("reasoning_content 补丁已应用，跳过重复应用")
        return True
    
    try:
        from langchain_openai.chat_models.base import _convert_dict_to_message as _original_convert
        import langchain_openai.chat_models.base
        from langchain_core.messages import AIMessage
        
        def _enhanced_convert_dict_to_message(_dict: Mapping[str, Any]):
            """
            增强版的消息转换函数，保留 reasoning_content
            
            原理：在调用原始函数后，检查原始字典中是否有 reasoning_content，
            如果有，则将其添加到 additional_kwargs 中
            """
            # 调用原始函数
            message = _original_convert(_dict)
            
            # 如果是 AIMessage 且原始字典包含 reasoning_content
            if isinstance(message, AIMessage) and 'reasoning_content' in _dict:
                reasoning_content = _dict.get('reasoning_content')
                if reasoning_content:
                    # 确保 additional_kwargs 存在
                    if not hasattr(message, 'additional_kwargs') or message.additional_kwargs is None:
                        message.additional_kwargs = {}
                    # 添加 reasoning_content
                    message.additional_kwargs['reasoning_content'] = reasoning_content
                    logger.debug(f"已提取 reasoning_content，长度: {len(reasoning_content)} 字符")
            
            return message
        
        # 应用 monkey patch
        langchain_openai.chat_models.base._convert_dict_to_message = _enhanced_convert_dict_to_message
        _patch_applied = True
        logger.info("✅ 已应用 reasoning_content 提取补丁")
        return True
    except Exception as e:
        logger.error(f"❌ 应用 reasoning_content 补丁失败: {e}", exc_info=True)
        return False

