"""
Agent工厂
根据配置创建Agent实例（使用 LangChain 1.x + LangGraph）
"""
import logging
from typing import List, Optional, Any
from langchain_core.language_models import BaseChatModel
from langchain_core.tools import BaseTool
from langchain_core.messages import BaseMessage, SystemMessage
# from langgraph.prebuilt import create_react_agent
from langchain.agents import create_agent

from backend.infrastructure.llm.client import get_llm
from backend.infrastructure.prompts.manager import prompt_manager
from backend.domain.flows.definition import AgentNodeConfig, ModelConfig
from backend.domain.tools.registry import tool_registry

logger = logging.getLogger(__name__)


class AgentExecutor:
    """Agent执行器包装类（兼容接口）"""
    
    def __init__(self, graph: Any, tools: List[BaseTool], prompt_cache_key: str, verbose: bool = False):
        """
        初始化Agent执行器
        
        Args:
            graph: LangGraph编译后的图
            tools: 工具列表
            prompt_cache_key: 提示词缓存键
            verbose: 是否输出详细信息
        """
        self.graph = graph
        self.tools = tools
        self.prompt_cache_key = prompt_cache_key
        self.verbose = verbose
    
    async def ainvoke(self, msgs: List[BaseMessage], callbacks: Optional[List] = None, sys_msg: Optional[SystemMessage] = None) -> dict:
        """
        异步调用Agent
        
        Args:
            msgs: 消息列表（BaseMessage类型）
            callbacks: 回调处理器列表（可选，用于运行时传递callbacks）
            sys_msg: 系统消息（可选，用于运行时动态设置）
            
        Returns:
            包含 "output" 和 "messages" 的字典
        """
        # 组装消息列表：sys_msg + msgs
        messages = []
        
        # 如果提供了系统消息，添加到消息列表开头
        if sys_msg:
            messages.append(sys_msg)
            logger.debug(f"[AgentExecutor] 添加系统消息，长度: {len(sys_msg.content) if hasattr(sys_msg, 'content') else 0}")
        
        # 添加传入的消息列表
        messages.extend(msgs)
        
        config = {"configurable": {"thread_id": "default"}}
        
        # 如果提供了callbacks，添加到config中（用于运行时传递callbacks）
        if callbacks:
            config["callbacks"] = callbacks
            logger.debug(f"[AgentExecutor] 传递运行时callbacks: count={len(callbacks)}")
        
        # 调用LangGraph图（异步）
        result = await self.graph.ainvoke({"messages": messages}, config)
        
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
    
    def invoke(self, msgs: List[BaseMessage], callbacks: Optional[List] = None, sys_msg: Optional[SystemMessage] = None) -> dict:
        """
        调用Agent（同步方法，向后兼容，内部调用异步方法）
        
        注意：在异步上下文中（如 FastAPI 路由），请使用 ainvoke() 方法。
        
        Args:
            msgs: 消息列表（BaseMessage类型）
            callbacks: 回调处理器列表（可选，用于运行时传递callbacks）
            sys_msg: 系统消息（可选，用于运行时动态设置）
            
        Returns:
            包含 "output" 和 "messages" 的字典
            
        Raises:
            RuntimeError: 如果在异步上下文中调用此方法
        """
        import asyncio
        # 检查是否在异步上下文中
        try:
            loop = asyncio.get_running_loop()
            # 如果事件循环正在运行，无法使用同步方法
            raise RuntimeError(
                "在异步上下文中，请使用 ainvoke() 方法而不是 invoke()。"
                "当前代码路径应该已经使用异步调用链。"
            )
        except RuntimeError:
            # 没有运行中的事件循环，可以使用 asyncio.run()
            return asyncio.run(self.ainvoke(msgs, callbacks, sys_msg))


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
        # 加载提示词并缓存
        prompt_cache_key = prompt_manager.cached_prompt(
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
        
        # 注意：工具内部已使用 get_token_id() 获取 token_id，不再需要包装器
        # 创建LLM客户端
        llm = get_llm(
            provider=config.model.provider,
            model=config.model.name,
            temperature=config.model.temperature,
            thinking=config.model.thinking,
            reasoning_effort=config.model.reasoning_effort,
            timeout=config.model.timeout
        )
        
        # 使用LangGraph的create_react_agent创建图
        graph = create_agent(
            model=llm,
            tools=agent_tools
        )
        
        logger.debug(f"创建Agent: {config.prompt}, 工具数量: {len(agent_tools)}")
        return AgentExecutor(graph, agent_tools, prompt_cache_key, verbose=True)
