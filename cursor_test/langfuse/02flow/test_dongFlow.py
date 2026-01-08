"""
动态流程与Langfuse集成测试
整合 test_minimal_flow.py 的动态流程编译方式和 test_Ex2_multiAgentLangGraph.py 的图结构

测试场景：
1. 使用 GraphBuilder.build_graph 编译动态流程（参考 test_minimal_flow.py）
2. 图的结构要像 test_Ex2_multiAgentLangGraph.py 中的图一样，包含 supervisor、Researcher、CurrentTime 节点
3. 使用相同的工具（Wikipedia 和 Datetime）
4. 能够指定 traceId（参考 test_Ex2_multiAgentLangGraph.py）

运行方式：
从项目根目录运行：
    python -m cursor_test.langfuse.02flow.test_dongFlow
或：
    cd cursor_test/langfuse/02flow && python test_dongFlow.py
"""
import sys
import secrets
import logging
import functools
import operator
from pathlib import Path
from typing import TypedDict, Annotated, Sequence, Literal, Optional
from datetime import datetime

# 将当前目录添加到 Python 路径（支持从项目根目录或测试目录运行）
current_dir = Path(__file__).parent
if str(current_dir) not in sys.path:
    sys.path.insert(0, str(current_dir))

from langchain_core.messages import HumanMessage, BaseMessage
from langchain_core.tools import Tool
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START

# 导入抽取的代码
from core.state import FlowState
from core.definition import FlowDefinition, NodeDefinition, EdgeDefinition
from flows.builder import GraphBuilder
from llm.providers.manager import ProviderManager
from llm.client import get_llm
from langchain.agents import create_agent as langchain_create_agent
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from pydantic import BaseModel

# Langfuse 相关导入
from langfuse import get_client
from langfuse.langchain import CallbackHandler
from core.config import settings

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# ==================== 工具创建 ====================

def create_tools():
    """
    创建工具（与 test_Ex2_multiAgentLangGraph.py 中的工具相同）
    
    Returns:
        tuple: (wikipedia_tool, datetime_tool)
    """
    # 定义 Mock Wikipedia 搜索工具（替代真实的 Wikipedia 工具）
    def mock_wikipedia_search(query: str) -> str:
        """
        Mock Wikipedia 搜索工具
        
        Args:
            query: 搜索查询内容
            
        Returns:
            str: Mock 搜索结果
        """
        return f"搜索后，返回{query}结果为：mock 结果"
    
    wikipedia_tool = Tool(
        name="Wikipedia",
        func=mock_wikipedia_search,
        description="Search Wikipedia for information about a given topic. Returns mock results for testing purposes.",
    )
    
    # 定义返回当前日期时间的工具
    datetime_tool = Tool(
        name="Datetime",
        func=lambda x: datetime.now().isoformat(),
        description="Returns the current datetime",
    )
    
    logger.info("工具创建完成: Wikipedia (Mock), Datetime")
    return wikipedia_tool, datetime_tool


# ==================== Supervisor 相关 ====================

class RouteDecision(BaseModel):
    """
    路由决策模型（用于 LangChain 1.x 的结构化输出）
    """
    next: Literal["FINISH", "Researcher", "CurrentTime"]


def create_supervisor_chain(llm):
    """
    创建智能体监督者链
    
    它将使用结构化输出选择下一个工作节点或完成处理。
    在 LangChain 1.x 中，使用 with_structured_output 替代 bind_functions。
    
    Args:
        llm: LLM 客户端
        
    Returns:
        监督者链
    """
    members = ["Researcher", "CurrentTime"]
    system_prompt = (
        "You are a supervisor tasked with managing a conversation between the"
        " following workers:  {members}. Given the following user request,"
        " respond with the worker to act next. Each worker will perform a"
        " task and respond with their results and status. When finished,"
        " respond with FINISH."
    )
    # 我们的团队监督者是一个 LLM 节点。它只是选择下一个要处理的智能体，并决定何时完成工作
    options = ["FINISH"] + members
    
    # 使用 ChatPromptTemplate 创建提示词
    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", system_prompt),
            MessagesPlaceholder(variable_name="messages"),
            (
                "system",
                "Given the conversation above, who should act next?"
                " Or should we FINISH? Select one of: {options}",
            ),
        ]
    ).partial(options=str(options), members=", ".join(members))
    
    # 在 LangChain 1.x 中，使用 with_structured_output 替代 bind_functions
    # 这会返回一个 Pydantic 模型实例，我们需要将其转换为字典格式
    structured_llm = llm.with_structured_output(RouteDecision)
    
    def parse_route_decision(response: RouteDecision) -> dict:
        """
        将 Pydantic 模型转换为字典格式，兼容原有的 JsonOutputFunctionsParser 输出格式
        
        Args:
            response: RouteDecision 模型实例
            
        Returns:
            dict: 包含 "next" 字段的字典
        """
        return {"next": response.next}
    
    # 构建监督者智能体的链
    # 使用 with_structured_output 获取结构化输出，然后转换为字典格式
    supervisor_chain = (
        prompt
        | structured_llm
        | parse_route_decision
    )
    
    logger.info("监督者链创建完成（使用 with_structured_output）")
    return supervisor_chain


def agent_node(state, agent, name):
    """
    智能体节点函数
    
    Args:
        state: 图状态
        agent: 智能体执行器
        name: 智能体名称
        
    Returns:
        dict: 包含消息的状态更新
    """
    result = agent.invoke(state)
    return {"messages": [HumanMessage(content=result["output"], name=name)]}


class AgentExecutor:
    """
    兼容 LangChain 0.x 的 AgentExecutor 包装类
    
    在 LangChain 1.x 中，AgentExecutor 已被移除，此类提供兼容接口。
    内部使用 LangGraph 的 CompiledStateGraph。
    """
    
    def __init__(self, graph=None, tools=None, agent=None):
        """
        Args:
            graph: LangGraph 编译后的图（CompiledStateGraph）
            tools: 工具列表
            agent: 智能体图（与 graph 参数等价，用于兼容旧代码）
        """
        # 兼容两种调用方式：AgentExecutor(graph=..., tools=...) 或 AgentExecutor(agent=..., tools=...)
        if agent is not None:
            self.graph = agent
        elif graph is not None:
            self.graph = graph
        else:
            raise ValueError("AgentExecutor 需要提供 graph 或 agent 参数")
        
        self.tools = tools or []
    
    def invoke(self, state):
        """
        调用智能体
        
        Args:
            state: 状态字典，通常包含 "messages" 字段
            
        Returns:
            dict: 包含 "output" 和 "messages" 字段的字典
        """
        # 调用 LangGraph 图
        result = self.graph.invoke(state)
        
        # 提取最后一条 AI 消息作为输出
        output = ""
        if result.get("messages"):
            for msg in reversed(result["messages"]):
                if hasattr(msg, "type") and msg.type == "ai":
                    output = msg.content if isinstance(msg.content, str) else str(msg.content)
                    break
            # 如果没有找到 AI 消息，尝试获取最后一条消息的内容
            if not output and result["messages"]:
                last_msg = result["messages"][-1]
                if hasattr(last_msg, "content"):
                    output = last_msg.content if isinstance(last_msg.content, str) else str(last_msg.content)
        
        return {"output": output, "messages": result.get("messages", [])}


def create_agent(llm, system_prompt: str, tools: list) -> AgentExecutor:
    """
    创建智能体执行器
    
    每个工作节点将被赋予一个名称和一些工具。
    
    Args:
        llm: LLM 客户端
        system_prompt: 系统提示词
        tools: 工具列表
        
    Returns:
        AgentExecutor: 智能体执行器
    """
    # 使用 LangChain 1.x 的 create_agent，需要传递关键字参数
    # 注意：create_agent 的参数是 model, tools, system_prompt（不是 prompt）
    agent = langchain_create_agent(
        model=llm,
        tools=tools,
        system_prompt=system_prompt
    )
    executor = AgentExecutor(agent=agent, tools=tools)
    return executor


# ==================== 流程定义创建 ====================

def create_multi_agent_flow_definition() -> FlowDefinition:
    """
    创建多智能体流程定义
    
    包含 supervisor、Researcher、CurrentTime 三个节点
    """
    return FlowDefinition(
        name="test_dongFlow",
        version="1.0.0",
        description="多智能体流程测试 - 包含 supervisor、Researcher、CurrentTime 节点",
        nodes=[
            NodeDefinition(
                name="supervisor",
                type="supervisor",  # 新增的节点类型
                config={
                    "model": {
                        "provider": "doubao",
                        "name": "doubao-seed-1-6-251015",
                        "temperature": 0.7
                    }
                }
            ),
            NodeDefinition(
                name="Researcher",
                type="agent",
                config={
                    "prompt": "You are a web researcher.",
                    "model": {
                        "provider": "doubao",
                        "name": "doubao-seed-1-6-251015",
                        "temperature": 0.7
                    },
                    "tools": ["Wikipedia"]  # 工具名称列表
                }
            ),
            NodeDefinition(
                name="CurrentTime",
                type="agent",
                config={
                    "prompt": "You can tell the current time at",
                    "model": {
                        "provider": "doubao",
                        "name": "doubao-seed-1-6-251015",
                        "temperature": 0.7
                    },
                    "tools": ["Datetime"]  # 工具名称列表
                }
            )
        ],
        edges=[
            # Researcher 和 CurrentTime 节点执行完后都回到 supervisor
            EdgeDefinition(
                from_node="Researcher",
                to_node="supervisor",
                condition="always"
            ),
            EdgeDefinition(
                from_node="CurrentTime",
                to_node="supervisor",
                condition="always"
            ),
            # supervisor 节点根据路由决策选择下一个节点
            # 注意：这里使用条件边，但条件判断逻辑需要在 GraphBuilder 中实现
            EdgeDefinition(
                from_node="supervisor",
                to_node="Researcher",
                condition="next == 'Researcher'"
            ),
            EdgeDefinition(
                from_node="supervisor",
                to_node="CurrentTime",
                condition="next == 'CurrentTime'"
            ),
            EdgeDefinition(
                from_node="supervisor",
                to_node="__end__",  # 使用特殊名称表示 END
                condition="next == 'FINISH'"
            )
        ],
        entry_node="supervisor"
    )


# ==================== 扩展 GraphBuilder ====================

def build_multi_agent_graph(flow_def: FlowDefinition, wikipedia_tool, datetime_tool):
    """
    构建多智能体图（扩展 GraphBuilder 的逻辑）
    
    这个函数手动构建图，但使用 GraphBuilder 的逻辑来创建 agent 节点
    
    Args:
        flow_def: 流程定义
        wikipedia_tool: Wikipedia 工具
        datetime_tool: Datetime 工具
        
    Returns:
        StateGraph: 构建的图
    """
    from langgraph.graph import StateGraph
    
    # 创建工具映射
    tools_map = {
        "Wikipedia": wikipedia_tool,
        "Datetime": datetime_tool
    }
    
    # 创建 LLM 客户端（用于 supervisor 和 agents）
    llm = get_llm(
        provider="doubao",
        model="doubao-seed-1-6-251015",
        temperature=0.7
    )
    
    # 创建 supervisor 链
    supervisor_chain = create_supervisor_chain(llm)
    
    # 创建智能体节点
    node_functions = {}
    
    for node_def in flow_def.nodes:
        if node_def.type == "supervisor":
            # Supervisor 节点
            def supervisor_node(state: FlowState) -> FlowState:
                """Supervisor 节点函数"""
                # 调用 supervisor 链
                result = supervisor_chain.invoke({"messages": state["messages"]})
                
                # 更新状态，添加 next 字段
                new_state = state.copy()
                new_state["next"] = result.get("next", "FINISH")
                
                # 将 supervisor 的决策作为消息添加到状态中
                from langchain_core.messages import AIMessage
                decision_msg = AIMessage(
                    content=f"Supervisor decision: {new_state['next']}",
                    name="supervisor"
                )
                new_state["messages"] = state["messages"] + [decision_msg]
                
                return new_state
            
            node_functions[node_def.name] = supervisor_node
        
        elif node_def.type == "agent":
            # Agent 节点
            config_dict = node_def.config
            system_prompt = config_dict["prompt"]
            tool_names = config_dict.get("tools", [])
            
            # 获取工具列表
            agent_tools = [tools_map[name] for name in tool_names if name in tools_map]
            
            # 创建 agent
            agent = create_agent(llm, system_prompt, agent_tools)
            
            # 创建节点函数
            node_name = node_def.name
            
            def create_agent_node_func(agent, name):
                """创建 agent 节点函数（使用闭包捕获 agent 和 name）"""
                def agent_node_func(state: FlowState) -> FlowState:
                    """Agent 节点函数（与 test_Ex2_multiAgentLangGraph.py 的逻辑一致）"""
                    # 调用 agent（AgentExecutor.invoke 返回 {"output": output, "messages": [...]}）
                    result = agent.invoke(state)
                    
                    # 更新状态（与 test_Ex2_multiAgentLangGraph.py 的 agent_node 函数一致）
                    return {"messages": [HumanMessage(content=result["output"], name=name)]}
                
                return agent_node_func
            
            node_functions[node_def.name] = create_agent_node_func(agent, node_name)
    
    # 构建图
    graph = StateGraph(FlowState)
    
    # 添加节点
    for node_name, node_func in node_functions.items():
        graph.add_node(node_name, node_func)
    
    # 添加边
    # 按源节点分组边
    edges_by_from = {}
    for edge in flow_def.edges:
        if edge.from_node not in edges_by_from:
            edges_by_from[edge.from_node] = []
        edges_by_from[edge.from_node].append(edge)
    
    # 添加边
    for from_node, edges in edges_by_from.items():
        # 检查是否有条件边（非always的边）
        conditional_edges = [e for e in edges if e.condition != "always"]
        always_edges = [e for e in edges if e.condition == "always"]
        
        if conditional_edges and always_edges:
            # 混合情况：既有条件边又有普通边（不支持，报错）
            raise ValueError(f"节点 {from_node} 同时包含条件边和普通边，不支持")
        
        if conditional_edges:
            # 条件边：创建路由函数
            edges_list = conditional_edges.copy()
            
            def create_route_func(edges_list, from_node):
                """创建路由函数（使用闭包捕获 edges_list）"""
                def route_func(state: FlowState) -> str:
                    """路由函数"""
                    # 如果是 supervisor 节点，使用 next 字段进行路由
                    if from_node == "supervisor":
                        next_node = state.get("next", "FINISH")
                        for edge in edges_list:
                            if edge.condition == f"next == '{next_node}'":
                                if edge.to_node == "__end__":
                                    return END
                                return edge.to_node
                        return END
                    else:
                        # 其他节点的条件判断（简化处理）
                        for edge in edges_list:
                            if evaluate_condition(edge.condition, state):
                                if edge.to_node == "__end__":
                                    return END
                                return edge.to_node
                        return END
                
                return route_func
            
            route_func = create_route_func(edges_list, from_node)
            
            # 构建路由映射
            route_map = {}
            for edge in conditional_edges:
                if edge.to_node == "__end__":
                    route_map[END] = END
                else:
                    route_map[edge.to_node] = edge.to_node
            route_map[END] = END
            
            graph.add_conditional_edges(from_node, route_func, route_map)
        else:
            # 普通边
            for edge in always_edges:
                if edge.to_node == "__end__":
                    graph.add_edge(edge.from_node, END)
                else:
                    graph.add_edge(edge.from_node, edge.to_node)
    
    # 设置入口点
    graph.add_edge(START, flow_def.entry_node)
    
    logger.info(f"成功构建多智能体流程图: {flow_def.name}")
    return graph


def evaluate_condition(condition: str, state: FlowState) -> bool:
    """
    评估条件表达式（简化版，仅支持简单的条件判断）
    
    Args:
        condition: 条件表达式（如 "next == 'Researcher'"）
        state: 流程状态
        
    Returns:
        bool: 条件是否为真
    """
    # 简化处理：仅支持 next == "xxx" 的条件
    if "==" in condition:
        parts = condition.split("==")
        if len(parts) == 2:
            key = parts[0].strip()
            value = parts[1].strip().strip('"\'')
            
            if key == "next":
                return state.get("next") == value
    
    # 默认返回False
    return False


# ==================== Langfuse Handler 创建 ====================

def create_langfuse_handler(trace_id: Optional[str] = None) -> Optional[CallbackHandler]:
    """
    创建 Langfuse CallbackHandler
    
    Args:
        trace_id: 可选的 Trace ID，用于关联到已存在的 Trace
    
    Returns:
        CallbackHandler: Langfuse 回调处理器，如果配置不完整则返回 None
    """
    public_key = settings.LANGFUSE_PUBLIC_KEY
    
    if not public_key:
        logger.warning("Langfuse CallbackHandler: 配置不完整，缺少LANGFUSE_PUBLIC_KEY")
        return None
    
    # 构建 trace_context（如果提供了 trace_id）
    trace_context = None
    if trace_id:
        # 规范化 trace_id（移除连字符并转换为小写）
        normalized_trace_id = trace_id.replace("-", "").lower()
        trace_context = {"trace_id": normalized_trace_id}
        logger.debug(f"Langfuse CallbackHandler: 使用 trace_id={normalized_trace_id}")
    
    # v3.x 版本：只需要 public_key，secret_key 通过全局客户端配置
    try:
        handler = CallbackHandler(
            public_key=public_key,
            trace_context=trace_context  # 如果提供了 trace_id，会关联到已存在的 Trace
        )
        logger.debug("Langfuse CallbackHandler 创建成功")
        return handler
    except Exception as e:
        logger.error(f"Langfuse CallbackHandler 创建失败: {e}", exc_info=True)
        return None


# ==================== 主测试函数 ====================

def load_config():
    """
    方法一：通用配置加载
    
    加载模型供应商配置（从YAML文件读取）
    """
    logger.info("[配置加载] 加载模型供应商配置...")
    try:
        ProviderManager.load_providers()
        logger.info("[配置加载] 模型供应商配置加载成功")
    except Exception as e:
        logger.error(f"[配置加载] 模型供应商配置加载失败: {e}", exc_info=True)
        raise


def compile_graph():
    """
    方法二：流程图的编译工作
    
    创建流程定义、创建工具、构建图、编译图
    
    Returns:
        tuple: (compiled_graph, wikipedia_tool, datetime_tool) - 编译后的图和工具
    """
    logger.info("=" * 80)
    logger.info("图编译阶段")
    logger.info("=" * 80)
    
    # 1. 创建流程定义
    logger.info("[步骤1] 创建流程定义...")
    flow_def = create_multi_agent_flow_definition()
    logger.info(f"[步骤1] 流程定义创建成功: {flow_def.name}, 节点数: {len(flow_def.nodes)}, 边数: {len(flow_def.edges)}")
    logger.info(f"[步骤1] 入口节点: {flow_def.entry_node}")
    for i, node in enumerate(flow_def.nodes, 1):
        logger.info(f"[步骤1]   节点{i}: {node.name} (类型: {node.type})")
    for i, edge in enumerate(flow_def.edges, 1):
        logger.info(f"[步骤1]   边{i}: {edge.from_node} -> {edge.to_node} (条件: {edge.condition})")
    
    # 2. 创建工具
    logger.info("[步骤2] 创建工具...")
    wikipedia_tool, datetime_tool = create_tools()
    logger.info("[步骤2] 工具创建完成")
    
    # 3. 构建图
    logger.info("[步骤3] 构建图...")
    graph = build_multi_agent_graph(flow_def, wikipedia_tool, datetime_tool)
    logger.info("[步骤3] 图构建成功")
    
    # 4. 编译图
    logger.info("[步骤4] 编译图...")
    checkpoint = MemorySaver()
    compiled_graph = graph.compile(checkpointer=checkpoint)
    logger.info("[步骤4] 图编译成功")
    
    logger.info("=" * 80)
    logger.info("图编译阶段完成")
    logger.info("=" * 80)
    
    return compiled_graph, wikipedia_tool, datetime_tool


def execute_graph(
    compiled_graph,
    question: str = "What time is it?",
    trace_id: Optional[str] = None,
    trace_name: Optional[str] = None,
    user_id: Optional[str] = None,
    session_id: Optional[str] = None,
    metadata: Optional[dict] = None
):
    """
    方法三：流程图的实际运行
    
    执行流程图，包含 Langfuse 追踪逻辑
    
    Args:
        compiled_graph: 编译后的图
        question: 要执行的问题
        trace_id: 可选的 Trace ID，用于关联到已存在的 Trace
        trace_name: 可选的 Trace 名称，用于在 Langfuse UI 中标识此追踪
        user_id: 可选的用户 ID，用于关联用户
        session_id: 可选的会话 ID，用于关联会话
        metadata: 可选的元数据字典，用于存储额外的追踪信息
        
    Returns:
        dict: 执行结果
    """
    logger.info("=" * 80)
    logger.info("图执行阶段")
    logger.info("=" * 80)
    
    # 生成 Trace ID（如果没有提供）
    if not trace_id:
        trace_id = secrets.token_hex(16)  # 生成 32 位十六进制字符
        logger.info(f"[执行] 生成Trace ID: {trace_id}")
    else:
        logger.info(f"[执行] 使用指定的Trace ID: {trace_id}")
    
    # 创建 Langfuse Handler
    handler_to_use = create_langfuse_handler(trace_id=trace_id)
    
    # 获取 Langfuse 客户端
    langfuse = get_client()
    
    # 构建初始状态
    logger.info("[执行] 构建初始状态...")
    initial_state: FlowState = {
        "messages": [HumanMessage(content=question)],
        "session_id": session_id or "test_session",
    }
    logger.info(f"[执行] 初始状态构建成功: messages_count={len(initial_state['messages'])}")
    
    # 如果提供了 trace_id 或需要设置 trace 元数据，且 Langfuse 客户端可用，使用 start_as_current_observation
    if langfuse and (trace_id or trace_name or user_id or session_id or metadata):
        # 构建 trace_context（如果提供了 trace_id）
        trace_context = None
        if trace_id:
            # 规范化 trace_id（移除连字符并转换为小写）
            normalized_trace_id = trace_id.replace("-", "").lower()
            trace_context = {"trace_id": normalized_trace_id}
            logger.debug(f"使用 trace_id={normalized_trace_id}")
        
        # 使用 start_as_current_observation 创建主追踪
        observation_name = trace_name or f"test_dongFlow-execution"
        with langfuse.start_as_current_observation(
            name=observation_name,
            trace_context=trace_context
        ) as observation:
            # 更新追踪元数据
            update_kwargs = {}
            if trace_name:
                update_kwargs["name"] = trace_name
            if user_id:
                update_kwargs["user_id"] = user_id
            if session_id:
                update_kwargs["session_id"] = session_id
            if metadata:
                update_kwargs["metadata"] = metadata
            
            if update_kwargs:
                langfuse.update_current_trace(**update_kwargs)
                logger.debug(f"更新 Trace 元数据: {update_kwargs}")
            
            # 更新追踪输入
            observation.update_trace(input=question)
            
            logger.info("-" * 80)
            
            # 执行图
            config = {"configurable": {"thread_id": session_id or "test_session"}}
            if handler_to_use:
                config["callbacks"] = [handler_to_use]
            
            result = compiled_graph.invoke(initial_state, config)
            
            logger.info("-" * 80)
            logger.info("[执行] 流程执行成功")
            
            # 验证结果
            logger.info("[执行] 验证结果...")
            messages = result.get("messages", [])
            logger.info(f"[执行] 结果消息数: {len(messages)}")
            
            if messages:
                # 显示所有消息
                for i, msg in enumerate(messages, 1):
                    msg_type = getattr(msg, "type", "unknown")
                    msg_name = getattr(msg, "name", None)
                    msg_content = msg.content if hasattr(msg, "content") else str(msg)
                    logger.info(f"[执行] 消息{i}: type={msg_type}, name={msg_name}, content={msg_content[:100]}...")
                
                if messages:
                    last_message = messages[-1]
                    response_text = last_message.content if hasattr(last_message, "content") else str(last_message)
                    logger.info(f"[执行] 最终响应: {response_text[:200]}...")
            
            logger.info("=" * 80)
            logger.info("图执行阶段完成")
            logger.info(f"Trace ID: {trace_id}")
            logger.info("=" * 80)
            
            logger.info("提示: 请在Langfuse UI中查看Trace记录")
            
            return result
    else:
        # 如果没有提供 trace 元数据，使用原来的简单方式
        logger.info("-" * 80)
        
        config = {"configurable": {"thread_id": session_id or "test_session"}}
        if handler_to_use:
            config["callbacks"] = [handler_to_use]
        
        result = compiled_graph.invoke(initial_state, config)
        
        logger.info("-" * 80)
        logger.info("[执行] 流程执行成功")
        
        logger.info("=" * 80)
        logger.info("图执行阶段完成")
        logger.info("=" * 80)
        
        return result


def test_dong_flow():
    """
    测试动态流程与Langfuse集成
    
    整合三个独立方法的调用
    """
    logger.info("=" * 80)
    logger.info("开始测试动态流程与Langfuse集成")
    logger.info("=" * 80)
    
    try:
        # 方法一：通用配置加载
        load_config()
        
        # 方法二：流程图的编译工作
        compiled_graph, wikipedia_tool, datetime_tool = compile_graph()
        
        # 方法三：流程图的实际运行
        custom_trace_id = secrets.token_hex(16)  # 生成 32 位十六进制字符
        result = execute_graph(
            compiled_graph,
            question="What time is it?",
            trace_id=custom_trace_id,
            trace_name="test_dongFlow",
            user_id="test_user",
            session_id="test_session",
            metadata={
                "test": True,
                "flow_name": "test_dongFlow",
                "flow_type": "multi-agent"
            }
        )
        
        logger.info("=" * 80)
        logger.info("测试完成")
        logger.info("=" * 80)
        
        return result
        
    except Exception as e:
        logger.error(f"测试失败: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    try:
        test_dong_flow()
    except Exception as e:
        logger.error(f"测试失败: {e}", exc_info=True)
        raise

