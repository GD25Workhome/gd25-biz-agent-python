"""
Agent工厂
根据配置创建Agent实例（使用 LangChain 1.x + LangGraph）
"""
import logging
from typing import List, Optional, Any
from langchain_core.language_models import BaseChatModel
from langchain_core.tools import BaseTool
from langgraph.prebuilt import create_react_agent

from backend.infrastructure.llm.client import get_llm
from backend.infrastructure.prompts.manager import prompt_manager
from backend.domain.flows.definition import AgentNodeConfig, ModelConfig
from backend.domain.tools.registry import tool_registry

logger = logging.getLogger(__name__)


class AgentExecutor:
    """Agent执行器包装类（兼容接口）"""
    
    def __init__(self, graph: Any, tools: List[BaseTool], verbose: bool = False):
        """
        初始化Agent执行器
        
        Args:
            graph: LangGraph编译后的图
            tools: 工具列表
            verbose: 是否输出详细信息
        """
        self.graph = graph
        self.tools = tools
        self.verbose = verbose
    
    def invoke(self, input_data: dict) -> dict:
        """
        调用Agent
        
        Args:
            input_data: 输入数据，包含 "input" 字段
            
        Returns:
            包含 "output" 和 "messages" 的字典
        """
        from langchain_core.messages import HumanMessage
        
        input_text = input_data.get("input", "")
        messages = [HumanMessage(content=input_text)]
        config = {"configurable": {"thread_id": "default"}}
        
        # 调用LangGraph图
        result = self.graph.invoke({"messages": messages}, config)
        
        # 提取最后一条AI消息作为输出
        output = ""
        if result.get("messages"):
            # 从后往前查找最后一条AI消息
            for msg in reversed(result["messages"]):
                if hasattr(msg, "type") and msg.type == "ai":
                    output = msg.content if isinstance(msg.content, str) else str(msg.content)
                    break
            # 如果没有找到，使用最后一条消息
            if not output and result["messages"]:
                last_msg = result["messages"][-1]
                output = last_msg.content if hasattr(last_msg, "content") else str(last_msg)
        
        return {"output": output, "messages": result.get("messages", [])}


class AgentFactory:
    """Agent工厂"""
    
    @staticmethod
    def create_agent(
        config: AgentNodeConfig,
        flow_dir: str,
        tools: Optional[List[BaseTool]] = None
    ) -> AgentExecutor:
        """
        创建Agent实例（使用LangGraph的create_react_agent）
        
        Args:
            config: Agent节点配置
            flow_dir: 流程目录路径（用于解析提示词相对路径）
            tools: 工具列表（可选）
            
        Returns:
            AgentExecutor: Agent执行器
        """
        # 加载提示词
        prompt_content = prompt_manager.get_prompt(
            prompt_path=config.prompt,
            flow_dir=flow_dir
        )
        
        # 获取工具列表
        agent_tools = []
        if config.tools:
            for tool_name in config.tools:
                tool = tool_registry.get_tool(tool_name)
                if tool:
                    agent_tools.append(tool)
                else:
                    logger.warning(f"工具 {tool_name} 未注册，跳过")
        
        if tools:
            agent_tools.extend(tools)
        
        # 创建LLM客户端
        llm = get_llm(
            provider=config.model.provider,
            model=config.model.name,
            temperature=config.model.temperature
        )
        
        # 使用LangGraph的create_react_agent创建图
        graph = create_react_agent(
            model=llm,
            tools=agent_tools,
            prompt=prompt_content  # 直接传入提示词字符串
        )
        
        logger.debug(f"创建Agent: {config.prompt}, 工具数量: {len(agent_tools)}")
        return AgentExecutor(graph, agent_tools, verbose=True)
