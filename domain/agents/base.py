from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage
from langchain_core.tools import BaseTool
from langgraph.graph import StateGraph
from langgraph.prebuilt import create_react_agent
from app.core.config import settings
from infrastructure.llm.client import get_llm
import yaml
import os

class BaseAgent(ABC):
    """
    Agent 基类
    
    定义了所有 Agent 的通用结构和行为，包括配置加载、LLM 初始化、工具管理以及 LangGraph 图的构建。
    """
    def __init__(
        self,
        name: str,
        config_path: Optional[str] = None,
        model: Optional[BaseChatModel] = None,
        tools: List[BaseTool] = []
    ):
        self.name = name
        self.config = self._load_config(config_path) if config_path else {}
        
        # 初始化 LLM
        if model:
            self.model = model
        else:
            llm_config = self.config.get("llm", {})
            self.model = get_llm(
                model=llm_config.get("model"),
                temperature=llm_config.get("temperature")
            )
            
        # 初始化工具
        self.tools = tools
        # TODO: 如果需要，从配置动态加载工具
        
        # 初始化系统提示词 (System Prompt)
        self.system_prompt = self._load_system_prompt()
        
        # 初始化图 (Graph)
        self.graph = self._build_graph()

    def _load_config(self, config_path: str) -> Dict[str, Any]:
        """从 YAML 加载 Agent 配置"""
        if not os.path.exists(config_path):
            return {}
        with open(config_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)

    def _load_system_prompt(self) -> str:
        """从配置或文件加载系统提示词"""
        prompt_path = self.config.get("system_prompt_path")
        if prompt_path and os.path.exists(prompt_path):
            with open(prompt_path, "r", encoding="utf-8") as f:
                return f.read()
        return self.config.get("system_prompt", "You are a helpful assistant.")

    @abstractmethod
    def _build_graph(self):
        """构建此 Agent 的 LangGraph"""
        pass

    async def ainvoke(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """调用 Agent"""
        return await self.graph.ainvoke(state)

class ReactAgent(BaseAgent):
    """标准 ReAct Agent 实现"""
    def _build_graph(self):
        return create_react_agent(
            model=self.model,
            tools=self.tools,
            prompt=self.system_prompt
        )
