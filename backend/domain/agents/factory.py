"""
Agent 工厂与执行器

AgentNodeCreator 编译期调用 AgentFactory.create_agent，生成内层 ReAct 图包装类 AgentExecutor；
运行期由 agent_node_action 调用 AgentExecutor.ainvoke 完成 LLM + 工具循环。
"""
import logging
from typing import Any, Dict, List, Optional

from langchain.agents import create_agent
from langchain_core.messages import BaseMessage, SystemMessage
from langchain_core.tools import BaseTool

from backend.domain.flows.models.definition import AgentNodeConfig
from backend.domain.tools.registry import tool_registry
from backend.infrastructure.llm.client import get_llm
from backend.infrastructure.prompts.manager import prompt_manager

logger = logging.getLogger(__name__)


class AgentFactory:
    """
        按 AgentNodeConfig 创建 AgentExecutor（LLM + 工具 + 提示词缓存键 + 内层 ReAct 图）。
    """

    @staticmethod
    def create_agent(
        config: AgentNodeConfig,
        flow_dir: str,
    ) -> "AgentExecutor":
        """
            编译期构建 AgentExecutor，供外层 LangGraph agent 节点闭包持有。

            Args:
                config: flow.yaml agent 配置（prompt、model、可选 tools 名称列表）
                flow_dir: 流程目录，用于解析 prompts 相对路径

            Returns:
                AgentExecutor: 绑定内层 ReAct 图与 prompt_cache_key 的执行器
        """
        # 1. 加载并缓存系统提示词模板
        # prompt_manager.cached_prompt：读 md 文件并返回缓存键，供运行时 build_system_message 使用
        prompt_cache_key = prompt_manager.cached_prompt(
            prompt_path=config.prompt,
            flow_dir=flow_dir,
        )

        # 2. 按 config.tools 从 tool_registry 解析 LangChain 工具实例
        agent_tools: List[BaseTool] = []
        if config.tools:
            for tool_name in config.tools:
                tool = tool_registry.get_tool(tool_name)
                if tool:
                    agent_tools.append(tool)
                else:
                    logger.warning(f"工具 {tool_name} 未注册，跳过")

        # 3. 创建 LLM 客户端（工具内通过 RuntimeContext 取 token_id，无需额外包装）
        llm = get_llm(
            provider=config.model.provider,
            model=config.model.name,
            temperature=config.model.temperature,
            thinking=config.model.thinking,
            reasoning_effort=config.model.reasoning_effort,
            timeout=config.model.timeout,
        )

        # 4. 编译内层 ReAct Agent 图（与外层流程图 checkpoint 独立，thread_id 固定 default）
        graph = create_agent(
            model=llm,
            tools=agent_tools,
        )

        logger.debug(f"创建Agent: {config.prompt}, 工具数量: {len(agent_tools)}")
        return AgentExecutor(graph, prompt_cache_key, verbose=True)


class AgentExecutor:
    """
        内层 ReAct Agent 的运行时包装。

        持有已编译的 LangGraph 子图与提示词缓存键；ainvoke 为 agent 节点实际调用入口。
    """

    def __init__(
        self,
        graph: Any,
        prompt_cache_key: str,
        verbose: bool = False,
    ) -> None:
        """
            Args:
                graph: langchain create_agent 返回的已编译 ReAct 图（工具已绑定在图内）
                prompt_cache_key: 系统提示词在 prompt_manager 中的缓存键
                verbose: 是否输出详细日志（当前未深度使用）
        """
        self.graph = graph
        self.prompt_cache_key = prompt_cache_key
        self.verbose = verbose

    async def ainvoke(
        self,
        msgs: List[BaseMessage],
        callbacks: Optional[List[Any]] = None,
        sys_msg: Optional[SystemMessage] = None,
    ) -> Dict[str, Any]:
        """
            异步执行内层 ReAct Agent，返回最后一条 AI 回复及完整 messages。

            Args:
                msgs: 对话消息（history + current，不含 system）
                callbacks: LangChain 回调（当前 agent 节点未透传外层 Langfuse callbacks）
                sys_msg: 运行时替换占位符后的 SystemMessage

            Returns:
                含 output、output_data（content 为 dict 时）、messages 的字典
        """
        # 1. 组装 sys_msg + 对话消息
        messages: List[BaseMessage] = []
        if sys_msg:
            messages.append(sys_msg)
            logger.debug(
                f"[AgentExecutor] 添加系统消息，长度: "
                f"{len(sys_msg.content) if hasattr(sys_msg, 'content') else 0}"
            )
        messages.extend(msgs)

        config: Dict[str, Any] = {"configurable": {"thread_id": "default"}}
        if callbacks:
            config["callbacks"] = callbacks
            logger.debug(f"[AgentExecutor] 传递运行时callbacks: count={len(callbacks)}")

        # 2. 调用内层 ReAct 图
        result = await self.graph.ainvoke({"messages": messages}, config)

        # 3. 从 messages 提取最后一条 AI 回复作为 output
        output = ""
        output_data: Optional[Dict[str, Any]] = None
        if result.get("messages"):
            for msg in reversed(result["messages"]):
                if hasattr(msg, "type") and msg.type == "ai":
                    content = getattr(msg, "content", None)
                    if isinstance(content, dict):
                        output_data = content
                        output = str(content)
                    else:
                        output = (
                            content
                            if isinstance(content, str)
                            else str(content) if content is not None else ""
                        )
                    break
            if not output and result["messages"]:
                last_msg = result["messages"][-1]
                content = getattr(last_msg, "content", None)
                if isinstance(content, dict):
                    output_data = content
                    output = str(content)
                else:
                    output = (
                        content
                        if isinstance(content, str)
                        else str(content) if content is not None else ""
                    )

        return {
            "output": output,
            "output_data": output_data,
            "messages": result.get("messages", []),
        }
