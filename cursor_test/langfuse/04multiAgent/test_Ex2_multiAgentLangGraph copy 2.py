"""
Example 2: Multi agent application with LangGraph

功能说明：
1. 构建 2 个执行智能体：
   - 研究智能体（Research Agent）：使用 LangChain WikipediaAPIWrapper 搜索 Wikipedia
   - 时间智能体（CurrentTime Agent）：使用自定义工具获取当前时间
2. 构建智能体监督者（Supervisor）：帮助将用户问题委托给两个智能体之一
3. 添加 Langfuse handler 作为回调，追踪监督者和执行智能体的步骤

参考文档：
https://langfuse.com/guides/cookbook/integration_langgraph#example-2-multi-agent-application-with-langgraph

运行方式：
从项目根目录运行：
    python -m cursor_test.langfuse.04multiAgent.test_Ex2_multiAgentLangGraph
或：
    cd cursor_test/langfuse/04multiAgent && python test_Ex2_multiAgentLangGraph.py

环境变量配置（.env 文件）：
    # Langfuse 配置
    LANGFUSE_PUBLIC_KEY=pk-lf-...
    LANGFUSE_SECRET_KEY=sk-lf-...
    LANGFUSE_HOST=https://cloud.langfuse.com  # 可选，默认使用 cloud.langfuse.com
    
    # LLM 配置（至少配置一个）
    OPENAI_API_KEY=sk-...
    # 或
    DOUBAO_API_KEY=...
    # 或
    DEEPSEEK_API_KEY=...
"""
import sys
import logging
import functools
import operator
from pathlib import Path
from typing import TypedDict, Annotated, Sequence, Optional, Literal
from datetime import datetime
from pydantic import Field, BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict

# ==================== 配置管理 ====================

def find_project_root() -> Path:
    """
    查找项目根目录（包含 .env 文件的目录）
    """
    current = Path(__file__).resolve()
    # 当前文件位于 cursor_test/langfuse/04multiAgent/test_Ex2_multiAgentLangGraph.py
    # 项目根目录应该是 current.parent.parent.parent
    project_root = current.parent.parent.parent
    
    # 验证项目根目录是否存在 .env 文件
    env_file = project_root / ".env"
    if env_file.exists():
        return project_root
    
    # 如果找不到，向上查找
    for parent in current.parents:
        env_file = parent / ".env"
        if env_file.exists():
            return parent
    
    # 如果都找不到，返回计算出的项目根目录
    return project_root


class Settings(BaseSettings):
    """应用配置（从 .env 文件读取）"""
    
    model_config = SettingsConfigDict(
        env_file=find_project_root() / ".env",  # 从项目根目录读取
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore"
    )
    
    # Langfuse 配置
    LANGFUSE_PUBLIC_KEY: str = Field(
        description="Langfuse公钥（从.env文件读取）"
    )
    LANGFUSE_SECRET_KEY: str = Field(
        description="Langfuse密钥（从.env文件读取）"
    )
    LANGFUSE_HOST: Optional[str] = Field(
        default=None,
        description="Langfuse服务器地址（可选，默认使用cloud.langfuse.com）"
    )
    
    # LLM 配置
    OPENAI_API_KEY: Optional[str] = None
    OPENAI_BASE_URL: Optional[str] = None
    DOUBAO_API_KEY: Optional[str] = None
    DOUBAO_BASE_URL: Optional[str] = None
    DEEPSEEK_API_KEY: Optional[str] = None
    DEEPSEEK_BASE_URL: Optional[str] = None
    LLM_MODEL: str = Field(default="gpt-3.5-turbo", description="默认模型名称")


# 创建全局配置实例
settings = Settings()

# 打印配置加载情况（用于调试）
env_file_path = find_project_root() / ".env"
print(f"[配置] .env 文件路径: {env_file_path}")
print(f"[配置] .env 文件存在: {env_file_path.exists()}")
print(f"[配置] LANGFUSE_PUBLIC_KEY: {'已设置' if settings.LANGFUSE_PUBLIC_KEY else '未设置'}")
print(f"[配置] LANGFUSE_SECRET_KEY: {'已设置' if settings.LANGFUSE_SECRET_KEY else '未设置'}")

# LangChain 和 LangGraph 相关导入
from langchain_core.messages import BaseMessage, HumanMessage
from langchain_core.tools import Tool
from langchain.agents import create_agent as langchain_create_agent
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_openai import ChatOpenAI
from langgraph.graph import END, StateGraph, START

# Langfuse 相关导入
from langfuse import Langfuse
from langfuse.langchain import CallbackHandler

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# ==================== 兼容层：AgentExecutor 和 create_openai_tools_agent ====================

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


def create_openai_tools_agent(llm, tools, prompt):
    """
    兼容函数：使用 LangChain 1.x 的 create_agent 创建智能体
    
    在 LangChain 1.x 中，create_openai_tools_agent 已被移除，此函数提供兼容接口。
    内部使用 langchain.agents.create_agent。
    
    Args:
        llm: LLM 客户端
        tools: 工具列表
        prompt: 提示词模板（ChatPromptTemplate）
        
    Returns:
        CompiledStateGraph: LangGraph 编译后的图
    """
    # 从 prompt 中提取 system_prompt
    # ChatPromptTemplate.from_messages 创建的消息格式是元组: ("system", content)
    system_prompt = None
    if hasattr(prompt, 'messages') and prompt.messages:
        # 遍历消息，查找系统消息
        for msg in prompt.messages:
            # 消息格式通常是元组: (role, content)
            if isinstance(msg, tuple) and len(msg) >= 2:
                role, content = msg[0], msg[1]
                if role == "system":
                    system_prompt = content
                    break
            # 处理其他可能的格式
            elif hasattr(msg, 'role') and getattr(msg, 'role') == 'system':
                if hasattr(msg, 'content'):
                    system_prompt = msg.content
                elif hasattr(msg, 'prompt') and hasattr(msg.prompt, 'template'):
                    system_prompt = msg.prompt.template
                break
    
    # 使用 LangChain 1.x 的 create_agent
    graph = langchain_create_agent(
        model=llm,
        tools=tools,
        system_prompt=system_prompt
    )
    
    return graph


# ==================== Langfuse 初始化 ====================

def init_langfuse() -> None:
    """
    初始化 Langfuse 客户端
    """
    public_key = settings.LANGFUSE_PUBLIC_KEY
    secret_key = settings.LANGFUSE_SECRET_KEY
    host = settings.LANGFUSE_HOST
    
    # 初始化 Langfuse 客户端（单例模式）
    langfuse_kwargs = {
        "public_key": public_key,
        "secret_key": secret_key,
    }
    if host:
        langfuse_kwargs["host"] = host
    
    Langfuse(**langfuse_kwargs)
    logger.info(f"Langfuse 客户端初始化成功: host={host or 'default'}")


def create_langfuse_handler() -> CallbackHandler:
    """
    创建 Langfuse CallbackHandler
    
    Returns:
        CallbackHandler: Langfuse 回调处理器
    """
    public_key = settings.LANGFUSE_PUBLIC_KEY
    
    # v3.x 版本：只需要 public_key，secret_key 通过全局客户端配置
    handler = CallbackHandler(public_key=public_key)
    logger.debug("Langfuse CallbackHandler 创建成功")
    return handler


# ==================== LLM 客户端创建 ====================

def create_llm() -> ChatOpenAI:
    """
    创建 LLM 客户端
    
    支持从环境变量读取多个供应商的配置：
    - OPENAI_API_KEY + OPENAI_BASE_URL
    - DOUBAO_API_KEY + DOUBAO_BASE_URL
    - DEEPSEEK_API_KEY + DEEPSEEK_BASE_URL
    
    Returns:
        ChatOpenAI: LLM 客户端实例
        
    Raises:
        ValueError: 如果未配置任何 API Key
    """
    # 从配置读取（使用 pydantic_settings，自动从 .env 文件加载）
    # 优先使用 OPENAI_API_KEY
    api_key = settings.OPENAI_API_KEY
    base_url = settings.OPENAI_BASE_URL
    model = settings.LLM_MODEL
    
    # 如果没有 OPENAI_API_KEY，尝试其他供应商
    if not api_key:
        api_key = settings.DOUBAO_API_KEY
        base_url = settings.DOUBAO_BASE_URL
        if not model or model == "gpt-3.5-turbo":  # 如果使用默认值，改为豆包默认值
            model = "doubao-seed-1-6-251015"
    
    if not api_key:
        api_key = settings.DEEPSEEK_API_KEY
        base_url = settings.DEEPSEEK_BASE_URL
        if not model or model == "gpt-3.5-turbo":  # 如果使用默认值，改为 DeepSeek 默认值
            model = "deepseek-chat"
    
    if not api_key:
        raise ValueError(
            "未配置 LLM API Key。请在 .env 文件中配置以下之一：\n"
            "  - OPENAI_API_KEY\n"
            "  - DOUBAO_API_KEY\n"
            "  - DEEPSEEK_API_KEY"
        )
    
    # 创建 Langfuse Handler
    langfuse_handler = create_langfuse_handler()
    
    # 创建 LLM 客户端
    llm = ChatOpenAI(
        model=model,
        openai_api_key=api_key,
        openai_api_base=base_url,
        temperature=0.7,
        callbacks=[langfuse_handler]
    )
    
    logger.info(f"创建 LLM 客户端: model={model}, base_url={base_url or 'default'}")
    return llm


# ==================== 工具创建 ====================

def create_tools():
    """
    创建工具
    
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


# ==================== Helper Utilities ====================

def create_agent(llm: ChatOpenAI, system_prompt: str, tools: list) -> AgentExecutor:
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
    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                system_prompt,
            ),
            MessagesPlaceholder(variable_name="messages"),
            MessagesPlaceholder(variable_name="agent_scratchpad"),
        ]
    )
    agent = create_openai_tools_agent(llm, tools, prompt)
    executor = AgentExecutor(agent=agent, tools=tools)
    return executor


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


# ==================== 创建智能体监督者 ====================

class RouteDecision(BaseModel):
    """
    路由决策模型（用于 LangChain 1.x 的结构化输出）
    """
    next: Literal["FINISH", "Researcher", "CurrentTime"]


def create_supervisor_chain(llm: ChatOpenAI):
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


# ==================== 构建图 ====================

# 智能体状态是图中每个节点的输入
class AgentState(TypedDict):
    # 注释告诉图，新消息将始终添加到当前状态
    messages: Annotated[Sequence[BaseMessage], operator.add]
    # 'next' 字段指示下一步路由到哪里
    next: str


def build_graph(llm: ChatOpenAI, wikipedia_tool, datetime_tool, supervisor_chain):
    """
    构建 LangGraph 图
    
    Args:
        llm: LLM 客户端
        wikipedia_tool: Wikipedia 工具
        datetime_tool: 日期时间工具
        supervisor_chain: 监督者链
        
    Returns:
        编译后的图
    """
    members = ["Researcher", "CurrentTime"]
    
    # 使用 create_agent 辅助函数添加研究智能体
    research_agent = create_agent(llm, "You are a web researcher.", [wikipedia_tool])
    research_node = functools.partial(agent_node, agent=research_agent, name="Researcher")
    
    # 使用 create_agent 辅助函数添加时间智能体
    currenttime_agent = create_agent(llm, "You can tell the current time at", [datetime_tool])
    currenttime_node = functools.partial(agent_node, agent=currenttime_agent, name="CurrentTime")
    
    workflow = StateGraph(AgentState)
    
    # 添加节点。节点代表工作单元。它们通常是常规的 Python 函数。
    workflow.add_node("Researcher", research_node)
    workflow.add_node("CurrentTime", currenttime_node)
    workflow.add_node("supervisor", supervisor_chain)
    
    # 我们希望我们的工作节点在完成时总是"报告"给监督者
    for member in members:
        workflow.add_edge(member, "supervisor")
    
    # 条件边通常包含"if"语句，根据当前图状态路由到不同的节点。
    # 这些函数接收当前图状态并返回一个字符串或字符串列表，指示下一步要调用的节点。
    conditional_map = {k: k for k in members}
    conditional_map["FINISH"] = END
    workflow.add_conditional_edges("supervisor", lambda x: x["next"], conditional_map)
    
    # 添加入口点。这告诉我们的图每次运行时从哪里开始工作。
    workflow.add_edge(START, "supervisor")
    
    # 为了能够运行我们的图，在图形构建器上调用 "compile()"。
    # 这创建了一个 "CompiledGraph"，我们可以在状态上使用 invoke。
    graph = workflow.compile()
    
    logger.info("图构建完成")
    return graph


# ==================== 主函数 ====================

def main():
    """主函数"""
    logger.info("=" * 80)
    logger.info("Example 2: Multi agent application with LangGraph")
    logger.info("=" * 80)
    
    # 1. 初始化 Langfuse
    logger.info("[步骤1] 初始化 Langfuse...")
    init_langfuse()
    logger.info("[步骤1] Langfuse 初始化成功")
    
    # 2. 创建 Langfuse Handler
    langfuse_handler = create_langfuse_handler()
    
    # 3. 创建 LLM
    logger.info("[步骤2] 创建 LLM 客户端...")
    llm = create_llm()
    logger.info("[步骤2] LLM 客户端创建完成")
    
    # 4. 创建工具
    logger.info("[步骤3] 创建工具...")
    wikipedia_tool, datetime_tool = create_tools()
    logger.info("[步骤3] 工具创建完成")
    
    # 5. 创建监督者链
    logger.info("[步骤4] 创建监督者链...")
    supervisor_chain = create_supervisor_chain(llm)
    logger.info("[步骤4] 监督者链创建完成")
    
    # 6. 构建图
    logger.info("[步骤5] 构建图...")
    graph = build_graph(llm, wikipedia_tool, datetime_tool, supervisor_chain)
    logger.info("[步骤5] 图构建完成")
    
    # 7. 执行图（使用 Langfuse 追踪）
    logger.info("[步骤6] 开始执行图...")
    logger.info("-" * 80)
    
    # 测试问题 1: 关于光合作用的研究问题
    question1 = "How does photosynthesis work?"
    logger.info(f"问题 1: {question1}")
    for s in graph.stream(
        {"messages": [HumanMessage(content=question1)]},
        config={"callbacks": [langfuse_handler]}
    ):
        print(s)
        print("----")
    
    logger.info("-" * 80)
    
    # 测试问题 2: 询问当前时间
    question2 = "What time is it?"
    logger.info(f"问题 2: {question2}")
    for s in graph.stream(
        {"messages": [HumanMessage(content=question2)]},
        config={"callbacks": [langfuse_handler]}
    ):
        print(s)
        print("----")
    
    logger.info("-" * 80)
    logger.info("[步骤6] 图执行完成")
    
    # 8. 刷新 Langfuse 事件
    logger.info("[步骤7] 刷新 Langfuse 事件...")
    langfuse = Langfuse()
    langfuse.flush()
    logger.info("[步骤7] Langfuse 事件已刷新")
    
    logger.info("=" * 80)
    logger.info("示例执行完成")
    logger.info("请在 Langfuse UI 中查看追踪记录")
    logger.info("=" * 80)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logger.error(f"程序执行失败: {e}", exc_info=True)
        sys.exit(1)

