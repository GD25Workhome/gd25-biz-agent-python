"""
血压记录智能体节点工厂函数
"""
from domain.agents.factory import AgentFactory


def create_blood_pressure_agent():
    """
    创建血压记录智能体
    
    Returns:
        CompiledGraph: 血压记录智能体实例
    """
    return AgentFactory.create_agent("blood_pressure_agent")

