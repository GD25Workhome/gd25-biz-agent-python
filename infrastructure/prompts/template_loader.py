"""
统一的提示词模板加载服务
负责从 Langfuse 或本地文件加载提示词模板
"""
from typing import Optional
from pathlib import Path
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)


class AgentTemplateLoader:
    """Agent 提示词模板加载器"""
    
    @staticmethod
    def load_template(agent_key: str, agent_config: dict) -> str:
        """
        加载 Agent 的提示词模板（统一入口）
        
        Args:
            agent_key: Agent键名
            agent_config: Agent配置字典
            
        Returns:
            提示词模板内容（包含占位符）
            
        Raises:
            ValueError: 无法加载模板
            FileNotFoundError: 本地文件不存在（当模式为local时）
        """
        prompt_source_mode = settings.PROMPT_SOURCE_MODE.lower()
        template = None
        
        # 从Langfuse加载提示词（如果模式为langfuse或auto）
        if prompt_source_mode in ("langfuse", "auto"):
            langfuse_template = agent_config.get("langfuse_template")
            if langfuse_template:
                try:
                    from infrastructure.prompts.langfuse_adapter import LangfusePromptAdapter
                    adapter = LangfusePromptAdapter()
                    template_version = agent_config.get("langfuse_template_version")
                    
                    template = adapter.get_template(
                        template_name=langfuse_template,
                        version=template_version
                    )
                    
                    logger.debug(f"从Langfuse加载提示词模板: {agent_key}, 模版: {langfuse_template}")
                    return template
                except Exception as e:
                    logger.warning(f"从Langfuse加载提示词模板失败: {agent_key}, 错误: {str(e)}")
                    if prompt_source_mode == "langfuse":
                        raise ValueError(f"无法从Langfuse加载提示词模板: {agent_key}, 错误: {str(e)}")
                    # 如果模式为auto，继续尝试从本地文件加载
                    logger.debug(f"尝试从本地文件加载提示词模板: {agent_key}")
            else:
                if prompt_source_mode == "langfuse":
                    raise ValueError(f"Agent {agent_key} 未配置 langfuse_template，请配置 Langfuse 模版名称")
                # 如果模式为auto，继续尝试从本地文件加载
                logger.debug(f"Agent {agent_key} 未配置 langfuse_template，尝试从本地文件加载")
        
        # 从本地文件加载提示词（如果模式为local，或auto模式下Langfuse失败）
        if not template and prompt_source_mode in ("local", "auto"):
            langfuse_template = agent_config.get("langfuse_template", "")
            if langfuse_template:
                local_filename = f"{langfuse_template}.txt"
            else:
                local_filename = f"{agent_key}_prompt.txt"
            
            local_file_path = Path("config/prompts/local") / local_filename
            
            # 尝试从项目根目录查找
            if not local_file_path.exists():
                local_file_path = Path.cwd() / local_file_path
            
            if local_file_path.exists():
                try:
                    with open(local_file_path, "r", encoding="utf-8") as f:
                        template = f.read()
                    
                    logger.debug(f"从本地文件加载提示词模板: {agent_key}, 文件: {local_file_path}")
                    return template
                except Exception as e:
                    logger.error(f"从本地文件加载提示词模板失败: {agent_key}, 错误: {str(e)}")
                    if prompt_source_mode == "local":
                        raise ValueError(f"无法从本地文件加载提示词模板: {agent_key}, 错误: {str(e)}")
            else:
                if prompt_source_mode == "local":
                    raise FileNotFoundError(f"未找到本地提示词文件: {agent_key}, 路径: {local_file_path}")
        
        if not template:
            raise ValueError(f"未找到提示词模板: {agent_key}")
        
        return template

