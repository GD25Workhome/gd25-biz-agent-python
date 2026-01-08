"""
多智能体 LangGraph 与 Langfuse 集成示例

功能说明：
1. 创建一个多智能体应用，包含：
   - 主智能体（Main Agent）：使用 ReAct 模式，可以调用工具
   - 子智能体（Research Sub-Agent）：专门用于研究任务的 LangGraph 智能体
   - 研究工具（Research Tool）：调用子智能体进行研究
2. 集成 Langfuse 进行分布式追踪，确保主智能体和子智能体的追踪关联
3. 从 .env 文件读取配置

参考文档：
https://langfuse.com/guides/cookbook/integration_langgraph#example-2-multi-agent-application-with-langgraph

运行方式：
从项目根目录运行：
    python -m cursor_test.langfuse.03LangChain.test_multi_agent_langgraph
或：
    cd cursor_test/langfuse/03LangChain && python test_multi_agent_langgraph.py

环境变量配置（.env 文件）：
    # Langfuse 配置
    LANGFUSE_ENABLED=true
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
import os
import secrets
import logging
from pathlib import Path
from typing import TypedDict, Annotated, Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


# ==================== 配置管理 ====================

def find_project_root() -> Path:
    """
    查找项目根目录（包含 .env 文件的目录）
    """
    current = Path(__file__).resolve()
    # 当前文件位于 cursor_test/langfuse/03LangChain/test_multi_agent_langgraph.py
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
    LANGFUSE_ENABLED: bool = Field(
        default=False,
        description="是否启用Langfuse可观测性"
    )
    LANGFUSE_PUBLIC_KEY: Optional[str] = Field(
        default=None,
        description="Langfuse公钥（从.env文件读取）"
    )
    LANGFUSE_SECRET_KEY: Optional[str] = Field(
        default=None,
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
print(f"[配置] LANGFUSE_ENABLED: {settings.LANGFUSE_ENABLED}")
print(f"[配置] LANGFUSE_PUBLIC_KEY: {'已设置' if settings.LANGFUSE_PUBLIC_KEY else '未设置'}")
print(f"[配置] LANGFUSE_SECRET_KEY: {'已设置' if settings.LANGFUSE_SECRET_KEY else '未设置'}")

# LangChain 和 LangGraph 相关导入
from langchain_core.messages import HumanMessage, AIMessage, BaseMessage
from langchain_openai import ChatOpenAI
from langchain_core.tools import tool
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import create_react_agent
from langgraph.checkpoint.memory import MemorySaver
from typing_extensions import TypedDict as LangGraphTypedDict

# Langfuse 相关导入
from langfuse import Langfuse, get_client
from langfuse.langchain import CallbackHandler

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# ==================== Langfuse 初始化 ====================

def init_langfuse() -> None:
    """
    初始化 Langfuse 客户端
    """
    public_key = settings.LANGFUSE_PUBLIC_KEY
    secret_key = settings.LANGFUSE_SECRET_KEY
    host = settings.LANGFUSE_HOST
    
    if not public_key or not secret_key:
        raise ValueError(
            "Langfuse 配置不完整：缺少 LANGFUSE_PUBLIC_KEY 或 LANGFUSE_SECRET_KEY"
        )
    
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
    if not public_key:
        raise ValueError("Langfuse 配置不完整：缺少 LANGFUSE_PUBLIC_KEY")
    
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


# ==================== 子智能体（Research Sub-Agent）创建 ====================

class SubAgentState(LangGraphTypedDict):
    """子智能体状态定义"""
    messages: Annotated[list, add_messages]


def build_research_sub_agent() -> StateGraph:
    """
    构建研究子智能体（Research Sub-Agent）
    
    这是一个简单的 LangGraph 智能体，专门用于回答研究类问题。
    
    Returns:
        StateGraph: 编译后的子智能体图
    """
    logger.info("[子智能体] 开始构建研究子智能体...")
    
    # 创建图
    graph_builder = StateGraph(SubAgentState)
    
    # 创建 LLM
    llm = create_llm()
    
    # 定义聊天节点
    def chatbot(state: SubAgentState):
        """聊天节点：使用 LLM 生成回复"""
        messages = state.get("messages", [])
        response = llm.invoke(messages)
        return {"messages": [response]}
    
    # 添加节点
    graph_builder.add_node("chatbot", chatbot)
    
    # 设置入口和结束点
    graph_builder.set_entry_point("chatbot")
    graph_builder.set_finish_point("chatbot")
    
    # 编译图
    checkpoint = MemorySaver()
    sub_agent = graph_builder.compile(checkpointer=checkpoint)
    
    logger.info("[子智能体] 研究子智能体构建完成")
    return sub_agent


# ==================== 工具定义 ====================

def create_research_tool(sub_agent: StateGraph, langfuse_handler: CallbackHandler, trace_id: str):
    """
    创建研究工具，该工具调用子智能体进行研究
    
    Args:
        sub_agent: 研究子智能体图
        langfuse_handler: Langfuse 回调处理器
        trace_id: 追踪 ID，用于关联分布式追踪
        
    Returns:
        工具函数
    """
    # 使用闭包捕获外部变量，创建工具函数
    @tool
    def langgraph_research(question: str) -> str:
        """
        进行研究，回答各种主题的问题。
        
        Args:
            question: 要研究的问题
            
        Returns:
            str: 研究结果
        """
        logger.info(f"[研究工具] 开始研究问题: {question[:50]}...")
        
        langfuse = get_client()
        
        # 使用 start_as_current_observation 创建子追踪，关联到主追踪
        with langfuse.start_as_current_observation(
            name="🤖-sub-research-agent",
            trace_context={"trace_id": trace_id}
        ) as observation:
            # 更新追踪输入
            observation.update_trace(input=question)
            
            # 调用子智能体
            response = sub_agent.invoke(
                {"messages": [HumanMessage(content=question)]},
                config={"callbacks": [langfuse_handler]}
            )
            
            # 提取回复内容
            response_content = ""
            messages = response.get("messages", [])
            if messages and len(messages) > 0:
                # 获取最后一条 AI 消息
                for msg in reversed(messages):
                    if hasattr(msg, "content"):
                        response_content = msg.content
                        break
            
            # 更新追踪输出
            observation.update_trace(output=response_content)
            
            logger.info(f"[研究工具] 研究完成: {response_content[:100]}...")
            return response_content
    
    return langgraph_research


# ==================== 主智能体创建 ====================

def create_main_agent(tools: list, langfuse_handler: CallbackHandler) -> StateGraph:
    """
    创建主智能体（Main Agent）
    
    使用 create_react_agent 创建一个 ReAct 模式的智能体，可以使用工具。
    
    Args:
        tools: 工具列表
        langfuse_handler: Langfuse 回调处理器
        
    Returns:
        StateGraph: 编译后的主智能体图
    """
    logger.info("[主智能体] 开始创建主智能体...")
    
    # 创建 LLM
    llm = create_llm()
    
    # 使用 create_react_agent 创建主智能体
    main_agent = create_react_agent(
        model=llm,
        tools=tools
    )
    
    logger.info(f"[主智能体] 主智能体创建完成，工具数量: {len(tools)}")
    return main_agent


# ==================== 主函数 ====================

def main():
    """主函数"""
    logger.info("=" * 80)
    logger.info("多智能体 LangGraph 与 Langfuse 集成示例")
    logger.info("=" * 80)
    
    # 1. 初始化 Langfuse
    logger.info("[步骤1] 初始化 Langfuse...")
    init_langfuse()
    logger.info("[步骤1] Langfuse 初始化成功")
    
    # 2. 创建 Langfuse Handler
    langfuse_handler = create_langfuse_handler()
    
    # 3. 构建子智能体
    logger.info("[步骤2] 构建研究子智能体...")
    sub_agent = build_research_sub_agent()
    logger.info("[步骤2] 研究子智能体构建完成")
    
    # 4. 生成追踪 ID（用于分布式追踪）
    trace_id = secrets.token_hex(16)
    logger.info(f"[步骤3] 生成追踪 ID: {trace_id}")
    
    # 5. 创建研究工具
    logger.info("[步骤4] 创建研究工具...")
    research_tool = create_research_tool(sub_agent, langfuse_handler, trace_id)
    logger.info("[步骤4] 研究工具创建完成")
    
    # 6. 创建主智能体
    logger.info("[步骤5] 创建主智能体...")
    main_agent = create_main_agent(tools=[research_tool], langfuse_handler=langfuse_handler)
    logger.info("[步骤5] 主智能体创建完成")
    
    # 7. 执行主智能体（使用 Langfuse 追踪）
    langfuse = get_client()
    
    # 使用 start_as_current_observation 创建主追踪
    with langfuse.start_as_current_observation(
        name="🤖-main-agent",
        trace_context={"trace_id": trace_id}
    ) as observation:
        # 更新追踪元数据
        langfuse.update_current_trace(
            name="multi-agent-langgraph-example",
            user_id="test_user",
            session_id="test_session",
            metadata={
                "example": "multi_agent_langgraph_integration",
                "agent_type": "multi-agent"
            }
        )
        
        # 准备用户问题
        user_question = "什么是 Langfuse？"
        logger.info(f"[步骤6] 用户问题: {user_question}")
        
        # 更新追踪输入
        observation.update_trace(input=user_question)
        
        # 调用主智能体
        logger.info("[步骤6] 开始执行主智能体...")
        logger.info("-" * 80)
        
        response = main_agent.invoke(
            {"messages": [{"role": "user", "content": user_question}]},
            config={"callbacks": [langfuse_handler]}
        )
        
        logger.info("-" * 80)
        logger.info("[步骤6] 主智能体执行完成")
        
        # 提取回复内容
        response_content = ""
        messages = response.get("messages", [])
        if messages:
            # 获取最后一条 AI 消息
            for msg in reversed(messages):
                if hasattr(msg, "content"):
                    response_content = msg.content
                    break
        
        # 更新追踪输出
        observation.update_trace(output=response_content)
        
        # 8. 显示结果
        logger.info("[步骤7] 执行结果:")
        logger.info(f"  用户问题: {user_question}")
        logger.info(f"  AI 回复: {response_content[:200]}...")
        
        # 9. 刷新 Langfuse 事件
        logger.info("[步骤8] 刷新 Langfuse 事件...")
        langfuse.flush()
        logger.info("[步骤8] Langfuse 事件已刷新")
        
        logger.info("=" * 80)
        logger.info("示例执行完成")
        logger.info(f"Trace ID: {trace_id}")
        logger.info("请在 Langfuse UI 中查看追踪记录")
        logger.info("=" * 80)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logger.error(f"程序执行失败: {e}", exc_info=True)
        sys.exit(1)

