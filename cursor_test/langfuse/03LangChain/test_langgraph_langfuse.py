"""
轻量化的 LangGraph 与 Langfuse 集成示例

功能说明：
1. 创建包含两个节点的 LangGraph 流程
   - 节点1：普通节点（处理输入）
   - 节点2：Agent 节点（使用 LLM 生成回复）
2. 集成 Langfuse 进行可观测性追踪
3. 从 .env 文件读取配置

运行方式：
从项目根目录运行：
    python -m cursor_test.langfuse.03LangChain.test_langgraph_langfuse
或：
    cd cursor_test/langfuse/03LangChain && python test_langgraph_langfuse.py

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
    # 当前文件位于 cursor_test/langfuse/03LangChain/test_langgraph_langfuse.py
    # 项目根目录应该是 current.parent.parent.parent.parent
    # 03LangChain -> langfuse -> cursor_test -> 项目根目录
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
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

# Langfuse 相关导入
try:
    from langfuse import Langfuse, get_client
    from langfuse.langchain import CallbackHandler
    LANGFUSE_AVAILABLE = True
except ImportError:
    print("警告: Langfuse 未安装，将跳过 Langfuse 集成")
    LANGFUSE_AVAILABLE = False

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# ==================== 状态定义 ====================

class GraphState(TypedDict):
    """图状态定义"""
    messages: Annotated[list[BaseMessage], "消息列表"]
    processed_input: str  # 节点1处理后的输入


# ==================== Langfuse 初始化 ====================

def init_langfuse() -> bool:
    """
    初始化 Langfuse 客户端
    
    Returns:
        bool: 是否成功初始化
    """
    if not LANGFUSE_AVAILABLE:
        logger.warning("Langfuse 未安装，跳过初始化")
        return False
    
    # 从配置读取（使用 pydantic_settings，自动从 .env 文件加载）
    if not settings.LANGFUSE_ENABLED:
        logger.info("Langfuse 未启用（LANGFUSE_ENABLED=false）")
        return False
    
    public_key = settings.LANGFUSE_PUBLIC_KEY
    secret_key = settings.LANGFUSE_SECRET_KEY
    host = settings.LANGFUSE_HOST
    
    if not public_key or not secret_key:
        logger.warning(
            "Langfuse 配置不完整：缺少 LANGFUSE_PUBLIC_KEY 或 LANGFUSE_SECRET_KEY"
        )
        return False
    
    try:
        # 初始化 Langfuse 客户端（单例模式）
        langfuse_kwargs = {
            "public_key": public_key,
            "secret_key": secret_key,
        }
        if host:
            langfuse_kwargs["host"] = host
        
        Langfuse(**langfuse_kwargs)
        logger.info(f"Langfuse 客户端初始化成功: host={host or 'default'}")
        return True
    except Exception as e:
        logger.error(f"Langfuse 客户端初始化失败: {e}", exc_info=True)
        return False


def create_langfuse_handler() -> CallbackHandler | None:
    """
    创建 Langfuse CallbackHandler
    
    Returns:
        CallbackHandler: Langfuse 回调处理器，如果不可用则返回 None
    """
    if not LANGFUSE_AVAILABLE:
        return None
    
    # 从配置读取（使用 pydantic_settings，自动从 .env 文件加载）
    if not settings.LANGFUSE_ENABLED:
        return None
    
    public_key = settings.LANGFUSE_PUBLIC_KEY
    if not public_key:
        return None
    
    try:
        # v3.x 版本：只需要 public_key，secret_key 通过全局客户端配置
        handler = CallbackHandler(public_key=public_key)
        logger.debug("Langfuse CallbackHandler 创建成功")
        return handler
    except Exception as e:
        logger.error(f"创建 Langfuse CallbackHandler 失败: {e}", exc_info=True)
        return None


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
    callbacks = [langfuse_handler] if langfuse_handler else None
    
    # 创建 LLM 客户端
    llm = ChatOpenAI(
        model=model,
        openai_api_key=api_key,
        openai_api_base=base_url,
        temperature=0.7,
        callbacks=callbacks
    )
    
    logger.info(f"创建 LLM 客户端: model={model}, base_url={base_url or 'default'}")
    return llm


# ==================== 节点函数定义 ====================

def node1_process_input(state: GraphState) -> GraphState:
    """
    节点1：普通节点，处理输入
    
    功能：将用户输入转换为更友好的格式，添加一些处理逻辑
    
    Args:
        state: 图状态
        
    Returns:
        GraphState: 更新后的状态
    """
    logger.info("[节点1] 开始处理输入...")
    
    # 获取最后一条用户消息
    messages = state.get("messages", [])
    if not messages:
        logger.warning("[节点1] 没有消息，跳过处理")
        return state
    
    last_message = messages[-1]
    input_text = last_message.content if hasattr(last_message, "content") else str(last_message)
    
    # 处理输入：添加前缀，转换为大写等（示例处理逻辑）
    processed_input = f"[已处理] {input_text.upper()}"
    
    logger.info(f"[节点1] 输入处理完成: {input_text[:50]}... -> {processed_input[:50]}...")
    
    # 更新状态
    new_state = state.copy()
    new_state["processed_input"] = processed_input
    
    return new_state


def node2_agent_response(state: GraphState) -> GraphState:
    """
    节点2：Agent 节点，使用 LLM 生成回复
    
    功能：基于处理后的输入，使用 LLM 生成回复
    
    Args:
        state: 图状态
        
    Returns:
        GraphState: 更新后的状态
    """
    logger.info("[节点2] 开始生成 Agent 回复...")
    
    # 获取处理后的输入
    processed_input = state.get("processed_input", "")
    if not processed_input:
        logger.warning("[节点2] 没有处理后的输入，使用原始消息")
        messages = state.get("messages", [])
        if messages:
            processed_input = messages[-1].content if hasattr(messages[-1], "content") else str(messages[-1])
        else:
            processed_input = "你好"
    
    # 创建 LLM 客户端
    llm = create_llm()
    
    # 创建 Langfuse Handler（如果可用）
    langfuse_handler = create_langfuse_handler()
    callbacks = [langfuse_handler] if langfuse_handler else None
    
    # 构建提示词
    prompt = f"""你是一个友好的AI助手。用户说：{processed_input}

请基于用户的输入，生成一个友好、简洁的回复。"""
    
    # 调用 LLM
    try:
        messages_list = [HumanMessage(content=prompt)]
        response = llm.invoke(messages_list, config={"callbacks": callbacks} if callbacks else {})
        
        # 提取回复内容
        response_text = response.content if hasattr(response, "content") else str(response)
        
        logger.info(f"[节点2] Agent 回复生成完成: {response_text[:100]}...")
        
        # 更新状态：添加 AI 回复到消息列表
        new_state = state.copy()
        new_messages = list(state.get("messages", []))
        new_messages.append(AIMessage(content=response_text))
        new_state["messages"] = new_messages
        
        return new_state
        
    except Exception as e:
        logger.error(f"[节点2] LLM 调用失败: {e}", exc_info=True)
        # 返回错误消息
        new_state = state.copy()
        new_messages = list(state.get("messages", []))
        new_messages.append(AIMessage(content=f"抱歉，处理时发生错误: {str(e)}"))
        new_state["messages"] = new_messages
        return new_state


# ==================== 图构建 ====================

def build_graph() -> StateGraph:
    """
    构建 LangGraph 图
    
    流程：
    1. 节点1（普通节点）：处理输入
    2. 节点2（Agent 节点）：生成回复
    3. 结束
    
    Returns:
        StateGraph: 构建的图
    """
    # 创建图
    graph = StateGraph(GraphState)
    
    # 添加节点
    graph.add_node("node1_process", node1_process_input)
    graph.add_node("node2_agent", node2_agent_response)
    
    # 添加边：节点1 -> 节点2 -> END
    graph.add_edge("node1_process", "node2_agent")
    graph.add_edge("node2_agent", END)
    
    # 设置入口节点
    graph.set_entry_point("node1_process")
    
    logger.info("LangGraph 图构建完成")
    return graph


# ==================== 主函数 ====================

def main():
    """主函数"""
    logger.info("=" * 80)
    logger.info("LangGraph 与 Langfuse 集成示例")
    logger.info("=" * 80)
    
    # 1. 初始化 Langfuse（如果可用）
    logger.info("[步骤1] 初始化 Langfuse...")
    langfuse_initialized = init_langfuse()
    if langfuse_initialized:
        logger.info("[步骤1] Langfuse 初始化成功")
    else:
        logger.warning("[步骤1] Langfuse 未初始化（将跳过 Langfuse 追踪）")
    
    # 2. 创建 Trace（如果 Langfuse 可用）
    if langfuse_initialized and LANGFUSE_AVAILABLE:
        try:
            langfuse = get_client()
            
            # 生成 trace_id（32 位十六进制字符）
            trace_id = secrets.token_hex(16)
            
            # 使用 start_as_current_span 创建 Trace（v3.x 方式）
            # 这会创建一个活动的 span 上下文，后续的所有 span 都会自动关联
            with langfuse.start_as_current_span(
                name="langgraph_langfuse_example",
                trace_context={"trace_id": trace_id},
                metadata={"example": "langgraph_langfuse_integration"}
            ) as span:
                # 更新 Trace 元数据
                langfuse.update_current_trace(
                    name="langgraph_langfuse_example",
                    user_id="test_user",
                    session_id="test_session",
                    metadata={"example": "langgraph_langfuse_integration"}
                )
                logger.info(f"[步骤1] 创建 Langfuse Trace: trace_id={trace_id}")
                
                # 3. 构建图
                logger.info("[步骤2] 构建 LangGraph 图...")
                graph = build_graph()
                
                # 4. 编译图
                logger.info("[步骤3] 编译 LangGraph 图...")
                checkpoint = MemorySaver()
                compiled_graph = graph.compile(checkpointer=checkpoint)
                logger.info("[步骤3] 图编译完成")
                
                # 5. 准备初始状态
                logger.info("[步骤4] 准备初始状态...")
                initial_state: GraphState = {
                    "messages": [HumanMessage(content="你好，请介绍一下你自己")],
                    "processed_input": ""
                }
                logger.info(f"[步骤4] 初始状态: {initial_state['messages'][0].content}")
                
                # 6. 执行图
                logger.info("[步骤5] 执行 LangGraph 图...")
                logger.info("-" * 80)
                config = {"configurable": {"thread_id": "test_session"}}
                result = compiled_graph.invoke(initial_state, config)
                logger.info("-" * 80)
                logger.info("[步骤5] 图执行完成")
                
                # 7. 显示结果
                logger.info("[步骤6] 执行结果:")
                messages = result.get("messages", [])
                for i, msg in enumerate(messages, 1):
                    msg_type = msg.type if hasattr(msg, "type") else "unknown"
                    content = msg.content if hasattr(msg, "content") else str(msg)
                    logger.info(f"  消息{i} ({msg_type}): {content[:100]}...")
                
                # 8. 刷新 Langfuse 事件
                logger.info("[步骤7] 刷新 Langfuse 事件...")
                langfuse.flush()
                logger.info("[步骤7] Langfuse 事件已刷新")
                
                logger.info("=" * 80)
                logger.info("示例执行完成")
                logger.info(f"Trace ID: {trace_id}")
                logger.info("请在 Langfuse UI 中查看追踪记录")
                logger.info("=" * 80)
                
        except Exception as e:
            logger.error(f"执行失败: {e}", exc_info=True)
            raise
    else:
        # 如果 Langfuse 不可用，仍然执行图（但不记录到 Langfuse）
        logger.info("[步骤2] 构建 LangGraph 图（无 Langfuse 追踪）...")
        graph = build_graph()
        
        logger.info("[步骤3] 编译 LangGraph 图...")
        checkpoint = MemorySaver()
        compiled_graph = graph.compile(checkpointer=checkpoint)
        
        logger.info("[步骤4] 准备初始状态...")
        initial_state: GraphState = {
            "messages": [HumanMessage(content="你好，请介绍一下你自己")],
            "processed_input": ""
        }
        
        logger.info("[步骤5] 执行 LangGraph 图...")
        logger.info("-" * 80)
        config = {"configurable": {"thread_id": "test_session"}}
        result = compiled_graph.invoke(initial_state, config)
        logger.info("-" * 80)
        
        logger.info("[步骤6] 执行结果:")
        messages = result.get("messages", [])
        for i, msg in enumerate(messages, 1):
            msg_type = msg.type if hasattr(msg, "type") else "unknown"
            content = msg.content if hasattr(msg, "content") else str(msg)
            logger.info(f"  消息{i} ({msg_type}): {content[:100]}...")
        
        logger.info("=" * 80)
        logger.info("示例执行完成（无 Langfuse 追踪）")
        logger.info("=" * 80)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logger.error(f"程序执行失败: {e}", exc_info=True)
        sys.exit(1)

