import yaml
import os
from typing import Dict, List, Any
from langchain_core.tools import BaseTool
from langgraph.prebuilt import create_react_agent
from infrastructure.llm.client import get_llm
from app.core.config import settings

# Import Tools
from domain.tools.blood_pressure import add_blood_pressure, query_blood_pressure_history
from domain.tools.search import search_knowledge_base

# 工具注册表: 映射配置中的工具名到实际函数
TOOL_REGISTRY: Dict[str, BaseTool] = {
    "add_blood_pressure": add_blood_pressure,
    "query_blood_pressure_history": query_blood_pressure_history,
    "search_knowledge_base": search_knowledge_base
}

class AgentFactory:
    """
    Agent 工厂类 (Factory Pattern)
    
    负责读取配置文件 (agents.yaml) 并动态创建 LangGraph Agent 实例。
    """
    _config: Dict[str, Any] = {}

    @classmethod
    def load_config(cls, config_path: str = "config/agents.yaml"):
        """
        加载 Agent 配置文件。
        
        Args:
            config_path (str): 配置文件路径。
        """
        if not os.path.exists(config_path):
            # Fallback relative path for execution from root
            config_path = os.path.join(os.getcwd(), config_path)
            
        if os.path.exists(config_path):
            with open(config_path, "r", encoding="utf-8") as f:
                cls._config = yaml.safe_load(f).get("agents", {})

    @classmethod
    def create_agent(cls, agent_key: str):
        """
        根据配置创建 Agent。
        
        Args:
            agent_key (str): agents.yaml 中的 agent 键名 (如 blood_pressure_agent)。
            
        Returns:
            CompiledGraph: 已编译的 LangGraph Agent 实例。
            
        Raises:
            ValueError: 如果找不到对应的配置。
        """
        if not cls._config:
            cls.load_config()
            
        agent_config = cls._config.get(agent_key)
        if not agent_config:
            raise ValueError(f"Agent config not found for key: {agent_key}")
            
        # 1. 获取 LLM 实例
        llm = get_llm(
            model=agent_config.get("model", settings.LLM_MODEL),
            temperature=agent_config.get("temperature", settings.LLM_TEMPERATURE)
        )
        
        # 2. 获取 Tools 列表
        tool_names = agent_config.get("tools", [])
        tools = [TOOL_REGISTRY[name] for name in tool_names if name in TOOL_REGISTRY]
        
        # 3. 获取 System Prompt
        system_prompt = agent_config.get("system_prompt", "You are a helpful assistant.")
        
        # 4. 创建 ReAct Agent
        # create_react_agent 会自动构建包含 LLM 和 ToolExecutor 的图
        return create_react_agent(
            model=llm,
            tools=tools,
            prompt=system_prompt
        )

# 模块加载时自动读取配置
AgentFactory.load_config()
