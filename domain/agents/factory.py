"""
智能体工厂
根据配置动态创建智能体实例
"""
import yaml
import os
from typing import Dict, List, Any, Optional
from langchain_core.tools import BaseTool
from langgraph.prebuilt import create_react_agent
from langchain_core.language_models import BaseChatModel

from infrastructure.llm.client import get_llm
from domain.tools.registry import TOOL_REGISTRY
from app.core.config import settings
from infrastructure.prompts.manager import PromptManager
import logging

logger = logging.getLogger(__name__)


class AgentFactory:
    """智能体工厂类"""
    
    _config: Dict[str, Any] = {}
    _config_path: str = "config/agents.yaml"
    _prompt_manager: Optional[PromptManager] = None
    
    @classmethod
    def _get_prompt_manager(cls) -> PromptManager:
        """获取提示词管理器实例（单例）"""
        if cls._prompt_manager is None:
            cls._prompt_manager = PromptManager()
        return cls._prompt_manager
    
    @classmethod
    def load_config(cls, config_path: Optional[str] = None):
        """
        加载智能体配置文件
        
        Args:
            config_path: 配置文件路径（可选）
        """
        if config_path:
            cls._config_path = config_path
        
        # 支持相对路径和绝对路径
        if not os.path.isabs(cls._config_path):
            config_path = os.path.join(os.getcwd(), cls._config_path)
        else:
            config_path = cls._config_path
        
        if os.path.exists(config_path):
            with open(config_path, "r", encoding="utf-8") as f:
                cls._config = yaml.safe_load(f).get("agents", {})
        else:
            raise FileNotFoundError(f"配置文件不存在: {config_path}")
    
    @classmethod
    def create_agent(
        cls,
        agent_key: str,
        llm: Optional[BaseChatModel] = None,
        tools: Optional[List[BaseTool]] = None
    ):
        """
        根据配置创建智能体
        
        Args:
            agent_key: 智能体键名（如 blood_pressure_agent）
            llm: LLM 实例（可选，如果不提供则从配置创建）
            tools: 工具列表（可选，如果不提供则从配置加载）
        
        Returns:
            CompiledGraph: 已编译的 LangGraph Agent 实例
        """
        if not cls._config:
            cls.load_config()
        
        agent_config = cls._config.get(agent_key)
        if not agent_config:
            raise ValueError(f"智能体配置不存在: {agent_key}")
        
        # 1. 获取 LLM 实例
        if not llm:
            llm_config = agent_config.get("llm", {})
            llm = get_llm(
                model=llm_config.get("model", settings.LLM_MODEL),
                temperature=llm_config.get(
                    "temperature",
                    settings.LLM_TEMPERATURE_DEFAULT
                )
            )
        
        # 2. 获取工具列表
        if not tools:
            tool_names = agent_config.get("tools", [])
            tools = [
                TOOL_REGISTRY[name]
                for name in tool_names
                if name in TOOL_REGISTRY
            ]
        
        # 3. 获取系统提示词
        # 优先使用新的提示词管理系统
        system_prompt = None
        try:
            prompt_manager = cls._get_prompt_manager()
            # 尝试从模板加载提示词
            system_prompt = prompt_manager.render(
                agent_key=agent_key,
                context={}  # Agent创建时没有上下文，上下文在运行时注入
            )
            logger.debug(f"使用PromptManager加载提示词: {agent_key}")
        except (FileNotFoundError, ValueError) as e:
            # 如果模板不存在，回退到原有方式
            logger.warning(f"提示词模板不存在或加载失败: {agent_key}, 错误: {str(e)}, 使用原有方式加载")
            system_prompt = agent_config.get("system_prompt", "")
            # 支持从文件加载提示词
            prompt_path = agent_config.get("system_prompt_path")
            if prompt_path and os.path.exists(prompt_path):
                with open(prompt_path, "r", encoding="utf-8") as f:
                    system_prompt = f.read()
        
        # 如果仍然没有提示词，使用空字符串
        if not system_prompt:
            logger.warning(f"未找到提示词配置: {agent_key}, 使用空提示词")
            system_prompt = ""
        
        # 4. 创建 ReAct Agent
        return create_react_agent(
            model=llm,
            tools=tools,
            prompt=system_prompt
        )
    
    @classmethod
    def list_agents(cls) -> List[str]:
        """
        列出所有可用的智能体
        
        Returns:
            智能体键名列表
        """
        if not cls._config:
            cls.load_config()
        return list(cls._config.keys())

# 模块加载时自动读取配置（如果配置文件存在）
try:
    AgentFactory.load_config()
except FileNotFoundError:
    # 配置文件不存在时，使用空配置（后续会通过配置创建）
    pass

