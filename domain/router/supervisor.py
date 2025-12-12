from typing import Literal, Dict, Any
from langchain_core.messages import SystemMessage
from langgraph.graph import StateGraph, END
from infrastructure.llm.client import get_llm
from .state import RouterState
from domain.agents.factory import AgentFactory

# 定义 Supervisor 节点
async def supervisor_node(state: RouterState):
    """
    路由主节点 (Supervisor Node)
    
    使用 LLM 分析对话历史，决定下一步将控制权移交给哪个 Agent。
    """
    llm = get_llm()
    messages = state["messages"]
    
    # Supervisor 提示词
    system_prompt = (
        "你是一个医疗 Agent 系统的路由主管 (Supervisor)。\n"
        "你需要根据用户的输入，决定将其分发给哪个专科 Agent 处理。\n"
        "\n"
        "可用的 Agent:\n"
        "1. blood_pressure_agent: 处理血压记录、查询、分析等请求。\n"
        "2. diagnosis_agent: 处理疾病咨询、症状分析、医学知识查询等请求。\n"
        "\n"
        "规则:\n"
        "- 如果用户只是打招呼或闲聊，回复 FINISH。\n"
        "- 如果任务完成，回复 FINISH。\n"
        "- 否则，只输出 Agent 的名称 (blood_pressure_agent 或 diagnosis_agent)。\n"
        "- 不要输出任何其他解释性文字。"
    )
    
    # 获取最后一条消息作为上下文
    response = await llm.ainvoke(
        [SystemMessage(content=system_prompt)] + messages
    )
    
    content = response.content.strip().lower()
    
    # 解析 LLM 输出，确定下一个 Agent
    if "blood_pressure" in content:
        next_agent = "blood_pressure_agent"
    elif "diagnosis" in content or "symptom" in content or "medical" in content:
        next_agent = "diagnosis_agent"
    else:
        # 默认结束或未识别
        next_agent = "FINISH"
        
    return {"next_agent": next_agent}

# 包装器函数: 解决 State 格式不匹配问题
# create_react_agent 期望的输入是 {"messages": ...}，与 RouterState 兼容

async def run_bp_agent(state: RouterState):
    """运行血压 Agent"""
    agent = AgentFactory.create_agent("blood_pressure_agent")
    result = await agent.ainvoke(state)
    # 仅返回 messages 以合并回主状态
    return {"messages": result["messages"]}

async def run_diag_agent(state: RouterState):
    """运行诊断 Agent"""
    agent = AgentFactory.create_agent("diagnosis_agent")
    result = await agent.ainvoke(state)
    # 仅返回 messages 以合并回主状态
    return {"messages": result["messages"]}

# 创建图
def create_workflow():
    """
    构建完整的工作流图 (Workflow Graph)
    
    结构:
    Supervisor -> [BloodPressureAgent | DiagnosisAgent | FINISH]
         ^                    |                 |
         |____________________|_________________|
    """
    workflow = StateGraph(RouterState)
    
    # 添加节点
    workflow.add_node("supervisor", supervisor_node)
    workflow.add_node("blood_pressure_agent", run_bp_agent)
    workflow.add_node("diagnosis_agent", run_diag_agent)
    
    # 设置入口点
    workflow.set_entry_point("supervisor")
    
    # 添加条件边 (根据 supervisor 的输出决定下一步)
    workflow.add_conditional_edges(
        "supervisor",
        lambda x: x["next_agent"],
        {
            "blood_pressure_agent": "blood_pressure_agent",
            "diagnosis_agent": "diagnosis_agent",
            "FINISH": END
        }
    )
    
    # Agent 执行完后，循环回到 supervisor (以支持多轮对话或任务链)
    workflow.add_edge("blood_pressure_agent", "supervisor")
    workflow.add_edge("diagnosis_agent", "supervisor")
    
    return workflow.compile()
