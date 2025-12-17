"""
复诊管理智能体节点工厂函数
"""
from domain.agents.factory import AgentFactory


def create_appointment_agent():
    """
    创建复诊管理智能体
    
    Returns:
        CompiledGraph: 复诊管理智能体实例
    """
    return AgentFactory.create_agent("appointment_agent")

