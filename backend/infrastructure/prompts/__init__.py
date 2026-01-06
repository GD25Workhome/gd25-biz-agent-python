"""
提示词管理模块
"""
from backend.infrastructure.prompts.manager import PromptManager, prompt_manager
from backend.infrastructure.prompts.loader import PromptLoader

__all__ = ["PromptManager", "prompt_manager", "PromptLoader"]
